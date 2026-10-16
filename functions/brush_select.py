"""Pure helpers for circle-brush face marking (no bpy dependency).

The Blender-side glue in ``functions/brush.py`` builds per-object arrays of
world-space face centers and normals, projects them through the viewport
matrix with :func:`project_points`, keeps the ones under the brush circle
(:func:`indices_in_circle`) that face the viewer (:func:`front_facing`), and
then ray-casts the survivors for occlusion. Stroke bookkeeping
(:func:`apply_stroke`) guarantees a face is only ever added, or only ever
removed, within a single LMB drag.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]

DEFAULT_RADIUS = 50
MIN_RADIUS = 5
MAX_RADIUS = 1000
RADIUS_FACTOR = 1.25
DRAG_THRESHOLD_PX = 4


def project_points(points: Iterable[Sequence[float]], perspective_matrix,
                   region_width: float, region_height: float) -> list[Vec2 | None]:
    """Project world-space points to region pixel coords.

    ``perspective_matrix`` is ``RegionView3D.perspective_matrix`` (or any
    4x4 indexable as ``m[row][col]``). Points with ``w <= 0`` (behind the
    viewer) map to ``None``.
    """
    m = perspective_matrix
    m0, m1, m3 = m[0], m[1], m[3]
    half_w = region_width * 0.5
    half_h = region_height * 0.5
    out: list[Vec2 | None] = []
    for p in points:
        x, y, z = p[0], p[1], p[2]
        w = m3[0] * x + m3[1] * y + m3[2] * z + m3[3]
        if w <= 0.0:
            out.append(None)
            continue
        cx = m0[0] * x + m0[1] * y + m0[2] * z + m0[3]
        cy = m1[0] * x + m1[1] * y + m1[2] * z + m1[3]
        out.append((half_w + half_w * (cx / w), half_h + half_h * (cy / w)))
    return out


def indices_in_circle(points_2d: Sequence[Vec2 | None], center: Vec2,
                      radius: float) -> list[int]:
    """Indices of points inside (or on) the circle. ``None`` entries skipped."""
    cx, cy = center
    r2 = radius * radius
    return [
        i for i, p in enumerate(points_2d)
        if p is not None and (p[0] - cx) ** 2 + (p[1] - cy) ** 2 <= r2
    ]


def front_facing(centers: Sequence[Vec3], normals: Sequence[Vec3], *,
                 eye: Vec3 | None = None, view_dir: Vec3 | None = None,
                 epsilon: float = 1e-6) -> list[bool]:
    """Whether each face's normal points toward the viewer.

    Pass ``eye`` for perspective views (direction is center -> eye) or
    ``view_dir`` for orthographic views (the viewing direction, i.e. from
    the viewer into the scene). Grazing faces (dot ~ 0) count as back faces.
    """
    if (eye is None) == (view_dir is None):
        raise ValueError("pass exactly one of eye / view_dir")
    result = []
    if eye is not None:
        ex, ey, ez = eye
        for c, n in zip(centers, normals):
            dx, dy, dz = ex - c[0], ey - c[1], ez - c[2]
            result.append(n[0] * dx + n[1] * dy + n[2] * dz > epsilon)
    else:
        vx, vy, vz = view_dir
        for n in normals:
            result.append(-(n[0] * vx + n[1] * vy + n[2] * vz) > epsilon)
    return result


def apply_stroke(marked: set, touched: set, faces: Iterable[int], *,
                 remove: bool) -> bool:
    """Add (or remove) ``faces`` to ``marked`` for an in-progress stroke.

    ``touched`` accumulates every face the stroke has already handled so the
    same face is never toggled twice in one drag. Returns True when
    ``marked`` actually changed.
    """
    new = [f for f in faces if f not in touched]
    if not new:
        return False
    touched.update(new)
    changed = False
    if remove:
        for f in new:
            if f in marked:
                marked.discard(f)
                changed = True
    else:
        for f in new:
            if f not in marked:
                marked.add(f)
                changed = True
    return changed


def exceeds_drag_threshold(start: Vec2, current: Vec2,
                           threshold: float = DRAG_THRESHOLD_PX) -> bool:
    dx = current[0] - start[0]
    dy = current[1] - start[1]
    return dx * dx + dy * dy >= threshold * threshold


def step_radius(radius: float, *, grow: bool, minimum: float = MIN_RADIUS,
                maximum: float = MAX_RADIUS, factor: float = RADIUS_FACTOR) -> int:
    """Multiply/divide the brush radius by ``factor``, clamped and rounded."""
    new = radius * factor if grow else radius / factor
    new = int(round(new))
    if new == int(round(radius)):
        new += 1 if grow else -1
    return max(int(minimum), min(int(maximum), new))


def circle_points(center: Vec2, radius: float, segments: int = 64) -> list[Vec2]:
    """Closed polyline (first point repeated) approximating a circle."""
    cx, cy = center
    pts = [
        (cx + radius * math.cos(2.0 * math.pi * i / segments),
         cy + radius * math.sin(2.0 * math.pi * i / segments))
        for i in range(segments)
    ]
    pts.append(pts[0])
    return pts
