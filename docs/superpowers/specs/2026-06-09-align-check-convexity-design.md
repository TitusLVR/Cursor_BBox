# Align `check_convexity.py` with `collision_mesh_geometry`

Date: 2026-06-09

## Goal

Rework the Blender addon file `operators/check_convexity.py` so its geometry
validation matches the content and ideas of the `collision_mesh_geometry`
package (`s:\packages\collision_mesh_geometry`, see its `README.md`). The package
is the single source of truth for *what counts as valid collision geometry*; the
addon operator keeps its unique value-add of dropping into edit mode with the
offending geometry selected.

## Motivation

The current `check_mesh_convexity()` uses a **centroid-plane test**: a face is
flagged only if the *mesh centroid* lies outside that face's plane. This is a
weak, partial convexity test — a clearly non-convex mesh can pass it, because the
centroid can sit inside every face plane while individual vertices poke out.

The package's `check_convex()` uses the correct definition: **for every face
plane, every other vertex must lie on or behind it.** It also offers watertight
(boundary edge) and manifold (non-manifold edge) checks with explicit tolerances.
Aligning the operator to these removes false negatives and unifies the validation
policy with the package consumed by tooling (Art Publisher, Graphite, the CLI).

## Scope

In scope (per decisions):

- Replace the centroid-plane convexity test with the package's per-vertex test.
- Keep/realign degenerate-triangle detection using the package.
- Add watertight (boundary edges) and manifold (non-manifold edges) checks.
- Realign the **Fix Convexity** operator's internal re-verification to the same
  per-vertex convex test (its repair actions are unchanged).

Out of scope (explicitly excluded):

- Signed-volume check (`Volume`) and centroid-divergence check (`Centroid`) from
  the package — not adopted by the operator.
- Non-triangle ("Triangulated") issue reporting — the operator triangulates
  internally for analysis, so n-gons are handled rather than reported.
- Any modification to the `collision_mesh_geometry` package itself. The target of
  this change is the addon file only.

## Package integration

The addon (`b:\scripts\addons\Cursor_BBox`) and the package (`s:\packages`) live
on different drives and the addon currently does no `sys.path` setup. Per
decision, **no path is hardcoded** — the addon relies on `s:\packages` already
being on `PYTHONPATH` (as the package README instructs for branch checkouts).

Import shim at the top of `check_convexity.py`:

```python
try:
    import collision_mesh_geometry as cmg
    from collision_mesh_geometry import validate_obj
    GEOMETRY_AVAILABLE = True
except ImportError:
    cmg = None
    validate_obj = None
    GEOMETRY_AVAILABLE = False
```

When `GEOMETRY_AVAILABLE` is `False`, both operators report a clear, actionable
error in `execute()` and return `{'CANCELLED'}`:

> `collision_mesh_geometry is not importable — ensure s:\packages is on PYTHONPATH`

Symbols used from the package:

- `cmg.check_convex(verts, tris)` → `(worst_outside, worst_face)` — canonical
  convexity verdict and the number cited in the report.
- `cmg.check_watertight(tris)` → `(boundary, nonmanifold, edge_count)` — counts
  for the verdict/report.
- `cmg.triangle_is_degenerate(a, b, c)` → degenerate-triangle test.
- `cmg.geo2` vector helpers (`Vec3Cross`, `Vec3Subtract`, `Vec3Dot`,
  `Vec3Scale`, `Vec3Length`) — reused by the per-face selection loop so its math
  is identical to `check_convex`.
- `validate_obj.CONVEXITY_TOLERANCE` (1e-3) — the threshold for both the verdict
  and the per-face selection loop. No tolerance is duplicated in the addon.

## Component: `check_mesh_convexity(mesh_obj)`

Reworked to return a `ConvexityResult` namedtuple instead of the current 4-tuple.

Fields:

