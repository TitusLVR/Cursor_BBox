"""Blender glue for circle-brush face marking.

``BrushFaceCache`` holds world-space face centers/normals per object for the
duration of one modal session (built lazily, invalidated on demand).
``pick_brush_faces`` returns the face indices of *obj* whose centers fall
under the brush circle, face the viewer, and are not occluded by other
geometry (checked with ``scene.ray_cast`` toward each face center).
"""
from __future__ import annotations

import numpy as np
from mathutils import Vector
from bpy_extras import view3d_utils

from . import brush_select as bs
from .utils import get_evaluated_mesh


class BrushFaceCache:
    """Per-object world-space face centers and normals."""

    def __init__(self, use_depsgraph: bool = False):
        self.use_depsgraph = use_depsgraph
        self._data: dict = {}

    def clear(self):
        self._data.clear()

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
        entry = {
            "matrix": matrix.copy(),
            "centers": centers_w,
            "normals": normals_w,
        }
        self._data[key] = entry
        return entry


def _candidates(entry, region, rv3d, mouse, radius):
    """Indices of faces under the circle and facing the viewer (no occlusion)."""
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
    if rv3d.is_perspective:
        eye = np.array(rv3d.view_matrix.inverted().translation, dtype=np.float64)
        to_eye = eye - centers
        facing = np.einsum("ij,ij->i", normals, to_eye) > 1e-6
    else:
        view_dir = np.array(rv3d.view_rotation @ Vector((0.0, 0.0, -1.0)), dtype=np.float64)
        facing = -(normals @ view_dir) > 1e-6
    return np.nonzero(inside & facing)[0].tolist()


def pick_brush_faces(context, obj, cache: BrushFaceCache, mouse, radius,
                     occlusion: bool = True):
    """Face indices of *obj* under the brush circle that are visible."""
    region = context.region
    rv3d = context.region_data
    if region is None or rv3d is None:
        return []
    entry = cache.get(obj, context)
    idx = _candidates(entry, region, rv3d, mouse, radius)
    if not idx or not occlusion:
        return idx

    scene = context.scene
    depsgraph = context.view_layer.depsgraph
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
        hit, loc, _nrm, face_index, hit_obj, _m = scene.ray_cast(
            depsgraph, origin, direction, distance=dist * 1.001 + 1e-4)
        if not hit:
            # Nothing in the way at all (e.g. object hidden from ray_cast):
            # treat as visible rather than dropping the face.
            visible.append(i)
            continue
        same_obj = hit_obj is not None and hit_obj.original == obj
        if same_obj and face_index == i:
            visible.append(i)
            continue
        # Numerical miss across an edge still counts if the hit is at the
        # target depth.
        if same_obj and abs((loc - origin).length - dist) <= 1e-4 * max(1.0, dist):
            visible.append(i)
    return visible


def region_mouse(event):
    return (event.mouse_region_x, event.mouse_region_y)


def exceeds_drag_threshold(start, current):
    return bs.exceeds_drag_threshold(start, current)


def step_radius(radius, grow):
    return bs.step_radius(radius, grow=grow)
