"""Tests for the pure split-mode helpers (no Blender required).

Run:
    python tests/test_hull_split.py
"""
import os
import sys
import unittest

_FUNCTIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "functions")
if _FUNCTIONS_DIR not in sys.path:
    sys.path.insert(0, _FUNCTIONS_DIR)

import hull_split as hs  # noqa: E402

EPS = 1e-9
SQUARE = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0))


def _cube_polys(size=1.0):
    s = size
    v = [(0, 0, 0), (s, 0, 0), (s, s, 0), (0, s, 0),
         (0, 0, s), (s, 0, s), (s, s, s), (0, s, s)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return tuple(tuple(tuple(float(c) for c in v[i]) for i in f) for f in faces)


def _bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


class ClipTests(unittest.TestCase):
    def test_polygon_on_one_side_is_returned_by_identity(self):
        front, back = hs.clip_polygon(SQUARE, (2.0, 0, 0), (1.0, 0, 0), EPS)
        self.assertIsNone(front)
        self.assertIs(back, SQUARE)
        front, back = hs.clip_polygon(SQUARE, (-2.0, 0, 0), (1.0, 0, 0), EPS)
        self.assertIs(front, SQUARE)
        self.assertIsNone(back)

    def test_polygon_in_plane_goes_to_the_side_of_its_solid(self):
        # Opposite to its own normal: whichever way the plane normal points,
        # the square ends up on exactly one side, and flipping the plane
        # normal flips that side.
        f1, b1 = hs.clip_polygon(SQUARE, (0, 0, 0), (0, 0, 1.0), EPS)
        f2, b2 = hs.clip_polygon(SQUARE, (0, 0, 0), (0, 0, -1.0), EPS)
        self.assertEqual(sorted([f1 is SQUARE, b1 is SQUARE]), [False, True])
        self.assertEqual((f1 is None, b1 is None), (f2 is not None, b2 is not None))
        flipped = tuple(reversed(SQUARE))
        f3, b3 = hs.clip_polygon(flipped, (0, 0, 0), (0, 0, 1.0), EPS)
        self.assertEqual((f3 is None, b3 is None), (f1 is not None, b1 is not None))

    def test_degenerate_polygon_in_plane_goes_to_both_sides(self):
        line = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0))
        front, back = hs.clip_polygon(line, (0, 0, 0), (0, 0, 1.0), EPS)
        self.assertIs(front, line)
        self.assertIs(back, line)

    def test_straddling_square_is_split(self):
        front, back = hs.clip_polygon(SQUARE, (0.5, 0, 0), (1.0, 0, 0), EPS)
        self.assertEqual(_bbox(front), ((0.5, 0.0, 0.0), (1.0, 1.0, 0.0)))
        self.assertEqual(_bbox(back), ((0.0, 0.0, 0.0), (0.5, 1.0, 0.0)))
        self.assertEqual(len(front), 4)
        self.assertEqual(len(back), 4)

    def test_second_cut_produces_corner_of_both_cut_lines(self):
        _, back = hs.clip_polygon(SQUARE, (0.5, 0, 0), (1.0, 0, 0), EPS)
        _, quarter = hs.clip_polygon(back, (0, 0.5, 0), (0, 1.0, 0), EPS)
        self.assertIsNotNone(quarter)
        self.assertIn((0.5, 0.5, 0.0), quarter)
        self.assertEqual(_bbox(quarter), ((0.0, 0.0, 0.0), (0.5, 0.5, 0.0)))
        self.assertEqual(len(quarter), 4)

    def test_points_within_eps_belong_to_both_sides(self):
        # Plane through the square's edge x=1 (shifted by less than eps).
        eps = 1e-6
        front, back = hs.clip_polygon(SQUARE, (1.0 + 1e-7, 0, 0), (1.0, 0, 0), eps)
        # Whole square is behind or on the plane: back is the square itself,
        # front would only be the degenerate edge -> None.
        self.assertIs(back, SQUARE)
        self.assertIsNone(front)

    def test_plane_through_vertex(self):
        tri = ((0.0, 0.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0))
        # Plane x=0 touches the vertex at the origin only.
        front, back = hs.clip_polygon(tri, (0, 0, 0), (1.0, 0, 0), EPS)
        self.assertIs(front, tri)
        self.assertIsNone(back)
        # Plane y=0 through vertex 0 splits the triangle into two.
        front, back = hs.clip_polygon(tri, (0, 0, 0), (0, 1.0, 0), EPS)
        self.assertEqual(len(front), 3)
        self.assertEqual(len(back), 3)
        self.assertIn((1.0, 0.0, 0.0), front)
        self.assertIn((1.0, 0.0, 0.0), back)

    def test_concave_ngon_does_not_crash(self):
        # U shape, cut across both prongs.
        u = ((0.0, 0.0, 0.0), (3.0, 0.0, 0.0), (3.0, 3.0, 0.0), (2.0, 3.0, 0.0),
             (2.0, 1.0, 0.0), (1.0, 1.0, 0.0), (1.0, 3.0, 0.0), (0.0, 3.0, 0.0))
        front, back = hs.clip_polygon(u, (0, 2.0, 0), (0, 1.0, 0), EPS)
        self.assertIsNotNone(front)
        self.assertIsNotNone(back)
        for p in front:
            self.assertGreaterEqual(p[1], 2.0 - 1e-9)
        for p in back:
            self.assertLessEqual(p[1], 2.0 + 1e-9)

    def test_degenerate_polygons(self):
        self.assertEqual(hs.clip_polygon((), (0, 0, 0), (1, 0, 0), EPS), (None, None))
        line = ((0.0, 0, 0), (1.0, 0, 0))
        self.assertEqual(hs.clip_polygon(line, (0.5, 0, 0), (1, 0, 0), EPS), (None, None))
        zero_area = ((0.0, 0, 0), (1.0, 0, 0), (2.0, 0, 0))
        front, back = hs.clip_polygon(zero_area, (0.5, 0, 0), (1, 0, 0), EPS)
        # Must not crash; whatever survives has at least 3 points.
        for side in (front, back):
            if side is not None:
                self.assertGreaterEqual(len(side), 3)