- `is_clean: bool`
- `total_faces: int` — original (pre-triangulation) polygon count
- `invalid_faces: set[int]` — original polygon indices with a convexity violation
- `degenerate_faces: set[int]` — original polygon indices that are degenerate
- `worst_outside: float` — package's worst outside distance (meters)
- `worst_face: int` — original polygon index of the worst face, or `-1`
- `boundary_count: int` — package boundary-edge count
- `nonmanifold_count: int` — package non-manifold-edge count
- `boundary_edges: set[frozenset[int]]` — vertex-index pairs of boundary edges,
  for selection (identities, not just the count)
- `nonmanifold_edges: set[frozenset[int]]` — vertex-index pairs of non-manifold
  edges, for selection

Algorithm:

1. Build a bmesh from `mesh_obj.data`, transform by `matrix_world`, ensure lookup
   tables.
2. Early-out: if `len(verts) < 4` or `len(faces) == 0`, return a clean result.
3. Record `original_count` and `orig_index_of = {face: face.index}`.
4. Triangulate the bmesh (`bmesh.ops.triangulate`), keep `face_map`
   (new triangle face → original face). Ensure vert/face lookup tables and
   indices.
5. Build `verts = [(v.co.x, v.co.y, v.co.z) for v in bm.verts]` and
   `tris = [[v.index for v in f.verts] for f in bm.faces]`.
6. Verdict numbers from the package:
   - `worst_outside, worst_tri = cmg.check_convex(verts, tris)`
   - `boundary_count, nonmanifold_count, _ = cmg.check_watertight(tris)`
   - Map `worst_tri` → original polygon via `face_map`/`orig_index_of`.
   - Edge identities for selection — build the package's own undirected edge-count
     dict from the same `tris` (`frozenset((tri[i], tri[j]))` per triangle edge),
     then `boundary_edges = {edges used exactly once}` and
     `nonmanifold_edges = {edges used more than twice}`. This mirrors
     `check_watertight` exactly, so the identities are consistent with the counts
     by construction. Triangulation does not add vertices, so these vertex
     indices equal the original mesh's vertex indices; triangulation diagonals are
     always shared by exactly two triangles, so they never appear here.
7. Degenerate set: for each triangle, `cmg.triangle_is_degenerate(a, b, c)`;
   collect offending original polygon indices.
8. Invalid (non-convex) set — per-face selection loop that mirrors
   `check_convex` exactly, using `cmg.geo2` and `CONVEXITY_TOLERANCE`: for each
   triangle, compute the unit normal and plane `d`; if any vertex not in the
   triangle has `dot(n, v) - d > CONVEXITY_TOLERANCE`, the face is violating →
   map to original polygon. Skip zero-area-normal triangles (already degenerate).
   Remove any indices already in `degenerate_faces` so they are not double-counted.
9. `is_clean = not invalid_faces and not degenerate_faces and boundary_count == 0
   and nonmanifold_count == 0`.
10. Return the `ConvexityResult`.

Rationale for two convex passes: `cmg.check_convex` provides the *authoritative*
worst-face/distance for the report; the per-face loop reuses the same package
primitives and tolerance so its results are identical by construction, but at the
per-face granularity the operator needs for selection. Cost is O(F·V), the same
order as the package call, and negligible for collision-sized meshes.

## Component: `CursorBBox_OT_check_convexity`

- `poll`: unchanged (any selected mesh).
- `execute`:
  1. If `not GEOMETRY_AVAILABLE`, report the import error and cancel.
  2. Leave edit mode, gather selected mesh objects (as today).
  3. Run `check_mesh_convexity` per object; partition clean vs. bad.
  4. If all clean: `All N selected mesh(es) are convex` (INFO), finish.
  5. Per bad object, report a `WARNING` summarizing counts, e.g.:
     `"name": 3 non-convex (worst 0.0123m @ face 7) + 2 boundary + 1 non-manifold / 124 faces`
     (only non-zero parts shown).
  6. Summary `WARNING`: `K/N mesh(es) have issues (C clean)`.
  7. Select bad objects, enter EDIT mode. Set
     `mesh_select_mode = (False, True, True)` (edge + face) so both faces and
     edges can be highlighted.
  8. For each bad object, via `bmesh.from_edit_mesh`:
     - Select faces in `invalid_faces | degenerate_faces`.
     - Select **edges**: build a lookup from the edit-mesh bmesh of
       `frozenset((e.verts[0].index, e.verts[1].index)) -> edge`, then select the
       edges in `boundary_edges | nonmanifold_edges`. These identities come from
       the package's edge definition (step 6), so selection is consistent with the
       reported counts — no reliance on bmesh-native edge flags.
     - `bmesh.update_edit_mesh(...)`.

