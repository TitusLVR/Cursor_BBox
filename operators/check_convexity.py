import os
import sys
from collections import namedtuple

import bpy
import bmesh

# collision_mesh_geometry ships in s:\packages, which is not always on
# PYTHONPATH (e.g. a fresh Blender launch). If the first import fails, add that
# directory and retry once before giving up.
_PACKAGES_FALLBACK = r"s:\packages"


def _import_geometry():
    import collision_mesh_geometry as cmg
    from collision_mesh_geometry import validate_obj
    from ..functions.convexity_geometry import (
        violating_faces, classify_edges, convex_hull_triangles,
    )
    return cmg, validate_obj, violating_faces, classify_edges, convex_hull_triangles


try:
    (cmg, validate_obj, violating_faces, classify_edges,
     convex_hull_triangles) = _import_geometry()
    GEOMETRY_AVAILABLE = True
except ImportError:
    if os.path.isdir(_PACKAGES_FALLBACK) and _PACKAGES_FALLBACK not in sys.path:
        sys.path.append(_PACKAGES_FALLBACK)
    try:
        (cmg, validate_obj, violating_faces, classify_edges,
         convex_hull_triangles) = _import_geometry()
        GEOMETRY_AVAILABLE = True
    except ImportError:
        cmg = None
        validate_obj = None
        violating_faces = None
        classify_edges = None
        convex_hull_triangles = None
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


def _build_convex_hull_bmesh(world_coords):
    """Return a triangulated convex-hull bmesh from world-space coords.

    Builds the hull with the double-precision quickhull in
    ``convexity_geometry`` (Blender's ``bmesh.ops.convex_hull`` merges nearly
    coplanar faces with a cloud-relative tolerance and its output can fail the
    collision_mesh_geometry convexity check by several millimetres). Falls
    back to the Blender operator if quickhull fails. Does NOT recenter, so a
    caller writing the result back through an object's inverse matrix keeps the
    object's origin and transform. Returns the bmesh, or None when there are
    fewer than 4 points or the hull has no solid faces (coplanar/collinear
    input). The caller owns (must free) a returned bmesh.
    """
    if len(world_coords) < 4:
        return None

    try:
        tris = convex_hull_triangles(
            [(c.x, c.y, c.z) for c in world_coords],
            tolerance=validate_obj.CONVEXITY_TOLERANCE,
        )
    except Exception:
        tris = None
    if tris:
        bm = bmesh.new()
        try:
            remap = {
                i: bm.verts.new(world_coords[i])
                for i in sorted({i for tri in tris for i in tri})
            }
            for tri in tris:
                bm.faces.new((remap[tri[0]], remap[tri[1]], remap[tri[2]]))
            bm.verts.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            bm.normal_update()
            return bm
        except Exception:
            bm.free()

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


PolicyCounts = namedtuple(
    "PolicyCounts", ["violations", "degenerate", "boundary", "nonmanifold"]
)
PolicyCounts.total = property(lambda self: sum(self))

_CLEAN_COUNTS = PolicyCounts(0, 0, 0, 0)


def _evaluate_policy(bm, tolerance):
    """Evaluate the full collision-mesh policy for the current bmesh geometry.

    Triangulates a throwaway copy (so the live bmesh is untouched) and runs the
    same four tests as ``check_mesh_convexity``: convexity violations,
    degenerate triangles, boundary edges, and non-manifold edges. Returns
    ``(triangle_count, PolicyCounts)``.
    """
    eval_bm = bm.copy()
    try:
        bmesh.ops.triangulate(eval_bm, faces=eval_bm.faces[:])
        eval_bm.verts.ensure_lookup_table()
        eval_bm.verts.index_update()
        verts = [(v.co.x, v.co.y, v.co.z) for v in eval_bm.verts]
        tris = [[v.index for v in f.verts] for f in eval_bm.faces]
        violations = len(violating_faces(verts, tris, tolerance))
        degenerate = sum(
            1 for tri in tris
            if cmg.triangle_is_degenerate(verts[tri[0]], verts[tri[1]], verts[tri[2]])
        )
        boundary, nonmanifold, _ = cmg.check_watertight(tris)
        return len(tris), PolicyCounts(violations, degenerate, boundary, nonmanifold)
    finally:
        eval_bm.free()