class SplitPolygonsTests(unittest.TestCase):
    def test_untouched_polygons_are_shared(self):
        polys = _cube_polys()
        front, back = hs.split_polygons(polys, (0.5, 0, 0), (1.0, 0, 0), EPS)
        # Face x=1 (index 3) is wholly in front, x=0 (index 5) wholly behind.
        self.assertTrue(any(p is polys[3] for p in front))
        self.assertTrue(any(p is polys[5] for p in back))
        self.assertFalse(any(p is polys[3] for p in back))

    def test_cube_split_halves(self):
        polys = _cube_polys()
        front, back = hs.split_polygons(polys, (0.5, 0, 0), (1.0, 0, 0), EPS)
        self.assertEqual(_bbox(hs.unique_points(front)), ((0.5, 0, 0), (1, 1, 1)))
        self.assertEqual(_bbox(hs.unique_points(back)), ((0, 0, 0), (0.5, 1, 1)))
        self.assertTrue(hs.is_solid(hs.unique_points(front), EPS))
        self.assertTrue(hs.is_solid(hs.unique_points(back), EPS))

    def test_plane_missing_the_geometry(self):
        polys = _cube_polys()
        front, back = hs.split_polygons(polys, (5.0, 0, 0), (1.0, 0, 0), EPS)
        self.assertEqual(front, ())
        self.assertEqual(len(back), len(polys))