## Component: `fix_invalid_faces` / `CursorBBox_OT_fix_convexity`

Repair actions (delete degenerate faces, weld near-duplicate verts, recalc
normals outward, flip if the majority face inward) are **unchanged**. Only the
final re-verification is realigned:

- Replace the centroid-plane "remaining concavities" computation with the
  package's convex test on the post-fix geometry: extract `verts`/`tris` from the
  fixed bmesh and count faces violating `CONVEXITY_TOLERANCE` using the same
  per-face loop as the check path (shared helper).
- `remaining` becomes the count of genuinely non-convex faces under the correct
  test. Reported message format is unchanged.
- The existing "majority normals inward → flip all" heuristic is retained for
  winding correction before the convex count (the convex test is sensitive to
  winding), but its inward/outward decision uses the package plane test rather
  than an ad-hoc centroid dot.

To avoid duplication, the per-face convex-violation loop is factored into a small
module-level helper (e.g. `_violating_faces(verts, tris, tolerance)` returning a
set of triangle indices) used by both `check_mesh_convexity` and
`fix_invalid_faces`.

## Error handling

- Missing package → clear operator error, no crash (see import shim).
- Empty/sub-tetrahedral meshes → treated as clean (early-out), as today.
- Degenerate triangles are excluded from the convex set to avoid double-counting.
- Edge selection is exact, not best-effort: boundary/non-manifold edge identities
  come from the package's own edge-count definition (the same one behind the
  reported counts), mapped back to real mesh edges by vertex-index pair.

## Fidelity

Against the mesh's live geometry, the operator's verdict and selection are 100%
the package's: `check_convex`, `check_watertight`, and `triangle_is_degenerate`
are called directly, and the per-face convex loop and edge classification reuse
the package's exact math and tolerance (`cmg.geo2`, `CONVEXITY_TOLERANCE`, and the
`check_watertight` edge definition). There is no second algorithm to drift.

The one thing this does not guarantee is bit-equality with
`collision_mesh_geometry.validate_obj` run on a later-exported OBJ of the same
mesh: an exporter rounds coordinates and may triangulate n-gons in a different
pattern, either of which can flip a verdict near the 1e-3 tolerance. That is an
export artifact and is out of scope for this operator.

## Testing

Manual verification in Blender (via the blender-mcp skill) on representative
objects:

1. A convex hull (e.g. icosphere/box) → reports all convex, no edit mode.
2. A deliberately concave mesh (vertex pushed inward) → flagged non-convex by the
   new test where the old centroid test would have passed; correct faces selected.
3. A mesh with a deleted face (boundary hole) → boundary count > 0, boundary
   edges selected in edit mode.
4. A mesh with an extra coplanar face sharing an edge (non-manifold) →
   non-manifold count > 0, those edges selected.
5. A mesh with a zero-area face → degenerate count > 0, face selected.
6. Fix Convexity on a mesh with degenerate + concave faces → repairs applied,
   remaining concavity count consistent with Check Convexity's verdict.
7. With `collision_mesh_geometry` not on `PYTHONPATH` → both operators report the
   clear import error and cancel.

Cross-check: where applicable, the operator's verdict (convex / boundary /
non-manifold) should agree with `collision_mesh_geometry.validate_obj` run on an
exported OBJ of the same mesh.
