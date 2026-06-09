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
