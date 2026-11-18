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

``M`` (both modes, 2+ pieces) toggles the MERGE state (``split_state ==
'MERGE'``; Islands mode uses the field only for this): LMB on a piece sets
the merge base, then LMB on other pieces merges them into the base (one
undo step each), RMB re-picks the base; hovering another piece previews
the merged hull. Pieces are drawn solid and the source objects are hidden
while MERGE lasts; ``M`` / ``TAB`` leave it (also automatically when one
piece is left).

``Q`` (both modes) picks an existing collision object under the mouse and
turns it into a piece: the source polygons clipped to that object's convex
hull (or its own polygons when no source geometry lies inside), so the work
continues where it stopped. ``Shift+Q`` (and, with the
``split_autoload_existing`` preference, entering the mode) does the same for
every existing collision of the selection in the collision collection; ``W``
adds the hull of the whole selection as another piece. A picked object is
hidden while editing. On Space it is kept when its piece is unchanged (no
hull is made for that piece) and deleted otherwise (replaced by the new
hulls, or removed with its piece); any other exit shows it again.

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
import math
import time

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector, geometry

from ..functions.core import (
    enable_split_overlay_wrapper as enable_split_overlay,
    disable_split_overlay_wrapper as disable_split_overlay,
    update_split_overlay,
    clear_split_overlay,
    clear_edge_highlight,
    hide_hull_preview,
    clear_preview_faces,
)
from ..functions.utils import (
    clear_all_caches,
    place_cursor_with_raycast_and_edge,
    build_all_faces_dict,
    get_evaluated_mesh,
)
from ..functions import hull_split as hs
from ..functions.split import (
    make_piece,
    hull_planes,
    hull_volume,
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
    HUDItem("Quick merge into active, stay picking (TAB to cut)", "Shift+LMB / Shift+RMB"),
    HUDItem("Hover a face / edge / vertex: cut by its plane / along the edge / "
            "through the vertex", "Mouse"),
    HUDItem("Plane: face / across X / across Y", "R"),
    HUDItem("Freeze plane", "F"),
    HUDItem("Plane offset 2% / 0.2%", "Alt+Wheel / Alt+Shift+Wheel"),
    HUDItem("Equal slabs", "2..9"),
    HUDItem("Explode active piece, go to Islands mode", "L"),
    HUDItem("Merge mode: click a base, then click pieces to merge into it", "M"),
    HUDItem("Delete active piece", "X"),
    HUDItem("Edit existing collision under cursor", "Q"),
    HUDItem("Load existing collisions", "Shift+Q"),
    HUDItem("Add hull of whole selection", "W"),
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
    HUDItem("Flat merge (coplanar parts ignore void %)", "F"),
    HUDItem("Merge mode: click a base, then click pieces to merge into it", "M"),
    HUDItem("Delete active piece", "X"),
    HUDItem("Edit existing collision under cursor", "Q"),
    HUDItem("Load existing collisions", "Shift+Q"),
    HUDItem("Add hull of whole selection", "W"),
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
_BLOCKED_KEYS = {'A', 'T', 'D', 'G', 'C', 'S'}
# Ray-cast steps past skipped objects when picking a collision object (Q).
_PICK_MAX_STEPS = 16
_CONFIRM_KEYS = {'SPACE', 'RET', 'NUMPAD_ENTER'}

# A preview computation slower than this (seconds) moves the next ones from
# every MOUSEMOVE to the timer.
_PREVIEW_BUDGET = 0.040
_TIMER_INTERVAL = 0.1
# Merge previews kept (keyed by uid pairs); the cache is emptied when full.
_MERGE_CACHE_MAX = 32

# Auto-merge parameter limits (see _split_wheel_param).
# Merge gap: lower bound only (no upper limit, at the user's request).
_GAP_MIN = 0.001
_COST_RANGE = (0.0, 0.95)
_THIN_START = 0.005
_THIN_MAX = 0.5
_THIN_OFF_BELOW = 0.004
_PARAM_FACTOR = 1.25

# Existing collisions are loaded when their bbox touches the source bbox
# expanded by this fraction of its diagonal.
_LOAD_BBOX_MARGIN = 0.02
# An existing collision belongs to the selection when the source geometry
# inside it has at least this fraction of its own hull volume.
_OWNED_MIN_RATIO = 0.25
# The uncovered remainder is added only when its hull has at least this
# fraction of the whole-selection hull volume.
_REMAINDER_MIN_RATIO = 0.01

# Split CUT state: the cutting plane snaps to the hovered face's vertex /
# edge when the mouse is within these screen distances (pixels).
_SNAP_VERT_PX = 12.0
_SNAP_EDGE_PX = 10.0
_SNAP_NAMES = {'FACE': "Face", 'EDGE': "Edge", 'VERTEX': "Vertex"}


def _gap_label(gap):
    """Merge gap for display: 3 decimals below 1, 2 from 1 up."""
    return f"{gap:.3f}" if gap < 1.0 else f"{gap:.2f}"


def _pref_autoload():
    """The ``split_autoload_existing`` preference (True when unreadable)."""
    try:
        prefs = bpy.context.preferences.addons["Cursor_BBox"].preferences
    except (KeyError, AttributeError):
        return True
    return bool(getattr(prefs, "split_autoload_existing", True))


def _collision_collection(context):
    """The collection new collision objects go into, resolved the way
    ``ensure_cbb_collection`` does it but WITHOUT creating anything: None
    when the named collection does not exist."""
    try:
        prefs = context.preferences.addons["Cursor_BBox"].preferences
    except (KeyError, AttributeError):
        prefs = None
    if prefs is not None and getattr(prefs, "use_active_collection", True):
        alc = context.view_layer.active_layer_collection
        if alc is not None and not alc.exclude:
            return alc.collection
    name = getattr(context.scene, "cursor_bbox_collection_name", "")
    if not name:
        return None
    return bpy.data.collections.get(name)


def _loaded_message(loaded, rejected, coll, remainder):
    """INFO text after a load of *loaded* existing collisions."""
    msg = f"Loaded {loaded} existing collision(s)"
    if remainder:
        msg += " + uncovered remainder"
    if rejected:
        where = coll.name if coll is not None else "the collision collection"
        msg += f" ({rejected} others in {where} do not belong to the selection)"
    return msg


def _world_bbox(obj):
    """World-space ``(min3, max3)`` of *obj*'s bound box, or None."""
    try:
        mw = obj.matrix_world
        return hs.bbox([tuple(mw @ Vector(c)) for c in obj.bound_box])
    except Exception:
        return None


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
        # Flat-merge rule: coplanar parts merge within the gap whatever the
        # void (F in Islands).
        self.split_merge_flat = True
        self._split_auto = None
        self._split_param_streak = False
        # Existing collision objects turned into pieces (Q, Shift+Q, autoload),
        # hidden while editing: {object name: uid of the piece built from
        # it}, in pick order. A uid still in the piece list on Space means
        # "unchanged": the original is kept.
        self._split_picked = {}
        # Source polygons with their bboxes, collected once per split session
        # for Q: tuple of (poly, lo, hi), or None.
        self._split_source_cache = None
        # True while the piece list is the untouched initial piece (a Q pick
        # then replaces it instead of being appended).
        self._split_pristine = False
        # {picked object name: its convex region (see _split_object_region)
        # or None}, for the uncovered remainder.
        self._split_regions = {}
        # uid of the uncovered-remainder piece added by the last load, or
        # None. While a piece with this uid exists (untouched), Space makes
        # no hull for it.
        self._split_remainder_uid = None
        # Split CUT: what the mouse hovers on a source face (see
        # _split_update_snap): dict kind 'FACE' / 'EDGE' / 'VERTEX', 'face'
        # (world points), 'edge' (a, b) or None, 'vertex' or None, 'origin'
        # and, for an edge, 'normal' of the plane; None when nothing is hovered.
        self._split_snap = None
        # Base plane (origin, normal; no offset) stored when F froze it, and
        # the plane preview's direction hint of that moment.
        self._split_frozen_plane = None
        self._split_frozen_axis = None
        # MERGE state: uid of the base piece (None: not chosen yet).
        self._split_merge_base = None
        # Split PICK: uid of the Shift+click merge target (None: not set).
        self._split_quick_target = None
        # Merge-preview hulls {(base uid, other uid): Piece or None}; uids
        # never change geometry, so entries never go stale (size-capped).
        self._split_merge_cache = {}
        # The hover wanted a preview not built yet (last build over budget).
        self._split_merge_dirty = False
        self._split_merge_cost = 0.0
        # Sources hidden for MERGE: {'names', 'selected', 'active'} or None.
        self._split_hidden_sources = None
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
        self._split_pristine = False
        self._split_source_cache = None
        self._split_regions = {}
        self._split_remainder_uid = None
        self._split_snap = None
        self._split_frozen_plane = None
        self._split_merge_base = None
        self._split_quick_target = None
        self._split_merge_cache = {}
        self._split_merge_dirty = False
        self._split_show_sources(None)
        self._split_unhide_picked()
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
            if self._split_merging():
                return "ISLANDS: MERGE" if self._split_islands() else "SPLIT: MERGE"
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

    def _split_merging(self):
        """True in the MERGE state (either kind): no plane, no preview,
        solid pieces, sources hidden."""
        return getattr(self, 'split_state', 'CUT') == 'MERGE'

    def _split_no_plane(self):
        """True when there is no cutting plane: Islands, PICK or MERGE."""
        return self._split_islands() or self._split_picking() or self._split_merging()

    def _split_normal_state(self):
        """The state MERGE returns to: PICK in Split (CUT with one piece, see
        _split_set_state), the plain state in Islands."""
        return 'CUT' if self._split_islands() else 'PICK'

    def _split_base_index(self):
        """Index of the MERGE base piece, or None."""
        uid = getattr(self, '_split_merge_base', None)
        if uid is None:
            return None
        for i, piece in enumerate(self.split_pieces):
            if piece.uid == uid:
                return i
        return None

    # ----- MERGE: hiding the source objects -----

    def _split_hide_sources(self, context):
        """Hide the visible source objects for MERGE, remembering which were
        selected and the active object (hide_set deselects)."""
        if getattr(self, '_split_hidden_sources', None) is not None:
            return
        record = {'names': [], 'selected': [], 'active': None}
        try:
            active = context.view_layer.objects.active
            record['active'] = active.name if active is not None else None
        except Exception:
            pass
        for obj in (self.original_selected_objects or ()):
            try:
                if obj.hide_get():
                    continue    # hidden before MERGE: stays hidden
                name = obj.name
                if obj.select_get():
                    record['selected'].append(name)
                obj.hide_set(True)
                record['names'].append(name)
            except Exception as e:
                print(f"Split: could not hide a source object: {e}")
        self._split_hidden_sources = record

    def _split_show_sources(self, context):
        """Show the sources hidden for MERGE again and restore their
        selection and the active object. *context* may be None (shutdown):
        objects are looked up by name; missing ones are skipped. Never
        raises."""
        record = getattr(self, '_split_hidden_sources', None)
        self._split_hidden_sources = None
        if not record:
            return
        try:
            view_layer = (context.view_layer if context is not None
                          else bpy.context.view_layer)
        except Exception:
            view_layer = None
        for name in record['names']:
            try:
                obj = bpy.data.objects.get(name)
                if obj is not None:
                    obj.hide_set(False)
            except Exception as e:
                print(f"Split: could not show {name!r} again: {e}")
        for name in record['selected']:
            try:
                obj = bpy.data.objects.get(name)
                if obj is not None:
                    obj.select_set(True)
            except Exception as e:
                print(f"Split: could not reselect {name!r}: {e}")
        if record['active'] is not None and view_layer is not None:
            try:
                obj = bpy.data.objects.get(record['active'])
                if obj is not None:
                    view_layer.objects.active = obj
            except Exception as e:
                print(f"Split: could not restore the active object: {e}")
        try:
            clear_all_caches()
        except Exception as e:
            print(f"Split: could not clear the raycast caches: {e}")

    def _split_sync_sources(self, context):
        """Sources hidden exactly while in MERGE (split mode on)."""
        if getattr(self, 'split_mode', False) and self._split_merging():
            self._split_hide_sources(context)
        else:
            self._split_show_sources(context)

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
            elif self._split_merging():
                window.cursor_modal_set('CROSSHAIR')
            elif self._split_islands() or self._split_picking():
                window.cursor_modal_set('HAND')
            else:
                window.cursor_modal_set('KNIFE')
        except Exception as e:
            print(f"Split: could not set the mouse cursor: {e}")

    def _split_set_state(self, context, state):
        """Switch between 'CUT', 'PICK' and 'MERGE' (PICK and MERGE need 2+
        pieces). Leaving PICK forgets the fresh pieces; leaving MERGE forgets
        the base and shows the sources again (entering hides them)."""
        if state == 'MERGE' and len(self.split_pieces) < 2:
            state = self._split_normal_state()
        if state == 'PICK' and (len(self.split_pieces) < 2 or self._split_islands()):
            state = 'CUT'
        if state != 'PICK':
            self._split_fresh = set()
            self._split_quick_target = None
        if state != 'MERGE':
            self._split_merge_base = None
            self._split_merge_dirty = False
        if not self.split_frozen:
            # Re-chosen on the next hover (or by _split_follow_mouse).
            self._split_snap = None
        self.split_state = state
        self._split_preview_reset()
        self._split_sync_sources(context)
        self._split_update_cursor(context)

    def _split_add_hud_params(self, hud):
        visible = lambda: getattr(self, 'split_mode', False)
        visible_split = lambda: getattr(self, 'split_mode', False) and not self._split_islands()
        visible_islands = lambda: getattr(self, 'split_mode', False) and self._split_islands()
        hud.add_param(HUDParam(
            "Pieces", lambda: len(self.split_pieces), kind="int", visible_getter=visible))
        hud.add_param(HUDParam(
            "Editing", lambda: len(getattr(self, '_split_picked', ())), kind="int",
            visible_getter=lambda: visible() and bool(getattr(self, '_split_picked', ()))))
        hud.add_param(HUDParam(
            "Plane",
            lambda: _AXIS_NAMES[self.split_axis] + (" (frozen)" if self.split_frozen else ""),
            visible_getter=visible_split))
        hud.add_param(HUDParam(
            "Snap",
            lambda: (_SNAP_NAMES.get(self._split_snap['kind'], "-")
                     if getattr(self, '_split_snap', None) else "-"),
            visible_getter=lambda: (visible_split() and not self._split_picking()
                                    and not self._split_merging())))
        hud.add_param(HUDParam(
            "Merge base", lambda: "set" if self._split_base_index() is not None else "-",
            visible_getter=lambda: visible() and self._split_merging()))
        hud.add_param(HUDParam(
            "Offset", lambda: self.split_offset, kind="float", fmt="{:.4f}",
            visible_getter=visible_split))
        hud.add_param(HUDParam(
            "Merge gap", lambda: _gap_label(self.split_merge_gap),
            visible_getter=visible_islands))
        hud.add_param(HUDParam(
            "Merge void %", lambda: int(round(self.split_merge_cost * 100)), kind="int",
            visible_getter=visible_islands))
        hud.add_param(HUDParam(
            "Ignore thinner",
            lambda: "off" if self.split_ignore_thin <= 0.0 else f"{self.split_ignore_thin:.3f}",
            visible_getter=visible_islands))
        hud.add_param(HUDParam(
            "Flat merge", lambda: self.split_merge_flat, kind="bool",
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

    def _split_base_plane(self, context):
        """(origin, normal) of the cutting plane before the offset.

        An edge snap gives the plane through the edge containing the face
        normal; otherwise the normal is the cursor axis chosen by
        ``split_axis`` and the origin the cursor location (which follows
        the snapped face hit / vertex, see _split_update_snap)."""
        snap = getattr(self, '_split_snap', None)
        if snap is not None and snap.get('normal') is not None:
            return snap['origin'].copy(), snap['normal'].copy()
        mat = context.scene.cursor.matrix
        col = _AXIS_COLUMN[self.split_axis]
        normal = Vector(mat.col[col][:3])
        if normal.length_squared < 1e-20:
            return None
        normal.normalize()
        return Vector(mat.col[3][:3]), normal

    def _split_plane(self, context):
        """(origin, normal) of the cutting plane: the frozen plane while F
        holds it, else the live (snapped) one; shifted by the offset."""
        base = None
        if self.split_frozen:
            base = getattr(self, '_split_frozen_plane', None)
        if base is None:
            base = self._split_base_plane(context)
        if base is None:
            return None
        origin, normal = base
        return origin + normal * self.split_offset, normal.copy()

    def _split_live_plane_axis(self, context):
        """In-plane direction hint for the plane preview's fallback square:
        the hovered edge (EDGE snap), the hovered face's first edge (FACE /
        VERTEX snap), else the 3D cursor's X axis. None when unavailable."""
        snap = getattr(self, '_split_snap', None)
        try:
            if snap is not None:
                if snap.get('kind') == 'EDGE' and snap.get('edge'):
                    a, b = snap['edge']
                    return Vector(b) - Vector(a)
                face = snap.get('face') or ()
                if len(face) >= 2:
                    return Vector(face[1]) - Vector(face[0])
            return Vector(context.scene.cursor.matrix.col[0][:3])
        except Exception:
            return None

    def _split_plane_axis(self, context):
        """The hint for the current plane: the one stored when F froze it,
        else the live one."""
        if self.split_frozen and getattr(self, '_split_frozen_plane', None) is not None:
            return getattr(self, '_split_frozen_axis', None)
        return self._split_live_plane_axis(context)

    def _split_track_mouse(self, context, event):
        """Split CUT, plane not frozen: put the 3D cursor on the hovered face,
        drop the host's edge highlight and update the snap target."""
        try:
            result = place_cursor_with_raycast_and_edge(
                context, event, True, 0, preview=False, use_depsgraph=self.use_depsgraph)
        except Exception as e:
            print(f"Split: could not place the cursor: {e}")
            result = None
        try:
            clear_edge_highlight()
        except Exception as e:
            print(f"Split: could not clear the edge highlight: {e}")
        try:
            self._split_update_snap(context, event, result)
        except Exception as e:
            print(f"Split: snap failed: {e}")
            self._split_snap = None

    def _split_update_snap(self, context, event, result):
        """Choose the snap target (vertex / edge / face of the hovered source
        face, by screen distance) and move the cursor to the plane origin."""
        self._split_snap = None
        face_data = result.get('face_data') if result else None
        if not face_data or not face_data.get('edges'):
            return
        obj = face_data.get('object')
        sources = self.original_selected_objects or ()
        if obj is None or not any(obj == o for o in sources):
            return
        region = context.region
        rv3d = context.region_data
        if region is None or rv3d is None:
            return
        edges = face_data['edges']
        verts = [Vector(e['start']) for e in edges]
        n = len(verts)
        if n < 3:
            return
        hit = Vector(face_data.get('hit_location', face_data.get('face_center')))
        mouse = (event.mouse_region_x, event.mouse_region_y)
        verts_2d = []
        for v in verts:
            p = view3d_utils.location_3d_to_region_2d(region, rv3d, v)
            verts_2d.append(None if p is None else (p.x, p.y))
        edges_2d = [(verts_2d[i], verts_2d[(i + 1) % n]) for i in range(n)]
        choice = hs.pick_snap(mouse, verts_2d, edges_2d, _SNAP_VERT_PX, _SNAP_EDGE_PX)
        face_pts = [tuple(v) for v in verts]
        snap = {'kind': 'FACE', 'face': face_pts, 'edge': None, 'vertex': None,
                'origin': hit, 'normal': None}
        if choice[0] == 'VERTEX':
            v = verts[choice[1]]
            snap.update(kind='VERTEX', vertex=tuple(v), origin=v.copy())
        elif choice[0] == 'EDGE':
            edge_snap = self._split_edge_plane(region, rv3d, mouse, verts, choice)
            if edge_snap is not None:
                point, normal, a, b = edge_snap
                snap.update(kind='EDGE', edge=(tuple(a), tuple(b)), origin=point,
                            normal=normal)
        self._split_snap = snap
        if snap['kind'] != 'FACE':
            # The cursor shows the plane origin; its rotation stays.
            context.scene.cursor.location = snap['origin']

    @staticmethod
    def _split_edge_plane(region, rv3d, mouse, verts, choice):
        """``(point, normal, a, b)`` of an edge snap: the point of edge
        ``choice[1]`` under the mouse and the plane normal containing the
        edge and the face normal, pointing away from the face centre; None
        when degenerate."""
        _kind, i, t2d = choice
        n = len(verts)
        a, b = verts[i], verts[(i + 1) % n]
        # Face normal (Newell) from the world vertices.
        fn = Vector((0.0, 0.0, 0.0))
        for k in range(n):
            p, q = verts[k], verts[(k + 1) % n]
            fn.x += (p.y - q.y) * (p.z + q.z)
            fn.y += (p.z - q.z) * (p.x + q.x)
            fn.z += (p.x - q.x) * (p.y + q.y)
        d = b - a
        normal = d.cross(fn)
        if fn.length_squared < 1e-30 or d.length_squared < 1e-30 \
                or normal.length_squared < 1e-30 * d.length_squared * fn.length_squared:
            return None
        normal.normalize()
        # The 3D point under the mouse: closest point between the view ray
        # and the edge line (2D parameter as fallback), clamped to the edge.
        t = t2d
        try:
            origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
            direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse)
            hits = geometry.intersect_line_line(origin, origin + direction, a, b)
            if hits is not None:
                t = (hits[1] - a).dot(d) / d.length_squared
        except Exception:
            pass
        t = min(1.0, max(0.0, t))
        point = a + d * t
        center = Vector((0.0, 0.0, 0.0))
        for v in verts:
            center += v
        center /= n
        if normal.dot(center - point) > 0.0:
            normal = -normal
        return point, normal, a, b

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
        if self._split_merging() and len(self.split_pieces) < 2:
            # One piece left: nothing to merge, leave MERGE.
            self._split_set_state(context, self._split_normal_state())
            self.report({'INFO'}, "One piece left: merge mode off")
        if self._split_picking() and len(self.split_pieces) < 2:
            # A single piece has nothing to pick from: always cutting.
            self._split_set_state(context, 'CUT')
        picking = self._split_picking()
        merging = self._split_merging()
        # Safety net: sources hidden exactly while MERGE lasts.
        self._split_sync_sources(context)
        if merging:
            self._split_update_merge_preview()
        merge_preview = self._split_current_merge_preview() if merging else None
        if self._split_islands() or picking or merging:
            # Islands mode, piece picking and merging have no cutting plane:
            # no plane quad, no cut preview.
            plane, preview = None, None
        else:
            self._split_update_preview(context)
            plane = self._split_plane(context)
            preview = None if self._split_preview_dirty else self._split_preview_pieces
        data = overlay_geometry(
            self.split_pieces, self.split_active, self._split_hover, plane, preview,
            pick=picking, fresh=self._split_fresh if picking else (),
            pick_base=self._split_quick_target_index() if picking else None,
            merge=merging, base=self._split_base_index() if merging else None,
            merge_preview=merge_preview,
            plane_axis=self._split_plane_axis(context) if plane is not None else None)
        snap = self._split_snap
        if snap is not None and not self._split_no_plane():
            # Hover feedback for draw_split_overlay (Split CUT only).
            data['snap'] = {'kind': snap['kind'], 'face': snap['face'],
                            'edge': snap['edge'], 'vertex': snap['vertex']}
        update_split_overlay(data)
        if context.area is not None:
            context.area.tag_redraw()

    def _split_snapshot(self):
        # The uid rides along so an unchanged piece keeps it through undo /
        # redo (Space keeps a picked original whose piece uid survives).
        return (tuple((p.polys, p.color_index, p.uid) for p in self.split_pieces),
                self.split_active, self.split_kind, self.split_state, self._split_pristine)

    def _split_restore(self, context, snap):
        pieces_data, active, kind, state, pristine = snap
        self._split_end_auto()
        self._split_pristine = pristine
        self.split_kind = kind
        self.split_state = state
        self._split_fresh = set()
        self._split_preview_reset()
        pieces = []
        for polys, color, uid in pieces_data:
            piece = make_piece(polys, color, uid=uid)
            if piece is not None:
                pieces.append(piece)
        self.split_pieces = pieces
        self._split_set_active(min(active, max(0, len(pieces) - 1)))
        self._split_hover = self._split_pick(context)
        if state == 'PICK' and len(pieces) < 2:
            self.split_state = 'CUT'
        if state == 'MERGE' and len(pieces) < 2:
            self.split_state = self._split_normal_state()
            if self.split_state == 'PICK':
                self.split_state = 'CUT'
        # The MERGE base and the quick-merge target never survive undo /
        # redo; sources follow the restored state.
        self._split_merge_base = None
        self._split_quick_target = None
        self._split_merge_dirty = False
        self._split_sync_sources(context)
        self._split_update_cursor(context)

    def _split_enter(self, context, event, kind='SPLIT'):
        """Enter split mode with one piece; *kind* 'ISLANDS' then explodes it
        into islands and auto-merges them right away.

        With the ``split_autoload_existing`` preference on, the existing
        collision objects of the selection are loaded first (see
        ``_split_load_existing``); when any is loaded, Islands mode starts
        from them without exploding."""
        self._split_color_counter = 0
        piece = self._split_whole_piece(context, self._split_next_color())
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
        self._split_source_cache = None
        self._split_regions = {}
        self._split_remainder_uid = None
        self._split_snap = None
        self._split_frozen_plane = None
        self._split_pristine = True
        if self._split_timer is None:
            try:
                self._split_timer = context.window_manager.event_timer_add(
                    _TIMER_INTERVAL, window=context.window)
            except Exception as e:
                print(f"Split: could not add the preview timer: {e}")
                self._split_timer = None
        hide_hull_preview()
        clear_preview_faces()
        clear_edge_highlight()
        enable_split_overlay()
        self._split_update_cursor(context)
        loaded = 0
        if _pref_autoload():
            try:
                loaded, rejected, coll, remainder = self._split_load_existing(context)
            except Exception as e:
                print(f"Split: loading existing collisions failed: {e}")
                loaded = 0
        if loaded:
            # Continuing existing work: no explode / auto-merge in Islands.
            self._split_undo.clear()
            self.report({'INFO'}, _loaded_message(loaded, rejected, coll, remainder))
        elif kind == 'ISLANDS':
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
            self._split_pristine = False
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
            self._split_pristine = False
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
        self._split_track_mouse(context, event)

    def _split_quick_target_index(self):
        """Index of the Shift+click merge target in Split PICK, or None."""
        uid = getattr(self, '_split_quick_target', None)
        if uid is None:
            return None
        for i, piece in enumerate(self.split_pieces):
            if piece.uid == uid:
                return i
        return None

    def _split_quick_merge(self, context, from_cut):
        """Split kind, Shift+LMB / Shift+RMB: merge the piece under the mouse
        into the active one and stay in (or go to) PICK, so more pieces can
        be Shift+clicked; TAB or a plain LMB pick resumes cutting.

        From CUT (*from_cut*): the active piece is the target; the active
        piece itself or nothing under the mouse is a no-op (no cut). In PICK
        without a target yet (e.g. right after a cut) the first Shift+click
        only makes the clicked piece the target (and active)."""
        idx = self._split_pick(context)
        if idx is None:
            return
        if from_cut:
            if idx == self.split_active:
                return
            if self._split_merge(context, idx):
                self._split_set_state(context, 'PICK')
                if self._split_picking():
                    self._split_quick_target = self.split_pieces[self.split_active].uid
            return
        target = self._split_quick_target_index()
        if target is None:
            self._split_set_active(idx)
            self._split_hover = idx
            self._split_quick_target = self.split_pieces[idx].uid
            self.report({'INFO'}, "Merge target set: Shift+click pieces to merge into it")
            return
        if idx == target:
            return
        self._split_set_active(target)
        if self._split_merge(context, idx):
            self._split_quick_target = self.split_pieces[self.split_active].uid

    def _split_pick_state_click(self, context, event, merge):
        """LMB / RMB in Split mode's PICK state: a piece under the mouse
        becomes active and cutting resumes; *merge* (Shift) is the quick
        merge (see _split_quick_merge) and stays in PICK. Nothing under the
        mouse: stay."""
        if merge:
            self._split_quick_merge(context, from_cut=False)
            self._split_refresh(context)
            return
        idx = self._split_pick(context)
        if idx is None:
            self._split_refresh(context)
            return
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
        self._split_pristine = False
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

    def _split_merge(self, context, index, merged=None):
        """Merge piece *index* into the active one (undoable). *merged* is
        an already built hull of the two (the MERGE preview), else it is
        built here. Returns True when merged."""
        if index is None or index == self.split_active:
            return False
        active = self.split_pieces[self.split_active]
        other = self.split_pieces[index]
        if merged is None:
            merged = make_piece(active.polys + other.polys, active.color_index)
        if merged is None:
            self.report({'WARNING'}, "Merge failed")
            return False
        self._split_undo.push(self._split_snapshot())
        self._split_end_auto()
        self._split_pristine = False
        self.split_pieces[self.split_active] = merged
        del self.split_pieces[index]
        new_active = self.split_active - 1 if index < self.split_active else self.split_active
        self._split_set_active(new_active)
        self._split_hover = self._split_pick(context)
        self.report({'INFO'}, f"Merged: {len(self.split_pieces)} pieces")
        return True

    # ----- MERGE state -----

    def _split_toggle_merge(self, context, event):
        """M: enter / leave the MERGE state."""
        if self._split_merging():
            self._split_set_state(context, self._split_normal_state())
            if not self._split_no_plane():
                self._split_follow_mouse(context, event)
            self.report({'INFO'}, "Merge mode off")
        elif len(self.split_pieces) < 2:
            self.report({'INFO'}, "Only one piece: nothing to merge")
            return
        else:
            # A meaningful active piece becomes the base: Split CUT or
            # Islands; coming from PICK there is none yet.
            had_base = self._split_islands() or not self._split_picking()
            self._split_set_state(context, 'MERGE')
            if had_base and 0 <= self.split_active < len(self.split_pieces):
                self._split_merge_base = self.split_pieces[self.split_active].uid
            self.report({'INFO'}, "Merge mode: click a base piece, then click pieces "
                                  "to merge into it. M / TAB to leave")
        self._split_hover = self._split_pick(context)
        self._split_refresh(context)

    def _split_merge_click(self, context, set_base):
        """LMB (*set_base* False) / RMB (*set_base* True) in MERGE."""
        idx = self._split_pick(context)
        if idx is None:
            return
        base = self._split_base_index()
        if set_base or base is None:
            self._split_merge_base = self.split_pieces[idx].uid
            self._split_set_active(idx)
            self._split_hover = idx
            return
        if idx == base:
            return
        other = self.split_pieces[idx]
        merged = self._split_merge_cache.get((self.split_pieces[base].uid, other.uid))
        self._split_set_active(base)
        if self._split_merge(context, idx, merged=merged):
            # The merged piece (now active) is the new base.
            self._split_merge_base = self.split_pieces[self.split_active].uid

    def _split_merge_preview_key(self):
        """``(base uid, hovered uid)`` the preview should show, or None."""
        base = self._split_base_index()
        hover = self._split_hover
        if base is None or hover is None or hover == base \
                or not 0 <= hover < len(self.split_pieces):
            return None
        return (self.split_pieces[base].uid, self.split_pieces[hover].uid)

    def _split_update_merge_preview(self, force=False):
        """Build the merge preview of the current hover when missing; over
        the time budget (last build) only mark it dirty for the timer
        unless *force*."""
        key = self._split_merge_preview_key()
        if key is None or key in self._split_merge_cache:
            self._split_merge_dirty = False
            return
        if not force and self._split_merge_cost > _PREVIEW_BUDGET:
            self._split_merge_dirty = True
            return
        base = self.split_pieces[self._split_base_index()]
        other = self.split_pieces[self._split_hover]
        t0 = time.perf_counter()
        try:
            piece = make_piece(base.polys + other.polys, base.color_index)
        except Exception as e:
            print(f"Split: merge preview failed: {e}")
            piece = None
        self._split_merge_cost = time.perf_counter() - t0
        if len(self._split_merge_cache) >= _MERGE_CACHE_MAX:
            self._split_merge_cache.clear()
        self._split_merge_cache[key] = piece
        self._split_merge_dirty = False

    def _split_current_merge_preview(self):
        """The cached merge preview Piece for the current hover, or None."""
        key = self._split_merge_preview_key()
        if key is None:
            return None
        return self._split_merge_cache.get(key)

    def _split_delete(self, context):
        if len(self.split_pieces) <= 1:
            self.report({'WARNING'}, "Cannot delete the last piece")
            return
        self._split_undo.push(self._split_snapshot())
        self._split_end_auto()
        self._split_pristine = False
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
        self._split_pristine = False
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
                self.split_merge_gap, self.split_merge_cost, self.split_ignore_thin,
                flat=self.split_merge_flat)
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
            v = max(_GAP_MIN, v)
            if math.isfinite(v):
                self.split_merge_gap = v
            label = f"Merge gap: {_gap_label(self.split_merge_gap)}"
        else:
            v = round(self.split_merge_cost + (0.05 if up else -0.05), 2)
            self.split_merge_cost = min(_COST_RANGE[1], max(_COST_RANGE[0], v))
            label = f"Merge void: {int(round(self.split_merge_cost * 100))}%"
        self._split_param_changed(context, label)

    def _split_toggle_flat(self, context):
        """F in Islands: toggle the flat-merge rule (re-groups while live)."""
        self.split_merge_flat = not self.split_merge_flat
        self._split_param_changed(
            context, "Flat merge: " + ("ON" if self.split_merge_flat else "OFF"))

    def _split_param_changed(self, context, label):
        """Report a changed auto-merge parameter and, while the last explode
        is live, re-group it (consecutive changes share one undo entry)."""
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

    # ----- editing existing collision objects (Q, Shift+Q, autoload) -----

    def _split_unhide_picked(self, names=None):
        """Show the picked objects *names* (default: all) again and forget
        them. No context needed (runs from _split_shutdown); objects gone
        meanwhile are skipped."""
        picked = getattr(self, '_split_picked', None) or {}
        if names is None:
            names = list(picked)
            self._split_picked = {}
        else:
            for name in names:
                picked.pop(name, None)
        for name in names:
            try:
                obj = bpy.data.objects.get(name)
                if obj is not None:
                    obj.hide_set(False)
            except Exception as e:
                print(f"Split: could not show {name!r} again: {e}")

    def _split_remove_picked(self, names):
        """Delete the picked objects *names* (replaced by the created hulls,
        or removed by the user), and each one's mesh when nothing else uses
        it; forget them. Returns how many were removed."""
        for name in names:
            self._split_picked.pop(name, None)
        removed = 0
        for name in names:
            try:
                obj = bpy.data.objects.get(name)
                if obj is None:
                    continue
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                removed += 1
                if isinstance(data, bpy.types.Mesh) and data.users == 0:
                    bpy.data.meshes.remove(data)
            except Exception as e:
                print(f"Split: could not delete the picked object {name!r}: {e}")
        return removed

    def _split_scene_pick(self, context, mouse):
        """The existing collision object under *mouse*: the first mesh object
        hit that is not a source mesh, hidden here or already picked."""
        region = context.region
        rv3d = context.region_data
        if region is None or rv3d is None or mouse is None:
            return None
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse)
        if origin is None or direction is None or direction.length_squared < 1e-20:
            return None
        direction = direction.normalized()
        scene = context.scene
        view_layer = context.view_layer
        depsgraph = view_layer.depsgraph
        sources = set()
        for o in (self.original_selected_objects or ()):
            try:
                sources.add(o.as_pointer())
            except Exception:
                pass
        picked = set(self._split_picked)
        for _ in range(_PICK_MAX_STEPS):
            hit, loc, _n, _fi, hit_obj, _m = scene.ray_cast(depsgraph, origin, direction)
            if not hit or hit_obj is None:
                return None
            obj = hit_obj.original
            try:
                ok = (obj.type == 'MESH'
                      and obj.as_pointer() not in sources
                      and obj.name not in picked
                      and obj.visible_get(view_layer=view_layer, viewport=context.space_data))
            except Exception:
                ok = False
            if ok:
                return obj
            origin = loc + direction * 1e-4
        return None

    def _split_source_cached(self, context):
        """Every source polygon with its bbox, as ``(poly, lo, hi)``;
        collected once per split session."""
        if self._split_source_cache is None:
            faces = build_all_faces_dict(
                self.original_selected_objects, use_depsgraph=self.use_depsgraph, context=context)
            polys = collect_source_polys(context, faces, self.use_depsgraph)
            cache = []
            for poly in polys:
                box = hs.bbox(poly)
                if box is not None:
                    cache.append((poly, box[0], box[1]))
            self._split_source_cache = tuple(cache)
        return self._split_source_cache

    def _split_object_geometry(self, context, obj):
        """``(points, polys)`` of *obj* in world space (evaluated when the
        host uses the depsgraph)."""
        mesh, matrix_world = get_evaluated_mesh(
            obj, use_depsgraph=self.use_depsgraph, context=context)
        points = [tuple(matrix_world @ v.co) for v in mesh.vertices]
        polys = []
        for poly in mesh.polygons:
            verts = poly.vertices
            if len(verts) >= 3:
                polys.append(tuple(points[i] for i in verts))
        return points, tuple(polys)

    def _split_object_region(self, context, obj):
        """``(points, own_polys, region)`` of *obj* in world space. *region*
        is its convex hull as a dict ``planes`` (outward, pushed OUT by
        ``tol``), ``tol``, ``eps``, ``lo`` / ``hi`` (bbox grown by tol), or
        None when the object has no solid hull."""
        points, own_polys = self._split_object_geometry(context, obj)
        box = hs.bbox(points)
        if box is None:
            return points, own_polys, None
        ext = hs.extent((points,))
        tol = max(1e-4 * ext, 1e-9)
        planes = hull_planes(points, tol)
        if not planes:
            return points, own_polys, None
        region = {
            'planes': planes,
            'tol': tol,
            'eps': max(1e-6 * ext, 1e-9),
            'lo': tuple(c - tol for c in box[0]),
            'hi': tuple(c + tol for c in box[1]),
        }
        return points, own_polys, region

    def _split_inside_polys(self, context, region):
        """The source polygons clipped to *region* (bbox-prefiltered)."""
        lo, hi = region['lo'], region['hi']
        candidates = [poly for poly, plo, phi in self._split_source_cached(context)
                      if all(plo[k] <= hi[k] and phi[k] >= lo[k] for k in range(3))]
        return hs.clip_to_convex(candidates, region['planes'], region['eps'])

    def _split_piece_from_object(self, context, obj):
        """Q: ``(piece, region)``: a Piece of the source geometry inside
        *obj*'s convex hull, else of *obj*'s own polygons; piece None when
        neither encloses a volume."""
        _points, own_polys, region = self._split_object_region(context, obj)
        color = self._split_color_counter
        piece = None
        if region is not None:
            clipped = self._split_inside_polys(context, region)
            if clipped:
                piece = make_piece(clipped, color)
        if piece is None and own_polys:
            piece = make_piece(own_polys, color)
        return piece, region

    def _split_owned_piece(self, context, obj):
        """Loader: ``(piece, region)`` when *obj* belongs to the selection —
        the source geometry clipped inside it is solid and its hull volume is
        at least ``_OWNED_MIN_RATIO`` of *obj*'s own hull volume — else
        ``(None, None)``. No fallback to the object's own polygons."""
        points, _own_polys, region = self._split_object_region(context, obj)
        if region is None:
            return None, None
        clipped = self._split_inside_polys(context, region)
        if not clipped:
            return None, None
        piece = make_piece(clipped, self._split_color_counter)
        if piece is None:
            return None, None
        own_volume = hull_volume(points)
        if not own_volume > 0.0 or piece.volume < _OWNED_MIN_RATIO * own_volume:
            return None, None
        return piece, region

    def _split_remainder_piece(self, context):
        """The source geometry OUTSIDE every picked object's convex region,
        as a new Piece, or None when it is not solid or under
        ``_REMAINDER_MIN_RATIO`` of the whole-selection hull volume (the
        selection counts as covered). Uses the same outward-pushed planes as
        the inside clip, so inside and remainder split the source along one
        surface."""
        regions = [r for r in self._split_regions.values() if r is not None]
        if not regions:
            return None
        polys = [poly for poly, _lo, _hi in self._split_source_cached(context)]
        if not polys:
            return None
        whole_volume = hull_volume(hs.unique_points(polys))
        for region in regions:
            lo, hi = region['lo'], region['hi']
            out = []
            for poly in polys:
                box = hs.bbox(poly)
                if box is not None and all(box[0][k] <= hi[k] and box[1][k] >= lo[k]
                                           for k in range(3)):
                    out.extend(hs.clip_outside_convex((poly,), region['planes'], region['eps']))
                else:
                    out.append(poly)
            polys = out
            if not polys:
                return None
        piece = make_piece(polys, self._split_color_counter)
        if piece is None:
            return None
        if not whole_volume > 0.0 or piece.volume < _REMAINDER_MIN_RATIO * whole_volume:
            return None
        self._split_next_color()
        return piece

    def _split_edit_existing(self, context, event):
        """Q: turn the existing collision object under the mouse into a piece
        (see the module docstring). Not undoable: clears the mode's undo."""
        self._split_mouse = (event.mouse_region_x, event.mouse_region_y)
        try:
            obj = self._split_scene_pick(context, self._split_mouse)
        except Exception as e:
            print(f"Split: collision pick failed: {e}")
            obj = None
        if obj is None:
            self.report({'WARNING'}, "No collision object under the cursor")
            return
        name = obj.name
        try:
            piece, region = self._split_piece_from_object(context, obj)
        except Exception as e:
            print(f"Split: could not build a piece from {name!r}: {e}")
            piece, region = None, None
        if piece is None:
            self.report({'WARNING'}, f"Cannot edit {name}: it has no volume")
            return
        self._split_next_color()
        self._split_adopt(context, [(obj, piece, region)])
        if not self._split_islands():
            self._split_set_state(context, 'CUT')
            self._split_follow_mouse(context, event)
        self.report({'INFO'}, f"Editing {name}: {len(self.split_pieces)} pieces")

    def _split_adopt(self, context, entries):
        """Add the pieces of picked existing objects: *entries* is a list of
        ``(obj, piece, region)``. Not undoable (clears the mode's undo
        stack). The untouched initial piece is replaced, otherwise they are
        appended; the first one becomes active. Each object is hidden and
        recorded (with its region, for the uncovered remainder)."""
        if not entries:
            return
        self._split_end_auto()
        self._split_undo.clear()
        new_pieces = [piece for _obj, piece, _region in entries]
        if self._split_pristine and len(self.split_pieces) == 1:
            first = 0
            self.split_pieces = list(new_pieces)
        else:
            first = len(self.split_pieces)
            self.split_pieces.extend(new_pieces)
        self._split_pristine = False
        self._split_fresh = set()
        self._split_set_active(first)
        for obj, piece, region in entries:
            name = obj.name
            try:
                obj.hide_set(True)
            except Exception as e:
                print(f"Split: could not hide {name!r}: {e}")
            self._split_picked[name] = piece.uid
            self._split_regions[name] = region
        self._split_after_change(context)

    def _split_existing_candidates(self, context):
        """``(objects, collection)``: the mesh objects of the collision
        collection (see ``_collision_collection``) that belong to the
        selection: not a source, not picked yet, visible here, with
        polygons, and with a world bbox touching the source bbox expanded by
        ``_LOAD_BBOX_MARGIN`` of its diagonal."""
        coll = _collision_collection(context)
        if coll is None:
            return [], None
        sources = list(self.original_selected_objects or ())
        source_keys = set()
        corners = []
        for o in sources:
            try:
                source_keys.add(o.as_pointer())
            except Exception:
                continue
            box = _world_bbox(o)
            if box is not None:
                corners.extend(box)
        src_box = hs.bbox(corners)
        if src_box is None:
            return [], coll
        lo, hi = src_box
        margin = _LOAD_BBOX_MARGIN * hs.extent(((lo, hi),))
        src_box = (tuple(c - margin for c in lo), tuple(c + margin for c in hi))
        view_layer = context.view_layer
        out = []
        for obj in coll.objects:
            try:
                if (obj.type != 'MESH' or obj.as_pointer() in source_keys
                        or obj.name in self._split_picked
                        or len(obj.data.polygons) == 0
                        or not obj.visible_get(view_layer=view_layer,
                                               viewport=context.space_data)):
                    continue
            except Exception:
                continue
            box = _world_bbox(obj)
            if box is not None and hs.bbox_gap(box, src_box) == 0.0:
                out.append(obj)
        return out, coll

    def _split_load_existing(self, context):
        """Turn every existing collision object of the selection (see
        ``_split_existing_candidates``) into a piece, like Q does for one.
        Only candidates that own enough of the selection's geometry are
        loaded (``_split_owned_piece``); the others are left alone (not
        hidden, not listed). After at least one load, the source geometry
        outside every picked region is added as an uncovered-remainder piece
        (replacing an untouched remainder of an earlier load). One
        undo-stack clear for the batch. Returns ``(loaded, rejected,
        collection, remainder_added)``."""
        objs, coll = self._split_existing_candidates(context)
        entries = []
        rejected = 0
        for obj in objs:
            try:
                piece, region = self._split_owned_piece(context, obj)
            except Exception as e:
                print(f"Split: could not build a piece from {obj.name!r}: {e}")
                piece, region = None, None
            if piece is None:
                rejected += 1
                continue
            self._split_next_color()
            entries.append((obj, piece, region))
        if not entries:
            return 0, rejected, coll, False
        # An untouched remainder of an earlier load is derived data: drop it,
        # a new one is computed against every picked region below.
        old = self._split_remainder_uid
        self._split_remainder_uid = None
        if old is not None:
            self.split_pieces = [p for p in self.split_pieces if p.uid != old]
            self.split_active = min(self.split_active, max(0, len(self.split_pieces) - 1))
        self._split_adopt(context, entries)
        try:
            remainder = self._split_remainder_piece(context)
        except Exception as e:
            print(f"Split: could not build the uncovered remainder: {e}")
            remainder = None
        if remainder is not None:
            self.split_pieces.append(remainder)
            self._split_remainder_uid = remainder.uid
        if not self._split_islands():
            if remainder is not None:
                # Most likely next step: work on what is not covered yet.
                self._split_set_active(len(self.split_pieces) - 1)
                self._split_set_state(context, 'CUT')
            elif len(entries) >= 2:
                self._split_set_state(context, 'PICK')
                self._split_fresh = {piece.uid for _obj, piece, _r in entries}
            else:
                self._split_set_state(context, 'CUT')
        self._split_after_change(context)
        return len(entries), rejected, coll, remainder is not None

    def _split_load_existing_key(self, context):
        """Shift+Q: load the existing collisions of the selection now."""
        try:
            loaded, rejected, coll, remainder = self._split_load_existing(context)
        except Exception as e:
            print(f"Split: loading existing collisions failed: {e}")
            self.report({'WARNING'}, "Could not load the existing collisions")
            return
        where = coll.name if coll is not None else "the collision collection"
        if loaded:
            self.report({'INFO'}, _loaded_message(loaded, rejected, coll, remainder))
        elif rejected:
            self.report({'WARNING'}, f"No existing collisions belong to the selection in "
                                     f"{where} ({rejected} others ignored)")
        else:
            self.report({'WARNING'}, f"No existing collisions for the selection in {where}")

    def _split_whole_piece(self, context, color):
        """The hull piece of the whole selection (the marked faces, else
        every polygon of the source objects), or None."""
        if self.marked_faces:
            faces = self.marked_faces
        else:
            faces = build_all_faces_dict(
                self.original_selected_objects, use_depsgraph=self.use_depsgraph, context=context)
        polys = collect_source_polys(context, faces, self.use_depsgraph)
        return make_piece(polys, color) if polys else None

    def _split_add_whole(self, context):
        """W: append the hull of the whole selection as a new active piece
        (undoable)."""
        try:
            piece = self._split_whole_piece(context, self._split_color_counter)
        except Exception as e:
            print(f"Split: could not build the whole-selection hull: {e}")
            piece = None
        if piece is None:
            self.report({'WARNING'}, "Split: the source geometry does not enclose a volume")
            return
        self._split_next_color()
        self._split_undo.push(self._split_snapshot())
        self._split_end_auto()
        self._split_pristine = False
        self.split_pieces.append(piece)
        self._split_set_active(len(self.split_pieces) - 1)
        self._split_after_change(context)
        if not self._split_islands():
            self._split_set_state(context, 'CUT')
        self.report({'INFO'}, f"Added hull of the whole selection: {len(self.split_pieces)} pieces")

    def _split_create(self, context):
        """Space: one hull object per changed piece. A picked original whose
        piece is still in the list unchanged is kept (shown again, no hull);
        the other picked originals are replaced (deleted)."""
        from .interactive_hull import _build_hull_object_from_vertices, report_auto_fix
        piece_uids = {p.uid for p in self.split_pieces}
        kept, replaced_names = [], []
        for name, uid in self._split_picked.items():
            (kept if uid in piece_uids else replaced_names).append(name)
        kept_uids = {self._split_picked[name] for name in kept}
        # An untouched uncovered remainder is "not covered yet", not a
        # collision the user asked for: no hull for it.
        remainder_skipped = (self._split_remainder_uid is not None
                             and self._split_remainder_uid in piece_uids)
        if remainder_skipped:
            kept_uids.add(self._split_remainder_uid)
        to_create = [p for p in self.split_pieces if p.uid not in kept_uids]
        if not to_create and not replaced_names:
            self._split_exit(context, message="Nothing changed")
            return
        base_name = context.scene.cursor_bbox_name_hull or "Convex"
        created, failed = 0, 0
        for piece in to_create:
            verts = [Vector(p) for p in hs.unique_points(piece.polys)]
            if _build_hull_object_from_vertices(context, verts, base_name):
                created += 1
            else:
                failed += 1
        replaced = 0
        if replaced_names:
            if created or not to_create:
                replaced = self._split_remove_picked(replaced_names)
            else:
                # Every hull failed: keep the originals rather than lose them.
                self._split_unhide_picked(replaced_names)
        self._split_unhide_picked(kept)
        if kept or replaced_names:
            msg = f"Created {created} hulls, replaced {replaced}, kept {len(kept)} unchanged"
        else:
            msg = f"Created {created} hulls"
        if remainder_skipped:
            msg += "; untouched remainder skipped"
        if failed:
            self.report({'WARNING'}, f"{msg}, {failed} failed")
        else:
            self.report({'INFO'}, msg)
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
            if self._split_merging():
                if self._split_merge_dirty:
                    self._split_update_merge_preview(force=True)
                    self._split_refresh(context)
            elif not islands and not self._split_picking() and self._split_preview_dirty:
                self._split_update_preview(context, force=True)
                self._split_refresh(context)
            return False

        if etype in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            if etype == 'MOUSEMOVE':
                self._split_mouse = (event.mouse_region_x, event.mouse_region_y)
                hover = self._split_pick(context)
                hover_changed = hover != self._split_hover
                self._split_hover = hover
                if self._split_no_plane():
                    # No cutting plane (Islands, Split PICK, MERGE): the 3D
                    # cursor stays, only the hover highlight (and the merge
                    # preview) follows the mouse.
                    if hover_changed:
                        self._split_refresh(context)
                elif not self.split_frozen:
                    self._split_track_mouse(context, event)
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
                if not self._split_no_plane() and self.split_pieces:
                    ext = self.split_pieces[self.split_active].extent
                    step = ext * (0.002 if event.shift else 0.02)
                    self.split_offset += step if etype == 'WHEELUPMOUSE' else -step
                    self._split_refresh(context)
                return True
            return False

        if etype == 'LEFTMOUSE':
            if press and self._split_merging():
                self._split_mouse = (event.mouse_region_x, event.mouse_region_y)
                if not event.ctrl:
                    self._split_merge_click(context, set_base=False)
                self._split_refresh(context)
            elif press and islands:
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
                elif event.shift:
                    # Quick merge into the active piece, then pick (no cut).
                    self._split_quick_merge(context, from_cut=True)
                else:
                    self._split_cut_or_pick(context)
                self._split_refresh(context)
            return True

        if not press:
            # Releases of keys we own are swallowed; others (HUD etc.) fall through.
            return etype in ({'RIGHTMOUSE', 'ESC', 'K', 'R', 'F', 'X', 'Z', 'L', 'TAB', 'Q', 'W',
                              'M'}
                             | _CONFIRM_KEYS | _BLOCKED_KEYS | set(_SLAB_KEYS))

        if etype == 'M':
            if not event.ctrl and not event.alt and not event.shift:
                self._split_mouse = (event.mouse_region_x, event.mouse_region_y)
                self._split_toggle_merge(context, event)
            return True

        if etype == 'Q':
            # Q: edit the existing collision under the mouse; Shift+Q: load
            # every existing collision of the selection. Never the host's
            # object pick.
            if not event.ctrl and not event.alt:
                self._split_mouse = (event.mouse_region_x, event.mouse_region_y)
                if event.shift:
                    self._split_load_existing_key(context)
                else:
                    self._split_edit_existing(context, event)
                self._split_refresh(context)
            return True

        if etype == 'W':
            if not event.ctrl and not event.alt and not event.shift:
                self._split_add_whole(context)
                self._split_refresh(context)
            return True

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
            if self._split_merging():
                self._split_toggle_merge(context, event)
                return True
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
            if self._split_merging():
                self._split_merge_click(context, set_base=True)
                self._split_refresh(context)
            elif self._split_picking():
                self._split_pick_state_click(context, event, merge=event.shift)
            elif event.shift and not islands:
                # Split CUT: quick merge into the active piece, then pick.
                self._split_quick_merge(context, from_cut=True)
                self._split_refresh(context)
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

        if etype == 'F' and islands and not self._split_merging():
            if not event.ctrl and not event.alt and not event.shift:
                self._split_toggle_flat(context)
                self._split_refresh(context)
            return True

        if (islands or self._split_merging()) and (etype in {'R', 'F'} or etype in _SLAB_KEYS):
            # Cutting tools: Split mode's CUT / PICK only.
            return True

        if etype == 'X' and self._split_merging():
            base = self._split_base_index()
            if base is None:
                self.report({'INFO'}, "Pick a merge base first (LMB)")
                return True
            self._split_set_active(base)
            self._split_merge_base = None
            self._split_delete(context)
            self._split_refresh(context)
            return True

        if etype == 'R':
            self.split_axis = (self.split_axis + 1) % 3
            snap = self._split_snap
            if self.split_frozen and (snap is None or snap.get('normal') is None):
                # The cursor has not moved since freezing: R still turns the
                # frozen face / vertex plane (an edge plane ignores R).
                self._split_frozen_plane = self._split_base_plane(context)
            self.report({'INFO'}, f"Split plane: {_AXIS_NAMES[self.split_axis]}")
            self._split_refresh(context)
            return True

        if etype == 'F':
            self.split_frozen = not self.split_frozen
            self._split_frozen_plane = (
                self._split_base_plane(context) if self.split_frozen else None)
            self._split_frozen_axis = (
                self._split_live_plane_axis(context) if self.split_frozen else None)
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
