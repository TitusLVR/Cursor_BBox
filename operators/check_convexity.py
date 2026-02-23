import bpy
import bmesh
from mathutils import Vector


def check_mesh_convexity(mesh_obj, area_threshold=1e-8):
    """Check whether a mesh object is convex using the centroid-plane test.

    For a convex mesh, the centroid (average of all vertices) must lie on
    the inside (or boundary) of every face plane.  If the centroid is on
    the *outside* of any face plane, the mesh is not convex.

    Faces with area below *area_threshold* are flagged as degenerate.

    Triangulates internally so non-planar quads/n-gons are handled
    correctly, then maps invalid triangles back to their original
    polygon indices.

    Returns (is_convex, total_original_faces, invalid_polygon_indices,
             degenerate_polygon_indices).
    """
    mesh = mesh_obj.data
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.transform(mesh_obj.matrix_world)
        bm.faces.ensure_lookup_table()

        if len(bm.verts) < 4 or len(bm.faces) == 0:
            return True, len(bm.faces), set(), set()

        centroid = sum((v.co for v in bm.verts), Vector()) / len(bm.verts)

        # Detect degenerate faces before triangulation
        degenerate_orig = set()
        for face in bm.faces:
            if face.calc_area() < area_threshold:
                degenerate_orig.add(face.index)

        orig_index_of = {f: f.index for f in bm.faces}
        original_count = len(bm.faces)

        result = bmesh.ops.triangulate(bm, faces=bm.faces[:])
        face_map = result['face_map']

        invalid_orig = set()
        for face in bm.faces:
            normal = face.normal
            if normal.length_squared < 1e-12:
                orig_face = face_map.get(face, face)
                degenerate_orig.add(orig_index_of[orig_face])
                continue
            plane_d = face.verts[0].co.dot(normal)
            if centroid.dot(normal) > plane_d + 1e-6:
                orig_face = face_map.get(face, face)
                invalid_orig.add(orig_index_of[orig_face])

        # Don't double-count: remove degenerates from the convexity set
        invalid_orig -= degenerate_orig

        is_clean = len(invalid_orig) == 0 and len(degenerate_orig) == 0
        return is_clean, original_count, invalid_orig, degenerate_orig
    finally:
        bm.free()


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
            return 0, 0, 0, 0

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
            return degen_count, welded, 0, 0

        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.normal_update()

        centroid = sum((v.co for v in bm.verts), Vector()) / len(bm.verts)

        # Check if majority of normals point away from centroid;
        # if not, the recalc picked the wrong direction -- flip all.
        inward = sum(
            1 for f in bm.faces
            if f.normal.length_squared > 1e-12
            and centroid.dot(f.normal.normalized())
            > f.verts[0].co.dot(f.normal.normalized()) + 1e-6
        )
        outward = len(bm.faces) - inward
        if inward > outward:
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
            bm.normal_update()

        normals_fixed = 0
        remaining = 0
        for face in bm.faces:
            normal = face.normal
            if normal.length_squared < 1e-12:
                remaining += 1
                continue
            n = normal.normalized()
            plane_d = face.verts[0].co.dot(n)
            if centroid.dot(n) > plane_d + 1e-6:
                remaining += 1

        if degen_count > 0 or welded > 0 or remaining < inward:
            normals_fixed = max(0, inward - remaining)

        bm.transform(inv_mat)
        bm.to_mesh(mesh)
        mesh.update()

        return degen_count, welded, normals_fixed, remaining
    finally:
        bm.free()


class CursorBBox_OT_fix_convexity(bpy.types.Operator):
    """Delete degenerate faces, weld vertices, and recalculate normals"""
    bl_idname = "cursor_bbox.fix_convexity"
    bl_label = "Fix Convexity"
    bl_description = (
        "Delete zero-area faces, weld nearby vertices, and "
        "recalculate normals outward"
    )
    bl_options = {'REGISTER', 'UNDO'}

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
        touched_objects = 0

        for obj in mesh_objects:
            degen, welded, normals, remaining = fix_invalid_faces(
                obj, self.area_threshold, self.weld_distance,
            )
            if degen + welded + normals > 0:
                touched_objects += 1
                total_degen += degen
                total_welded += welded
                total_normals += normals
                total_remaining += remaining

        if total_degen + total_welded + total_normals == 0:
            self.report({'INFO'}, "All meshes are already clean")
            return {'FINISHED'}

        parts = []
        if total_degen:
            parts.append(f"{total_degen} degenerate deleted")
        if total_welded:
            parts.append(f"{total_welded} verts welded")
        if total_normals:
            parts.append(f"{total_normals} normals fixed")
        msg = f"{', '.join(parts)} on {touched_objects} object(s)"

        if total_remaining:
            msg += f" — {total_remaining} genuine concavities remain"
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
            is_clean, total_faces, invalid, degenerate = check_mesh_convexity(obj)
            if is_clean:
                clean_count += 1
            else:
                bad_objects.append((obj, total_faces, invalid, degenerate))

        total = len(mesh_objects)

        if not bad_objects:
            self.report(
                {'INFO'},
                f"All {total} selected mesh(es) are convex",
            )
            return {'FINISHED'}

        for obj, total_faces, invalid, degenerate in bad_objects:
            parts = []
            if invalid:
                parts.append(f"{len(invalid)} non-convex")
            if degenerate:
                parts.append(f"{len(degenerate)} degenerate")
            self.report(
                {'WARNING'},
                f"\"{obj.name}\": {' + '.join(parts)}"
                f" / {total_faces} faces",
            )
        self.report(
            {'WARNING'},
            f"{len(bad_objects)}/{total} mesh(es) have issues"
            f" ({clean_count} clean)",
        )

        bpy.ops.object.select_all(action='DESELECT')
        for obj, _, _, _ in bad_objects:
            obj.select_set(True)
        context.view_layer.objects.active = bad_objects[0][0]

        bpy.ops.object.mode_set(mode='EDIT')
        context.tool_settings.mesh_select_mode = (False, False, True)
        bpy.ops.mesh.select_all(action='DESELECT')

        for obj, _, invalid, degenerate in bad_objects:
            all_bad = invalid | degenerate
            bm = bmesh.from_edit_mesh(obj.data)
            bm.faces.ensure_lookup_table()
            for idx in all_bad:
                if idx < len(bm.faces):
                    bm.faces[idx].select = True
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)

        return {'FINISHED'}
