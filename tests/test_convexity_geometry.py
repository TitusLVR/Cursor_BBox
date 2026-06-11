"""Tests for the pure convexity/topology helpers (no Blender required).

Run with the package on PYTHONPATH:
    $env:PYTHONPATH = "s:\\packages"
    python b:\\scripts\\addons\\Cursor_BBox\\tests\\test_convexity_geometry.py
"""
import os
import sys
import unittest

# Make the bpy-free helper importable standalone (it is normally imported as
# Cursor_BBox.functions.convexity_geometry inside Blender).
_FUNCTIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "functions")
if _FUNCTIONS_DIR not in sys.path:
    sys.path.insert(0, _FUNCTIONS_DIR)

import convexity_geometry as cg  # noqa: E402

TOL = 1e-3

# Closed, convex, correctly wound unit cube (0-indexed port of the package's
# CUBE_OBJ): no convexity violations, no boundary or non-manifold edges.
CUBE_VERTS = [
    (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
    (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
]
CUBE_TRIS = [
    [0, 3, 2], [0, 2, 1], [4, 5, 6], [4, 6, 7],
    [0, 1, 5], [0, 5, 4], [3, 7, 6], [3, 6, 2],
    [0, 4, 7], [0, 7, 3], [1, 2, 6], [1, 6, 5],
]


class ViolatingFacesTests(unittest.TestCase):
    def test_convex_cube_has_no_violations(self):
        self.assertEqual(cg.violating_faces(CUBE_VERTS, CUBE_TRIS, TOL), set())

    def test_vertex_outside_face_plane_is_flagged(self):
        # Triangle in the z=0 plane (normal +z); a vertex above it is outside.
        verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
        tris = [[0, 1, 2]]
        self.assertEqual(cg.violating_faces(verts, tris, TOL), {0})

    def test_vertex_behind_face_plane_is_clean(self):
        verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, -1)]
        tris = [[0, 1, 2]]
        self.assertEqual(cg.violating_faces(verts, tris, TOL), set())

    def test_within_tolerance_is_clean(self):
        # Vertex only 0.0005 outside (< 1e-3 tolerance) -> not flagged.
        verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 0.0005)]
        tris = [[0, 1, 2]]
        self.assertEqual(cg.violating_faces(verts, tris, TOL), set())

    def test_degenerate_triangle_is_skipped(self):
        # Collinear triangle has zero-area normal and is skipped (not flagged).
        verts = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 0, 1)]
        tris = [[0, 1, 2]]
        self.assertEqual(cg.violating_faces(verts, tris, TOL), set())