def fix_invalid_faces(mesh_obj, area_threshold=1e-6, weld_distance=0.0,
                      rebuild_hull=True):
    """Fix collision meshes that fail the collision_mesh_geometry policy.

    1. Delete degenerate (zero-area) faces and clean up orphaned
       geometry.
    2. Weld vertices closer than *weld_distance* to collapse
       near-duplicate verts that create micro-area faces.
    3. Recalculate normals outward to fix any winding inconsistencies
       that cause false convexity violations.
    4. If the mesh still fails any part of the policy that Check
       Convexity enforces (non-convex faces, degenerate triangles,
       boundary edges, or non-manifold edges) and *rebuild_hull* is
       True, rebuild its convex hull in place (triangulated), which
       guarantees a convex, watertight, manifold result. The object's
       transform and origin are preserved.

    Returns (degenerate_deleted, verts_welded, normals_fixed,
             remaining: PolicyCounts, hull_rebuilt).
    """
    mesh = mesh_obj.data
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        world_mat = mesh_obj.matrix_world
        inv_mat = world_mat.inverted()
        bm.transform(world_mat)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        if len(bm.verts) < 4 or len(bm.faces) == 0:
            return 0, 0, 0, _CLEAN_COUNTS, False

        # --- Pass 1: delete degenerate faces ---
        degen_faces = []
        for face in bm.faces:
            if face.calc_area() < area_threshold:
                degen_faces.append(face)
            elif face.normal.length_squared < 1e-12:
                degen_faces.append(face)

        degen_count = len(degen_faces)
        if degen_faces:
            bmesh.ops.delete(bm, geom=degen_faces, context='FACES')

        # --- Pass 2: weld nearby vertices ---
        verts_before = len(bm.verts)
        welded = 0
        if weld_distance > 0.0:
            bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=weld_distance)
            bm.verts.ensure_lookup_table()
            welded = verts_before - len(bm.verts)

        # --- Pass 3: recalculate normals outward ---
        bm.faces.ensure_lookup_table()

        if len(bm.faces) == 0:
            bm.transform(inv_mat)
            bm.to_mesh(mesh)
            mesh.update()
            return degen_count, welded, 0, _CLEAN_COUNTS, False

        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.normal_update()

        tolerance = validate_obj.CONVEXITY_TOLERANCE
        tri_count, counts_before = _evaluate_policy(bm, tolerance)
        remaining = counts_before

        # If most faces report violations, recalc picked inward winding; flip all
        # and re-evaluate with the same package test.
        if counts_before.violations * 2 > tri_count:
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
            bm.normal_update()
            _, remaining = _evaluate_policy(bm, tolerance)

        normals_fixed = max(0, counts_before.violations - remaining.violations)

        hull_rebuilt = False
        if rebuild_hull and remaining.total > 0 and len(bm.verts) >= 4:
            coords = [v.co.copy() for v in bm.verts]  # world space, post-weld
            hull_bm = _build_convex_hull_bmesh(coords)
            if hull_bm is not None:
                bm.free()
                bm = hull_bm
                hull_rebuilt = True
                _, remaining = _evaluate_policy(bm, tolerance)

        bm.transform(inv_mat)
        bm.to_mesh(mesh)
        mesh.update()

        return degen_count, welded, normals_fixed, remaining, hull_rebuilt
    finally:
        bm.free()


class CursorBBox_OT_fix_convexity(bpy.types.Operator):
    """Delete degenerate faces, weld vertices, and recalculate normals"""
    bl_idname = "cursor_bbox.fix_convexity"
    bl_label = "Fix Convexity"
    bl_description = (
        "Delete zero-area faces, weld nearby vertices, recalculate normals, "
        "and rebuild the convex hull in place when a mesh stays non-convex, "
        "open, or non-manifold"
    )
    bl_options = {'REGISTER', 'UNDO'}

    rebuild_hull: bpy.props.BoolProperty(
        name="Rebuild Hull",
        description=(
            "When gentle repairs can't make a mesh convex, watertight, and "
            "manifold, rebuild its convex hull in place (replaces the mesh "
            "topology)"
        ),
        default=True,
    )

    area_threshold: bpy.props.FloatProperty(
        name="Area Threshold",
        description="Faces with area below this value are treated as degenerate and deleted",
        default=1e-6,
        min=0.0,
        max=1.0,
        precision=6,
        step=0.01,
    )

    weld_distance: bpy.props.FloatProperty(
        name="Weld Distance",
        description="Merge vertices closer than this distance (0 to skip)",
        default=0.0001,
        min=0.0,
        max=1.0,
        precision=6,
        step=0.01,
        unit='LENGTH',
    )

    @classmethod
    def poll(cls, context):
        return any(
            obj.type == 'MESH' for obj in context.selected_objects
        )

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
        total_remaining = _CLEAN_COUNTS
        total_hull = 0
        touched_objects = 0
        dirty_objects = []

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
            total_remaining = PolicyCounts(
                *(a + b for a, b in zip(total_remaining, remaining))
            )
            if remaining.total > 0:
                dirty_objects.append(obj.name)

        did_work = total_degen + total_welded + total_normals + total_hull
        if did_work == 0 and total_remaining.total == 0:
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

        if total_remaining.total:
            issues = []
            if total_remaining.violations:
                issues.append(f"{total_remaining.violations} non-convex")
            if total_remaining.degenerate:
                issues.append(f"{total_remaining.degenerate} degenerate")
            if total_remaining.boundary:
                issues.append(f"{total_remaining.boundary} boundary")
            if total_remaining.nonmanifold:
                issues.append(f"{total_remaining.nonmanifold} non-manifold")
            msg += (
                f" — {' + '.join(issues)} remain on "
                f"{len(dirty_objects)} object(s): "
                f"{', '.join(dirty_objects[:5])}"
            )
            if len(dirty_objects) > 5:
                msg += ", …"
            if not self.rebuild_hull:
                msg += "; enable Rebuild Hull to fix"
            else:
                msg += "; geometry may be too flat to form a solid hull"
            self.report({'WARNING'}, msg)
        else:
            self.report({'INFO'}, msg)

        return {'FINISHED'}


class CursorBBox_OT_check_convexity(bpy.types.Operator):
    """Check whether selected objects have convex collision meshes"""
    bl_idname = "cursor_bbox.check_convexity"
    bl_label = "Check Convexity"
    bl_description = (
        "Verify that selected mesh objects are convex. "
        "Non-convex shapes will enter edit mode with invalid faces selected"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(
            obj.type == 'MESH' for obj in context.selected_objects
        )

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
