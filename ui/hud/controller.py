"""HUDController — one-stop helper for modal operators that want the new HUD.

Use:

    # invoke():
    self.hud_ctl = HUDController("interactive_box", "Interactive Box")
    self.hud_ctl.help.add_section(HUDSection("Marking", [
        HUDItem("Mark face", "LMB"),
        HUDItem("Add point", "A"),
        HUDItem("Clear", "Z"),
        HUDItem("Confirm", "RMB"),
        HUDItem("Cancel", "ESC"),
    ]))
    self.hud_ctl.hud.add_param(HUDParam("Marked faces",
                                       lambda: len(self.marked_faces),
                                       kind="int"))
    self.hud_ctl.attach(context)

    # modal():
    self.hud_ctl.update_event(event, context)
    if self.hud_ctl.handle_events(context, event):
        return {'RUNNING_MODAL'}

    # at finish/cancel:
    self.hud_ctl.detach(context)
"""
from __future__ import annotations

import bpy
import weakref

from .overlay import HUDOverlay
from .help import HelpOverlay
from .event_snap import capture_event
from . import handle_help_toggle
from ..hud_draw.handlers import safe_handler_add, safe_handler_remove


class HUDController:
    # Controllers whose draw handler is currently registered. Lets the addon
    # drop overlays left behind by a modal that crashed or was running when
    # the addon got reloaded (see ``detach_all``).
    _live: "weakref.WeakSet[HUDController]" = weakref.WeakSet()

    @classmethod
    def detach_all(cls) -> None:
        """Remove every registered HUD draw handler (addon unregister)."""
        for ctl in list(cls._live):
            try:
                ctl.detach(None)
            except Exception as e:
                print(f"CursorBBox: HUD detach failed: {e}")
        cls._live.clear()

    def __init__(self, operator_name: str, title: str = ""):
        self.hud = HUDOverlay(operator_name)
        if title:
            self.hud.title = title
        self.help = HelpOverlay(operator_name)
        self._restore_scene_state(bpy.context)
        self._handle = None
        self._event_snap = None
        self._context = None

    def attach(self, context) -> None:
        """Bind both overlays to the current region and register the
        POST_PIXEL draw handler."""
        region = context.region
        self.hud.bind_region(region)
        self.help.bind_region(region)
        self._context = context
        self._handle = safe_handler_add(
            bpy.types.SpaceView3D, self._draw_cb, (),
            'WINDOW', 'POST_PIXEL', tick=True)
        HUDController._live.add(self)

    def _draw_cb(self) -> None:
        # Use the live bpy.context inside the draw handler — the context
        # captured in invoke() may be stale by the time we're called.
        ctx = bpy.context
        self.hud.draw(ctx, self._event_snap)
        self.help.draw(ctx, self._event_snap)

    def update_event(self, event, context) -> None:
        """Capture event into a snapshot and tag the region for redraw.
        Call this at the top of `modal()` on every event."""
        self._event_snap = capture_event(event, self._event_snap)
        if context.area is not None:
            context.area.tag_redraw()

    def handle_events(self, context, event) -> bool:
        """Forward param-toggle / help-toggle / drag events to the
        overlays. Returns True if the event was consumed and the modal
        operator should `return {'RUNNING_MODAL'}` immediately."""
        theme_prefs = self._theme_prefs(context)
        if theme_prefs is None:
            return False
        scene = getattr(context, "scene", None)
        if self.hud.handle_param_toggle_event(event, theme_prefs):
            if scene is not None:
                scene.cursor_bbox_hud_params_visible = self.hud.params_visible
            if context.area is not None:
                context.area.tag_redraw()
            return True
        hud_dragging = self.hud._drag.active
        help_dragging = self.help._drag.active
        if handle_help_toggle(self.help, context, event, hud=self.hud):
            if scene is not None:
                scene.cursor_bbox_help_expanded = self.help.expanded
                # A drag just ended: remember where it was dropped.
                if hud_dragging and not self.hud._drag.active:
                    scene.cursor_bbox_hud_pos_set = True
                    scene.cursor_bbox_hud_pos_x = theme_prefs.hud_free_x
                    scene.cursor_bbox_hud_pos_y = theme_prefs.hud_free_y
                if help_dragging and not self.help._drag.active:
                    scene.cursor_bbox_help_pos_set = True
                    scene.cursor_bbox_help_pos_x = theme_prefs.help_free_x
                    scene.cursor_bbox_help_pos_y = theme_prefs.help_free_y
            return True
        return False

    @staticmethod
    def _theme_prefs(context):
        try:
            return context.preferences.addons["Cursor_BBox"].preferences.hud_theme
        except (KeyError, AttributeError):
            return None

    def _restore_scene_state(self, context) -> None:
        """Apply the HUD/Help state saved in the scene (.blend): param rows
        and Help toggles, plus any position the user dragged an overlay to."""
        scene = getattr(context, "scene", None)
        if scene is None or not hasattr(scene, "cursor_bbox_help_expanded"):
            return
        self.hud.params_visible = bool(scene.cursor_bbox_hud_params_visible)
        expanded = bool(scene.cursor_bbox_help_expanded)
        self.help.expanded = expanded
        self.help._anim_from_expanded = expanded
        self.help._anim_to_expanded = expanded
        theme_prefs = self._theme_prefs(context)
        if theme_prefs is None:
            return
        if scene.cursor_bbox_hud_pos_set:
            theme_prefs.hud_mode = "free"
            theme_prefs.hud_free_x = max(0, scene.cursor_bbox_hud_pos_x)
            theme_prefs.hud_free_y = max(0, scene.cursor_bbox_hud_pos_y)
        if scene.cursor_bbox_help_pos_set:
            theme_prefs.help_corner = "free"
            theme_prefs.help_free_x = max(0, scene.cursor_bbox_help_pos_x)
            theme_prefs.help_free_y = max(0, scene.cursor_bbox_help_pos_y)

    def detach(self, context) -> None:
        """Remove the draw handler. Safe to call multiple times."""
        if self._handle is None:
            return
        safe_handler_remove(self._handle, bpy.types.SpaceView3D, 'WINDOW')
        self._handle = None
        HUDController._live.discard(self)
        if context is not None and context.area is not None:
            context.area.tag_redraw()