class HelperTests(unittest.TestCase):
    def test_unique_points(self):
        pts = hs.unique_points(_cube_polys())
        self.assertEqual(len(pts), 8)

    def test_extent_and_eps(self):
        self.assertAlmostEqual(hs.extent(_cube_polys(2.0)), 12 ** 0.5)
        self.assertEqual(hs.extent(()), 0.0)
        self.assertEqual(hs.plane_eps(()), 1e-9)
        self.assertAlmostEqual(hs.plane_eps(_cube_polys(2.0)), 1e-6 * 12 ** 0.5)

    def test_is_solid_on_flat_input(self):
        self.assertFalse(hs.is_solid(list(SQUARE), EPS))
        self.assertFalse(hs.is_solid([(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)], EPS))
        self.assertFalse(hs.is_solid([(0, 0, 0)] * 5, EPS))
        self.assertFalse(hs.is_solid(list(SQUARE)[:3], EPS))
        self.assertTrue(hs.is_solid(list(SQUARE) + [(0.0, 0.0, 1.0)], EPS))

    def test_equal_planes(self):
        planes = hs.equal_planes(_cube_polys(), (0, 0, 2.0), 4)
        self.assertEqual(len(planes), 3)
        for got, want in zip(planes, (0.25, 0.5, 0.75)):
            self.assertAlmostEqual(got[2], want)
            self.assertAlmostEqual(got[0], 0.0)
        self.assertEqual(hs.equal_planes(_cube_polys(), (0, 0, 1.0), 1), [])
        self.assertEqual(hs.equal_planes((SQUARE,), (0, 0, 1.0), 3), [])
        self.assertEqual(hs.equal_planes(_cube_polys(), (0, 0, 0), 3), [])

    def test_equal_slabs_split_cube(self):
        polys = _cube_polys()
        normal = (1.0, 0.0, 0.0)
        eps = hs.plane_eps(polys)
        slabs = []
        remaining = polys
        for co in hs.equal_planes(polys, normal, 3):
            front, back = hs.split_polygons(remaining, co, normal, eps)
            slabs.append(back)
            remaining = front
        slabs.append(remaining)
        self.assertEqual(len(slabs), 3)
        for i, slab in enumerate(slabs):
            lo, hi = _bbox(hs.unique_points(slab))
            self.assertAlmostEqual(lo[0], i / 3)
            self.assertAlmostEqual(hi[0], (i + 1) / 3)
            self.assertTrue(hs.is_solid(hs.unique_points(slab), eps))

    def test_facing_alpha(self):
        self.assertAlmostEqual(hs.facing_alpha(1.0, 0.2), 0.2)
        self.assertAlmostEqual(hs.facing_alpha(2.0, 0.2), 0.2)
        self.assertAlmostEqual(hs.facing_alpha(1e-9, 0.2), 0.2 * 0.35, places=6)
        self.assertAlmostEqual(hs.facing_alpha(0.5, 0.2), 0.2 * (0.35 + 0.325))
        self.assertAlmostEqual(hs.facing_alpha(0.0, 0.2), 0.2 * 0.12)
        self.assertAlmostEqual(hs.facing_alpha(-1.0, 0.2), 0.2 * 0.12)

    def test_plane_key_same_for_points_of_one_plane(self):
        n = (0.0, 0.0, 1.0)
        a = hs.plane_key(n, (0.0, 0.0, 0.5), 2.0)
        b = hs.plane_key(n, (3.0, -7.0, 0.5), 2.0)
        self.assertEqual(a, b)
        # A shift of a fraction of the quantisation step keeps the key ...
        self.assertEqual(a, hs.plane_key(n, (0.0, 0.0, 0.5 + 1e-7), 2.0))
        # ... a visible shift changes it.
        self.assertNotEqual(a, hs.plane_key(n, (0.0, 0.0, 0.51), 2.0))
        self.assertNotEqual(a, hs.plane_key((0.0, 1.0, 0.0), (0.0, 0.0, 0.5), 2.0))
        self.assertEqual(hs.plane_key((-0.0, 0.0, 1.0), (0, 0, 0), 1.0),
                         hs.plane_key((0.0, 0.0, 1.0), (0, 0, 0), 1.0))
        hash(a)

    def test_plane_key_degenerate(self):
        self.assertIsNone(hs.plane_key((float('nan'), 0.0, 1.0), (0, 0, 0), 1.0))
        self.assertIsNone(hs.plane_key((0.0, 0.0, 1.0), (0, 0, float('inf')), 1.0))
        self.assertIsNotNone(hs.plane_key((0.0, 0.0, 1.0), (0, 0, 1.0), 0.0))


