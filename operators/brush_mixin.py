"""Circle-brush face marking shared by the interactive Hull / Box / Sphere modals.

Mix into the operator class and:

* call ``self._brush_init(context)`` in ``invoke`` (after ``use_depsgraph`` is set)
  and ``enable_brush_circle()`` is registered by ``_brush_init`` itself;
* at the top of ``modal`` (after HUD event handling) call
  ``if self._brush_handle_event(context, event): return {'RUNNING_MODAL'}``;
* in the LMB PRESS branch, when in plain face-marking mode, call
  ``self._brush_on_press(event)`` instead of marking immediately. The click is
  resolved on RELEASE via ``self._click_mark_face(context, event)`` unless the
  mouse moved past the drag threshold, in which case a stroke runs;
* call ``self._brush_shutdown()`` on every exit path;
* list ``BRUSH_HELP_ITEMS`` in the HUD help and call
  ``self._brush_add_hud_params(hud)`` for the live rows.

Extra brush keys handled here: ``X`` toggles the "through" brush (all faces
under the circle, no facing / occlusion test) and ``Q`` toggles *pick
objects* mode, where LMB adds the visible mesh under the cursor to
``original_selected_objects`` (Ctrl+LMB removes it) so the selection can be
extended without leaving the modal.

The host must provide ``_click_mark_face(context, event)``,
``_brush_update_preview(context)``, ``_push_undo()``, ``marked_faces``,
``original_selected_objects``, ``use_depsgraph``.
"""
from ..functions.core import (
    enable_brush_circle_wrapper as enable_brush_circle,
    disable_brush_circle_wrapper as disable_brush_circle,
    update_brush_circle,
    clear_brush_circle,
    clear_preview_faces,
    rebuild_marked_faces_visual_data,
)
from ..functions.utils import get_faces_to_process
from ..functions.brush_select import apply_stroke
from ..functions.brush import (
    BrushFaceCache,
    pick_brush_faces,
    pick_scene_object,
    region_mouse,
    exceeds_drag_threshold,
    step_radius,
)
from ..ui.hud.items import HUDItem, HUDParam


BRUSH_HELP_ITEMS = [
    HUDItem("Brush mark / unmark", "LMB drag / Ctrl+LMB drag"),
    HUDItem("Brush radius", "Alt+Wheel / [ ]"),
    HUDItem("Brush through (all faces)", "X"),
    HUDItem("Pick objects: add / Ctrl remove", "Q"),
]


