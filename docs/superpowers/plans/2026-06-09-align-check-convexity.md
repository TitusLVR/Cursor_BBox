# Align check_convexity.py with collision_mesh_geometry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Blender addon's convexity validation use `collision_mesh_geometry` as the single source of truth — replacing the weak centroid-plane test with the package's correct per-vertex convex test and adding watertight/manifold checks — while keeping the operator's edit-mode selection of offending geometry.

**Architecture:** Pure geometry logic (per-face convex violations, boundary/non-manifold edge identities) lives in a new bpy-free module `functions/convexity_geometry.py` so it can be unit-tested outside Blender; it reuses the package's primitives and tolerance. The bpy/bmesh glue in `operators/check_convexity.py` extracts `(verts, tris)` from a triangulated bmesh, calls the package for the verdict, calls the pure helpers for selection identities, and maps results back to original mesh elements.

**Tech Stack:** Python, Blender `bpy`/`bmesh`/`mathutils`, `collision_mesh_geometry` (on `PYTHONPATH`), `unittest` for the pure-geometry tests.

**Spec:** `docs/superpowers/specs/2026-06-09-align-check-convexity-design.md`

---

## File Structure

- **Create** `functions/convexity_geometry.py` — pure helpers `violating_faces(vertices, triangles, tolerance)` and `classify_edges(triangles)`. Imports `collision_mesh_geometry` only; **no `bpy`/`bmesh`**.
- **Create** `tests/test_convexity_geometry.py` — `unittest` tests for the two pure helpers.
- **Modify** `operators/check_convexity.py` — guarded package import, `ConvexityResult` namedtuple, reworked `check_mesh_convexity`, reworked `CursorBBox_OT_check_convexity.execute`, realigned `fix_invalid_faces` verification.

The package `s:\packages\collision_mesh_geometry` is **not** modified.

**Prerequisite for running tests:** `s:\packages` on `PYTHONPATH`. PowerShell:
```powershell
$env:PYTHONPATH = "s:\packages"
```

---

## Task 1: Pure geometry helpers (TDD, bpy-free)

**Files:**
- Create: `functions/convexity_geometry.py`
- Test: `tests/test_convexity_geometry.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_convexity_geometry.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```powershell
$env:PYTHONPATH = "s:\packages"
python b:\scripts\addons\Cursor_BBox\tests\test_convexity_geometry.py
```
Expected: FAIL — `ModuleNotFoundError: No module named 'convexity_geometry'`.

- [ ] **Step 3: Write minimal implementation**

Create `functions/convexity_geometry.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```powershell
$env:PYTHONPATH = "s:\packages"
python b:\scripts\addons\Cursor_BBox\tests\test_convexity_geometry.py
```
Expected: PASS — `OK` with 8 tests run.

- [ ] **Step 5: Commit**

```powershell
git add functions/convexity_geometry.py tests/test_convexity_geometry.py
git commit -m "feat: add bpy-free convexity geometry helpers with tests"
```

---

## Task 2: Guarded import, ConvexityResult, reworked check_mesh_convexity

**Files:**
- Modify: `operators/check_convexity.py:1-64`

This task changes the bpy/bmesh analysis core. Automated verification happens in Task 5 (inside Blender); here, verify the module still imports and the addon registers.

- [ ] **Step 1: Replace the imports and add the guarded package import + namedtuple**

Replace the top of the file (`operators/check_convexity.py:1-3`):

```python
import bpy
import bmesh
from mathutils import Vector
```

with:

```python
from collections import namedtuple

import bpy
import bmesh
from mathutils import Vector

try:
    import collision_mesh_geometry as cmg
    from collision_mesh_geometry import validate_obj
    from ..functions.convexity_geometry import violating_faces, classify_edges
    GEOMETRY_AVAILABLE = True
except ImportError:
    cmg = None
    validate_obj = None
    violating_faces = None
    classify_edges = None
    GEOMETRY_AVAILABLE = False

GEOMETRY_IMPORT_ERROR = (
    "collision_mesh_geometry is not importable - ensure s:\\packages is on PYTHONPATH"
)

ConvexityResult = namedtuple(
    "ConvexityResult",
    [
        "is_clean",
        "total_faces",
        "invalid_faces",
        "degenerate_faces",
        "worst_outside",
        "worst_face",
        "boundary_count",
        "nonmanifold_count",
        "boundary_edges",
        "nonmanifold_edges",
    ],
)
```

- [ ] **Step 2: Replace `check_mesh_convexity` entirely**

Replace the whole `check_mesh_convexity` function (`operators/check_convexity.py:6-64`, from `def check_mesh_convexity` through its `finally: bm.free()`) with:

```python
def _clean_result(total_faces):
    return ConvexityResult(
        True, total_faces, set(), set(), 0.0, -1, 0, 0, set(), set()
    )


def check_mesh_convexity(mesh_obj):
    """Validate a mesh object against the collision_mesh_geometry policy.

    Triangulates internally, extracts world-space vertices/triangles, and uses
    the package as the single source of truth: ``check_convex`` for the worst
    violation, ``check_watertight`` for boundary/non-manifold counts, and
    ``triangle_is_degenerate`` for zero-area triangles. The pure helpers
    ``violating_faces`` / ``classify_edges`` provide per-element identities for
    edit-mode selection. Triangle indices are mapped back to original polygon
    indices, and edge identities use original vertex indices (triangulation adds
    no vertices and its diagonals are always interior manifold edges).

    Returns a ``ConvexityResult``.
    """
    mesh = mesh_obj.data
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.transform(mesh_obj.matrix_world)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        original_count = len(bm.faces)
        if len(bm.verts) < 4 or original_count == 0:
            return _clean_result(original_count)

        orig_index_of = {f: f.index for f in bm.faces}

        tri_result = bmesh.ops.triangulate(bm, faces=bm.faces[:])
        face_map = tri_result['face_map']
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm.verts.index_update()

        verts = [(v.co.x, v.co.y, v.co.z) for v in bm.verts]
        tris = [[v.index for v in f.verts] for f in bm.faces]

        tolerance = validate_obj.CONVEXITY_TOLERANCE

        worst_outside, worst_tri = cmg.check_convex(verts, tris)
        boundary_count, nonmanifold_count, _ = cmg.check_watertight(tris)
        boundary_edges, nonmanifold_edges = classify_edges(tris)

        def orig_polygon(tri_index):
            tri_face = bm.faces[tri_index]
            source = face_map.get(tri_face, tri_face)
            return orig_index_of[source]

        worst_face = -1
        if 0 <= worst_tri < len(bm.faces):
            worst_face = orig_polygon(worst_tri)

        degenerate_orig = set()
        for i, tri in enumerate(tris):
            if cmg.triangle_is_degenerate(verts[tri[0]], verts[tri[1]], verts[tri[2]]):
                degenerate_orig.add(orig_polygon(i))

        invalid_orig = {orig_polygon(i) for i in violating_faces(verts, tris, tolerance)}
        invalid_orig -= degenerate_orig

        is_clean = (
            not invalid_orig
            and not degenerate_orig
            and boundary_count == 0
            and nonmanifold_count == 0
        )

        return ConvexityResult(
            is_clean,
            original_count,
            invalid_orig,
            degenerate_orig,
            worst_outside,
            worst_face,
            boundary_count,
            nonmanifold_count,
            boundary_edges,
            nonmanifold_edges,
        )
    finally:
        bm.free()
```

- [ ] **Step 3: Verify the module imports cleanly**

Run (no Blender needed — just byte-compile to catch syntax/name errors):
```powershell
python -m py_compile b:\scripts\addons\Cursor_BBox\operators\check_convexity.py
```
Expected: no output, exit code 0.

- [ ] **Step 4: Commit**

```powershell
git add operators/check_convexity.py
git commit -m "feat: rework check_mesh_convexity to use collision_mesh_geometry"
```

---

## Task 3: Rework the Check Convexity operator (face + edge selection)

**Files:**
- Modify: `operators/check_convexity.py` — `CursorBBox_OT_check_convexity.execute` (currently around lines 268-333)

- [ ] **Step 1: Replace the `execute` method of `CursorBBox_OT_check_convexity`**

Replace the entire `def execute(self, context):` body of `CursorBBox_OT_check_convexity` with:

```python
    def execute(self, context):
        if not GEOMETRY_AVAILABLE:
            self.report({'ERROR'}, GEOMETRY_IMPORT_ERROR)
            return {'CANCELLED'}

        if context.active_object and context.active_object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        mesh_objects = [
            obj for obj in context.selected_objects if obj.type == 'MESH'
        ]
        if not mesh_objects:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}

        bad_objects = []
        clean_count = 0

        for obj in mesh_objects:
            result = check_mesh_convexity(obj)
            if result.is_clean:
                clean_count += 1
            else:
                bad_objects.append((obj, result))

        total = len(mesh_objects)

        if not bad_objects:
            self.report({'INFO'}, f"All {total} selected mesh(es) are convex")
            return {'FINISHED'}

        for obj, result in bad_objects:
            parts = []
            if result.invalid_faces:
                detail = f"{len(result.invalid_faces)} non-convex"
                if result.worst_face >= 0:
                    detail += (
                        f" (worst {result.worst_outside:.4f}m"
                        f" @ face {result.worst_face})"
                    )
                parts.append(detail)
            if result.degenerate_faces:
                parts.append(f"{len(result.degenerate_faces)} degenerate")
            if result.boundary_count:
                parts.append(f"{result.boundary_count} boundary")
            if result.nonmanifold_count:
                parts.append(f"{result.nonmanifold_count} non-manifold")
            self.report(
                {'WARNING'},
                f"\"{obj.name}\": {' + '.join(parts)} / {result.total_faces} faces",
            )

        self.report(
            {'WARNING'},
            f"{len(bad_objects)}/{total} mesh(es) have issues ({clean_count} clean)",
        )

        bpy.ops.object.select_all(action='DESELECT')
        for obj, _ in bad_objects:
            obj.select_set(True)
        context.view_layer.objects.active = bad_objects[0][0]

        bpy.ops.object.mode_set(mode='EDIT')
        context.tool_settings.mesh_select_mode = (False, True, True)
        bpy.ops.mesh.select_all(action='DESELECT')

        for obj, result in bad_objects:
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            for idx in (result.invalid_faces | result.degenerate_faces):
                if idx < len(bm.faces):
                    bm.faces[idx].select = True

            wanted_edges = result.boundary_edges | result.nonmanifold_edges
            if wanted_edges:
                for edge in bm.edges:
                    key = frozenset((edge.verts[0].index, edge.verts[1].index))
                    if key in wanted_edges:
                        edge.select = True

            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)

        return {'FINISHED'}
```

- [ ] **Step 2: Verify the module still compiles**

Run:
```powershell
python -m py_compile b:\scripts\addons\Cursor_BBox\operators\check_convexity.py
```
Expected: no output, exit code 0.

- [ ] **Step 3: Commit**

```powershell
git add operators/check_convexity.py
git commit -m "feat: select non-convex faces and boundary/non-manifold edges in Check Convexity"
```

---

## Task 4: Realign Fix Convexity verification to the package test

**Files:**
- Modify: `operators/check_convexity.py` — `fix_invalid_faces` (currently around lines 67-162), the convexity re-check block (currently lines 114-154) and the guard in `CursorBBox_OT_fix_convexity.execute`.

The repair actions (delete degenerate faces, weld, recalc normals, flip-if-inward) stay; only the convexity re-check changes from the centroid-plane test to the package's per-vertex test via a shared helper.

- [ ] **Step 1: Add a bmesh-side evaluation helper above `fix_invalid_faces`**

Insert this helper immediately before `def fix_invalid_faces(`:

```python
def _evaluate_convexity(bm, tolerance):
    """Count convexity-violating triangles for the current bmesh geometry.

    Triangulates a throwaway copy (so the live bmesh is untouched) and runs the
    same per-vertex convex test used by ``check_mesh_convexity``. Returns
    ``(triangle_count, violating_count)``.
    """
    eval_bm = bm.copy()
    try:
        bmesh.ops.triangulate(eval_bm, faces=eval_bm.faces[:])
        eval_bm.verts.ensure_lookup_table()
        eval_bm.verts.index_update()
        verts = [(v.co.x, v.co.y, v.co.z) for v in eval_bm.verts]
        tris = [[v.index for v in f.verts] for f in eval_bm.faces]
        return len(tris), len(violating_faces(verts, tris, tolerance))
    finally:
        eval_bm.free()
```

- [ ] **Step 2: Replace the normals/remaining block inside `fix_invalid_faces`**

Replace the block from `bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])` through the end of the `remaining` computation (currently `operators/check_convexity.py:123-154`, i.e. the recalc call, the centroid computation, the inward/outward count, the conditional `reverse_faces`, and the per-face `remaining` loop ending just before `bm.transform(inv_mat)`) with:

```python
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.normal_update()

        tolerance = validate_obj.CONVEXITY_TOLERANCE
        _, violations_before = _evaluate_convexity(bm, tolerance)
        remaining = violations_before

        # If most faces report violations, recalc picked inward winding; flip all
        # and re-evaluate with the same package test.
        tri_count, _ = _evaluate_convexity(bm, tolerance)
        if violations_before * 2 > tri_count:
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
            bm.normal_update()
            _, remaining = _evaluate_convexity(bm, tolerance)

        normals_fixed = max(0, violations_before - remaining)
```

Note: the early-return branch for an emptied mesh (currently `operators/check_convexity.py:117-121`, `if len(bm.faces) == 0: ... return degen_count, welded, 0, 0`) is unchanged and still precedes this block.

- [ ] **Step 3: Add the import guard to `CursorBBox_OT_fix_convexity.execute`**

At the very start of `CursorBBox_OT_fix_convexity.execute` (before the `mode_set` call), insert:

```python
        if not GEOMETRY_AVAILABLE:
            self.report({'ERROR'}, GEOMETRY_IMPORT_ERROR)
            return {'CANCELLED'}
```

