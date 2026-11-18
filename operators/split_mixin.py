"""Split / Islands modes for the Interactive Hull modal: manual convex
decomposition.

Both modes share one piece list (overlay, undo, picking, merging, deleting,
Space to create one hull object per piece); ``split_kind`` selects the tools.

* Split mode (``K``) shows a translucent convex hull of the whole selection
  (or of the marked faces). It has two states (``split_state``):
  CUT: hovering a face puts the 3D cursor on it and previews the two hulls a
  cut of the ACTIVE piece by the plane through the cursor (cursor Z, or X / Y
  with ``R``) would produce; LMB makes that cut. Each side's hull is rebuilt
  from the source polygons on that side.
  PICK: entered after a keep-both cut or slabs; no plane, no preview, every
  piece filled evenly, the new pieces outlined; LMB on a piece makes it
  active and goes back to CUT. ``TAB`` toggles the two by hand.
  ``L`` explodes the active piece into islands and switches to Islands mode.
* Islands mode (``L``) explodes the source into its loose islands and merges
  the ones that sit close together and merge cheaply; the merge thresholds
  stay live (Ctrl / Shift / Ctrl+Shift+Wheel) until the pieces are edited by
  hand. There is no cutting plane: LMB / RMB make the piece under the mouse
  active, Shift+LMB / Shift+RMB merge it into the active one. ``K`` switches
  to Split mode keeping the pieces.

RMB makes the piece under the mouse active, Shift+RMB merges it into the
active one, in both modes. The source meshes are never modified: pieces hold
clipped copies of the polygons in memory.

Mix into the operator class and:

* call ``self._split_init(context)`` in ``invoke`` (next to ``_brush_init``);
* in ``modal``, right after the HUD block and BEFORE ``_brush_handle_event``,
  call ``if self._split_handle_event(context, event): return {'RUNNING_MODAL'}``;
* call ``self._split_shutdown()`` on every exit path;
* list ``SPLIT_HELP_ITEMS`` and ``ISLANDS_HELP_ITEMS`` in help sections, call
  ``self._split_add_hud_params(hud)`` and use ``self._split_mode_label()`` in
  the HUD mode string.

The host must provide ``marked_faces``, ``original_selected_objects``,
``use_depsgraph``, ``point_mode``, ``thickness_mode``, ``pick_objects_mode``,
``_brush_pending`` / ``_brush_stroke`` and ``_brush_update_preview(context)``.
"""
import time

import bpy
from mathutils import Vector

from ..functions.core import (
    enable_split_overlay_wrapper as enable_split_overlay,
    disable_split_overlay_wrapper as disable_split_overlay,
    update_split_overlay,
    clear_split_overlay,
    hide_hull_preview,
    clear_preview_faces,
)
from ..functions.utils import place_cursor_with_raycast_and_edge, build_all_faces_dict
from ..functions import hull_split as hs
from ..functions.split import (
    make_piece,
    collect_source_polys,
    cut_piece,
    pick_piece,
    overlay_geometry,
    IslandSet,
    MAX_AUTO_MERGE_ISLANDS,
)
from ..functions.undo_stack import OperatorUndoStack
from ..ui.hud.items import HUDItem, HUDParam


SPLIT_HELP_ITEMS = [
    HUDItem("Enter / exit (discard)", "K / ESC"),
    HUDItem("Cut: cut active piece, then pick a piece", "LMB"),
    HUDItem("Cut, keep back / keep front", "Ctrl+LMB / Ctrl+Shift+LMB"),
    HUDItem("Pick: make piece active, back to cutting", "LMB / RMB"),
    HUDItem("Toggle cut / pick piece", "TAB"),
    HUDItem("Make piece under mouse active", "RMB"),
    HUDItem("Merge piece under mouse into active", "Shift+RMB / Shift+LMB (pick)"),
    HUDItem("Plane: face / across X / across Y", "R"),
    HUDItem("Freeze plane", "F"),
    HUDItem("Plane offset 2% / 0.2%", "Alt+Wheel / Alt+Shift+Wheel"),
    HUDItem("Equal slabs", "2..9"),
    HUDItem("Explode active piece, go to Islands mode", "L"),
    HUDItem("Delete active piece", "X"),
    HUDItem("Undo / Redo", "Ctrl+Z / Ctrl+Shift+Z"),
    HUDItem("Create hulls", "SPACE"),
]

ISLANDS_HELP_ITEMS = [
    HUDItem("Enter / exit (discard)", "L / ESC"),
    HUDItem("Make piece under mouse active", "LMB / RMB"),
    HUDItem("Merge piece under mouse into active", "Shift+LMB / Shift+RMB"),
    HUDItem("Merge gap", "Ctrl+Wheel"),
    HUDItem("Merge void %", "Shift+Wheel"),
    HUDItem("Ignore thinner", "Ctrl+Shift+Wheel"),
    HUDItem("Delete active piece", "X"),
    HUDItem("Undo / Redo", "Ctrl+Z / Ctrl+Shift+Z"),
    HUDItem("Split mode (keep pieces)", "K"),
    HUDItem("Create hulls", "SPACE"),
]

