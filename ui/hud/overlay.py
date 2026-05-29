"""HUDOverlay — cursor-following parameter dashboard.

Two content layers coexist:

- `title` (str) + `_header_lines` (list[str]) — always rendered when the
  overlay is visible, regardless of `params_visible`. The operator name /
  live distance info / etc. lives here.
- Sections of `HUDItem` (legacy hotkey list) AND `HUDParamSection` of
  `HUDParam` (live operator-parameter rows). Both are hidden by the
  HUD-param toggle key but the title stays.

Operator wiring:

    self.hud = HUDOverlay("interactive_box")
    self.hud.title = "Interactive Box"
    self.hud.add_param(HUDParam("Size", lambda: self.size, "float"))
    ...

    # in modal():
    if self.hud.handle_param_toggle_event(event, prefs):
        return {"RUNNING_MODAL"}
"""
from __future__ import annotations
import time

from ..hud_draw.theme import Role, get_theme
from ..hud_draw import primitives
from ..hud_draw.state import draw_scope
from . import text as hud_text
from .items import (HUDItem, HUDSection, HUDParam, HUDParamSection,
                    ItemState)
from .layout import (compute_origin, DragState, is_inside,
                     area_for_region, region_side_insets)


def _view_matrix_fingerprint(region_data) -> tuple | None:
    """Cheap fingerprint of the current view matrix. None when there's
    no region_data (e.g. POST_PIXEL in a non-3D space)."""
    if region_data is None:
        return None
    m = region_data.view_matrix
    return tuple(round(float(v), 5)
                 for row in m for v in row)


_STATE_ALPHA = {
    ItemState.ON: 1.0,
    ItemState.OFF: 1.0,
    ItemState.DISABLED: 1.0,
}
_STATE_ROLE = {
    ItemState.ON: Role.HUD_LABEL,
    ItemState.OFF: Role.HUD_LABEL_INACTIVE,
    ItemState.DISABLED: Role.HUD_LABEL_INACTIVE,
}


