"""Blender glue for circle-brush face marking.

``BrushFaceCache`` holds world-space face centers/normals and a world-space
``BVHTree`` per object for the duration of one modal session (built lazily,
invalidated on demand). ``pick_brush_faces`` returns the face indices of
*obj* that are under the brush: the face directly under the cursor plus
every face whose center falls inside the circle, faces the viewer, and is
not occluded by the brush target objects themselves.

Occlusion has two layers:

* the brush targets are tested against their cached BVH trees. The BVH is
  built from the very same mesh the face indices come from (raw or
  depsgraph-evaluated), so a hit index is comparable to a cached index even
  when modifiers change the polygon count (``scene.ray_cast`` always hits
  the evaluated mesh and its indices are useless for a raw-mesh cache);
* the rest of the scene is tested with ``scene.ray_cast``, skipping objects
  that are not visible in the current viewport (hidden, or outside the
  active local view) or are drawn as Wire/Bounds. A collision hull created
  earlier in the same modal session is linked without local-view bits, so
  in isolation mode it never blocks the brush.
"""
from __future__ import annotations

import bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils

from . import brush_select as bs
from .utils import get_evaluated_mesh


class BrushFaceCache:
    """Per-object world-space face centers and normals."""

    def __init__(self, use_depsgraph: bool = False):
        self.use_depsgraph = use_depsgraph
        self._data: dict = {}
        # obj pointer -> bool: may this non-target object block the brush?
        self.scene_filter: dict = {}

    def clear(self):
        self._data.clear()
        self.scene_filter.clear()

    def reset_scene_filter(self):
        """Forget visibility decisions (call at the start of each stroke)."""
        self.scene_filter = {}

    def get(self, obj, context=None):
        key = obj.as_pointer()
        entry = self._data.get(key)
        if entry is not None and entry["matrix"] == obj.matrix_world:
            return entry
        mesh, matrix = get_evaluated_mesh(obj, self.use_depsgraph, context)
        n = len(mesh.polygons)
        centers = np.empty(n * 3, dtype=np.float32)
        normals = np.empty(n * 3, dtype=np.float32)
        if n:
            mesh.polygons.foreach_get("center", centers)
            mesh.polygons.foreach_get("normal", normals)
        centers = centers.reshape(n, 3).astype(np.float64)
        normals = normals.reshape(n, 3).astype(np.float64)
        m = np.array(matrix, dtype=np.float64)
        rot = m[:3, :3]
        centers_w = centers @ rot.T + m[:3, 3]
        # Normals transform with the inverse-transpose; renormalize.
        try:
            nrm_m = np.linalg.inv(rot).T
        except np.linalg.LinAlgError:
            nrm_m = rot
        normals_w = normals @ nrm_m.T
        lengths = np.linalg.norm(normals_w, axis=1)
        lengths[lengths == 0.0] = 1.0
        normals_w /= lengths[:, None]
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.transform(matrix)
        bvh = BVHTree.FromBMesh(bm, epsilon=0.0)
        bm.free()
        entry = {
            "matrix": matrix.copy(),
            "centers": centers_w,
            "normals": normals_w,
            "bvh": bvh,
        }
        self._data[key] = entry
        return entry


def _candidates(entry, region, rv3d, mouse, radius, facing=True):
    """Indices of faces under the circle (and facing the viewer when *facing*)."""
    centers = entry["centers"]
    normals = entry["normals"]
    if len(centers) == 0:
        return []
    persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
    hom = np.concatenate([centers, np.ones((len(centers), 1))], axis=1)
    clip = hom @ persp.T
    w = clip[:, 3]
    valid = w > 0.0
    safe_w = np.where(valid, w, 1.0)
    sx = region.width * 0.5 * (1.0 + clip[:, 0] / safe_w)
    sy = region.height * 0.5 * (1.0 + clip[:, 1] / safe_w)
    d2 = (sx - mouse[0]) ** 2 + (sy - mouse[1]) ** 2
    inside = valid & (d2 <= radius * radius)
    if not inside.any():
        return []
    if not facing:
        return np.nonzero(inside)[0].tolist()
    if rv3d.is_perspective:
        eye = np.array(rv3d.view_matrix.inverted().translation, dtype=np.float64)
        to_eye = eye - centers
        facing = np.einsum("ij,ij->i", normals, to_eye) > 1e-6
    else:
        view_dir = np.array(rv3d.view_rotation @ Vector((0.0, 0.0, -1.0)), dtype=np.float64)
        facing = -(normals @ view_dir) > 1e-6
    return np.nonzero(inside & facing)[0].tolist()


def _nearest_hit(occluders, cache: BrushFaceCache, context, origin, direction):
    """Closest hit among *occluders* for a world-space ray.

    Returns ``(distance, obj, face_index)`` or ``None``. Uses the cached
    world-space BVH of each occluder, so face indices match the cache.
    """
    best = None
    for o in occluders:
        if o.type != 'MESH':
            continue
        entry = cache.get(o, context)
        loc, _nrm, face_index, dist = entry["bvh"].ray_cast(origin, direction)
        if loc is None:
            continue
        if best is None or dist < best[0]:
            best = (dist, o, face_index)
    return best


_SOLID_DISPLAY = {'SOLID', 'TEXTURED'}
_MAX_SKIPS = 8


def _scene_filter(cache: BrushFaceCache):
    # Tolerate a cache instance created by a stale (pre-reload) class.
    scene_filter = getattr(cache, "scene_filter", None)
    if scene_filter is None:
        scene_filter = cache.scene_filter = {}
    return scene_filter


