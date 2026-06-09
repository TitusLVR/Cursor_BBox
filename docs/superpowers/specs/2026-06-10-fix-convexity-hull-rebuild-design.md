# Fold in-place convex-hull rebuild into Fix Convexity

Date: 2026-06-10

## Goal

Make the **Fix Convexity** operator actually repair non-convex collision meshes.
Today it only deletes degenerate faces, welds vertices, and recalculates normals —
none of which can remove a concavity — so on genuinely non-convex meshes it does
nothing and misreports "All meshes are already clean". This change lets Fix
escalate to rebuilding the mesh's convex hull in place when gentle repairs leave a
mesh non-convex, guaranteeing a convex result.

## Motivation

Observed: running Fix Convexity on 11 `ConvexHull.*` pieces (CoACD/VHACD-style
decomposition outputs) that Check Convexity flags as non-convex (worst violations
from 0.0023 m up to 0.2 m). Fix reports "All meshes are already clean" and the
geometry is unchanged; Check still flags them.

Two root causes:

1. **Fix cannot remove concavities by design.** Its three passes (delete
   degenerate, weld, recalc normals) never rebuild geometry. The only operation
   that makes a non-convex point cloud convex is recomputing its convex hull
   (`bmesh.ops.convex_hull`). Verified non-destructively in the live scene:
   re-hulling `ConvexHull.005` took it from 30 non-convex faces (worst 0.2005 m)
   to 0 non-convex / 0 boundary / 0 non-manifold.
2. **A reporting bug.** In `CursorBBox_OT_fix_convexity.execute`, `total_remaining`
   is accumulated *only inside* the `if degen + welded + normals > 0:` block. A
   purely non-convex mesh does no gentle work, so its remaining-concavity count is
   dropped and the operator falls through to "All meshes are already clean".

## Scope

In scope:

- A new helper that builds a triangulated convex-hull bmesh from world-space
  vertex coordinates (no recentering).
- `fix_invalid_faces` escalates to an in-place hull rebuild when a mesh stays
  non-convex after gentle repairs and the rebuild is enabled.
- A `Rebuild Hull` operator toggle (default ON).
- Fix the `total_remaining` accounting/reporting bug.

Out of scope:

- Changing Check Convexity (`check_mesh_convexity` / `CursorBBox_OT_check_convexity`).
- Changing the existing hull operators (`interactive_hull.py`).
- Re-hulling meshes that are convex but merely open/non-manifold (the trigger is
  non-convexity; a hull rebuild does incidentally produce a watertight manifold
  solid, but Fix only escalates when `remaining > 0`).
- Decisions about origin/centroid relocation — the in-place rebuild deliberately
  preserves the object's existing transform and origin.

## Component 1: `_build_convex_hull_bmesh(world_coords)`

New module-level helper in `operators/check_convexity.py`.

Mirrors the proven logic in `interactive_hull.py::_build_hull_object_from_vertices`,
**minus the centroid translation and object creation**:

```python
def _build_convex_hull_bmesh(world_coords):
    """Return a triangulated convex-hull bmesh from world-space coords.

    Builds the convex hull of the given points, discards interior/unused input
    points, recomputes outward normals, and triangulates. Does NOT recenter, so
    callers writing the result back through an object's inverse matrix keep the
    object's origin and transform. Returns the bmesh, or None when there are
    fewer than 4 points or the hull has no solid faces (coplanar/collinear input)
    — the caller is responsible for freeing a returned bmesh.
    """
    if len(world_coords) < 4:
        return None
    bm = bmesh.new()
    for co in world_coords:
        bm.verts.new(co)
    bm.verts.ensure_lookup_table()
    ret = bmesh.ops.convex_hull(bm, input=bm.verts)
    interior = set(ret.get('geom_interior', [])) | set(ret.get('geom_unused', []))
    if interior:
        bmesh.ops.delete(bm, geom=list(interior), context='VERTS')
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    if not bm.faces:
        bm.free()
        return None
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.normal_update()
    return bm
```

