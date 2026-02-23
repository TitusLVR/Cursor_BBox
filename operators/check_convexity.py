import bpy
import bmesh
from mathutils import Vector


def check_mesh_convexity(mesh_obj):
    """Check whether a mesh object is convex using the centroid-plane test.

    For a convex mesh, the centroid (average of all vertices) must lie on
    the inside (or boundary) of every face plane.  If the centroid is on
    the *outside* of any face plane, the mesh is not convex.

    Returns a tuple (is_convex, total_faces, invalid_faces).
    """
    mesh = mesh_obj.data
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.transform(mesh_obj.matrix_world)

        if len(bm.verts) < 4 or len(bm.faces) == 0:
            return True, len(bm.faces), 0

        centroid = sum((v.co for v in bm.verts), Vector()) / len(bm.verts)

        bmesh.ops.triangulate(bm, faces=bm.faces[:])

        invalid = 0
        for face in bm.faces:
            normal = face.normal
            if normal.length_squared < 1e-12:
                continue
            plane_d = face.verts[0].co.dot(normal)
            if centroid.dot(normal) > plane_d + 1e-6:
                invalid += 1

        return invalid == 0, len(bm.faces), invalid
    finally:
        bm.free()


class CursorBBox_OT_check_convexity(bpy.types.Operator):
    """Check whether selected objects have convex collision meshes"""
    bl_idname = "cursor_bbox.check_convexity"
    bl_label = "Check Convexity"
    bl_description = (
        "Verify that selected mesh objects are convex. "
        "Non-convex shapes can cause issues with collision systems"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(
            obj.type == 'MESH' for obj in context.selected_objects
        )

    def execute(self, context):
        mesh_objects = [
            obj for obj in context.selected_objects if obj.type == 'MESH'
        ]
        if not mesh_objects:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}

        non_convex = []
        convex_count = 0

        for obj in mesh_objects:
            is_convex, total_faces, invalid_faces = check_mesh_convexity(obj)
            if is_convex:
                convex_count += 1
            else:
                non_convex.append((obj, total_faces, invalid_faces))

        total = len(mesh_objects)

        if not non_convex:
            self.report(
                {'INFO'},
                f"All {total} selected mesh(es) are convex",
            )
        else:
            for obj, total_faces, invalid_faces in non_convex:
                self.report(
                    {'WARNING'},
                    f"\"{obj.name}\": {invalid_faces}/{total_faces} "
                    f"triangles violate convexity",
                )
            self.report(
                {'WARNING'},
                f"{len(non_convex)}/{total} mesh(es) are NOT convex"
                f" ({convex_count} passed)",
            )

            bpy.ops.object.select_all(action='DESELECT')
            for obj, _, _ in non_convex:
                obj.select_set(True)
            if non_convex:
                context.view_layer.objects.active = non_convex[0][0]

        return {'FINISHED'}
