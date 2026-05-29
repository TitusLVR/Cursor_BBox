"""HelpOverlay — corner-anchored hotkey legend with collapse/animation.

Pinned to a configurable screen corner with offset. Two states:

- expanded   → renders the full section/item list.
- collapsed  → renders just `prefs.help_hint_text` (default "Press H for help").

Toggle key: configured via the `cursor_bbox.ui_help_toggle` keymap item
(default "H", editable in the Keymaps tab). Animation between
states: `prefs.help_anim_preset` ∈ {none, fade, slide-fade, wave, shockwave}
over `prefs.help_anim_duration` seconds.
"""
from __future__ import annotations
import time

from ..hud_draw.theme import Role, get_theme
from ..hud_draw import primitives
from ..hud_draw.state import draw_scope
from . import text as hud_text
from .items import HUDItem, HUDSection, ItemState
from .layout import area_for_region, region_side_insets, DragState, is_inside


_STATE_ROLE = {
    ItemState.ON: Role.HUD_LABEL,
    ItemState.OFF: Role.HUD_LABEL_INACTIVE,
    ItemState.DISABLED: Role.HUD_LABEL_INACTIVE,
}


def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 4.0 * t * t * t
    p = 2.0 * t - 2.0
    return 0.5 * p * p * p + 1.0


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