class ConvexHullTrianglesTests(unittest.TestCase):
    def assert_valid_hull(self, points, tris, tolerance=1e-6):
        """A hull must be convex (per the package test), watertight, manifold,
        outward-wound, and contain every input point."""
        self.assertTrue(tris)
        self.assertEqual(cg.violating_faces(points, tris, tolerance), set())
        boundary, nonmanifold = cg.classify_edges(tris)
        self.assertEqual(boundary, set())
        self.assertEqual(nonmanifold, set())
        for a, b, c in tris:
            self.assertFalse(
                cg.cmg.triangle_is_degenerate(points[a], points[b], points[c])
            )
        # outward winding => positive signed volume
        _, volume = cg.cmg.volume_centroid(points, [list(t) for t in tris])
        self.assertGreater(volume, 0.0)
        # every input point inside (no plane more than tolerance outside)
        worst, _ = cg.cmg.check_convex(points, [list(t) for t in tris])
        self.assertLessEqual(worst, tolerance)

    def test_cube_corners(self):
        tris = cg.convex_hull_triangles(CUBE_VERTS)
        self.assertEqual(len(tris), 12)
        self.assert_valid_hull(CUBE_VERTS, tris)

    def test_interior_points_are_dropped(self):
        pts = CUBE_VERTS + [(0.5, 0.5, 0.5), (0.25, 0.5, 0.75)]
        tris = cg.convex_hull_triangles(pts)
        used = {i for t in tris for i in t}
        self.assertEqual(used, set(range(8)))
        self.assert_valid_hull(pts, tris)

    def test_duplicate_points(self):
        pts = CUBE_VERTS + CUBE_VERTS
        tris = cg.convex_hull_triangles(pts)
        self.assert_valid_hull(pts, tris)

    def test_tetrahedron(self):
        pts = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
        tris = cg.convex_hull_triangles(pts)
        self.assertEqual(len(tris), 4)
        self.assert_valid_hull(pts, tris)

    def test_far_from_origin_dense_cloud(self):
        # Regression for the live failure: points ~270 m from the origin with
        # small features must still produce a hull that passes the package's
        # 1e-3 tolerance. Deterministic pseudo-random cloud.
        import random
        rng = random.Random(20260611)
        pts = [
            (253.0 + rng.uniform(0, 12.0),
             -148.0 + rng.uniform(0, 7.0),
             31.0 + rng.uniform(0, 4.0))
            for _ in range(400)
        ]
        # plus near-coplanar clusters that trip Blender's hull face merging
        for i in range(60):
            t = i / 59.0
            pts.append((253.0 + 12.0 * t, -148.0 + 7.0 * t,
                        31.0 + 4.0 * t + rng.uniform(-5e-4, 5e-4)))
        tris = cg.convex_hull_triangles(pts)
        self.assert_valid_hull(pts, tris, tolerance=1e-3)

    def test_sliver_face_regression_mesh_084(self):
        # Real CoACD hull piece whose exact hull contains a 10.6 m x 8.9 mm
        # sliver face. An epsilon-scale visibility misjudgment next to that
        # sliver is amplified ~1200x and folded the surface by 1.08 mm,
        # failing the 1e-3 policy; the tolerance-driven retry must catch it.
        import json
        data = os.path.join(os.path.dirname(__file__), "data_mesh_084.json")
        with open(data) as fh:
            pts = [tuple(p) for p in json.load(fh)]
        tris = cg.convex_hull_triangles(pts, tolerance=1e-3)
        self.assert_valid_hull(pts, tris, tolerance=1e-3)

    def test_degenerate_inputs_return_none(self):
        self.assertIsNone(cg.convex_hull_triangles([]))
        self.assertIsNone(cg.convex_hull_triangles([(0, 0, 0)] * 10))
        self.assertIsNone(
            cg.convex_hull_triangles([(i, 0, 0) for i in range(10)])
        )
        self.assertIsNone(
            cg.convex_hull_triangles(
                [(i % 4, i // 4, 0) for i in range(16)]
            )
        )
        self.assertIsNone(cg.convex_hull_triangles([(0, 0, 0), (1, 0, 0), (0, 1, 0)]))


class ClassifyEdgesTests(unittest.TestCase):
    def test_closed_cube_has_no_boundary_or_nonmanifold(self):
        boundary, nonmanifold = cg.classify_edges(CUBE_TRIS)
        self.assertEqual(boundary, set())
        self.assertEqual(nonmanifold, set())

    def test_open_pair_reports_boundary_edges(self):
        # Two triangles sharing edge (0,2); the other four edges are boundary.
        tris = [[0, 1, 2], [0, 2, 3]]
        boundary, nonmanifold = cg.classify_edges(tris)
        self.assertEqual(
            boundary,
            {frozenset((0, 1)), frozenset((1, 2)), frozenset((2, 3)), frozenset((0, 3))},
        )
        self.assertEqual(nonmanifold, set())

    def test_edge_shared_by_three_triangles_is_nonmanifold(self):
        tris = [[0, 1, 2], [0, 1, 3], [0, 1, 4]]
        boundary, nonmanifold = cg.classify_edges(tris)
        self.assertEqual(nonmanifold, {frozenset((0, 1))})


if __name__ == "__main__":
    unittest.main()
