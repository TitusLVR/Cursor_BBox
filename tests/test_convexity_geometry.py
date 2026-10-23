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


class ExportUnitsTests(unittest.TestCase):
    """The engine validates the exported .obj, which is written at
    EXPORT_SCALE x Blender units (1 Blender cm = 1 game metre). Checking in
    Blender metres against the engine's 1e-3 tolerance lets dents up to 1 mm
    through that the engine then rejects."""

    def test_scale_is_one_blender_cm_per_engine_metre(self):
        self.assertEqual(cg.EXPORT_SCALE, 100.0)
        self.assertEqual(cg.to_export_units([(0.01, 0.0, -0.02)]), [(1.0, 0.0, -2.0)])

    def test_half_millimetre_dent_is_only_caught_in_export_units(self):
        # Cube with one top corner pushed 0.5 mm down: the two top triangles
        # are no longer coplanar, so one of them sees the sunken corner as
        # outside. In Blender metres that is 5e-4 < 1e-3 and passes; in
        # export units it is 0.05 and fails, as it does in the engine.
        verts = list(CUBE_VERTS)
        verts[6] = (1, 1, 1 - 5e-4)
        self.assertEqual(cg.violating_faces(verts, CUBE_TRIS, TOL), set())
        self.assertNotEqual(
            cg.violating_faces(cg.to_export_units(verts), CUBE_TRIS, TOL), set())

    def test_hull_of_thin_plate_passes_engine_check_in_export_units(self):
        # ConvexHull.450 from creche_02.blend (world space, Blender metres):
        # bmesh.ops.convex_hull folded this plate by 9 m. Our hull, built and
        # validated in export units, must pass the engine's tolerance there.
        import json
        data = os.path.join(os.path.dirname(__file__), "data_convexhull_450.json")
        with open(data) as fh:
            pts = cg.to_export_units(tuple(p) for p in json.load(fh))
        tris = cg.convex_hull_triangles(pts, tolerance=TOL)
        self.assertTrue(tris)
        self.assertEqual(cg.violating_faces(pts, tris, TOL), set())
        boundary, nonmanifold = cg.classify_edges(tris)
        self.assertEqual((boundary, nonmanifold), (set(), set()))


def _wedge(height, top, shift):
    """Closed lopsided box (v=8 f=12, like the hulls the engine rejects for
    centroid mismatch): base 2x2 on z=0, square top of side ``top`` at
    ``height``, pushed sideways by ``shift``."""
    t = top / 2.0
    verts = [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0),
             (-t + shift, -t, height), (t + shift, -t, height),
             (t + shift, t, height), (-t + shift, t, height)]
    tris = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
            [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
            [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]]
    return verts, tris


def _pyramid(height):
    """Closed square pyramid, base 2x2 on z=0, apex at (0, 0, height)."""
    verts = [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0), (0, 0, height)]
    tris = [[0, 2, 1], [0, 3, 2], [0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]]
    return verts, tris


class CentroidTests(unittest.TestCase):
    def test_cube_centroids_coincide(self):
        percent, volume = cg.centroid_mismatch_percent(CUBE_VERTS, CUBE_TRIS)
        self.assertAlmostEqual(percent, 0.0, places=9)
        self.assertAlmostEqual(volume, 1.0, places=9)

    def test_wedge_fails_only_the_centroid_check(self):
        verts, tris = _wedge(1.0, 0.2, 0.8)
        percent, _ = cg.centroid_mismatch_percent(verts, tris)
        self.assertGreater(percent, cg.MAX_CENTROID_MISMATCH_PERCENT)
        self.assertEqual(cg.piece_issue_kinds(verts, tris, TOL), {"Centroid"})

    def test_inside_out_cube_kinds(self):
        flipped = [[a, c, b] for a, b, c in CUBE_TRIS]
        self.assertEqual(cg.piece_issue_kinds(CUBE_VERTS, flipped, TOL), {"Convex", "Volume"})


class SplitLopsidedTests(unittest.TestCase):
    def _assert_exact_split(self, verts, tris, pieces):
        for i, (v, t) in enumerate(pieces):
            self.assertEqual(cg.piece_issue_kinds(v, t, TOL), set(), f"piece {i}")
        total = sum(cg.centroid_mismatch_percent(v, t)[1] for v, t in pieces)
        self.assertAlmostEqual(total, cg.centroid_mismatch_percent(verts, tris)[1], places=9)

    def test_clip_cube_in_half(self):
        front, back = cg.clip_convex_piece(CUBE_VERTS, CUBE_TRIS, (0.5, 0.0, 0.0), (1.0, 0.0, 0.0))
        for v, t in (front, back):
            self.assertEqual(cg.piece_issue_kinds(v, t, TOL), set())
            self.assertAlmostEqual(cg.centroid_mismatch_percent(v, t)[1], 0.5, places=9)

    def test_clip_through_vertices_stays_closed(self):
        front, back = cg.clip_convex_piece(CUBE_VERTS, CUBE_TRIS, (0.0, 0.0, 0.0), (1.0, -1.0, 0.0))
        self._assert_exact_split(CUBE_VERTS, CUBE_TRIS, [front, back])

    def test_wedge_is_split_into_passing_pieces(self):
        verts, tris = _wedge(1.0, 0.2, 0.8)
        pieces = cg.split_lopsided(verts, tris, TOL)
        self.assertIsNotNone(pieces)
        self.assertGreaterEqual(len(pieces), 2)
        self.assertLessEqual(len(pieces), cg.MAX_SPLIT_PIECES)
        self._assert_exact_split(verts, tris, pieces)

    def test_wedge_in_export_units_splits_the_same(self):
        verts, tris = _wedge(1.0, 0.2, 0.8)
        pieces = cg.split_lopsided(cg.to_export_units(verts), tris, TOL)
        self.assertIsNotNone(pieces)
        self._assert_exact_split(cg.to_export_units(verts), tris, pieces)

    def test_passing_piece_is_returned_whole(self):
        pieces = cg.split_lopsided(CUBE_VERTS, CUBE_TRIS, TOL)
        self.assertEqual(len(pieces), 1)

    def test_sharp_pyramid_cannot_be_split(self):
        verts, tris = _pyramid(10.0)
        self.assertEqual(cg.piece_issue_kinds(verts, tris, TOL), {"Centroid"})
        self.assertIsNone(cg.split_lopsided(verts, tris, TOL))

    def test_other_issues_are_not_split_away(self):
        flipped = [[a, c, b] for a, b, c in CUBE_TRIS]
        self.assertIsNone(cg.split_lopsided(CUBE_VERTS, flipped, TOL))


if __name__ == "__main__":
    unittest.main()
