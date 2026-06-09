# Fix Convexity Hull-Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the **Fix Convexity** operator rebuild a mesh's convex hull in place when gentle repairs can't make it convex, and fix the report that wrongly says "All meshes are already clean" for non-convex meshes.

**Architecture:** Add a bmesh hull-builder helper, escalate inside `fix_invalid_faces` (swapping the working bmesh for a triangulated convex hull of its vertices, preserving the object's transform/origin), add a `Rebuild Hull` toggle, and correct the operator's accounting/reporting. All changes are in one file: `operators/check_convexity.py`.

**Tech Stack:** Python, Blender `bpy`/`bmesh`, `collision_mesh_geometry` (already wired in), verified live via blender-mcp.

**Spec:** `docs/superpowers/specs/2026-06-10-fix-convexity-hull-rebuild-design.md`

---

## File Structure

- **Modify** `operators/check_convexity.py`:
  - Add module-level `_build_convex_hull_bmesh(world_coords)`.
  - Add the hull escalation to `fix_invalid_faces`, changing its return to a 5-tuple.
  - Add the `rebuild_hull` property and rework `execute` of `CursorBBox_OT_fix_convexity`.

No other files change. `_evaluate_convexity`, `_build_convex_hull_bmesh`, and the convexity helpers stay bpy/bmesh-bound, so verification is in-Blender (Task 3), not pytest.

---

## Task 1: Hull-builder helper + escalation in `fix_invalid_faces`

**Files:**
- Modify: `operators/check_convexity.py`

This task adds the helper and the escalation, and changes `fix_invalid_faces` to return a 5-tuple. The operator `execute` still unpacks a 4-tuple after this task — that runtime mismatch is fixed in Task 2 (compile-only check passes here).

- [ ] **Step 1: Add the `_build_convex_hull_bmesh` helper**

Insert this new module-level function immediately BEFORE `def _evaluate_convexity(` (locate `_evaluate_convexity` by content; the new helper goes just above it):

```python
def _build_convex_hull_bmesh(world_coords):
    """Return a triangulated convex-hull bmesh from world-space coords.

    Builds the convex hull of the given points, discards interior/unused input
    points, recomputes outward normals, and triangulates. Does NOT recenter, so
    a caller writing the result back through an object's inverse matrix keeps the
    object's origin and transform. Returns the bmesh, or None when there are
    fewer than 4 points or the hull has no solid faces (coplanar/collinear input).
    The caller owns (must free) a returned bmesh.
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

- [ ] **Step 2: Change the `fix_invalid_faces` signature and docstring**

Replace the signature line and docstring of `fix_invalid_faces`. The current code is:

```python
def fix_invalid_faces(mesh_obj, area_threshold=1e-6, weld_distance=0.0):
    """Fix degenerate and non-convex faces.

    1. Delete degenerate (zero-area) faces and clean up orphaned
       geometry.  Zero-area faces occupy no space so no hole-fill is
       needed.
    2. Weld vertices closer than *weld_distance* to collapse
       near-duplicate verts that create micro-area faces.
    3. Recalculate normals outward to fix any winding inconsistencies
       that cause false convexity violations.

    Returns (degenerate_deleted, verts_welded, normals_fixed,
             remaining_count).
    """
```

Replace it with:

```python
def fix_invalid_faces(mesh_obj, area_threshold=1e-6, weld_distance=0.0,
                      rebuild_hull=True):
    """Fix degenerate and non-convex collision meshes.

    1. Delete degenerate (zero-area) faces and clean up orphaned
       geometry.  Zero-area faces occupy no space so no hole-fill is
       needed.
    2. Weld vertices closer than *weld_distance* to collapse
       near-duplicate verts that create micro-area faces.
    3. Recalculate normals outward to fix any winding inconsistencies
       that cause false convexity violations.
    4. If the mesh is still non-convex and *rebuild_hull* is True,
       rebuild its convex hull in place (triangulated), which guarantees
       a convex, watertight, manifold result. The object's transform and
       origin are preserved.

    Returns (degenerate_deleted, verts_welded, normals_fixed,
             remaining_count, hull_rebuilt).
    """
```

- [ ] **Step 3: Update the two early-return paths to 5-tuples**

In `fix_invalid_faces`, the guard for tiny meshes currently reads:

```python
        if len(bm.verts) < 4 or len(bm.faces) == 0:
            return 0, 0, 0, 0
```

Change it to:

```python
        if len(bm.verts) < 4 or len(bm.faces) == 0:
            return 0, 0, 0, 0, False
```

The emptied-mesh branch currently reads:

```python
        if len(bm.faces) == 0:
            bm.transform(inv_mat)
            bm.to_mesh(mesh)
            mesh.update()
            return degen_count, welded, 0, 0
```

Change its return to:

```python
        if len(bm.faces) == 0:
            bm.transform(inv_mat)
            bm.to_mesh(mesh)
            mesh.update()
            return degen_count, welded, 0, 0, False
```

- [ ] **Step 4: Insert the hull escalation and update the final return**

The current tail of `fix_invalid_faces` (after the winding-flip block) reads:

```python
        normals_fixed = max(0, violations_before - remaining)

        bm.transform(inv_mat)
        bm.to_mesh(mesh)
        mesh.update()

        return degen_count, welded, normals_fixed, remaining
    finally:
        bm.free()
```

Replace that block with:

```python
        normals_fixed = max(0, violations_before - remaining)

        hull_rebuilt = False
        if rebuild_hull and remaining > 0 and len(bm.verts) >= 4:
            coords = [v.co.copy() for v in bm.verts]  # world space, post-weld
            hull_bm = _build_convex_hull_bmesh(coords)
            if hull_bm is not None:
                bm.free()
                bm = hull_bm
                hull_rebuilt = True
                _, remaining = _evaluate_convexity(bm, tolerance)

        bm.transform(inv_mat)
        bm.to_mesh(mesh)
        mesh.update()

        return degen_count, welded, normals_fixed, remaining, hull_rebuilt
    finally:
        bm.free()
```

Note: rebinding the local `bm` to `hull_bm` after freeing the old one means the `finally: bm.free()` frees the hull bmesh — no double free. `tolerance` and `inv_mat` are already defined earlier in the function.

- [ ] **Step 5: Verify the module compiles**

Run:
```
python -m py_compile b:\scripts\addons\Cursor_BBox\operators\check_convexity.py
```
Expected: no output, exit 0. (Windows/PowerShell; if `python` missing, try `py`.)

- [ ] **Step 6: Commit**

```
git add operators/check_convexity.py
git commit -m "feat: rebuild convex hull in place when Fix Convexity can't repair concavity"
```

---

## Task 2: `rebuild_hull` property + reworked `execute`

**Files:**
- Modify: `operators/check_convexity.py` — class `CursorBBox_OT_fix_convexity`

- [ ] **Step 1: Update `bl_description` and add the `rebuild_hull` property**

The class currently has:

```python
    bl_description = (
        "Delete zero-area faces, weld nearby vertices, and "
        "recalculate normals outward"
    )
    bl_options = {'REGISTER', 'UNDO'}

    area_threshold: bpy.props.FloatProperty(
```

Replace that span (the `bl_description` through just before `area_threshold:`) with:

```python
    bl_description = (
        "Delete zero-area faces, weld nearby vertices, recalculate normals, "
        "and rebuild the convex hull in place when a mesh stays non-convex"
    )
    bl_options = {'REGISTER', 'UNDO'}

    rebuild_hull: bpy.props.BoolProperty(
        name="Rebuild Hull",
        description=(
            "When gentle repairs can't make a mesh convex, rebuild its convex "
            "hull in place (replaces the mesh topology)"
        ),
        default=True,
    )

    area_threshold: bpy.props.FloatProperty(
```

- [ ] **Step 2: Replace the body of `execute`**

Replace the ENTIRE `execute` method of `CursorBBox_OT_fix_convexity` (from `def execute(self, context):` through its final `return {'FINISHED'}`) with:

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

        total_degen = 0
        total_welded = 0
        total_normals = 0
        total_remaining = 0
        total_hull = 0
        touched_objects = 0
        concave_objects = 0

        for obj in mesh_objects:
            degen, welded, normals, remaining, rebuilt = fix_invalid_faces(
                obj, self.area_threshold, self.weld_distance, self.rebuild_hull,
            )
            if degen + welded + normals + (1 if rebuilt else 0) > 0:
                touched_objects += 1
            total_degen += degen
            total_welded += welded
            total_normals += normals
            total_hull += 1 if rebuilt else 0
            total_remaining += remaining
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

- [ ] **Step 3: Verify the module compiles**

Run:
```
python -m py_compile b:\scripts\addons\Cursor_BBox\operators\check_convexity.py
```
Expected: no output, exit 0.

- [ ] **Step 4: Commit**

```
git add operators/check_convexity.py
git commit -m "feat: add Rebuild Hull toggle and fix Fix Convexity reporting"
```

---

## Task 3: In-Blender integration verification (blender-mcp)

**Files:** none (verification only). Use the `blender-mcp` skill to run Python in the user's Blender. The addon module is `Cursor_BBox`. If `collision_mesh_geometry` is not importable, append `s:\packages` to `sys.path` before reloading (it is not persistent; that's expected).

- [ ] **Step 1: Reload the addon**

Via blender-mcp, reload `Cursor_BBox` (disable → clear `sys.modules` entries → enable). Confirm `bpy.ops.cursor_bbox.fix_convexity` exists and `Cursor_BBox.operators.check_convexity.GEOMETRY_AVAILABLE` is True (inject `s:\packages` onto `sys.path` first if needed).

- [ ] **Step 2: Verify hull rebuild on a synthetic non-convex mesh, transform preserved**

Run via blender-mcp:

```python
import bpy, bmesh, traceback
from Cursor_BBox.operators.check_convexity import check_mesh_convexity, fix_invalid_faces

created = []
out = {}
try:
    me = bpy.data.meshes.new("t_fix")
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2.0); bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new("t_fix", me); created.append(obj)
    bpy.context.collection.objects.link(obj)
    obj.location = (5.0, -3.0, 2.0)            # non-identity transform
    obj.data.vertices[0].co = obj.data.vertices[0].co * 0.2  # dent -> non-convex

    before = check_mesh_convexity(obj)
    loc_before = tuple(obj.location)
    mw_before = [tuple(r) for r in obj.matrix_world]

    degen, welded, normals, remaining, rebuilt = fix_invalid_faces(obj, 1e-6, 0.0001, True)
    after = check_mesh_convexity(obj)

    out = {
        "before_non_convex": len(before.invalid_faces),
        "rebuilt": rebuilt,
        "remaining_after": remaining,
        "after_is_clean": after.is_clean,
        "after_non_convex": len(after.invalid_faces),
        "location_preserved": tuple(obj.location) == loc_before,
        "matrix_preserved": [tuple(r) for r in obj.matrix_world] == mw_before,
    }
    err = None
except Exception:
    err = traceback.format_exc()
finally:
    for o in created:
        try: bpy.data.objects.remove(o, do_unlink=True)
        except Exception: pass
result = {"out": out, "error": err}
```

Expected: `before_non_convex > 0`, `rebuilt == True`, `remaining_after == 0`, `after_is_clean == True`, `after_non_convex == 0`, `location_preserved == True`, `matrix_preserved == True`.

- [ ] **Step 3: Verify the toggle-off path leaves geometry intact and warns**

Run via blender-mcp:

```python
import bpy, bmesh, traceback
from Cursor_BBox.operators.check_convexity import fix_invalid_faces

created = []
out = {}
try:
    me = bpy.data.meshes.new("t_off")
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2.0); bm.to_mesh(me); bm.free()
    obj = bpy.data.objects.new("t_off", me); created.append(obj)
    bpy.context.collection.objects.link(obj)
    obj.data.vertices[0].co = obj.data.vertices[0].co * 0.2
    vcount_before = len(obj.data.vertices)
    degen, welded, normals, remaining, rebuilt = fix_invalid_faces(obj, 1e-6, 0.0001, False)
    out = {"rebuilt": rebuilt, "remaining": remaining,
           "verts_unchanged": len(obj.data.vertices) == vcount_before}
    err = None
except Exception:
    err = traceback.format_exc()
finally:
    for o in created:
        try: bpy.data.objects.remove(o, do_unlink=True)
        except Exception: pass
result = {"out": out, "error": err}
```

Expected: `rebuilt == False`, `remaining > 0`, `verts_unchanged == True`.

- [ ] **Step 4: Verify on the user's real pieces, then run Check**

If the `ConvexHull.*` objects are still present, select them and run the operator, then Check:

```python
import bpy
names = [o.name for o in bpy.data.objects if o.name.startswith("ConvexHull")]
bpy.ops.object.select_all(action='DESELECT')
for n in names:
    bpy.data.objects[n].select_set(True)
if names:
    bpy.context.view_layer.objects.active = bpy.data.objects[names[0]]
fix_ret = list(bpy.ops.cursor_bbox.fix_convexity('EXEC_DEFAULT'))
# Re-check
from Cursor_BBox.operators.check_convexity import check_mesh_convexity
residual = {n: len(check_mesh_convexity(bpy.data.objects[n]).invalid_faces) for n in names}
result = {"count": len(names), "fix_ret": fix_ret,
          "still_non_convex": {n: c for n, c in residual.items() if c > 0}}
```

Expected: `fix_ret == ['FINISHED']` and `still_non_convex == {}` (every piece convex after Fix). Note: this mutates the user's meshes — only run after confirming they want the in-scene fix applied.

- [ ] **Step 5: Final commit (if any verification fixes were needed)**

```
git add -A
git commit -m "test: verify Fix Convexity hull rebuild in Blender"
```

---

## Self-Review notes

- **Spec coverage:** `_build_convex_hull_bmesh` (Task 1 Step 1), escalation in `fix_invalid_faces` + 5-tuple return (Task 1 Steps 2-4), `rebuild_hull` toggle (Task 2 Step 1), reworked accounting/reporting incl. the `total_remaining` bug fix (Task 2 Step 2), transform/origin preservation + toggle-off + real-pieces verification (Task 3). All spec sections covered.
- **Type consistency:** `fix_invalid_faces` returns a 5-tuple `(degen, welded, normals_fixed, remaining, hull_rebuilt)` in every return path (Task 1 Steps 3-4); the sole caller unpacks five values (Task 2 Step 2). `_build_convex_hull_bmesh` returns a bmesh or None; the escalation null-checks before swapping.
- **No placeholders:** every code step shows full code; commands have expected output.