def _box_polys(lo, hi):
    """Six quads of the axis-aligned box lo..hi (outward winding)."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return tuple(tuple(tuple(float(c) for c in v[i]) for i in f) for f in faces)


def _box_tris(lo, hi):
    out = []
    for quad in _box_polys(lo, hi):
        out.extend((quad[0], quad[1], quad[2], quad[0], quad[2], quad[3]))
    return out


def _box_volume(b):
    return ((b[1][0] - b[0][0]) * (b[1][1] - b[0][1]) * (b[1][2] - b[0][2]))


def _fake_union(boxes):
    """union_volume for plan_merges: volume of the members' union bbox."""
    calls = []

    def union_volume(members):
        calls.append(members)
        it = iter(sorted(members))
        b = boxes[next(it)]
        for i in it:
            b = hs.bbox_union(b, boxes[i])
        return _box_volume(b)
    return union_volume, calls


class IslandTests(unittest.TestCase):
    def test_two_separate_cubes_and_order(self):
        a = _box_polys((0, 0, 0), (1, 1, 1))
        b = _box_polys((3, 0, 0), (4, 1, 1))
        # Interleave the polygons: islands still come out by first polygon.
        polys = tuple(p for pair in zip(b, a) for p in pair)
        islands = hs.split_islands(polys)
        self.assertEqual(len(islands), 2)
        self.assertEqual(set(islands[0]), set(b))
        self.assertEqual(set(islands[1]), set(a))
        self.assertIs(islands[0][0], polys[0])

    def test_rounding_joins_nearly_equal_points(self):
        t1 = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        t2 = ((1.0 + 1e-9, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 1.0, 0.0))
        self.assertEqual(len(hs.split_islands((t1, t2))), 1)
        self.assertEqual(len(hs.split_islands((t1, t2), digits=12)), 2)

    def test_chain_merges_into_one_island(self):
        polys = tuple(((float(i), 0.0, 0.0), (i + 1.0, 0.0, 0.0), (i + 0.5, 1.0, 0.0))
                      for i in range(2000))
        islands = hs.split_islands(polys)
        self.assertEqual(len(islands), 1)
        self.assertEqual(len(islands[0]), 2000)

    def test_many_polygons_are_fast_enough(self):
        polys = []
        for i in range(10000):
            x = i * 3.0
            polys.append(((x, 0.0, 0.0), (x + 1, 0.0, 0.0), (x, 1.0, 0.0)))
        self.assertEqual(len(hs.split_islands(polys)), 10000)

    def test_empty_and_single(self):
        self.assertEqual(hs.split_islands(()), [])
        self.assertEqual(hs.split_islands((SQUARE,)), [(SQUARE,)])


class VolumeAndBoxTests(unittest.TestCase):
    def test_tris_volume(self):
        self.assertAlmostEqual(hs.tris_volume(_box_tris((0, 0, 0), (1, 1, 1))), 1.0)
        self.assertAlmostEqual(hs.tris_volume(_box_tris((1, 2, 3), (3, 3, 4))), 2.0)
        flipped = list(reversed(_box_tris((0, 0, 0), (2, 1, 1))))
        self.assertAlmostEqual(hs.tris_volume(flipped), 2.0)
        self.assertEqual(hs.tris_volume([]), 0.0)

    def test_bbox_and_gap(self):
        self.assertIsNone(hs.bbox([]))
        a = hs.bbox([(0, 0, 0), (1, 1, 1)])
        self.assertEqual(a, ((0, 0, 0), (1, 1, 1)))
        self.assertEqual(hs.bbox_gap(a, ((1, 0, 0), (2, 1, 1))), 0.0)    # touch
        self.assertEqual(hs.bbox_gap(a, ((0.5, 0.5, 0.5), (3, 3, 3))), 0.0)  # overlap
        self.assertAlmostEqual(hs.bbox_gap(a, ((3, 0, 0), (4, 1, 1))), 2.0)
        self.assertAlmostEqual(hs.bbox_gap(a, ((4, 5, 0), (5, 6, 1))), 5.0)
        self.assertEqual(hs.bbox_union(a, ((3, -1, 0), (4, 0, 2))), ((0, -1, 0), (4, 1, 2)))

    def test_min_width(self):
        pts = hs.unique_points(_box_polys((0, 0, 0), (4, 2, 0.1)))
        normals = [(1.0, 0, 0), (0, 1.0, 0), (0, 0, -1.0), (0.0, 0.0, 0.0)]
        self.assertAlmostEqual(hs.min_width(pts, normals), 0.1)
        self.assertEqual(hs.min_width([], normals), 0.0)
        self.assertEqual(hs.min_width(pts, []), 0.0)
        self.assertEqual(hs.min_width(pts, [(0.0, 0.0, 0.0)]), 0.0)


