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
* call ``self._brush_shutdown()`` on every exit path.

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
    region_mouse,
    exceeds_drag_threshold,
    step_radius,
)


class BrushMarkingMixin:

    # ----- lifecycle -----

    def _brush_init(self, context):
        self.brush_radius = int(context.scene.cursor_bbox_brush_radius)
        self._brush_pending = None
        self._brush_stroke = None
        self._brush_cache = None
        enable_brush_circle()

    def _brush_shutdown(self):
        self._brush_pending = None
        self._brush_stroke = None
        disable_brush_circle()

    def _brush_marking_mode(self):
        """True when LMB marks faces (not point / thickness mode)."""
        return (not getattr(self, 'point_mode', False)
                and not getattr(self, 'thickness_mode', False))

    # ----- events -----

    def _brush_on_press(self, event):
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

        if (event.type in {'LEFT_BRACKET', 'RIGHT_BRACKET'} and event.value == 'PRESS'
                and self._brush_marking_mode()):
            self.brush_radius = step_radius(self.brush_radius, event.type == 'RIGHT_BRACKET')
            context.scene.cursor_bbox_brush_radius = self.brush_radius
            update_brush_circle(region_mouse(event), self.brush_radius)
            context.area.tag_redraw()
            return True

        if event.type == 'MOUSEMOVE':
            # Hide a lingering radius-preview circle; never consume the move.
            clear_brush_circle()
        return False

    # ----- stroke -----

    def _begin_brush_stroke(self, context, remove):
        self._push_undo()
        if (self._brush_cache is None
                or self._brush_cache.use_depsgraph != self.use_depsgraph):
            self._brush_cache = BrushFaceCache(self.use_depsgraph)
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
            hits = pick_brush_faces(context, obj, self._brush_cache, mouse, self.brush_radius)
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