- [ ] **Step 4: Verify the module compiles**

Run:
```powershell
python -m py_compile b:\scripts\addons\Cursor_BBox\operators\check_convexity.py
```
Expected: no output, exit code 0.

- [ ] **Step 5: Commit**

```powershell
git add operators/check_convexity.py
git commit -m "feat: realign Fix Convexity verification to package convex test"
```

---

## Task 5: In-Blender integration verification (blender-mcp)

**Files:** none (verification only). Use the `blender-mcp` skill to run Python in the user's Blender.

This verifies the bpy/bmesh paths that the unittest in Task 1 cannot reach, and confirms parity with the package on live geometry.

- [ ] **Step 1: Reload the addon in Blender**

Via blender-mcp, reload the `Cursor_BBox` addon (disable/enable or `importlib.reload` of the operators) so the new code is active. Confirm no import errors in the console and that `cursor_bbox.check_convexity` is registered.

- [ ] **Step 2: Run the verification script in Blender**

Run this script via blender-mcp; it builds known meshes and asserts `check_mesh_convexity` results directly (independent of UI):

```python
import bmesh
import bpy
from Cursor_BBox.operators.check_convexity import check_mesh_convexity, GEOMETRY_AVAILABLE

assert GEOMETRY_AVAILABLE, "collision_mesh_geometry not importable in Blender"


def _make_obj(name, build):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


# 1. Convex cube -> clean.
cube = _make_obj("t_cube", lambda bm: bmesh.ops.create_cube(bm, size=2.0))
r = check_mesh_convexity(cube)
assert r.is_clean, r
assert r.boundary_count == 0 and r.nonmanifold_count == 0, r

# 2. Cube with one vertex pushed inward -> non-convex flagged.
dent = _make_obj("t_dent", lambda bm: bmesh.ops.create_cube(bm, size=2.0))
dm = dent.data
dm.vertices[0].co.x *= 0.2
dm.vertices[0].co.y *= 0.2
dm.vertices[0].co.z *= 0.2
r = check_mesh_convexity(dent)
assert not r.is_clean and len(r.invalid_faces) > 0, r
assert r.worst_outside > 1e-3, r

# 3. Cube with a face deleted -> boundary edges.
hole = _make_obj("t_hole", lambda bm: bmesh.ops.create_cube(bm, size=2.0))
bm = bmesh.new(); bm.from_mesh(hole.data); bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.faces[0]], context='FACES')
bm.to_mesh(hole.data); bm.free()
r = check_mesh_convexity(hole)
assert r.boundary_count > 0 and not r.is_clean, r

print("check_mesh_convexity integration checks passed")
```

Expected: prints `check_mesh_convexity integration checks passed` with no `AssertionError`.

- [ ] **Step 3: Verify operator selection behavior**

Select the dented cube from Step 2 in the viewport and invoke **Check Convexity** (`bpy.ops.cursor_bbox.check_convexity()` via MCP, or from the panel). Confirm:
- A WARNING report naming the object with a `non-convex` count and worst distance.
- The object enters EDIT mode with the offending face(s) selected.

Invoke **Check Convexity** on the holed cube and confirm boundary edges are selected in edit mode (select mode shows edges).

- [ ] **Step 4: Verify the missing-package error path**

This is covered by code review of the guard (`if not GEOMETRY_AVAILABLE: report ERROR; CANCELLED`) plus the `except ImportError` block from Task 2 — no separate run needed unless `PYTHONPATH` can be unset in a scratch Blender. Confirm by reading the guard is present in both operators.

- [ ] **Step 5: Final commit (if any verification fixes were needed)**

```powershell
git add -A
git commit -m "test: verify convexity alignment in Blender"
```

---

## Self-Review notes

- **Spec coverage:** package import + guard (Task 2/3/4), per-vertex convex verdict via `check_convex` (Task 2), per-face violation selection via `violating_faces` (Task 1+2), degenerate via `triangle_is_degenerate` (Task 2), watertight/manifold counts via `check_watertight` + edge identities via `classify_edges` (Task 1+2), face+edge edit-mode selection (Task 3), Fix operator re-verification realigned (Task 4), fidelity via shared package math (Tasks 1-4), tolerance from `validate_obj.CONVEXITY_TOLERANCE` (Task 2/4). Excluded checks (volume/centroid/non-triangle) are not added. All covered.
- **Type consistency:** `ConvexityResult` fields defined in Task 2 are exactly the ones read in Task 3. Helper names `violating_faces`/`classify_edges` are consistent across Tasks 1, 2, 4. `_evaluate_convexity` defined and used only in Task 4.
- **No placeholders:** every code step contains full code; the one inline substitution (`validate_obj_tol()` → `1e-3`) is called out explicitly.
