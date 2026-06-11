"""Pure-Python convexity and topology helpers shared by the convexity operators.

This module imports no Blender modules so the geometry logic can be unit-tested
outside Blender. It reuses ``collision_mesh_geometry`` as the single source of
truth for what counts as valid collision geometry: ``violating_faces`` mirrors
``check_convex`` (reporting every offending face, not just the worst), and
``classify_edges`` mirrors ``check_watertight``'s edge definition (returning edge
identities, not just counts).
"""
from collections import defaultdict

import collision_mesh_geometry as cmg


def violating_faces(vertices, triangles, tolerance):
    """Return the set of triangle indices that violate convexity.

    A face is violating when any vertex not belonging to it lies more than
    ``tolerance`` outside the face plane. Mirrors the math of
    ``collision_mesh_geometry.check_convex`` exactly (same primitives, same
    plane test) but collects every offending face. Faces with a zero-area
    normal are skipped (they are degenerate, handled separately).
    """
    geo2 = cmg.geo2
    bad = set()
    for face_idx, tri in enumerate(triangles):
        a = vertices[tri[0]]
        b = vertices[tri[1]]
        c = vertices[tri[2]]
        n = geo2.Vec3Cross(geo2.Vec3Subtract(b, a), geo2.Vec3Subtract(c, a))
        length = geo2.Vec3Length(n)
        if length < 1e-12:
            continue
        n = geo2.Vec3Scale(n, 1.0 / length)
        d = geo2.Vec3Dot(n, a)
        own = (tri[0], tri[1], tri[2])
        for v_idx, v in enumerate(vertices):
            if v_idx in own:
                continue
            if geo2.Vec3Dot(n, v) - d > tolerance:
                bad.add(face_idx)
                break
    return bad


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def convex_hull_triangles(points, epsilon=None, tolerance=None):
    """Compute the convex hull of 3D points in double precision (quickhull).

    Returns a list of ``(i, j, k)`` triangles indexing into *points* with
    outward winding, or ``None`` when the input is degenerate (fewer than 4
    points, or all points coincident/collinear/coplanar).

    Exists because Blender's ``bmesh.ops.convex_hull`` merges nearly coplanar
    regions with an internal tolerance that scales with the point cloud, which
    can leave hull vertices several millimetres outside face planes — failing
    ``collision_mesh_geometry.check_convex`` at its fixed tolerance. Here the
    residual error is on the order of float64 rounding.

    One caveat remains: an epsilon-scale visibility misjudgment next to a
    long, thin hull face is amplified by the face's length/width ratio and can
    fold the surface by more than the construction epsilon. When *tolerance*
    is given, the result is validated against the full collision policy
    (convex within tolerance, watertight, manifold, no degenerate triangles)
    and construction is retried with adjusted epsilons until an attempt
    passes; the first attempt is returned if none does.
    """
    pts = [(float(p[0]), float(p[1]), float(p[2])) for p in points]
    if len(pts) < 4:
        return None

    max_abs = max(abs(c) for p in pts for c in p)
    eps = epsilon if epsilon is not None else 1e-9 * max(1.0, max_abs)

    first = _quickhull(pts, eps)
    if first is None or tolerance is None or _hull_is_valid(pts, first, tolerance):
        return first
    for retry_eps in (eps / 256.0, eps * 256.0, eps / 65536.0):
        tris = _quickhull(pts, retry_eps)
        if tris is not None and _hull_is_valid(pts, tris, tolerance):
            return tris
    return first


def _hull_is_valid(pts, tris, tolerance):
    """True when a triangulated hull passes the full collision-mesh policy."""
    if violating_faces(pts, tris, tolerance):
        return False
    boundary, nonmanifold = classify_edges(tris)
    if boundary or nonmanifold:
        return False
    return not any(
        cmg.triangle_is_degenerate(pts[a], pts[b], pts[c]) for a, b, c in tris
    )