class BrushMarkingMixin:

    # ----- lifecycle -----

    def _brush_init(self, context):
        self.brush_radius = int(context.scene.cursor_bbox_brush_radius)
        self.brush_through = bool(context.scene.cursor_bbox_brush_through)
        self.pick_objects_mode = False
        self._brush_pending = None
        self._brush_stroke = None
        self._brush_cache = None
        enable_brush_circle()

    def _brush_add_hud_params(self, hud):
        hud.add_param(HUDParam("Brush px", lambda: self.brush_radius, kind="int"))
        hud.add_param(HUDParam("Brush through", lambda: self.brush_through, kind="bool"))
        hud.add_param(HUDParam(
            "Objects", lambda: len(self.original_selected_objects), kind="int"))

    def _brush_mode_label(self):
        """Mode name for the HUD, or None when the host decides."""
        return "PICK OBJECTS" if self.pick_objects_mode else None

    def _brush_shutdown(self):
        self._brush_pending = None
        self._brush_stroke = None
        disable_brush_circle()

    def _brush_marking_mode(self):
        """True when LMB marks faces (not point / thickness / pick mode)."""
        return (not getattr(self, 'point_mode', False)
                and not getattr(self, 'thickness_mode', False)
                and not getattr(self, 'pick_objects_mode', False))

    def _brush_ensure_cache(self):
        if (self._brush_cache is None
                or self._brush_cache.use_depsgraph != self.use_depsgraph):
            self._brush_cache = BrushFaceCache(self.use_depsgraph)
        return self._brush_cache

    # ----- events -----

    def _brush_on_press(self, event):
        if getattr(self, 'pick_objects_mode', False):
            return
        self._brush_pending = {'start': region_mouse(event), 'remove': bool(event.ctrl)}
        self._brush_stroke = None

    def _brush_handle_event(self, context, event):
        """Returns True when the event was consumed by the brush."""
        if self._brush_pending is not None or self._brush_stroke is not None:
            if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
                mouse = region_mouse(event)
                if (self._brush_stroke is None
                        and exceeds_drag_threshold(self._brush_pending['start'], mouse)):
                    self._begin_brush_stroke(context, self._brush_pending['remove'])
                if self._brush_stroke is not None:
                    self._apply_brush(context, mouse)
                    context.area.tag_redraw()
                return True
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                if self._brush_stroke is not None:
                    self._end_brush_stroke(context)
                else:
                    self._brush_pending = None
                    self._push_undo()
                    self._click_mark_face(context, event)
                self._brush_pending = None
                context.area.tag_redraw()
                return True
            return False

        in_face_modes = (not getattr(self, 'point_mode', False)
                         and not getattr(self, 'thickness_mode', False))

        if event.type == 'Q' and event.value == 'PRESS' and in_face_modes:
            self.pick_objects_mode = not self.pick_objects_mode
            clear_brush_circle()
            self.report({'INFO'}, "Pick objects: LMB add, Ctrl+LMB remove, Q / RMB to exit"
                        if self.pick_objects_mode else "Pick objects mode off")
            context.area.tag_redraw()
            return True

        if self.pick_objects_mode:
            if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                self._pick_object(context, event)
                context.area.tag_redraw()
                return True
            if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
                self.pick_objects_mode = False
                self.report({'INFO'}, "Pick objects mode off")
                context.area.tag_redraw()
                return True

        if event.type == 'X' and event.value == 'PRESS' and in_face_modes:
            self.brush_through = not self.brush_through
            context.scene.cursor_bbox_brush_through = self.brush_through
            self.report({'INFO'}, "Brush through: ON (all faces under the circle)"
                        if self.brush_through else "Brush through: OFF (visible faces only)")
            context.area.tag_redraw()
            return True

        bracket = (event.type in {'LEFT_BRACKET', 'RIGHT_BRACKET'} and event.value == 'PRESS')
        alt_wheel = (event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}
                     and event.alt and not event.ctrl and not event.shift)
        if (bracket or alt_wheel) and self._brush_marking_mode():
            grow = event.type in {'RIGHT_BRACKET', 'WHEELUPMOUSE'}
            self.brush_radius = step_radius(self.brush_radius, grow)
            context.scene.cursor_bbox_brush_radius = self.brush_radius
            update_brush_circle(region_mouse(event), self.brush_radius)
            context.area.tag_redraw()
            return True

        if event.type == 'MOUSEMOVE':
            # Hide a lingering radius-preview circle; never consume the move.
            clear_brush_circle()
        return False

    # ----- pick objects -----

    def _pick_object(self, context, event):
        cache = self._brush_ensure_cache()
        if hasattr(cache, 'reset_scene_filter'):
            cache.reset_scene_filter()
        obj = pick_scene_object(context, cache, region_mouse(event))
        if obj is None:
            self.report({'WARNING'}, "No visible mesh under the cursor")
            return
        if obj.name not in context.view_layer.objects:
            self.report({'WARNING'}, f"{obj.name} is not in this view layer "
                                     "(collection instance?) and cannot be added")
            return
        if event.ctrl:
            if obj not in self.original_selected_objects:
                self.report({'INFO'}, f"{obj.name} is not a target")
                return
            self.original_selected_objects.discard(obj)
            if self.marked_faces.pop(obj, None) is not None:
                rebuild_marked_faces_visual_data(obj, set(), use_depsgraph=self.use_depsgraph)
                self._brush_update_preview(context)
            try:
                obj.select_set(False)
            except RuntimeError:
                pass
            self.report({'INFO'}, f"Removed {obj.name}")
            return
        if obj in self.original_selected_objects:
            self.report({'INFO'}, f"{obj.name} is already a target")
            return
        self.original_selected_objects.add(obj)
        try:
            obj.select_set(True)
        except RuntimeError:
            pass
        self.report({'INFO'}, f"Added {obj.name} ({len(self.original_selected_objects)} objects)")

    # ----- stroke -----

    def _begin_brush_stroke(self, context, remove):
        self._push_undo()
        cache = self._brush_ensure_cache()
        if hasattr(cache, 'reset_scene_filter'):
            cache.reset_scene_filter()
        self._brush_stroke = {'remove': remove, 'touched': {}, 'dirty': set()}
        clear_preview_faces()

    def _apply_brush(self, context, mouse):
        stroke = self._brush_stroke
        remove = stroke['remove']
        update_brush_circle(mouse, self.brush_radius, remove=remove)
        use_coplanar = context.scene.cursor_bbox_select_coplanar
        angle = context.scene.cursor_bbox_coplanar_angle
        for obj in self.original_selected_objects:
            if obj.type != 'MESH':
                continue
            hits = pick_brush_faces(context, obj, self._brush_cache, mouse, self.brush_radius,
                                    occlusion=not self.brush_through,
                                    occluders=self.original_selected_objects)
            if not hits:
                continue
            touched = stroke['touched'].setdefault(obj, set())
            new_hits = [i for i in hits if i not in touched]
            if not new_hits:
                continue
            faces = set(new_hits)
            if use_coplanar:
                for i in new_hits:
                    faces |= get_faces_to_process(
                        obj, i, True, angle, use_depsgraph=self.use_depsgraph)
            marked = self.marked_faces.setdefault(obj, set())
            if apply_stroke(marked, touched, faces, remove=remove):
                stroke['dirty'].add(obj)
                rebuild_marked_faces_visual_data(obj, marked, use_depsgraph=self.use_depsgraph)

    def _end_brush_stroke(self, context):
        stroke = self._brush_stroke
        self._brush_stroke = None
        self._brush_pending = None
        clear_brush_circle()
        for obj in list(self.marked_faces):
            if not self.marked_faces[obj]:
                del self.marked_faces[obj]
                rebuild_marked_faces_visual_data(obj, set(), use_depsgraph=self.use_depsgraph)
        if stroke['dirty']:
            self._brush_update_preview(context)