class HUDOverlay:
    def __init__(self, operator_name: str, verbosity: str | None = None):
        self.operator_name = operator_name
        self.title: str | None = None
        self.sections: list[HUDSection] = []
        self.param_sections: list[HUDParamSection] = []
        self._items_by_key: dict[str, HUDItem] = {}
        self._drag = DragState()
        self._last_origin = (0, 0)
        self._last_size = (0, 0)
        self._bound_region = None
        self._header_lines: list[str] = []
        self._pin_until: float = 0.0
        self._last_view_fp: tuple | None = None
        self._smooth_origin: tuple[float, float] | None = None
        self._recovering: bool = False
        self._was_nav_frozen: bool = False
        self.visible: bool = True
        self.params_visible: bool = True
        self.mode_override: str | None = None

    # --- visibility ---
    def toggle_visibility(self) -> bool:
        self.visible = not self.visible
        return self.visible

    def toggle_params_visible(self) -> bool:
        self.params_visible = not self.params_visible
        return self.params_visible

    def handle_param_toggle_event(self, event, prefs) -> bool:
        """Params-only toggle (title stays visible). Key comes from the
        `cursor_bbox.ui_hud_params_toggle` keymap item (default "SLASH"),
        configurable in the addon's Keymaps tab."""
        if event.value != "PRESS":
            return False
        from ...functions.keymap_utils import get_ui_toggle_key
        key = get_ui_toggle_key("cursor_bbox.ui_hud_params_toggle", "SLASH")
        if event.type != key:
            return False
        if event.shift or event.ctrl or event.alt or event.oskey:
            return False
        self.toggle_params_visible()
        return True

    # --- setup ---
    def add_section(self, section: HUDSection) -> None:
        self.sections.append(section)
        for it in section.items:
            self._items_by_key[it.key] = it

    def add_param(self, param: HUDParam, *, title: str = "") -> None:
        if title:
            for sec in self.param_sections:
                if sec.title == title:
                    sec.params.append(param)
                    return
            self.param_sections.append(HUDParamSection(title, [param]))
            return
        if not self.param_sections:
            self.param_sections.append(HUDParamSection("", []))
        self.param_sections[-1].params.append(param)

    def add_param_section(self, section: HUDParamSection) -> None:
        self.param_sections.append(section)

    def bind_region(self, region) -> None:
        """Restrict drawing to one region (the one the operator was invoked in)."""
        self._bound_region = region.as_pointer() if region is not None else None

    def _find_bound_region(self):
        if self._bound_region is None:
            return None
        import bpy
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type != "VIEW_3D":
                    continue
                for rgn in area.regions:
                    if rgn.as_pointer() == self._bound_region:
                        return rgn
        return None

    def set_state(self, key: str, state: ItemState | str) -> None:
        if key not in self._items_by_key:
            return
        if isinstance(state, str):
            state = ItemState(state)
        self._items_by_key[key].state = state

    def set_header(self, *lines: str | None) -> None:
        """Set 0+ header lines rendered above the section list, in primary
        at title size. Falsy entries are skipped."""
        self._header_lines = [ln for ln in lines if ln]

    def pin_for(self, seconds: float) -> None:
        """Freeze the HUD origin for at least `seconds` more from now."""
        new_deadline = time.perf_counter() + max(0.0, seconds)
        if new_deadline > self._pin_until:
            self._pin_until = new_deadline

    @property
    def _pinned(self) -> bool:
        return time.perf_counter() < self._pin_until

    # --- visible item selection ---
    def _visible_sections(self) -> list[HUDSection]:
        out: list[HUDSection] = []
        for sec in self.sections:
            items = [it for it in sec.items if it.always_show or it.is_modified()]
            if items:
                out.append(HUDSection(sec.title, items))
        return out

    # --- measurement ---
    def _measure(self, theme, sections, param_sections, draw_params: bool):
        title_h = theme.text_size("hud_header")
        row_h = max(theme.text_size("hud_key"),
                    theme.text_size("hud_label"))
        gap = theme.hud.key_label_spacing
        h = 0
        max_w = 0
        widest_key = 0
        widest_param_name = 0

        if self.title:
            tw, _ = hud_text.measure(self.title, theme=theme, size_token="title")
            max_w = max(max_w, int(tw))
            h += title_h + theme.hud.row_spacing

        for line in self._header_lines:
            hw, _ = hud_text.measure(line, theme=theme, size_token="hud_label")
            max_w = max(max_w, int(hw))
            h += row_h + theme.hud.row_spacing

        if not draw_params:
            return max_w, h, 0, 0

        for i, sec in enumerate(sections):
            if i > 0 or self._header_lines or self.title:
                h += theme.hud.section_spacing
            if sec.title:
                tw, _ = hud_text.measure(sec.title, theme=theme,
                                         size_token="title")
                max_w = max(max_w, int(tw))
                h += title_h + theme.hud.row_spacing
            for it in sec.items:
                kw, _ = hud_text.measure(it.key, theme=theme,
                                         size_token="hud_key")
                widest_key = max(widest_key, int(kw))
        key_col_w = widest_key + gap
        for sec in sections:
            rows = self._rows_for_layout(sec.items)
            for row in rows:
                row_w = 0
                for it in row:
                    lw, _ = hud_text.measure(it.label, theme=theme,
                                             size_token="hud_label")
                    row_w += key_col_w + int(lw)
                max_w = max(max_w, row_w)
                h += row_h + theme.hud.row_spacing

        for sec in param_sections:
            for p in sec.params:
                if not p.is_visible():
                    continue
                nw, _ = hud_text.measure(p.name + ":", theme=theme,
                                         size_token="normal")
                widest_param_name = max(widest_param_name, int(nw))
        param_name_col_w = widest_param_name + gap

        for i, sec in enumerate(param_sections):
            if (i > 0 or self._header_lines or self.title
                    or sections):
                h += theme.hud.section_spacing
            if sec.title:
                tw, _ = hud_text.measure(sec.title, theme=theme,
                                         size_token="title")
                max_w = max(max_w, int(tw))
                h += title_h + theme.hud.row_spacing
            for p in sec.params:
                if not p.is_visible():
                    continue
                vw, _ = hud_text.measure(p.value_text(), theme=theme,
                                         size_token="normal")
                row_w = param_name_col_w + int(vw)
                max_w = max(max_w, row_w)
                h += row_h + theme.hud.row_spacing

        return max_w, h, key_col_w, param_name_col_w

    def _rows_for_layout(self, items: list[HUDItem]) -> list[list[HUDItem]]:
        return [[it] for it in items]

    # --- draw ---
    def draw(self, context, event=None) -> None:
        if not self.visible:
            return
        if self._bound_region is not None:
            cur = getattr(context, "region", None)
            if cur is None or cur.as_pointer() != self._bound_region:
                return
        sections = self._visible_sections() if self.params_visible else []
        param_sections = (self.param_sections
                          if self.params_visible else [])
        if (not sections and not param_sections and not self._header_lines
                and not self.title):
            return
        theme = get_theme(context)
        region = self._find_bound_region() or context.region
        if region is None:
            return
        w, h, key_col_w, param_name_col_w = self._measure(
            theme, sections, param_sections, self.params_visible)
        size = (w, h)
        self._last_size = size
        self._last_key_col_w = key_col_w
        self._last_param_name_col_w = param_name_col_w
        mouse = (0, 0)
        if event is not None:
            mouse = (event.mouse_x - region.x, event.mouse_y - region.y)
        fp = _view_matrix_fingerprint(getattr(context, "region_data", None))
        nav_frozen = (fp is not None and self._last_view_fp is not None
                      and fp != self._last_view_fp)
        if fp is not None:
            self._last_view_fp = fp
        if self._drag.active and event is not None:
            new = self._drag.update(mouse)
            free = (int(new[0]), int(new[1]))
        else:
            free = (theme.hud.free_x, theme.hud.free_y)
        held = ((self._pinned or nav_frozen)
                and self._last_origin != (0, 0))
        if held:
            target = self._last_origin
            self._smooth_origin = (float(target[0]), float(target[1]))
            origin = target
            self._recovering = False
        else:
            mode = self.mode_override or theme.hud.mode
            insets = region_side_insets(area_for_region(region))
            target = compute_origin(
                mode, region=region, mouse=mouse,
                content_size=size, padding=theme.hud.padding,
                offset=(theme.hud.offset_x, theme.hud.offset_y),
                anchor_offset=(theme.hud.anchor_offset_x,
                               theme.hud.anchor_offset_y),
                free=free, side_insets=insets)
            if self._was_nav_frozen and not nav_frozen:
                self._recovering = True
            if self._smooth_origin is None or not self._recovering:
                sx, sy = float(target[0]), float(target[1])
                self._recovering = False
            else:
                alpha = max(0.0, min(1.0, 1.0 - theme.hud.smoothing))
                if alpha >= 1.0:
                    sx, sy = float(target[0]), float(target[1])
                    self._recovering = False
                else:
                    sx = self._smooth_origin[0] + (target[0] - self._smooth_origin[0]) * alpha
                    sy = self._smooth_origin[1] + (target[1] - self._smooth_origin[1]) * alpha
                    if abs(target[0] - sx) < 0.5 and abs(target[1] - sy) < 0.5:
                        sx, sy = float(target[0]), float(target[1])
                        self._recovering = False
            self._smooth_origin = (sx, sy)
            origin = (int(sx), int(sy))
            self._last_origin = origin
        self._was_nav_frozen = nav_frozen
        self._render(theme, origin, size, sections, param_sections)

    def _render(self, theme, origin, size, sections, param_sections) -> None:
        x0, y0 = origin
        w, h = size
        if theme.hud.bg_enabled and w > 0 and h > 0:
            pad = theme.hud.bg_padding
            with draw_scope(blend="ALPHA"):
                primitives.rect_2d(x0 - pad, y0 - pad,
                                   w + 2 * pad, h + 2 * pad,
                                   color=theme.hud.bg_color, theme=theme)
        y = y0 + h
        title_h = theme.text_size("hud_header")
        row_h = max(theme.text_size("hud_key"),
                    theme.text_size("hud_label"))
        key_col_w = getattr(self, "_last_key_col_w", 0)
        param_name_col_w = getattr(self, "_last_param_name_col_w", 0)

        if self.title:
            y -= title_h
            hud_text.draw(self.title, x0, y, theme=theme,
                          role=Role.HUD_HEADER, size_token="hud_header")
            y -= theme.hud.row_spacing

        for line in self._header_lines:
            y -= row_h
            label_part, sep, value_part = line.partition(":")
            if sep and value_part:
                lbl = label_part + sep
                hud_text.draw(lbl, x0, y, theme=theme,
                              role=Role.HUD_LABEL, size_token="hud_label")
                lw, _ = hud_text.measure(lbl, theme=theme,
                                         size_token="hud_label")
                hud_text.draw(value_part, x0 + int(lw), y, theme=theme,
                              role=Role.HUD_ACTIVE_VALUE,
                              size_token="hud_label")
            else:
                hud_text.draw(line, x0, y, theme=theme,
                              role=Role.HUD_LABEL, size_token="hud_label")
            y -= theme.hud.row_spacing

        col_w = key_col_w

        for i, sec in enumerate(sections):
            if i > 0 or self._header_lines or self.title:
                y -= theme.hud.section_spacing
            if sec.title:
                y -= title_h
                hud_text.draw(sec.title, x0, y, theme=theme,
                              role=Role.HUD_HEADER, size_token="hud_header")
                y -= theme.hud.row_spacing
            for row in self._rows_for_layout(sec.items):
                y -= row_h
                for col_idx, it in enumerate(row):
                    col_x = x0 + col_idx * col_w
                    hud_text.draw(it.key, col_x, y, theme=theme,
                                  role=Role.HUD_KEY, size_token="hud_key")
                    label_role = _STATE_ROLE[it.state]
                    label_alpha = _STATE_ALPHA[it.state]
                    hud_text.draw(it.label, col_x + key_col_w, y, theme=theme,
                                  role=label_role, size_token="hud_label",
                                  alpha_mul=label_alpha)
                y -= theme.hud.row_spacing

        prev_block = bool(self.title or self._header_lines or sections)
        for i, sec in enumerate(param_sections):
            if i > 0 or prev_block:
                y -= theme.hud.section_spacing
            if sec.title:
                y -= title_h
                hud_text.draw(sec.title, x0, y, theme=theme,
                              role=Role.HUD_HEADER, size_token="hud_header")
                y -= theme.hud.row_spacing
            for p in sec.params:
                if not p.is_visible():
                    continue
                y -= row_h
                active = p.is_active()
                name_role = Role.HUD_LABEL if active else Role.HUD_LABEL_INACTIVE
                value_role = Role.HUD_ACTIVE_VALUE if active else Role.HUD_LABEL_INACTIVE
                hud_text.draw(p.name + ":", x0, y, theme=theme,
                              role=name_role, size_token="normal")
                hud_text.draw(p.value_text(), x0 + param_name_col_w, y,
                              theme=theme, role=value_role,
                              size_token="normal")
                y -= theme.hud.row_spacing

    # --- drag (Shift+Ctrl+Alt+LMB → switch to Free + Position X/Y) ---
    def handle_drag_event(self, context, event, theme_prefs) -> bool:
        all_mods = bool(event.shift and event.ctrl and event.alt)
        region = self._find_bound_region() or context.region
        if region is None:
            return False
        mxy = (event.mouse_x - region.x, event.mouse_y - region.y)
        if (all_mods and event.type == 'LEFTMOUSE'
                and event.value == 'PRESS'
                and not self._drag.active):
            target_origin = (mxy[0], mxy[1] - max(1, self._last_size[1]))
            self._last_origin = target_origin
            self._drag.begin(mxy, target_origin)
            try:
                theme_prefs.hud_mode = "free"
                theme_prefs.hud_free_x = int(target_origin[0])
                theme_prefs.hud_free_y = int(target_origin[1])
            except AttributeError:
                pass
            return True
        if self._drag.active:
            if event.type == 'MOUSEMOVE':
                new = self._drag.update(mxy)
                try:
                    theme_prefs.hud_free_x = int(new[0])
                    theme_prefs.hud_free_y = int(new[1])
                except AttributeError:
                    pass
                return True
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self._drag.end()
                try:
                    theme_prefs.hud_mode = "free"
                    theme_prefs.hud_free_x = int(self._last_origin[0])
                    theme_prefs.hud_free_y = int(self._last_origin[1])
                except AttributeError:
                    pass
                return True
        return False

    # --- legacy drag entry points (kept for compatibility) ---
    def try_begin_drag(self, mouse_xy) -> bool:
        if is_inside(mouse_xy[0], mouse_xy[1],
                     self._last_origin, self._last_size):
            self._drag.begin(mouse_xy, self._last_origin)
            return True
        return False

    def end_drag(self, context) -> None:
        if not self._drag.active:
            return
        self._drag.end()
        try:
            prefs = context.preferences.addons["Cursor_BBox"].preferences
            prefs.hud_theme.hud_free_x = int(self._last_origin[0])
            prefs.hud_theme.hud_free_y = int(self._last_origin[1])
        except (KeyError, AttributeError):
            pass