Note: triangulation uses `bmesh.ops.triangulate` defaults (no dependency on the
Hull tool's scene properties), per the "triangulated raw hull" decision.

## Component 2: `fix_invalid_faces(mesh_obj, area_threshold, weld_distance, rebuild_hull=True)`

Add the `rebuild_hull` parameter (default `True`). The existing passes (delete
degenerate, weld, recalc normals, winding-flip, `_evaluate_convexity` →
`remaining`) are unchanged. After `remaining` is computed and before the
transform-back/write, insert the escalation:

```python
        hull_rebuilt = False
        if rebuild_hull and remaining > 0 and len(bm.verts) >= 4:
            coords = [v.co.copy() for v in bm.verts]  # world space, post-weld
            hull_bm = _build_convex_hull_bmesh(coords)
            if hull_bm is not None:
                bm.free()
                bm = hull_bm
                hull_rebuilt = True
                _, remaining = _evaluate_convexity(bm, tolerance)  # expected 0
```

Mechanics:

- `coords` are world-space (the bmesh was already `bm.transform(world_mat)`-ed),
  post-degenerate-delete and post-weld.
- On success, the old `bm` is freed and the local `bm` name is rebound to the hull
  bmesh; the function's `finally: bm.free()` then frees the hull bmesh — no double
  free, no leak. The existing `bm.transform(inv_mat)` + `bm.to_mesh(mesh)` writes
  the hull back in local space, preserving origin/transform.
- If `_build_convex_hull_bmesh` returns `None` (coplanar/degenerate input), no
  swap occurs and `remaining` keeps its value (reported as residual).

Return signature becomes `(degen_count, welded, normals_fixed, remaining, hull_rebuilt)`.
The early-return paths (`<4 verts or 0 faces`, and the emptied-mesh branch) return
a matching 5-tuple with `hull_rebuilt=False`.

## Component 3: `CursorBBox_OT_fix_convexity`

**Property:**

```python
    rebuild_hull: bpy.props.BoolProperty(
        name="Rebuild Hull",
        description="When gentle repairs can't make a mesh convex, rebuild its "
                    "convex hull in place (replaces the mesh topology)",
        default=True,
    )
```

**`bl_description`** updated to mention the hull rebuild.

**`execute` rework** (fixing the accounting bug):

```python
        total_degen = total_welded = total_normals = 0
        total_remaining = 0
        total_hull = 0
        touched_objects = 0
        concave_objects = 0

        for obj in mesh_objects:
            degen, welded, normals, remaining, rebuilt = fix_invalid_faces(
                obj, self.area_threshold, self.weld_distance, self.rebuild_hull,
            )
            work = degen + welded + normals + (1 if rebuilt else 0)
            if work > 0:
                touched_objects += 1
            total_degen += degen
            total_welded += welded
            total_normals += normals
            total_hull += 1 if rebuilt else 0
            total_remaining += remaining          # accumulate unconditionally
            if remaining > 0:
                concave_objects += 1

        did_work = total_degen + total_welded + total_normals + total_hull
        if did_work == 0 and total_remaining == 0:
            self.report({'INFO'}, "All meshes are already clean")
            return {'FINISHED'}

        parts = []
        if total_degen:
            parts.append(f"{total_degen} degenerate deleted")
        if total_welded:
            parts.append(f"{total_welded} verts welded")
        if total_normals:
            parts.append(f"{total_normals} normals fixed")
        if total_hull:
            parts.append(f"{total_hull} hull-rebuilt")

        if parts:
            msg = f"{', '.join(parts)} on {touched_objects} object(s)"
        else:
            msg = "No repairs applied"

        if total_remaining:
            msg += (
                f" — {total_remaining} concavities remain on "
                f"{concave_objects} object(s)"
            )
            if not self.rebuild_hull:
                msg += "; enable Rebuild Hull to fix"
            self.report({'WARNING'}, msg)
        else:
            self.report({'INFO'}, msg)

        return {'FINISHED'}
```

## Error handling

- `<4` vertices or `0` faces → existing early-return (5-tuple, `hull_rebuilt=False`),
  hull skipped.
- Hull build fails (coplanar/collinear cloud) → `None`, no swap, residual
  `remaining` reported as a WARNING.
- Rebuild toggle OFF and mesh non-convex → no rebuild, WARNING names the residual
  count and hints to enable Rebuild Hull.
- bmesh lifecycle: exactly one live bmesh at any time; the swap frees the old one
  before rebinding, and `finally` frees the survivor.

## Testing

bpy/bmesh-bound, so verified in the live Blender via the blender-mcp skill (the
pure convexity helpers already have unittest coverage and are unchanged):

1. Select the actual `ConvexHull.*` pieces, run Fix → report shows
   "N hull-rebuilt"; re-run Check Convexity → 0 issues on all of them.
2. For a rebuilt object, assert its `matrix_world` / `location` and origin are
   unchanged versus before Fix (transform/origin preserved).
3. A synthetic non-convex mesh with `rebuild_hull=False` → geometry unchanged,
   WARNING reports residual concavities with the "enable Rebuild Hull" hint.
4. A genuinely convex mesh → "already clean" (no rebuild).
5. A degenerate-only mesh (<4 unique verts) → no crash, hull skipped.
6. Package absent (`GEOMETRY_AVAILABLE` False) → ERROR + CANCELLED (unchanged guard).
