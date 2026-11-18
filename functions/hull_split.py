"""Pure plane-splitting helpers for the Hull modal's split mode (no bpy dependency).

Split mode is manual convex decomposition: the source geometry of a piece is
kept as world-space polygons, a plane cuts the polygons of the active piece in
two, and each side's convex hull is rebuilt from the polygons on that side.

Polygons (not just vertices) are kept because a cut creates new points on the
cut line inside faces; a second cut must be able to produce the corner where
both cut lines meet, which only works when the first cut's clipped polygons
are clipped again.

A polygon is a tuple of ``(x, y, z)`` tuples; a piece's geometry is a tuple of
polygons. Everything is immutable so undo snapshots can share it.
"""
from __future__ import annotations

import math
from typing import Sequence

Vec3 = tuple[float, float, float]
Polygon = tuple[Vec3, ...]


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _length(a) -> float:
    return math.sqrt(_dot(a, a))


def _normalized(v) -> Vec3 | None:
    length = _length(v)
    if length < 1e-30:
        return None
    return (v[0] / length, v[1] / length, v[2] / length)


def clip_polygon(poly: Polygon, plane_co: Sequence[float], plane_no: Sequence[float],
                 eps: float) -> tuple[Polygon | None, Polygon | None]:
    """Clip *poly* against both half-spaces of a plane at once.

    Returns ``(front, back)``: ``front`` is the part with signed distance
    ``>= -eps`` (the side ``plane_no`` points to), ``back`` the part with
    distance ``<= eps``. Points within *eps* of the plane belong to both
    sides. Each side is a polygon or None when fewer than 3 points remain.
    A polygon lying entirely on one side is returned as the same object.

    A polygon lying IN the plane goes to one side only: the side its solid
    is on, i.e. opposite to its own normal. Giving it to both sides would
    let the top face of a box below the plane widen the hull of the part
    above it (an L-shape cut along its inner face would not become two
    tight boxes). Only a degenerate in-plane polygon (no normal) goes to both.
    """
    if len(poly) < 3:
        return None, None
    px, py, pz = plane_co
    nx, ny, nz = plane_no
    dists = [(p[0] - px) * nx + (p[1] - py) * ny + (p[2] - pz) * nz for p in poly]
    # Snap distances within eps to the plane: sign -1 / 0 / +1.
    signs = [0 if -eps <= d <= eps else (1 if d > 0 else -1) for d in dists]
    lo = min(signs)
    hi = max(signs)
    if lo == 0 and hi == 0:
        facing = _newell_dot(poly, nx, ny, nz)
        if facing > 0.0:
            return None, poly      # faces the front: its solid is behind
        if facing < 0.0:
            return poly, None
        return poly, poly
    if lo >= 0:
        return poly, None
    if hi <= 0:
        return None, poly

    front: list[Vec3] = []
    back: list[Vec3] = []
    n = len(poly)
    for i in range(n):
        q = poly[i - 1]
        p = poly[i]
        sq = signs[i - 1]
        sp = signs[i]
        if sq * sp < 0:
            dq = dists[i - 1]
            dp = dists[i]
            t = dq / (dq - dp)
            ip = (q[0] + (p[0] - q[0]) * t,
                  q[1] + (p[1] - q[1]) * t,
                  q[2] + (p[2] - q[2]) * t)
            front.append(ip)
            back.append(ip)
        if sp >= 0:
            front.append(p)
        if sp <= 0:
            back.append(p)
    return _finish(front), _finish(back)


def _newell_dot(poly, nx, ny, nz) -> float:
    """Dot product of the polygon's (unnormalized, Newell) normal with n."""
    ax = ay = az = 0.0
    q = poly[-1]
    for p in poly:
        ax += (q[1] - p[1]) * (q[2] + p[2])
        ay += (q[2] - p[2]) * (q[0] + p[0])
        az += (q[0] - p[0]) * (q[1] + p[1])
        q = p
    return ax * nx + ay * ny + az * nz


