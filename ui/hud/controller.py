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
        try:
            prefs = context.preferences.addons["Cursor_BBox"].preferences
            theme_prefs = prefs.hud_theme
        except (KeyError, AttributeError):
            return False
        if self.hud.handle_param_toggle_event(event, theme_prefs):
            if context.area is not None:
                context.area.tag_redraw()
            return True
        if handle_help_toggle(self.help, context, event, hud=self.hud):
            return True
        return False

    def detach(self, context) -> None:
        """Remove the draw handler. Safe to call multiple times."""
        if self._handle is None:
            return
        safe_handler_remove(self._handle, bpy.types.SpaceView3D, 'WINDOW')
        self._handle = None
        HUDController._live.discard(self)
        if context is not None and context.area is not None:
            context.area.tag_redraw()