class PlanMergesTests(unittest.TestCase):
    def _run(self, boxes, gap, cost):
        union, calls = _fake_union(boxes)
        vols = [_box_volume(b) for b in boxes]
        return hs.plan_merges(vols, boxes, gap, cost, union), calls

    def test_adjacent_boxes_merge_far_box_does_not(self):
        boxes = [((0, 0, 0), (1, 1, 1)), ((1, 0, 0), (2, 1, 1)), ((10, 0, 0), (11, 1, 1))]
        groups, _ = self._run(boxes, 0.01, 0.25)
        self.assertEqual(groups, [[0, 1], [2]])

    def test_cost_over_max_does_not_merge(self):
        # Diagonal neighbours: union bbox 8, members 1 + 1 -> cost 0.75.
        boxes = [((0, 0, 0), (1, 1, 1)), ((1, 1, 1), (2, 2, 2))]
        groups, _ = self._run(boxes, 0.01, 0.5)
        self.assertEqual(groups, [[0], [1]])
        groups, _ = self._run(boxes, 0.01, 0.75)
        self.assertEqual(groups, [[0, 1]])

    def test_lowest_cost_first(self):
        # 0-1 adjacent (cost 0), 1-2 diagonal-ish (cost > 0): with a loose
        # threshold everything merges, with a tight one only the cheap pair.
        boxes = [((0, 0, 0), (1, 1, 1)), ((1, 0, 0), (2, 1, 1)), ((2, 0.5, 0), (3, 1.5, 1))]
        groups, _ = self._run(boxes, 0.01, 0.1)
        self.assertEqual(groups, [[0, 1]] + [[2]])
        groups, _ = self._run(boxes, 0.01, 0.5)
        self.assertEqual(groups, [[0, 1, 2]])

    def test_gap_prefilter_skips_union_volume(self):
        boxes = [((0, 0, 0), (1, 1, 1)), ((5, 0, 0), (6, 1, 1)), ((10, 0, 0), (11, 1, 1))]
        groups, calls = self._run(boxes, 0.5, 0.95)
        self.assertEqual(groups, [[0], [1], [2]])
        self.assertEqual(calls, [])

    def test_zero_volume_items(self):
        # Two flat sheets in one plane: union volume 0 -> never merged.
        boxes = [((0, 0, 0), (1, 1, 0)), ((1, 0, 0), (2, 1, 0))]
        groups, _ = self._run(boxes, 0.01, 0.95)
        self.assertEqual(groups, [[0], [1]])
        # A sheet on top of a box merges at cost 0 (adds no volume).
        boxes = [((0, 0, 0), (1, 1, 1)), ((0, 0, 1), (1, 1, 1))]
        groups, _ = self._run(boxes, 0.01, 0.0)
        self.assertEqual(groups, [[0, 1]])

    def test_deterministic_and_cached(self):
        boxes = [((i * 1.0, 0, 0), (i + 1.0, 1, 1)) for i in range(12)]
        boxes += [((i * 1.0, 3, 0), (i + 1.0, 4, 1)) for i in range(12)]
        g1, calls = self._run(boxes, 0.01, 0.2)
        g2, _ = self._run(list(boxes), 0.01, 0.2)
        self.assertEqual(g1, g2)
        self.assertEqual(g1, [list(range(12)), list(range(12, 24))])
        # Cached pair costs: never asked twice for the same member set.
        self.assertEqual(len(calls), len(set(calls)))

    def test_empty(self):
        self.assertEqual(hs.plan_merges([], [], 0.1, 0.5, lambda m: 1.0), [])
        self.assertEqual(hs.plan_merges([1.0], [((0, 0, 0), (1, 1, 1))], 0.1, 0.5,
                                        lambda m: 1.0), [[0]])


if __name__ == "__main__":
    unittest.main()
