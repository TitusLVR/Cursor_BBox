"""Tests for the pure brush-selection helpers (no Blender required).

Run:
    python b:\\scripts\\addons\\Cursor_BBox\\tests\\test_brush_select.py
"""
import os
import sys
import unittest

_FUNCTIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "functions")
if _FUNCTIONS_DIR not in sys.path:
    sys.path.insert(0, _FUNCTIONS_DIR)

import brush_select as bs  # noqa: E402


class ProjectTests(unittest.TestCase):
    def test_identity_projection_maps_ndc_to_region(self):
        # Identity perspective matrix: clip == world, so NDC x,y in [-1, 1]
        # map onto the region [0, w] x [0, h].
        ident = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        pts = [(0.0, 0.0, 0.0), (1.0, 1.0, 0.0), (-1.0, -1.0, 0.0)]
        out = bs.project_points(pts, ident, 200, 100)
        self.assertEqual(out[0], (100.0, 50.0))
        self.assertEqual(out[1], (200.0, 100.0))
        self.assertEqual(out[2], (0.0, 0.0))

    def test_points_behind_camera_are_dropped(self):
        # w <= 0 means behind the viewer; such points must not be returned.
        mat = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 1, 0]]  # w = z
        pts = [(0.0, 0.0, 1.0), (0.0, 0.0, -1.0), (0.0, 0.0, 0.0)]
        out = bs.project_points(pts, mat, 10, 10)
        self.assertIsNotNone(out[0])
        self.assertIsNone(out[1])
        self.assertIsNone(out[2])


class CircleTests(unittest.TestCase):
    def test_indices_inside_radius(self):
        pts = [(0, 0), (3, 4), (5.1, 0), None, (-2, -2)]
        self.assertEqual(bs.indices_in_circle(pts, (0, 0), 5.0), [0, 1, 4])

    def test_radius_is_inclusive(self):
        self.assertEqual(bs.indices_in_circle([(3, 4)], (0, 0), 5.0), [0])


class FrontFacingTests(unittest.TestCase):
    def test_perspective_uses_center_to_eye(self):
        eye = (0.0, 0.0, 10.0)
        centers = [(0, 0, 1), (0, 0, -1)]
        normals = [(0, 0, 1), (0, 0, 1)]  # both +Z; second is a back face of a box
        # Face at z=1 faces the eye, face at z=-1 with +Z normal also points
        # toward the eye (eye is above), so both are front-facing here.
        self.assertEqual(bs.front_facing(centers, normals, eye=eye), [True, True])
        normals = [(0, 0, 1), (0, 0, -1)]
        self.assertEqual(bs.front_facing(centers, normals, eye=eye), [True, False])

    def test_orthographic_uses_view_direction(self):
        view_dir = (0.0, 0.0, -1.0)  # looking down -Z
        centers = [(0, 0, 0), (5, 5, 5)]
        normals = [(0, 0, 1), (0, 0, -1)]
        self.assertEqual(bs.front_facing(centers, normals, view_dir=view_dir),
                         [True, False])

    def test_grazing_faces_count_as_back(self):
        view_dir = (0.0, 0.0, -1.0)
        self.assertEqual(bs.front_facing([(0, 0, 0)], [(1, 0, 0)], view_dir=view_dir),
                         [False])


class StrokeTests(unittest.TestCase):
    def test_add_stroke_only_adds_and_remembers_touched(self):
        marked = {1, 2}
        touched = set()
        changed = bs.apply_stroke(marked, touched, {2, 3, 4}, remove=False)
        self.assertTrue(changed)
        self.assertEqual(marked, {1, 2, 3, 4})
        self.assertEqual(touched, {2, 3, 4})

    def test_remove_stroke_only_removes(self):
        marked = {1, 2, 3}
        touched = set()
        changed = bs.apply_stroke(marked, touched, {3, 4}, remove=True)
        self.assertTrue(changed)
        self.assertEqual(marked, {1, 2})

    def test_already_touched_faces_do_not_report_change(self):
        marked = {1}
        touched = {1}
        changed = bs.apply_stroke(marked, touched, {1}, remove=False)
        self.assertFalse(changed)
        self.assertEqual(marked, {1})

    def test_drag_threshold(self):
        self.assertFalse(bs.exceeds_drag_threshold((10, 10), (12, 11), 4))
        self.assertTrue(bs.exceeds_drag_threshold((10, 10), (14, 10), 4))

    def test_radius_step_clamps(self):
        self.assertEqual(bs.step_radius(10, grow=False, minimum=10, maximum=500), 10)
        self.assertEqual(bs.step_radius(500, grow=True, minimum=10, maximum=500), 500)
        self.assertGreater(bs.step_radius(50, grow=True), 50)
        self.assertLess(bs.step_radius(50, grow=False), 50)


if __name__ == "__main__":
    unittest.main()