def _is_viewport_occluder(cache: BrushFaceCache, context, orig):
    """May *orig* (an original object) block the brush in this viewport?"""
    scene_filter = _scene_filter(cache)
    key = orig.as_pointer()
    allowed = scene_filter.get(key)
    if allowed is None:
        try:
            allowed = (orig.type == 'MESH'
                       and orig.display_type in _SOLID_DISPLAY
                       and orig.visible_get(view_layer=context.view_layer,
                                            viewport=context.space_data))
        except Exception:
            allowed = False
        scene_filter[key] = allowed
    return allowed


def pick_scene_object(context, cache: BrushFaceCache, mouse):
    """Original mesh object under the cursor, honoring viewport visibility.

    Skips objects hidden in this viewport (or outside the active local
    view) and Wire/Bounds-drawn objects, the same rule the brush uses for
    occlusion. Returns ``None`` when nothing eligible is hit.
    """
    region = context.region
    rv3d = context.region_data
    if region is None or rv3d is None:
        return None
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse)
    if origin is None or direction is None:
        return None
    direction = direction.normalized()
    scene = context.scene
    depsgraph = context.view_layer.depsgraph
    for _ in range(_MAX_SKIPS):
        hit, loc, _n, _fi, hit_obj, _m = scene.ray_cast(depsgraph, origin, direction)
        if not hit or hit_obj is None:
            return None
        orig = hit_obj.original
        if _is_viewport_occluder(cache, context, orig):
            return orig
        origin = loc + direction * 1e-4
    return None


def _scene_blocks(cache: BrushFaceCache, context, targets, origin, direction, max_dist):
    """True when a visible non-target scene object is hit before *max_dist*.

    Objects hidden in this viewport (including everything outside the active
    local view) and objects drawn as Wire/Bounds are skipped: the ray is
    re-cast from just past them, at most ``_MAX_SKIPS`` times.
    """
    scene = context.scene
    depsgraph = context.view_layer.depsgraph
    target_keys = {o.as_pointer() for o in targets}
    remaining = max_dist
    for _ in range(_MAX_SKIPS):
        if remaining <= 0.0:
            return False
        hit, loc, _n, _fi, hit_obj, _m = scene.ray_cast(
            depsgraph, origin, direction, distance=remaining)
        if not hit or hit_obj is None:
            return False
        orig = hit_obj.original
        # Targets are handled by the BVH layer; look past them.
        if (orig.as_pointer() not in target_keys
                and _is_viewport_occluder(cache, context, orig)):
            return True
        step = (loc - origin).length + 1e-4
        origin = origin + direction * step
        remaining -= step
    return False


def _cursor_face(context, obj, cache, occluders, region, rv3d, mouse):
    """Index of the *obj* face directly under the cursor, or ``None``."""
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse)
    if origin is None or direction is None:
        return None
    direction = direction.normalized()
    best = _nearest_hit(occluders, cache, context, origin, direction)
    if best is None or best[1] != obj:
        return None
    if _scene_blocks(cache, context, occluders, origin, direction, best[0]):
        return None
    return best[2]


def pick_brush_faces(context, obj, cache: BrushFaceCache, mouse, radius,
                     occlusion: bool = True, occluders=None):
    """Face indices of *obj* under the brush circle that are visible.

    With ``occlusion=False`` ("through" brush) every face whose center is
    under the circle is returned, back faces and hidden faces included.

    The face directly under the cursor is always included (when it belongs
    to *obj* and is the nearest hit among *occluders*), so large faces mark
    without having to sweep over their centers.

    *occluders* are the only objects that may hide faces of *obj*; defaults
    to ``[obj]``. Pass all brush targets so they shadow each other without
    letting unrelated scene objects interfere.
    """
    region = context.region
    rv3d = context.region_data
    if region is None or rv3d is None:
        return []
    if occluders is None:
        occluders = [obj]
    entry = cache.get(obj, context)
    idx = _candidates(entry, region, rv3d, mouse, radius, facing=occlusion)
    under_cursor = _cursor_face(context, obj, cache, occluders, region, rv3d, mouse)

    if not occlusion:
        visible = list(idx)
    else:
        centers = entry["centers"]
        visible = []
        is_persp = rv3d.is_perspective
        if is_persp:
            eye = rv3d.view_matrix.inverted().translation
        else:
            # Push the ray origin far back along the view direction for ortho.
            view_dir = rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))
            back = max(1000.0, rv3d.view_distance * 100.0)

        for i in idx:
            target = Vector(centers[i])
            if is_persp:
                origin = eye
                direction = target - origin
            else:
                direction = view_dir
                origin = target - view_dir * back
            dist = (target - origin).length
            if dist <= 0.0:
                continue
            direction = direction.normalized()
            limit = dist * 1.001 + 1e-4
            if _scene_blocks(cache, context, occluders, origin, direction, limit):
                continue
            best = _nearest_hit(occluders, cache, context, origin, direction)
            if best is None or best[0] > limit:
                # Nothing in the way up to the target: treat as visible.
                visible.append(i)
                continue
            hit_dist, hit_obj, face_index = best
            same_obj = hit_obj == obj
            if same_obj and face_index == i:
                visible.append(i)
                continue
            # Numerical miss across an edge still counts if the hit is at the
            # target depth.
            if same_obj and abs(hit_dist - dist) <= 1e-4 * max(1.0, dist):
                visible.append(i)

    if under_cursor is not None and under_cursor not in visible:
        visible.append(under_cursor)
    return visible


def region_mouse(event):
    return (event.mouse_region_x, event.mouse_region_y)


def exceeds_drag_threshold(start, current):
    return bs.exceeds_drag_threshold(start, current)


def step_radius(radius, grow):
    return bs.step_radius(radius, grow=grow)