class HelpOverlay:
    def __init__(self, operator_name: str):
        self.operator_name = operator_name
        self.sections: list[HUDSection] = []
        self._items_by_key: dict[str, HUDItem] = {}
        self.visible: bool = True
        self.expanded: bool = True
        self._anim_from_expanded: bool = True
        self._anim_to_expanded: bool = True
        self._anim_start: float = 0.0
        self._anim_duration: float = 0.18
        self._anim_timer_active: bool = False
        self._bound_region = None
        self._drag = DragState()
        self._last_origin: tuple[int, int] = (0, 0)
        self._last_size: tuple[int, int] = (0, 0)

    # --- setup ---
    def add_section(self, section: HUDSection) -> None:
        self.sections.append(section)
        for it in section.items:
            self._items_by_key[it.key] = it

    def set_state(self, key: str, state) -> None:
        it = self._items_by_key.get(key)
        if it is None:
            return
        if isinstance(state, str):
            state = ItemState(state)
        it.state = state

    def bind_region(self, region) -> None:
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

    # --- visibility / toggle ---
    def toggle_expanded(self, now: float | None = None,
                        duration: float | None = None) -> bool:
        now = now if now is not None else time.perf_counter()
        if self._anim_to_expanded != self.expanded:
            pass
        self._anim_from_expanded = self.expanded
        self.expanded = not self.expanded
        self._anim_to_expanded = self.expanded
        self._anim_start = now
        if duration is not None:
            self._anim_duration = max(0.001, float(duration))
        self._start_anim_timer()
        return self.expanded

    def _start_anim_timer(self) -> None:
        if self._anim_timer_active:
            return
        if self._bound_region is None:
            return
        import bpy
        self._anim_timer_active = True
        bpy.app.timers.register(self._anim_tick)

    def _anim_tick(self):
        elapsed = time.perf_counter() - self._anim_start
        rgn = self._find_bound_region()
        if rgn is not None:
            rgn.tag_redraw()
        if elapsed >= self._anim_duration:
            self._anim_timer_active = False
            return None
        fps = 240
        try:
            import bpy
            fps = int(bpy.context.preferences.addons["Cursor_BBox"]
                      .preferences.hud_theme.hud_anim_fps)
        except (KeyError, AttributeError):
            pass
        return 1.0 / max(1, fps)

    def handle_drag_event(self, context, event, theme_prefs) -> bool:
        if not self.visible:
            return False
        all_mods = bool(event.shift and event.ctrl and event.alt)
        region = self._find_bound_region()
        if region is None:
            region = getattr(context, "region", None)
        if region is None:
            return False
        mxy = (event.mouse_x - region.x, event.mouse_y - region.y)
        if (all_mods and event.type == 'LEFTMOUSE'
                and event.value == 'PRESS'
                and not self._drag.active):
            if not is_inside(mxy[0], mxy[1],
                             self._last_origin, self._last_size):
                return False
            self._drag.begin(mxy, self._last_origin)
            try:
                theme_prefs.help_corner = "free"
                theme_prefs.help_free_x = int(self._last_origin[0])
                theme_prefs.help_free_y = int(self._last_origin[1])
            except AttributeError:
                pass
            return True
        if self._drag.active:
            if event.type == 'MOUSEMOVE':
                new = self._drag.update(mxy)
                try:
                    theme_prefs.help_free_x = int(new[0])
                    theme_prefs.help_free_y = int(new[1])
                except AttributeError:
                    pass
                return True
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self._drag.end()
                try:
                    theme_prefs.help_corner = "free"
                    theme_prefs.help_free_x = int(self._last_origin[0])
                    theme_prefs.help_free_y = int(self._last_origin[1])
                except AttributeError:
                    pass
                return True
        return False

    def handle_toggle_event(self, event, prefs) -> bool:
        if event.value != "PRESS":
            return False
        from ...functions.keymap_utils import get_ui_toggle_key
        key = get_ui_toggle_key("cursor_bbox.ui_help_toggle", "H")
        if event.type != key:
            return False
        if event.shift or event.ctrl or event.alt or event.oskey:
            return False
        dur = self._effective_duration(prefs)
        self.toggle_expanded(duration=dur)
        return True

    # --- animation ---
    @staticmethod
    def _effective_duration(prefs) -> float:
        preset = getattr(prefs, "help_anim_preset", "fade")
        if preset == "wave":
            return float(getattr(prefs, "help_anim_wave_duration", 2.0))
        return float(getattr(prefs, "help_anim_duration", 0.18))

    def _anim_progress(self, theme, prefs) -> float:
        preset = getattr(prefs, "help_anim_preset", "fade")
        if preset == "none":
            return 1.0
        dur = max(0.001, self._effective_duration(prefs))
        elapsed = time.perf_counter() - self._anim_start
        return _ease_out(elapsed / dur)

    # --- corner layout ---
    @staticmethod
    def _corner_origin(corner: str, region, size, offset_x, offset_y,
                       slide: int, *, side_insets=(0, 0)):
        cw, ch = size
        rw, rh = region.width, region.height
        li, ri = side_insets
        avail_w = rw - li - ri
        cx = li + (avail_w - cw) // 2
        cy = (rh - ch) // 2
        if corner == "top_left":
            return (li + offset_x + slide, rh - offset_y - ch)
        if corner == "top_right":
            return (rw - ri - cw - offset_x - slide, rh - offset_y - ch)
        if corner == "bottom_left":
            return (li + offset_x + slide, offset_y)
        if corner == "bottom_right":
            return (rw - ri - cw - offset_x - slide, offset_y)
        if corner == "top_center":
            return (cx + offset_x, rh - offset_y - ch + slide)
        if corner == "bottom_center":
            return (cx + offset_x, offset_y + slide)
        if corner == "left_center":
            return (li + offset_x + slide, cy + offset_y)
        if corner == "right_center":
            return (rw - ri - cw - offset_x - slide, cy + offset_y)
        return (li + offset_x + slide, rh - offset_y - ch)

    # --- measurement ---
    def _measure_expanded(self, theme):
        title_h = theme.text_size("hud_header")
        row_h = max(theme.text_size("hud_key"),
                    theme.text_size("hud_label"))
        gap = theme.hud.key_label_spacing
        h = 0
        max_w = 0
        widest_key = 0
        for sec in self.sections:
            for it in sec.items:
                kw, _ = hud_text.measure(it.key, theme=theme,
                                         size_token="hud_key")
                widest_key = max(widest_key, int(kw))
        key_col_w = widest_key + gap
        for i, sec in enumerate(self.sections):
            if i > 0:
                h += theme.hud.section_spacing
            if sec.title:
                tw, _ = hud_text.measure(sec.title, theme=theme,
                                         size_token="title")
                max_w = max(max_w, int(tw))
                h += title_h + theme.hud.row_spacing
            for it in sec.items:
                lw, _ = hud_text.measure(it.label, theme=theme,
                                         size_token="hud_label")
                max_w = max(max_w, key_col_w + int(lw))
                h += row_h + theme.hud.row_spacing
        return max_w, h, key_col_w

    def _measure_collapsed(self, theme, prefs):
        hint = self._hint_text(prefs)
        w, _ = hud_text.measure(hint, theme=theme, size_token="normal")
        return int(w), theme.text_size("normal")

    def _hint_text(self, prefs) -> str:
        from ...functions.keymap_utils import get_ui_toggle_key
        tpl = getattr(prefs, "help_hint_text", "Press {key} for help")
        key = get_ui_toggle_key("cursor_bbox.ui_help_toggle", "H")
        try:
            return tpl.format(key=key)
        except (KeyError, IndexError, ValueError):
            return tpl

    # --- draw ---
    def draw(self, context, event=None) -> None:
        if not self.visible:
            return
        if self._bound_region is not None:
            cur = getattr(context, "region", None)
            if cur is None or cur.as_pointer() != self._bound_region:
                return
        try:
            prefs = context.preferences.addons["Cursor_BBox"].preferences
            theme_prefs = prefs.hud_theme
        except (KeyError, AttributeError):
            return
        theme = get_theme(context)
        region = self._find_bound_region() or context.region
        if region is None:
            return

        preset = getattr(theme_prefs, "help_anim_preset", "fade")
        progress = self._anim_progress(theme, theme_prefs)
        animating = self._anim_from_expanded != self._anim_to_expanded
        if not animating:
            progress = 1.0

        show_expanded = self._anim_to_expanded if animating else self.expanded
        alpha = 1.0
        wave_progress: float | None = None
        flash_boost = 0.0

        if animating and preset != "none" and progress < 1.0:
            if preset == "fade":
                if progress < 0.5:
                    show_expanded = self._anim_from_expanded
                    alpha = 1.0 - _ease_in_out(progress / 0.5)
                else:
                    show_expanded = self._anim_to_expanded
                    alpha = _ease_in_out((progress - 0.5) / 0.5)
            elif preset == "slide-fade":
                if progress < 0.5:
                    show_expanded = self._anim_from_expanded
                    eased = _ease_in_out(progress / 0.5)
                    alpha = 1.0 - eased
                else:
                    show_expanded = self._anim_to_expanded
                    eased = _ease_in_out((progress - 0.5) / 0.5)
                    alpha = eased
            elif preset == "wave":
                show_expanded = self._anim_to_expanded
                wave_progress = _ease_out(progress)
                alpha = 1.0
            elif preset == "shockwave":
                show_expanded = self._anim_to_expanded
                alpha = _ease_out(min(1.0, progress * 1.4))

        if show_expanded and self.sections:
            w, h, key_col_w = self._measure_expanded(theme)
        else:
            w, h = self._measure_collapsed(theme, theme_prefs)
            key_col_w = 0
        if w <= 0:
            return

        corner = getattr(theme_prefs, "help_corner", "left_center")
        offx = int(getattr(theme_prefs, "help_offset_x", 12))
        offy = int(getattr(theme_prefs, "help_offset_y", 12))
        slide = 0
        if preset == "slide-fade" and animating and progress < 1.0:
            slide_amount = int(getattr(theme_prefs, "help_anim_slide_amount", 28))
            if progress < 0.5:
                eased = _ease_in_out(progress / 0.5)
                slide = -int(slide_amount * eased)
            else:
                eased = _ease_in_out((progress - 0.5) / 0.5)
                slide = int(slide_amount * (1.0 - eased))

        insets = region_side_insets(area_for_region(region))
        if corner == "free":
            fx = int(getattr(theme_prefs, "help_free_x", 40))
            fy = int(getattr(theme_prefs, "help_free_y", 40))
            origin = (fx, fy)
        else:
            origin = self._corner_origin(
                corner, region, (w, h), offx, offy, slide,
                side_insets=insets)
        self._last_origin = origin
        self._last_size = (w, h)
        self._render(theme, origin, (w, h), key_col_w,
                     show_expanded, theme_prefs, alpha,
                     wave_progress=wave_progress, flash_boost=flash_boost)

        if (preset == "shockwave" and animating and progress < 1.0):
            out_expanded = self._anim_from_expanded
            if out_expanded and self.sections:
                ow, oh, okey = self._measure_expanded(theme)
            else:
                ow, oh = self._measure_collapsed(theme, theme_prefs)
                okey = 0
            if ow > 0:
                if corner == "free":
                    o_origin = (int(getattr(theme_prefs, "help_free_x", 40)),
                                int(getattr(theme_prefs, "help_free_y", 40)))
                else:
                    o_origin = self._corner_origin(
                        corner, region, (ow, oh), offx, offy, 0,
                        side_insets=insets)
                radius = int(getattr(theme_prefs,
                                     "help_anim_shockwave_radius", 160))
                shock_state = {
                    "cx": o_origin[0] + ow / 2,
                    "cy": o_origin[1] + oh / 2,
                    "distance": radius * _ease_out(progress),
                    "alpha_factor": (1.0 - progress) ** 2,
                }
                self._render(theme, o_origin, (ow, oh), okey,
                             out_expanded, theme_prefs, 1.0,
                             shock_state=shock_state)

    def _collect_strings(self, prefs, show_expanded):
        if not show_expanded:
            return [self._hint_text(prefs)]
        out = []
        for sec in self.sections:
            if sec.title:
                out.append(sec.title)
            for it in sec.items:
                out.append(it.key)
                out.append(it.label)
        return out

    def _draw_text(self, text, x, y, *, theme, role, size_token, alpha_mul,
                   wave_state, flash_boost, shock_state=None):
        if shock_state is not None:
            cx = shock_state["cx"]
            cy = shock_state["cy"]
            dist = shock_state["distance"]
            a_factor = shock_state["alpha_factor"]
            row_h = theme.text_size(size_token)
            cur_x = x
            import math
            for ch in text:
                w, _ = hud_text.measure(ch, theme=theme,
                                        size_token=size_token)
                px = cur_x + w * 0.5
                py = y + row_h * 0.5
                dx = px - cx
                dy = py - cy
                length = math.hypot(dx, dy)
                if length < 1e-3:
                    nx, ny = 0.0, 1.0
                else:
                    nx = dx / length
                    ny = dy / length
                ox = int(nx * dist)
                oy = int(ny * dist)
                if a_factor > 0.0:
                    hud_text.draw(ch, cur_x + ox, y + oy, theme=theme,
                                  role=role, size_token=size_token,
                                  alpha_mul=alpha_mul * a_factor)
                cur_x += int(w)
            return
        if wave_state is None:
            hud_text.draw(text, x, y, theme=theme, role=role,
                          size_token=size_token, alpha_mul=alpha_mul)
        else:
            cur_x = x
            prog = wave_state["progress"]
            stagger = wave_state["stagger"]
            window = wave_state["fade_window"]
            spread = wave_state["spread"]
            idx_holder = wave_state["index"]
            for ch in text:
                i = idx_holder["v"]
                idx_holder["v"] = i + 1
                local_raw = (prog - i * stagger) / max(1e-6, window)
                local = _clamp01(local_raw)
                ch_alpha = local
                local_eased = _ease_out(local)
                dx = int(spread * (1.0 - local_eased))
                if ch_alpha > 0.0:
                    hud_text.draw(ch, cur_x + dx, y, theme=theme, role=role,
                                  size_token=size_token,
                                  alpha_mul=alpha_mul * ch_alpha)
                w, _ = hud_text.measure(ch, theme=theme,
                                        size_token=size_token)
                cur_x += int(w)

        if flash_boost > 0.0:
            hud_text.draw(text, x, y, theme=theme, role=Role.HUD_KEY,
                          size_token=size_token, alpha_mul=flash_boost)

    def _render(self, theme, origin, size, key_col_w, show_expanded,
                prefs, alpha, *, wave_progress=None,
                flash_boost: float = 0.0, shock_state=None) -> None:
        x0, y0 = origin
        w, h = size
        if theme.hud.bg_enabled and w > 0 and h > 0 and alpha > 0.0:
            pad = theme.hud.bg_padding
            bgc = theme.hud.bg_color
            bgc = (bgc[0], bgc[1], bgc[2], bgc[3] * alpha)
            with draw_scope(blend="ALPHA"):
                primitives.rect_2d(x0 - pad, y0 - pad,
                                   w + 2 * pad, h + 2 * pad,
                                   color=bgc, theme=theme)
        y = y0 + h
        title_h = theme.text_size("hud_header")
        row_h = max(theme.text_size("hud_key"),
                    theme.text_size("hud_label"))

        wave_state = None
        if wave_progress is not None:
            total_chars = sum(len(s) for s in
                              self._collect_strings(prefs, show_expanded))
            total_chars = max(1, total_chars)
            fade_window = float(getattr(prefs, "help_anim_wave_fade_window", 0.45))
            stagger_scale = float(getattr(prefs, "help_anim_wave_stagger_scale", 2.0))
            spread = int(getattr(prefs, "help_anim_wave_spread", 64))
            base_stagger = (1.0 - fade_window) / total_chars
            stagger = max(0.0, base_stagger * stagger_scale)
            wave_state = {
                "progress": _clamp01(wave_progress),
                "stagger": stagger,
                "fade_window": fade_window,
                "spread": spread,
                "index": {"v": 0},
            }

        if not show_expanded:
            y -= row_h
            self._draw_text(self._hint_text(prefs), x0, y, theme=theme,
                            role=Role.HUD_LABEL_INACTIVE, size_token="hud_label",
                            alpha_mul=alpha, wave_state=wave_state,
                            flash_boost=flash_boost, shock_state=shock_state)
            return

        for i, sec in enumerate(self.sections):
            if i > 0:
                y -= theme.hud.section_spacing
            if sec.title:
                y -= title_h
                self._draw_text(sec.title, x0, y, theme=theme,
                                role=Role.HUD_HEADER, size_token="hud_header",
                                alpha_mul=alpha, wave_state=wave_state,
                                flash_boost=flash_boost, shock_state=shock_state)
                y -= theme.hud.row_spacing
            for it in sec.items:
                y -= row_h
                self._draw_text(it.key, x0, y, theme=theme,
                                role=Role.HUD_KEY, size_token="hud_key",
                                alpha_mul=alpha, wave_state=wave_state,
                                flash_boost=flash_boost, shock_state=shock_state)
                label_role = _STATE_ROLE[it.state]
                self._draw_text(it.label, x0 + key_col_w, y, theme=theme,
                                role=label_role, size_token="hud_label",
                                alpha_mul=alpha, wave_state=wave_state,
                                flash_boost=flash_boost, shock_state=shock_state)
                y -= theme.hud.row_spacing