def _finish(points: list) -> Polygon | None:
    """Drop consecutive duplicates; None when fewer than 3 points remain."""
    out = []
    for p in points:
        if not out or out[-1] != p:
            out.append(p)
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    if len(out) < 3:
        return None
    return tuple(out)


def split_polygons(polys: Sequence[Polygon], plane_co: Sequence[float],
                   plane_no: Sequence[float], eps: float
                   ) -> tuple[tuple[Polygon, ...], tuple[Polygon, ...]]:
    """Split every polygon by the plane; returns ``(front_polys, back_polys)``.

    Polygons wholly on one side are passed through without copying.
    """
    front: list[Polygon] = []
    back: list[Polygon] = []
    for poly in polys:
        f, b = clip_polygon(poly, plane_co, plane_no, eps)
        if f is not None:
            front.append(f)
        if b is not None:
            back.append(b)
    return tuple(front), tuple(back)


def clip_to_convex(polys: Sequence[Polygon], planes, eps: float) -> tuple[Polygon, ...]:
    """Clip every polygon to the convex region bounded by *planes*.

    *planes* is an iterable of ``(point, outward_normal)``; the region is the
    intersection of their back half-spaces (signed distance ``<= eps``).
    Polygons left with fewer than 3 points are dropped; a polygon lying
    entirely inside is returned as the same object.
    """
    planes = tuple(planes)
    out: list[Polygon] = []
    for poly in polys:
        cur = poly
        for co, no in planes:
            cur = clip_polygon(cur, co, no, eps)[1]
            if cur is None:
                break
        if cur is not None:
            out.append(cur)
    return tuple(out)


def clip_outside_convex(polys: Sequence[Polygon], planes, eps: float) -> tuple[Polygon, ...]:
    """The parts of *polys* OUTSIDE the convex region bounded by *planes*.

    *planes* is an iterable of ``(point, outward_normal)``. Each polygon is
    peeled plane by plane: the part in front of a plane is outside the
    region and emitted, the part behind goes on to the next plane; what is
    left behind every plane is inside and dropped. A polygon wholly in front
    of the first plane it meets is emitted as the same object. One input
    polygon can yield several output pieces (in plane order); input order is
    preserved.
    """
    planes = tuple(planes)
    out: list[Polygon] = []
    for poly in polys:
        remaining = poly
        for co, no in planes:
            front, back = clip_polygon(remaining, co, no, eps)
            if front is not None:
                out.append(front)
            remaining = back
            if remaining is None:
                break
    return tuple(out)


def section_polygon(flat_tris: Sequence[Sequence[float]], plane_co: Sequence[float],
                    plane_no: Sequence[float], eps: float) -> list[Vec3]:
    """Convex cross-section of a closed convex triangle soup by a plane.

    *flat_tris* holds three points per triangle. Every triangle edge whose
    ends lie on strictly opposite sides (beyond *eps*) contributes its
    intersection point, every vertex within *eps* of the plane itself.
    Points closer than *eps* (at least 1e-9) are merged, and points lying
    on a straight side between their neighbours (from the diagonals of a
    triangulated flat hull face) are dropped. Returns the points ordered
    counter-clockwise around their centroid (seen from the side *plane_no*
    points to), or [] when fewer than 3 distinct points remain or the normal
    is zero.
    """
    no = _normalized(plane_no)
    if no is None:
        return []
    merge = max(eps, 1e-9)
    pts: list[Vec3] = []

    def add(p):
        for q in pts:
            if abs(p[0] - q[0]) <= merge and abs(p[1] - q[1]) <= merge \
                    and abs(p[2] - q[2]) <= merge:
                return
        pts.append((float(p[0]), float(p[1]), float(p[2])))

    for i in range(0, len(flat_tris) - 2, 3):
        tri = (flat_tris[i], flat_tris[i + 1], flat_tris[i + 2])
        d = [_dot(_sub(p, plane_co), no) for p in tri]
        for k in range(3):
            if abs(d[k]) <= eps:
                add(tri[k])
        for k in range(3):
            j = (k + 1) % 3
            if (d[k] > eps and d[j] < -eps) or (d[k] < -eps and d[j] > eps):
                t = d[k] / (d[k] - d[j])
                a, b = tri[k], tri[j]
                add((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
                     a[2] + (b[2] - a[2]) * t))
    if len(pts) < 3:
        return []
    n = float(len(pts))
    c = (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n, sum(p[2] for p in pts) / n)
    # 2D basis of the plane: u from the world axis least parallel to no.
    axis = min(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
               key=lambda a: abs(_dot(a, no)))
    u = _normalized(_cross(no, axis))
    v = _cross(no, u)
    pts.sort(key=lambda p: math.atan2(_dot(_sub(p, c), v), _dot(_sub(p, c), u)))
    # Drop points on straight sides (triangle diagonals of a flat hull face
    # cut the plane mid-side).
    changed = True
    while changed and len(pts) > 3:
        changed = False
        for i in range(len(pts)):
            a, p, b = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
            ab = _sub(b, a)
            length = _length(ab)
            if length <= merge or _length(_cross(ab, _sub(p, a))) / length <= merge:
                del pts[i]
                changed = True
                break
    if len(pts) < 3:
        return []
    return pts


