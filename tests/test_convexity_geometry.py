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