def _quickhull(pts, eps):
    """Single quickhull construction at a fixed epsilon (see convex_hull_triangles)."""
    n_pts = len(pts)

    # --- initial simplex: two extreme points, furthest from their line,
    # furthest from their plane ---
    extremes = set()
    for axis in range(3):
        extremes.add(min(range(n_pts), key=lambda i: pts[i][axis]))
        extremes.add(max(range(n_pts), key=lambda i: pts[i][axis]))
    extremes = sorted(extremes)
    i0 = i1 = -1
    best = -1.0
    for ii, ei in enumerate(extremes):
        for ej in extremes[ii + 1:]:
            d = _sub(pts[ei], pts[ej])
            d2 = _dot(d, d)
            if d2 > best:
                best = d2
                i0, i1 = ei, ej
    if best <= eps * eps:
        return None  # all points coincident
    a = pts[i0]
    ab = _sub(pts[i1], a)
    ab_len = _dot(ab, ab) ** 0.5

    i2 = max(
        range(n_pts),
        key=lambda i: _dot(_cross(ab, _sub(pts[i], a)),
                           _cross(ab, _sub(pts[i], a))),
    )
    line_dist = _dot(_cross(ab, _sub(pts[i2], a)),
                     _cross(ab, _sub(pts[i2], a))) ** 0.5 / ab_len
    if line_dist <= eps:
        return None  # collinear

    n0 = _cross(ab, _sub(pts[i2], a))
    n0_len = _dot(n0, n0) ** 0.5
    n0 = (n0[0] / n0_len, n0[1] / n0_len, n0[2] / n0_len)
    d0 = _dot(n0, a)
    i3 = max(range(n_pts), key=lambda i: abs(_dot(n0, pts[i]) - d0))
    if abs(_dot(n0, pts[i3]) - d0) <= eps:
        return None  # coplanar

    # --- face bookkeeping ---
    faces = {}      # fid -> {"v": (i, j, k), "n": unit normal, "d": offset,
                    #         "out": [(dist, point_idx), ...]}
    edge_map = {}   # frozenset((u, v)) -> set of fids
    next_id = [0]

    def add_face(i, j, k):
        nv = _cross(_sub(pts[j], pts[i]), _sub(pts[k], pts[i]))
        ln = _dot(nv, nv) ** 0.5
        if ln > 1e-30:
            nv = (nv[0] / ln, nv[1] / ln, nv[2] / ln)
            dv = _dot(nv, pts[i])
        else:
            nv = (0.0, 0.0, 0.0)
            dv = 0.0
        fid = next_id[0]
        next_id[0] += 1
        faces[fid] = {"v": (i, j, k), "n": nv, "d": dv, "out": []}
        for u, v in ((i, j), (j, k), (k, i)):
            edge_map.setdefault(frozenset((u, v)), set()).add(fid)
        return fid

    def remove_face(fid):
        i, j, k = faces.pop(fid)["v"]
        for u, v in ((i, j), (j, k), (k, i)):
            key = frozenset((u, v))
            owners = edge_map[key]
            owners.discard(fid)
            if not owners:
                del edge_map[key]

    # initial tetrahedron, each face oriented away from its opposite vertex
    simplex = (i0, i1, i2, i3)
    for i, j, k, opposite in (
        (i0, i1, i2, i3), (i0, i3, i1, i2), (i1, i3, i2, i0), (i2, i3, i0, i1),
    ):
        fid = add_face(i, j, k)
        f = faces[fid]
        if _dot(f["n"], pts[opposite]) - f["d"] > 0.0:
            remove_face(fid)
            add_face(i, k, j)

    def assign(idx, fids):
        # Conflict graph (de Berg): a point lives in the list of EVERY face it
        # is outside of. Single-owner lists are subtly wrong: an orphaned point
        # reassigned only to the replacement faces can be silently dropped
        # while still outside an old, untouched face, leaving a violation as
        # large as that face's conflict distance in the output.
        for fid in fids:
            f = faces[fid]
            dist = _dot(f["n"], pts[idx]) - f["d"]
            if dist > eps:
                f["out"].append((dist, idx))

    initial = list(faces)
    for idx in range(n_pts):
        if idx not in simplex:
            assign(idx, initial)

    # --- quickhull insertion loop ---
    inserted = set(simplex)
    while True:
        target = next((fid for fid, f in faces.items() if f["out"]), None)
        if target is None:
            break
        _, p_idx = max(faces[target]["out"])
        p = pts[p_idx]

        # all faces p can see, grown outward from the conflict face
        visible = {target}
        stack = [target]
        while stack:
            i, j, k = faces[stack.pop()]["v"]
            for u, v in ((i, j), (j, k), (k, i)):
                for nb in edge_map[frozenset((u, v))]:
                    if nb not in visible:
                        g = faces[nb]
                        if _dot(g["n"], p) - g["d"] > eps:
                            visible.add(nb)
                            stack.append(nb)

        # horizon: directed edges of visible faces bordering a hidden face.
        # Candidates for the replacement faces come from the visible faces AND
        # the hidden faces across the horizon (the de Berg parent pair).
        horizon = []
        candidates = set()
        for fid in visible:
            i, j, k = faces[fid]["v"]
            for u, v in ((i, j), (j, k), (k, i)):
                hidden = edge_map[frozenset((u, v))] - visible
                if hidden:
                    horizon.append((u, v))
                    for hid in hidden:
                        candidates.update(idx for _, idx in faces[hid]["out"])
            candidates.update(idx for _, idx in faces[fid]["out"])
        candidates -= inserted
        candidates.discard(p_idx)

        for fid in list(visible):
            remove_face(fid)
        new_fids = [add_face(u, v, p_idx) for u, v in horizon]
        for idx in candidates:
            assign(idx, new_fids)

        # p is a hull vertex now; retire it from every remaining conflict list
        inserted.add(p_idx)
        for f in faces.values():
            if any(idx == p_idx for _, idx in f["out"]):
                f["out"] = [e for e in f["out"] if e[1] != p_idx]

    return [f["v"] for f in faces.values()]


def classify_edges(triangles):
    """Return ``(boundary_edges, nonmanifold_edges)`` as sets of frozenset pairs.

    Mirrors ``collision_mesh_geometry.check_watertight``'s edge definition:
    boundary edges are used by exactly one triangle; non-manifold edges are used
    by more than two. Edges are ``frozenset`` of the two vertex indices so they
    can be matched against unordered bmesh edges.
    """
    edge_count = defaultdict(int)
    for tri in triangles:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            edge_count[frozenset((a, b))] += 1
    boundary = {edge for edge, count in edge_count.items() if count == 1}
    nonmanifold = {edge for edge, count in edge_count.items() if count > 2}
    return boundary, nonmanifold