def polygon_area(points: Sequence[Sequence[float]]) -> float:
    """Area of a planar 3D polygon (half the Newell normal's length); 0 for
    fewer than 3 points."""
    if len(points) < 3:
        return 0.0
    ax = ay = az = 0.0
    q = points[-1]
    for p in points:
        ax += (q[1] - p[1]) * (q[2] + p[2])
        ay += (q[2] - p[2]) * (q[0] + p[0])
        az += (q[0] - p[0]) * (q[1] + p[1])
        q = p
    return 0.5 * math.sqrt(ax * ax + ay * ay + az * az)


def scale_polygon(points: Sequence[Sequence[float]], factor: float) -> list[Vec3]:
    """*points* scaled by *factor* about their centroid ([] for none)."""
    if not points:
        return []
    n = float(len(points))
    c = (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n,
         sum(p[2] for p in points) / n)
    return [(c[0] + (p[0] - c[0]) * factor, c[1] + (p[1] - c[1]) * factor,
             c[2] + (p[2] - c[2]) * factor) for p in points]


def closest_on_segment_2d(p, a, b) -> tuple[float, float]:
    """``(t, distance)`` of the point of segment *a*-*b* closest to *p*
    (2D); *t* in [0, 1] along the segment, 0 for a zero-length segment."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    if length2 <= 1e-24:
        t = 0.0
    else:
        t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2
        t = min(1.0, max(0.0, t))
    cx, cy = a[0] + dx * t, a[1] + dy * t
    return t, math.hypot(p[0] - cx, p[1] - cy)


def pick_snap(mouse, verts_2d, edges_2d, vert_px: float, edge_px: float):
    """Snap target of the mouse among a face's projected elements.

    *verts_2d* is a list of 2D points (None for one that does not
    project), *edges_2d* a list of ``(a, b)`` 2D pairs (None, or a None end,
    to skip). Returns ``('VERTEX', i)`` for the nearest vertex within
    *vert_px*, else ``('EDGE', i, t)`` for the nearest edge within *edge_px*
    (*t* the clamped 2D parameter along it), else ``('FACE',)``. A vertex in
    range wins over any edge.
    """
    best_v = None
    for i, v in enumerate(verts_2d):
        if v is None:
            continue
        d = math.hypot(mouse[0] - v[0], mouse[1] - v[1])
        if d <= vert_px and (best_v is None or d < best_v[1]):
            best_v = (i, d)
    if best_v is not None:
        return ('VERTEX', best_v[0])
    best_e = None
    for i, e in enumerate(edges_2d):
        if e is None or e[0] is None or e[1] is None:
            continue
        t, d = closest_on_segment_2d(mouse, e[0], e[1])
        if d <= edge_px and (best_e is None or d < best_e[2]):
            best_e = (i, t, d)
    if best_e is not None:
        return ('EDGE', best_e[0], best_e[1])
    return ('FACE',)


def unique_points(polys: Sequence[Polygon], digits: int = 6) -> list[Vec3]:
    """Deduplicated points of *polys* (rounded to *digits* for the comparison).

    Returns the first original point seen for each rounded key, in order.
    """
    seen = set()
    out: list[Vec3] = []
    for poly in polys:
        for p in poly:
            key = (round(p[0], digits), round(p[1], digits), round(p[2], digits))
            if key not in seen:
                seen.add(key)
                out.append(p)
    return out


def extent(polys: Sequence[Polygon]) -> float:
    """Diagonal length of the axis-aligned bounding box of *polys* (0 if empty)."""
    lo = [math.inf, math.inf, math.inf]
    hi = [-math.inf, -math.inf, -math.inf]
    any_point = False
    for poly in polys:
        for p in poly:
            any_point = True
            for k in range(3):
                if p[k] < lo[k]:
                    lo[k] = p[k]
                if p[k] > hi[k]:
                    hi[k] = p[k]
    if not any_point:
        return 0.0
    return _length((hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]))


def plane_eps(polys: Sequence[Polygon]) -> float:
    """Plane-distance tolerance for *polys*: 1e-6 of their extent, min 1e-9."""
    return max(1e-6 * extent(polys), 1e-9)


def is_solid(points: Sequence[Sequence[float]], eps: float) -> bool:
    """True when there are at least 4 points that are not all coplanar."""
    if len(points) < 4:
        return False
    p0 = points[0]
    # Farthest point from p0.
    best, p1 = -1.0, None
    for p in points:
        d = _length(_sub(p, p0))
        if d > best:
            best, p1 = d, p
    if p1 is None or best <= eps:
        return False
    axis = _normalized(_sub(p1, p0))
    # Farthest point from the line p0-p1.
    best, normal = -1.0, None
    for p in points:
        c = _cross(axis, _sub(p, p0))
        d = _length(c)
        if d > best:
            best, normal = d, c
    if normal is None or best <= eps:
        return False
    normal = _normalized(normal)
    for p in points:
        if abs(_dot(_sub(p, p0), normal)) > eps:
            return True
    return False


def facing_alpha(facing: float, base: float, back_factor: float = 0.12) -> float:
    """Fill alpha of a triangle for the split overlay.

    *facing* is the dot product of the triangle's outward unit normal with the
    unit direction to the viewer. Front faces fade from full *base* (facing
    the viewer) to 35% of it (edge-on); back faces get a constant
    *back_factor* of it.
    """
    if facing > 0.0:
        return base * (0.35 + 0.65 * min(facing, 1.0))
    return base * back_factor


def edge_is_back(n1_dot_v: float, n2_dot_v: float) -> bool:
    """True when a hull edge faces away from the viewer: both adjacent faces
    do (``n . v <= 0`` for each, *v* towards the viewer). Silhouette edges
    (one face front, one back) and front edges are not back edges."""
    return n1_dot_v <= 0.0 and n2_dot_v <= 0.0


def plane_key(normal: Sequence[float], origin: Sequence[float], extent_: float,
              digits: int = 5, rel: float = 1e-5):
    """Hashable, quantised identity of a plane for caching a cut preview.

    *normal* must be unit length. The normal is rounded to *digits* decimals
    and the signed plane distance ``origin . normal`` to steps of *rel* times
    *extent_* (the piece size), so every point of one face plane gives the
    same key. None for non-finite input.
    """
    step = max(float(extent_) * rel, 1e-12)
    d = _dot(origin, normal) / step
    values = (normal[0], normal[1], normal[2], d)
    if not all(math.isfinite(v) for v in values):
        return None
    # "+ 0.0" folds -0.0 into 0.0.
    return (round(normal[0], digits) + 0.0, round(normal[1], digits) + 0.0,
            round(normal[2], digits) + 0.0, int(round(d)))


def equal_planes(polys: Sequence[Polygon], normal: Sequence[float], n: int) -> list[Vec3]:
    """Origins of the ``n - 1`` planes (normal *normal*) that cut the span of
    *polys* along *normal* into *n* equal slabs, in increasing order along the
    normal. Empty when ``n < 2``, the normal is zero or the span is flat."""
    if n < 2:
        return []
    nrm = _normalized(normal)
    if nrm is None:
        return []
    lo, hi = math.inf, -math.inf
    for poly in polys:
        for p in poly:
            d = _dot(p, nrm)
            if d < lo:
                lo = d
            if d > hi:
                hi = d
    if lo == math.inf or hi - lo <= 1e-12:
        return []
    out = []
    for i in range(1, n):
        d = lo + (hi - lo) * i / n
        out.append((nrm[0] * d, nrm[1] * d, nrm[2] * d))
    return out


# ----- islands and auto-merge -----

def split_islands(polys: Sequence[Polygon], digits: int = 6) -> list[tuple[Polygon, ...]]:
    """Connected components of *polys*: two polygons are connected when they
    share a point (compared after rounding to *digits*).

    Returns one tuple of polygons per island, ordered by the index of each
    island's first polygon; polygons keep their input order inside an island.
    """
    n = len(polys)
    parent = list(range(n))

    def find(i):
        root = i
        while parent[root] != root:
            root = parent[root]
        while parent[i] != root:
            parent[i], i = root, parent[i]
        return root

    owner: dict = {}
    for i, poly in enumerate(polys):
        for p in poly:
            key = (round(p[0], digits), round(p[1], digits), round(p[2], digits))
            j = owner.get(key)
            if j is None:
                owner[key] = i
                continue
            ri, rj = find(i), find(j)
            if ri != rj:
                # The smaller index becomes the root: keeps the result stable.
                if ri < rj:
                    parent[rj] = ri
                else:
                    parent[ri] = rj
    groups: dict = {}
    order: list = []
    for i in range(n):
        r = find(i)
        members = groups.get(r)
        if members is None:
            members = groups[r] = []
            order.append(r)
        members.append(polys[i])
    return [tuple(groups[r]) for r in order]


def tris_volume(flat_tris: Sequence[Sequence[float]]) -> float:
    """Absolute volume enclosed by a closed triangle soup given as a flat
    list of points (three per triangle, consistent winding)."""
    total = 0.0
    for i in range(0, len(flat_tris) - 2, 3):
        a, b, c = flat_tris[i], flat_tris[i + 1], flat_tris[i + 2]
        total += _dot(a, _cross(b, c))
    return abs(total) / 6.0


def bbox(points: Sequence[Sequence[float]]):
    """``(min3, max3)`` of *points*, or None when there are none."""
    lo = [math.inf, math.inf, math.inf]
    hi = [-math.inf, -math.inf, -math.inf]
    for p in points:
        for k in range(3):
            if p[k] < lo[k]:
                lo[k] = p[k]
            if p[k] > hi[k]:
                hi[k] = p[k]
    if lo[0] == math.inf:
        return None
    return tuple(lo), tuple(hi)


def bbox_union(a, b):
    """Smallest box containing boxes *a* and *b*."""
    return (tuple(min(a[0][k], b[0][k]) for k in range(3)),
            tuple(max(a[1][k], b[1][k]) for k in range(3)))


def bbox_gap(a, b) -> float:
    """Euclidean distance between two axis-aligned boxes (0 when they
    overlap or touch)."""
    s = 0.0
    for k in range(3):
        d = max(0.0, a[0][k] - b[1][k], b[0][k] - a[1][k])
        s += d * d
    return math.sqrt(s)


def min_width(points: Sequence[Sequence[float]], normals: Sequence[Sequence[float]]) -> float:
    """Smallest extent of *points* along any of the unit *normals*
    (``max(dot) - min(dot)``). Zero-length normals (degenerate triangles) are
    skipped. 0.0 when there are no points or no usable normals."""
    if not points:
        return 0.0
    best = math.inf
    for n in normals:
        if _dot(n, n) < 1e-12:
            continue
        lo, hi = math.inf, -math.inf
        for p in points:
            d = _dot(p, n)
            if d < lo:
                lo = d
            if d > hi:
                hi = d
        if hi - lo < best:
            best = hi - lo
    return 0.0 if best == math.inf else best


# Flat-merge rule of plan_merges: a union up to this many times as thick as
# the thickest ORIGINAL item of the two groups counts as flat.
FLAT_FACTOR = 1.05


def plan_merges(volumes: Sequence[float], boxes, max_gap: float, max_cost: float,
                union_volume, union_thickness=None, thicknesses=None,
                flat: bool = False) -> list[list[int]]:
    """Greedy agglomerative grouping of items ``0 .. n-1``.

    Each group has members, a volume and a bounding box (*volumes* /
    *boxes* per item to start). Among all pairs of groups whose
    :func:`bbox_gap` is ``<= max_gap``, the pair with the lowest cost
    ``max(0, vu - va - vb) / vu`` is merged while that cost is ``<= max_cost``
    (``vu = union_volume(frozenset(members))``; pairs with ``vu <= 0`` are
    skipped). The merged group's volume is ``vu`` and its box the union.
    Pair costs are cached: only pairs with a newly merged group are computed.
    Ties are broken by group creation order, so the result is deterministic.

    Flat rule (*flat* True and both *union_thickness* — a callable taking
    the same frozenset, returning the union hull's thickness or None — and
    *thicknesses* — one per item — given): a pair whose cost exceeds
    *max_cost* is still eligible when the union is not meaningfully thicker
    than the thickest original item of either group, ``union <=
    max(base_a, base_b) * FLAT_FACTOR + 1e-6`` (coplanar plates merge into a
    slab whatever the void). A group's base thickness is the max of its
    original items' *thicknesses* and never grows through merging, so the
    limit cannot drift upward step by step. Eligible pairs are still merged
    lowest cost first.
    Without these arguments the result is exactly the classic one.

    Returns the groups as sorted index lists, ordered by smallest member.
    """
    import heapq

    use_flat = bool(flat) and union_thickness is not None and thicknesses is not None
    n = len(volumes)
    members: dict = {i: frozenset((i,)) for i in range(n)}
    vol: dict = {i: float(volumes[i]) for i in range(n)}
    box: dict = {i: boxes[i] for i in range(n)}
    # Max thickness of each group's ORIGINAL items (flat rule only).
    base_thick: dict = ({i: float(thicknesses[i]) for i in range(n)} if use_flat else {})
    heap: list = []

    def flat_ok(a, b, union):
        tu = union_thickness(union)
        if tu is None:
            return False
        return tu <= max(base_thick[a], base_thick[b]) * FLAT_FACTOR + 1e-6

    def pair(a, b):
        if bbox_gap(box[a], box[b]) > max_gap:
            return
        union = members[a] | members[b]
        vu = union_volume(union)
        if vu is None or not vu > 0.0:
            return
        cost = max(0.0, vu - vol[a] - vol[b]) / vu
        # Pairs over max_cost can never merge (classic rule) unless flat:
        # leaving them out is the same as stopping at the first of them.
        if cost > max_cost and not (use_flat and flat_ok(a, b, union)):
            return
        heapq.heappush(heap, (cost, a, b, vu))

    for a in range(n):
        for b in range(a + 1, n):
            pair(a, b)

    next_id = n
    while heap:
        cost, a, b, vu = heapq.heappop(heap)
        if a not in members or b not in members:
            continue        # stale: one side was merged already
        g = next_id
        next_id += 1
        members[g] = members.pop(a) | members.pop(b)
        vol[g] = vu
        box[g] = bbox_union(box.pop(a), box.pop(b))
        del vol[a], vol[b]
        if use_flat:
            base_thick[g] = max(base_thick.pop(a), base_thick.pop(b))
        for other in sorted(members):
            if other != g:
                pair(other, g)

    groups = [sorted(m) for m in members.values()]
    groups.sort(key=lambda m: m[0])
    return groups