_AXIS_NAMES = ("Face", "Across X", "Across Y")
# split_axis -> cursor matrix column: 0 = Z, 1 = X, 2 = Y
_AXIS_COLUMN = (2, 0, 1)

_SLAB_KEYS = {
    'TWO': 2, 'THREE': 3, 'FOUR': 4, 'FIVE': 5, 'SIX': 6, 'SEVEN': 7, 'EIGHT': 8, 'NINE': 9,
    'NUMPAD_2': 2, 'NUMPAD_3': 3, 'NUMPAD_4': 4, 'NUMPAD_5': 5,
    'NUMPAD_6': 6, 'NUMPAD_7': 7, 'NUMPAD_8': 8, 'NUMPAD_9': 9,
}
_BLOCKED_KEYS = {'A', 'T', 'Q', 'D', 'G', 'C', 'S'}
_CONFIRM_KEYS = {'SPACE', 'RET', 'NUMPAD_ENTER'}

# A preview computation slower than this (seconds) moves the next ones from
# every MOUSEMOVE to the timer.
_PREVIEW_BUDGET = 0.040
_TIMER_INTERVAL = 0.1

# Auto-merge parameter limits (see _split_wheel_param).
_GAP_RANGE = (0.001, 1.0)
_COST_RANGE = (0.0, 0.95)
_THIN_START = 0.005
_THIN_MAX = 0.5
_THIN_OFF_BELOW = 0.004
_PARAM_FACTOR = 1.25


class SplitMixin:

    # ----- lifecycle -----

    def _split_init(self, context):
        self.split_mode = False
        # 'SPLIT' (plane cutting) or 'ISLANDS' (island auto-merge); same pieces.
        self.split_kind = 'SPLIT'
        # Split kind only: 'CUT' (plane, preview, LMB cuts) or 'PICK' (choose
        # the piece to cut next). Islands kind ignores it.
        self.split_state = 'CUT'
        # uids of the pieces made by the last cut / slabs, outlined in PICK.
        self._split_fresh = set()
        self.split_pieces = []
        self.split_active = 0
        self.split_axis = 0
        self.split_offset = 0.0
        self.split_frozen = False
        self._split_hover = None
        self._split_mouse = None
        self._split_color_counter = 0
        self._split_undo = OperatorUndoStack()
        # Event type whose RELEASE must be swallowed after leaving split mode
        # (the host's ESC / RMB branches do not check event.value).
        self._split_swallow_release = None
        self._split_timer = None
        self._split_preview_cost = 0.0
        # Auto-merge parameters (kept across explodes and split sessions).
        self.split_merge_gap = 0.01
        self.split_merge_cost = 0.25
        self.split_ignore_thin = 0.0
        self._split_auto = None
        self._split_param_streak = False
        self._split_preview_reset()

    def _split_preview_reset(self):
        """Forget the cached cut preview (pieces or the active index changed)."""
        # (active uid, plane key) the cached result belongs to, or None.
        self._split_preview_key = None
        # (front, back) when that plane splits the active piece, else None.
        self._split_preview_pieces = None
        # The plane moved but the preview waits for the timer (slow pieces).
        self._split_preview_dirty = False

    def _split_shutdown(self):
        self.split_mode = False
        self.split_kind = 'SPLIT'
        self.split_state = 'CUT'
        self._split_fresh = set()
        self.split_pieces = []
        self._split_hover = None
        try:
            window = bpy.context.window
            if window is not None:
                window.cursor_modal_restore()
        except Exception as e:
            print(f"Split: could not restore the mouse cursor: {e}")
        self._split_end_auto()
        self._split_preview_reset()
        timer = getattr(self, '_split_timer', None)
        self._split_timer = None
        if timer is not None:
            try:
                bpy.context.window_manager.event_timer_remove(timer)
            except Exception as e:
                print(f"Split: could not remove the preview timer: {e}")
        clear_split_overlay()
        disable_split_overlay()

    def _split_mode_label(self):
        """Mode name for the HUD, or None outside split mode."""
        if getattr(self, 'split_mode', False):
            if self._split_islands():
                return "ISLANDS"
            return "SPLIT: PICK PIECE" if self._split_picking() else "SPLIT: CUT"
        return None

    def _split_islands(self):
        """True in Islands mode (no cutting plane)."""
        return getattr(self, 'split_kind', 'SPLIT') == 'ISLANDS'

    def _split_picking(self):
        """True in Split mode's piece-selection state (no plane, no preview)."""
        return (not self._split_islands()
                and getattr(self, 'split_state', 'CUT') == 'PICK')

    def _split_update_cursor(self, context):
        """Mouse cursor as mode feedback: knife while cutting, hand while
        picking pieces (Split PICK, Islands); restored outside split mode.
        Never raises."""
        try:
            window = context.window if context is not None else bpy.context.window
            if window is None:
                return
            if not getattr(self, 'split_mode', False):
                window.cursor_modal_restore()
            elif self._split_islands() or self._split_picking():
                window.cursor_modal_set('HAND')
            else:
                window.cursor_modal_set('KNIFE')
        except Exception as e:
            print(f"Split: could not set the mouse cursor: {e}")

    def _split_set_state(self, context, state):
        """Switch Split mode between 'CUT' and 'PICK' (PICK needs 2+ pieces).
        Leaving PICK forgets the fresh pieces."""
        if state == 'PICK' and len(self.split_pieces) < 2:
            state = 'CUT'
        if state != 'PICK':
            self._split_fresh = set()
        self.split_state = state
        self._split_preview_reset()
        self._split_update_cursor(context)

    def _split_add_hud_params(self, hud):
        visible = lambda: getattr(self, 'split_mode', False)
        visible_split = lambda: getattr(self, 'split_mode', False) and not self._split_islands()
        visible_islands = lambda: getattr(self, 'split_mode', False) and self._split_islands()
        hud.add_param(HUDParam(
            "Pieces", lambda: len(self.split_pieces), kind="int", visible_getter=visible))
        hud.add_param(HUDParam(
            "Plane",
            lambda: _AXIS_NAMES[self.split_axis] + (" (frozen)" if self.split_frozen else ""),
            visible_getter=visible_split))
        hud.add_param(HUDParam(
            "Offset", lambda: self.split_offset, kind="float", fmt="{:.4f}",
            visible_getter=visible_split))
        hud.add_param(HUDParam(
            "Merge gap", lambda: self.split_merge_gap, kind="float", fmt="{:.3f}",
            visible_getter=visible_islands))
        hud.add_param(HUDParam(
            "Merge void %", lambda: int(round(self.split_merge_cost * 100)), kind="int",
            visible_getter=visible_islands))
        hud.add_param(HUDParam(
            "Ignore thinner",
            lambda: "off" if self.split_ignore_thin <= 0.0 else f"{self.split_ignore_thin:.3f}",
            visible_getter=visible_islands))
        hud.add_param(HUDParam(
            "Islands", lambda: "live",
            visible_getter=lambda: (visible_islands()
                                    and getattr(self, '_split_auto', None) is not None)))

    # ----- helpers -----

    def _split_next_color(self):
        c = self._split_color_counter
        self._split_color_counter += 1
        return c

    def _split_plane(self, context):
        """(origin, normal) of the cutting plane from the 3D cursor."""
        mat = context.scene.cursor.matrix
        col = _AXIS_COLUMN[self.split_axis]
        normal = Vector(mat.col[col][:3])
        if normal.length_squared < 1e-20:
            return None
        normal.normalize()
        origin = Vector(mat.col[3][:3]) + normal * self.split_offset
        return origin, normal

    def _split_pick(self, context, pieces=None, mouse=None):
        """Index into *pieces* (default: all pieces) of the piece under the
        mouse (default: the last MOUSEMOVE position), or None."""
        if mouse is None:
            mouse = self._split_mouse
        if mouse is None:
            return None
        try:
            return pick_piece(context, self.split_pieces if pieces is None else pieces, mouse)
        except Exception as e:
            print(f"Split: pick failed: {e}")
            return None

    def _split_set_active(self, index):
        self.split_active = index
        self._split_preview_reset()

    def _split_end_auto(self):
        """End the live link of the last explode (any manual piece edit)."""
        self._split_auto = None
        self._split_param_streak = False

    def _split_preview_key_for(self, plane):
        """Cache key of a cut of the active piece by *plane*, or None."""
        if plane is None or not self.split_pieces:
            return None
        active = self.split_pieces[self.split_active]
        pk = hs.plane_key(tuple(plane[1]), tuple(plane[0]), active.extent)
        if pk is None:
            return None
        return (active.uid, pk)

    def _split_compute_cut(self, plane, key):
        """Cut the active piece by *plane*, timed; cached under *key* (if any).
        Returns ``(front, back)``; a failure counts as "does not split"."""
        active = self.split_pieces[self.split_active]
        t0 = time.perf_counter()
        try:
            front, back = cut_piece(active, plane[0], plane[1], self._split_color_counter)
        except Exception as e:
            print(f"Split: cut preview failed: {e}")
            front, back = None, None
        self._split_preview_cost = time.perf_counter() - t0
        if key is not None:
            self._split_preview_key = key
            self._split_preview_pieces = (
                (front, back) if front is not None and back is not None else None)
            self._split_preview_dirty = False
        return front, back

    def _split_update_preview(self, context, force=False):
        """Bring the cut preview in line with the current plane.

        Unchanged plane (same quantised key): nothing to do. Otherwise compute
        now, unless the last computation was over budget and *force* is not
        set: then only mark the preview dirty for the timer.
        """
        if not self.split_pieces:
            self._split_preview_reset()
            return
        plane = self._split_plane(context)
        key = self._split_preview_key_for(plane)
        if key is None:
            self._split_preview_reset()
            return
        if key == self._split_preview_key:
            self._split_preview_dirty = False
            return
        if not force and self._split_preview_cost > _PREVIEW_BUDGET:
            self._split_preview_dirty = True
            return
        self._split_compute_cut(plane, key)

    def _split_cut_pieces(self, plane):
        """``(front, back)`` of cutting the active piece by *plane*: the cached
        preview when it belongs to this plane, else computed now."""
        key = self._split_preview_key_for(plane)
        if key is not None and key == self._split_preview_key:
            return self._split_preview_pieces or (None, None)
        return self._split_compute_cut(plane, key)

    def _split_refresh(self, context):
        if self._split_picking() and len(self.split_pieces) < 2:
            # A single piece has nothing to pick from: always cutting.
            self._split_set_state(context, 'CUT')
        picking = self._split_picking()
        if self._split_islands() or picking:
            # Islands mode and piece picking have no cutting plane: no plane
            # quad, no cut preview.
            plane, preview = None, None
        else:
            self._split_update_preview(context)
            plane = self._split_plane(context)
            preview = None if self._split_preview_dirty else self._split_preview_pieces
        update_split_overlay(overlay_geometry(
            self.split_pieces, self.split_active, self._split_hover, plane, preview,
            pick=picking, fresh=self._split_fresh if picking else ()))
        if context.area is not None:
            context.area.tag_redraw()

    def _split_snapshot(self):
        return (tuple((p.polys, p.color_index) for p in self.split_pieces),
                self.split_active, self.split_kind, self.split_state)

    def _split_restore(self, context, snap):
        pieces_data, active, kind, state = snap
        self._split_end_auto()
        self.split_kind = kind
        self.split_state = state
        self._split_fresh = set()
        self._split_preview_reset()
        pieces = []
        for polys, color in pieces_data:
            piece = make_piece(polys, color)
            if piece is not None:
                pieces.append(piece)
        self.split_pieces = pieces
        self._split_set_active(min(active, max(0, len(pieces) - 1)))
        self._split_hover = self._split_pick(context)
        if state == 'PICK' and len(pieces) < 2:
            self.split_state = 'CUT'
        self._split_update_cursor(context)

    def _split_enter(self, context, event, kind='SPLIT'):
        """Enter split mode with one piece; *kind* 'ISLANDS' then explodes it
        into islands and auto-merges them right away."""
        if self.marked_faces:
            faces = self.marked_faces
        else:
            faces = build_all_faces_dict(
                self.original_selected_objects, use_depsgraph=self.use_depsgraph, context=context)
        polys = collect_source_polys(context, faces, self.use_depsgraph)
        self._split_color_counter = 0
        piece = make_piece(polys, self._split_next_color()) if polys else None
        if piece is None:
            self.report({'WARNING'}, "Split: the source geometry does not enclose a volume")
            return
        self.split_mode = True
        self.split_kind = kind
        self.split_state = 'CUT'
        self._split_fresh = set()
        self.split_pieces = [piece]
        self.split_offset = 0.0
        self.split_frozen = False
        self._split_mouse = (event.mouse_region_x, event.mouse_region_y)
        self._split_preview_cost = 0.0
        self._split_set_active(0)
        self._split_hover = None
        self._split_end_auto()
        self._split_undo.clear()
        if self._split_timer is None:
            try:
                self._split_timer = context.window_manager.event_timer_add(
                    _TIMER_INTERVAL, window=context.window)
            except Exception as e:
                print(f"Split: could not add the preview timer: {e}")
                self._split_timer = None
        hide_hull_preview()
        clear_preview_faces()
        enable_split_overlay()
        self._split_update_cursor(context)
        if kind == 'ISLANDS':
            self._split_hover = self._split_pick(context)
            self._split_explode(context, single_msg="Single island: nothing to merge")
            # The explode is the starting state of Islands mode, not an edit.
            self._split_undo.clear()
        else:
            self.report({'INFO'}, "Split mode: hover a face, LMB cuts, then pick a piece. "
                                  "TAB cut / pick, Space create, K exit")
        self._split_refresh(context)

    def _split_exit(self, context, message="Split mode off"):
        self._split_shutdown()
        self._split_undo.clear()
        self._brush_update_preview(context)
        if message:
            self.report({'INFO'}, message)
        if context.area is not None:
            context.area.tag_redraw()

    def _split_after_change(self, context):
        """Common tail of every piece change: reset the plane tweaks, drop the
        preview and re-pick the hovered piece."""
        self.split_offset = 0.0
        self.split_frozen = False
        self._split_preview_reset()
        self._split_hover = self._split_pick(context)

    # ----- actions -----

    def _split_cut(self, context, keep):
        """keep: 'BOTH', 'BACK' or 'FRONT'.

        Returns False when nothing was cut because the plane does not split
        the active piece and keep is 'BOTH' (the caller decides what to do);
        True otherwise (trims report their own warning).
        """
        plane = self._split_plane(context)
        if plane is None or not self.split_pieces:
            return keep != 'BOTH'
        active = self.split_pieces[self.split_active]
        front, back = self._split_cut_pieces(plane)
        if keep == 'BOTH':
            if front is None or back is None:
                return False
            snap = self._split_snapshot()
            # The back piece was built with the next colour (see cut_piece).
            self._split_next_color()
            self._split_undo.push(snap)
            self._split_end_auto()
            i = self.split_active
            self.split_pieces[i] = front
            self.split_pieces.insert(i + 1, back)
            sub = self._split_pick(context, pieces=[front, back])
            self._split_set_active(i + 1 if sub == 1 else i)
            # Now choose the piece to cut next; the two new pieces are
            # outlined until then (the visual confirmation of the cut).
            self._split_set_state(context, 'PICK')
            self._split_fresh = {front.uid, back.uid}
            self.report({'INFO'}, f"Cut: {len(self.split_pieces)} pieces. Pick the piece to cut next")
        else:
            kept = back if keep == 'BACK' else front
            other = front if keep == 'BACK' else back
            if kept is None or other is None:
                self.report({'WARNING'}, "Plane does not split the active piece")
                return True
            self._split_undo.push(self._split_snapshot())
            self._split_end_auto()
            # A trimmed piece keeps its colour.
            kept.color_index = active.color_index
            self.split_pieces[self.split_active] = kept
            self.report({'INFO'}, "Trimmed the active piece")
        self._split_after_change(context)
        return True

    def _split_cut_or_pick(self, context):
        """Plain LMB: cut the active piece, or, when the plane does not split
        it, make the piece under the mouse active."""
        if self._split_cut(context, 'BOTH'):
            return
        idx = self._split_pick(context)
        if idx is not None and idx != self.split_active:
            self._split_set_active(idx)
            self._split_hover = idx
        else:
            self.report({'WARNING'}, "Plane does not split the active piece")

    def _split_pick_or_merge(self, context, merge):
        """Make the piece under the mouse active, or (*merge*) merge it into
        the active one (RMB / Shift+RMB; also LMB / Shift+LMB in Islands)."""
        idx = self._split_pick(context)
        if idx is None:
            return
        if merge:
            self._split_merge(context, idx)
        elif idx != self.split_active:
            self._split_set_active(idx)
            self._split_hover = idx
        self._split_refresh(context)

    def _split_follow_mouse(self, context, event):
        """Put the 3D cursor (the cutting plane) under the mouse, unless the
        plane is frozen (entering CUT, so the plane does not lag one move)."""
        if self.split_frozen or event is None:
            return
        try:
            place_cursor_with_raycast_and_edge(
                context, event, True, 0, preview=False, use_depsgraph=self.use_depsgraph)
        except Exception as e:
            print(f"Split: could not place the cursor: {e}")

    def _split_pick_state_click(self, context, event, merge):
        """LMB / RMB in Split mode's PICK state: a piece under the mouse
        becomes active and cutting resumes; *merge* (Shift) merges it into
        the active piece and stays in PICK. Nothing under the mouse: stay."""
        idx = self._split_pick(context)
        if idx is None:
            self._split_refresh(context)
            return
        if merge:
            self._split_merge(context, idx)
        else:
            self._split_set_active(idx)
            self._split_hover = idx
            self._split_set_state(context, 'CUT')
            self._split_follow_mouse(context, event)
        self._split_refresh(context)

    def _split_slabs(self, context, n):
        plane = self._split_plane(context)
        if plane is None or not self.split_pieces:
            return
        normal = tuple(plane[1])
        active = self.split_pieces[self.split_active]
        origins = hs.equal_planes(active.polys, normal, n)
        if not origins:
            self.report({'WARNING'}, "Active piece has no extent along the plane normal")
            return
        eps = hs.plane_eps(active.polys)
        slabs = []
        remaining = active.polys
        for co in origins:
            front, back = hs.split_polygons(remaining, co, normal, eps)
            slabs.append(back)
            remaining = front
        slabs.append(remaining)
        new_pieces = []
        for k, polys in enumerate(slabs):
            color = active.color_index if k == 0 else self._split_color_counter
            piece = make_piece(polys, color) if polys else None
            if piece is not None:
                if k != 0:
                    self._split_next_color()
                new_pieces.append(piece)
        if len(new_pieces) < 2:
            self.report({'WARNING'}, "Could not split the active piece into slabs")
            return
        self._split_undo.push(self._split_snapshot())
        self._split_end_auto()
        i = self.split_active
        self.split_pieces[i:i + 1] = new_pieces
        sub = self._split_pick(context, pieces=new_pieces)
        self._split_set_active(i + (sub if sub is not None else 0))
        self._split_after_change(context)
        self._split_set_state(context, 'PICK')
        self._split_fresh = {p.uid for p in new_pieces}
        skipped = len(slabs) - len(new_pieces)
        msg = f"Split into {len(new_pieces)} slabs"
        if skipped:
            msg += f" ({skipped} empty skipped)"
        self.report({'INFO'}, msg)

    def _split_merge(self, context, index):
        if index is None or index == self.split_active:
            return
        active = self.split_pieces[self.split_active]
        other = self.split_pieces[index]
        merged = make_piece(active.polys + other.polys, active.color_index)
        if merged is None:
            self.report({'WARNING'}, "Merge failed")
            return
        self._split_undo.push(self._split_snapshot())
        self._split_end_auto()
        self.split_pieces[self.split_active] = merged
        del self.split_pieces[index]
        new_active = self.split_active - 1 if index < self.split_active else self.split_active
        self._split_set_active(new_active)
        self._split_hover = self._split_pick(context)
        self.report({'INFO'}, f"Merged: {len(self.split_pieces)} pieces")

    def _split_delete(self, context):
        if len(self.split_pieces) <= 1:
            self.report({'WARNING'}, "Cannot delete the last piece")
            return
        self._split_undo.push(self._split_snapshot())
        self._split_end_auto()
        del self.split_pieces[self.split_active]
        idx = self._split_pick(context)
        if idx is None:
            idx = min(self.split_active, len(self.split_pieces) - 1)
        self._split_set_active(idx)
        self._split_hover = idx
        self.report({'INFO'}, f"Deleted piece: {len(self.split_pieces)} left")

    def _split_explode(self, context, single_msg="Active piece is a single island"):
        """Replace the active piece by the auto-merged groups of its islands
        and keep the grouping live for the merge parameters (entering Islands
        mode, or ``L`` in Split mode)."""
        if not self.split_pieces:
            return
        i = self.split_active
        active = self.split_pieces[i]
        try:
            islands = hs.split_islands(active.polys)
        except Exception as e:
            print(f"Split: island search failed: {e}")
            self.report({'WARNING'}, "Could not split the active piece into islands")
            return
        if len(islands) <= 1:
            self.report({'INFO'}, single_msg)
            return
        try:
            iset = IslandSet(islands)
        except Exception as e:
            print(f"Split: island set failed: {e}")
            self.report({'WARNING'}, "Could not split the active piece into islands")
            return
        record = {
            'islands': iset,
            'before': list(self.split_pieces[:i]),
            'after': list(self.split_pieces[i + 1:]),
            'color_base': self._split_color_counter,
        }
        snap = self._split_snapshot()
        result = self._split_apply_auto(context, record)
        if result is None:
            return
        self._split_undo.push(snap)
        self._split_after_change(context)
        self._split_auto = None if iset.too_many else record
        self._split_param_streak = False
        groups, ignored, built = result
        msg = f"{len(islands)} islands -> {built} hulls ({ignored} ignored)"
        if iset.too_many:
            msg += f"; over {MAX_AUTO_MERGE_ISLANDS} islands, not auto-merged"
            self.report({'WARNING'}, msg)
        else:
            self.report({'INFO'}, msg)

    def _split_apply_auto(self, context, record):
        """Group *record*'s islands with the current parameters and rebuild
        the piece list as before + new + after. Returns ``(groups, ignored,
        built)``, or None (with a warning, pieces unchanged) when no hull
        could be built."""
        iset = record['islands']
        try:
            groups, ignored = iset.groups(
                self.split_merge_gap, self.split_merge_cost, self.split_ignore_thin)
            # Same colours for the same group positions on every re-grouping.
            counter = [record['color_base']]

            def next_color():
                c = counter[0]
                counter[0] += 1
                return c
            new_pieces = iset.build_pieces(groups, next_color)
        except Exception as e:
            print(f"Split: auto-merge failed: {e}")
            self.report({'WARNING'}, "Auto-merge failed")
            return None
        if not new_pieces:
            self.report({'WARNING'}, "No hull left: every island is ignored at these settings")
            return None
        self._split_color_counter = max(self._split_color_counter, counter[0])
        before = record['before']
        self.split_pieces = before + new_pieces + record['after']
        sub = self._split_pick(context, pieces=new_pieces)
        self._split_set_active(len(before) + (sub if sub is not None else 0))
        self._split_hover = self._split_pick(context)
        return groups, ignored, len(new_pieces)

    def _split_wheel_param(self, context, event):
        """Ctrl / Shift / Ctrl+Shift+Wheel: merge gap, merge cost, ignore
        thinner. Re-groups the last explode while it is live."""
        up = event.type == 'WHEELUPMOUSE'
        if event.ctrl and event.shift:
            v = self.split_ignore_thin
            if up:
                v = _THIN_START if v <= 0.0 else min(_THIN_MAX, v * _PARAM_FACTOR)
            else:
                v /= _PARAM_FACTOR
                if v < _THIN_OFF_BELOW:
                    v = 0.0
            self.split_ignore_thin = v
            label = "Ignore thinner: " + ("off" if v <= 0.0 else f"{v:.3f}")
        elif event.ctrl:
            v = self.split_merge_gap * (_PARAM_FACTOR if up else 1.0 / _PARAM_FACTOR)
            self.split_merge_gap = min(_GAP_RANGE[1], max(_GAP_RANGE[0], v))
            label = f"Merge gap: {self.split_merge_gap:.3f}"
        else:
            v = round(self.split_merge_cost + (0.05 if up else -0.05), 2)
            self.split_merge_cost = min(_COST_RANGE[1], max(_COST_RANGE[0], v))
            label = f"Merge void: {int(round(self.split_merge_cost * 100))}%"
        record = self._split_auto
        if record is None:
            self.report({'INFO'}, label)
            return
        snap = self._split_snapshot()
        result = self._split_apply_auto(context, record)
        if result is None:
            return
        # Consecutive parameter changes share one undo entry.
        if not self._split_param_streak:
            self._split_undo.push(snap)
            self._split_param_streak = True
        _groups, ignored, built = result
        self.report({'INFO'}, f"{label}: {len(record['islands'].islands)} islands -> "
                              f"{built} hulls ({ignored} ignored)")

    def _split_create(self, context):
        from .interactive_hull import _build_hull_object_from_vertices, report_auto_fix
        base_name = context.scene.cursor_bbox_name_hull or "Convex"
        created, failed = 0, 0
        for piece in self.split_pieces:
            verts = [Vector(p) for p in hs.unique_points(piece.polys)]
            if _build_hull_object_from_vertices(context, verts, base_name):
                created += 1
            else:
                failed += 1
        if failed:
            self.report({'WARNING'}, f"Created {created} hulls, {failed} failed")
        else:
            self.report({'INFO'}, f"Created {created} hulls")
        report_auto_fix(self)
        self._split_exit(context, message=None)

    # ----- events -----

    def _split_handle_event(self, context, event):
        """Returns True when the event was consumed by split mode."""
        swallow = getattr(self, '_split_swallow_release', None)
        if swallow is not None and event.type == swallow:
            if event.value == 'RELEASE':
                self._split_swallow_release = None
            return True
        if not getattr(self, 'split_mode', False):
            if (event.type in {'K', 'L'} and event.value == 'PRESS'
                    and not event.ctrl and not event.alt and not event.shift
                    and not getattr(self, 'point_mode', False)
                    and not getattr(self, 'thickness_mode', False)
                    and not getattr(self, 'pick_objects_mode', False)
                    and getattr(self, '_brush_pending', None) is None
                    and getattr(self, '_brush_stroke', None) is None):
                self._split_enter(context, event,
                                  kind='ISLANDS' if event.type == 'L' else 'SPLIT')
                return True
            return False

        etype = event.type
        press = event.value == 'PRESS'
        islands = self._split_islands()

        # Timer: compute a preview that was deferred (over budget). Never
        # consumed, so the host / HUD still see it.
        if etype == 'TIMER':
            if not islands and not self._split_picking() and self._split_preview_dirty:
                self._split_update_preview(context, force=True)
                self._split_refresh(context)
            return False

        if etype in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            if etype == 'MOUSEMOVE':
                self._split_mouse = (event.mouse_region_x, event.mouse_region_y)
                hover = self._split_pick(context)
                hover_changed = hover != self._split_hover
                self._split_hover = hover
                if islands or self._split_picking():
                    # No cutting plane (Islands, Split PICK): the 3D cursor
                    # stays, only the hover highlight follows the mouse.
                    if hover_changed:
                        self._split_refresh(context)
                elif not self.split_frozen:
                    place_cursor_with_raycast_and_edge(
                        context, event, True, 0, preview=False,
                        use_depsgraph=self.use_depsgraph)
                    self._split_refresh(context)
                elif hover_changed:
                    self._split_refresh(context)
            return True

        # Viewport navigation passes through (host handles it).
        if etype == 'MIDDLEMOUSE':
            return False
        if etype in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            if (event.ctrl or event.shift) and not event.alt:
                self._split_wheel_param(context, event)
                self._split_refresh(context)
                return True
            if event.alt and not event.ctrl:
                if not islands and not self._split_picking() and self.split_pieces:
                    ext = self.split_pieces[self.split_active].extent
                    step = ext * (0.002 if event.shift else 0.02)
                    self.split_offset += step if etype == 'WHEELUPMOUSE' else -step
                    self._split_refresh(context)
                return True
            return False

        if etype == 'LEFTMOUSE':
            if press and islands:
                self._split_mouse = (event.mouse_region_x, event.mouse_region_y)
                if not event.ctrl:
                    self._split_pick_or_merge(context, merge=event.shift)
            elif press and self._split_picking():
                self._split_mouse = (event.mouse_region_x, event.mouse_region_y)
                if not event.ctrl:
                    self._split_pick_state_click(context, event, merge=event.shift)
            elif press:
                self._split_mouse = (event.mouse_region_x, event.mouse_region_y)
                if event.ctrl and event.shift:
                    self._split_cut(context, 'FRONT')
                elif event.ctrl:
                    self._split_cut(context, 'BACK')
                else:
                    self._split_cut_or_pick(context)
                self._split_refresh(context)
            return True

        if not press:
            # Releases of keys we own are swallowed; others (HUD etc.) fall through.
            return etype in ({'RIGHTMOUSE', 'ESC', 'K', 'R', 'F', 'X', 'Z', 'L', 'TAB'}
                             | _CONFIRM_KEYS | _BLOCKED_KEYS | set(_SLAB_KEYS))

        if etype == 'K' and islands:
            # Keep the pieces (and the live merge link until the next edit).
            self.split_kind = 'SPLIT'
            self._split_set_state(context, 'CUT')
            self.report({'INFO'}, "Split mode: cut pieces with planes")
            self._split_refresh(context)
            return True

        if etype == 'L' and not islands:
            self._split_explode(context)
            self.split_kind = 'ISLANDS'
            self._split_set_state(context, 'CUT')
            self._split_refresh(context)
            return True

        if etype == 'TAB':
            if islands:
                return True
            if len(self.split_pieces) < 2:
                self.report({'INFO'}, "Only one piece: nothing to pick")
                return True
            if self._split_picking():
                self._split_set_state(context, 'CUT')
                self._split_follow_mouse(context, event)
                self.report({'INFO'}, "Split: cut the active piece")
            else:
                self._split_set_state(context, 'PICK')
                self.report({'INFO'}, "Split: pick the piece to cut")
            self._split_hover = self._split_pick(context)
            self._split_refresh(context)
            return True

        if etype in {'K', 'L', 'ESC'}:
            name = "Islands" if islands else "Split"
            self._split_exit(context, f"{name} mode off (pieces discarded)")
            self._split_swallow_release = etype
            return True

        if etype == 'RIGHTMOUSE':
            # Never finishes the modal in split mode: picks / merges a piece.
            self._split_mouse = (event.mouse_region_x, event.mouse_region_y)
            if self._split_picking():
                self._split_pick_state_click(context, event, merge=event.shift)
            else:
                self._split_pick_or_merge(context, merge=event.shift)
            return True

        if etype in _CONFIRM_KEYS:
            self._split_create(context)
            return True

        if etype == 'Z':
            if event.ctrl and not event.alt:
                if event.shift:
                    snap = self._split_undo.pop_redo(self._split_snapshot())
                    label = "Redo"
                else:
                    snap = self._split_undo.pop_undo(self._split_snapshot())
                    label = "Undo"
                if snap is not None:
                    self._split_restore(context, snap)
                    self.report({'INFO'}, label)
                    self._split_refresh(context)
                else:
                    self.report({'INFO'}, f"Nothing to {label.lower()}")
            return True

        if islands and (etype in {'R', 'F'} or etype in _SLAB_KEYS):
            # Cutting tools: Split mode only.
            return True

        if etype == 'R':
            self.split_axis = (self.split_axis + 1) % 3
            self.report({'INFO'}, f"Split plane: {_AXIS_NAMES[self.split_axis]}")
            self._split_refresh(context)
            return True

        if etype == 'F':
            self.split_frozen = not self.split_frozen
            self.report({'INFO'}, "Split plane frozen" if self.split_frozen
                        else "Split plane follows the mouse")
            self._split_refresh(context)
            return True

        if etype == 'X':
            self._split_delete(context)
            self._split_refresh(context)
            return True

        if etype in _SLAB_KEYS:
            if self._split_picking():
                # No plane while picking: choose the piece to slab first.
                self.report({'INFO'}, "Pick a piece first (LMB), or TAB to cut")
                return True
            self._split_slabs(context, _SLAB_KEYS[etype])
            self._split_refresh(context)
            return True

        if etype in _BLOCKED_KEYS:
            self.report({'INFO'}, "Exit islands mode (L) first" if islands
                        else "Exit split mode (K) first")
            return True

        return False
