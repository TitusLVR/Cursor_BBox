"""Shared OBJ export/import and hull organization utilities for collision decomposition operators."""

import bpy

from .utils import assign_object_styles


def export_mesh_as_obj(context, obj, export_path):
    """
    Export a single mesh object as a triangulated OBJ file.

    Selects only the target object, exports with modifiers applied,
    Y-up / -Z-forward axis convention, no materials/UVs/colors.

    Args:
        context: Blender context.
        obj: Mesh object to export.
        export_path: Absolute file path for the output .obj file.
    """
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    context.view_layer.objects.active = obj

    bpy.ops.wm.obj_export(
        filepath=export_path,
        check_existing=False,
        export_selected_objects=True,
        apply_modifiers=True,
        up_axis='Y',
        forward_axis='NEGATIVE_Z',
        global_scale=1.0,
        export_materials=False,
        export_triangulated_mesh=True,
        export_uv=False,
        export_normals=False,
        export_colors=False,
    )


def _obj_to_blender_coord(x, y, z):
    """Map an OBJ vertex (Y-up, -Z-forward) to Blender space (Z-up, -Y-forward).

    This reproduces exactly what ``bpy.ops.wm.obj_import`` does with
    ``up_axis='Y', forward_axis='NEGATIVE_Z'`` (a +90deg rotation about X),
    verified against the operator on multi-object OBJ files.
    """
    return (x, -z, y)


def import_obj_as_new_objects(filepath):
    """
    Build Blender objects from an OBJ file using the low-level ``bpy.data`` API.

    IMPORTANT: this deliberately does NOT call ``bpy.ops.wm.obj_import``. The
    result is imported from a ``bpy.app.timers`` callback (see
    async_subprocess._finish_job), and invoking operators from a timer pushes
    undo steps from an unsafe context. In scenes with linked libraries that
    corrupts the undo memfile and crashes Blender on the next depsgraph rebuild
    / Ctrl+Z (EXCEPTION_ACCESS_VIOLATION in DepsgraphNodeBuilder::add_id_node).
    Building data directly avoids any operator-driven undo/depsgraph churn.

    Objects are created UNLINKED (not in any collection); organize_hull_objects
    links them into the target collection.

    Args:
        filepath: Absolute path to the .obj file.

    Returns:
        list[bpy.types.Object]: Newly created, unlinked Blender objects.
    """
    # Parse the OBJ: a flat global vertex list plus per-object face groups
    # (the decomposition helper writes faces with cumulative global indices).
    global_verts = []
    groups = []  # list of (name, faces) where faces use 0-based global indices
    cur_name = None
    cur_faces = None

    def _flush():
        if cur_faces is not None:
            groups.append((cur_name or "hull", cur_faces))

    with open(filepath, 'r') as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
            tag = parts[0]
            if tag == 'v' and len(parts) >= 4:
                global_verts.append(
                    _obj_to_blender_coord(float(parts[1]),
                                          float(parts[2]),
                                          float(parts[3]))
                )
            elif tag == 'o':
                _flush()
                cur_name = parts[1] if len(parts) > 1 else "hull"
                cur_faces = []
            elif tag == 'f':
                if cur_faces is None:
                    cur_faces = []
                face = [int(tok.split('/')[0]) - 1 for tok in parts[1:]]
                cur_faces.append(face)
    _flush()

    # If the file had no 'o' lines, treat everything as a single object.
    if not groups and global_verts:
        groups = [("hull", [])]

    new_objects = []
    for name, faces in groups:
        # Remap the global vertex indices used by this group to a local set.
        used = []
        seen = {}
        local_faces = []
        for face in faces:
            local_face = []
            for gi in face:
                if gi not in seen:
                    seen[gi] = len(used)
                    used.append(gi)
                local_face.append(seen[gi])
            local_faces.append(local_face)

        local_verts = [global_verts[gi] for gi in used]

        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(local_verts, [], local_faces)
        mesh.update()

        obj = bpy.data.objects.new(name, mesh)
        new_objects.append(obj)

    return new_objects


def organize_hull_objects(context, new_objects, source_name, prefix, collection):
    """
    Rename imported hull objects, move them into *collection*, and apply addon material/color.

    Args:
        context: Blender context.
        new_objects: List of freshly imported Blender objects.
        source_name: Name of the source mesh (used in the new name).
        prefix: Short tag prepended to each hull name (e.g. "VHACD", "CoACD").
        collection: Target bpy.types.Collection.

    Returns:
        int: Number of objects organized.
    """
    for i, hull in enumerate(new_objects):
        hull.name = f"{prefix}_{source_name}_{i:03d}"
        if hull.data:
            hull.data.name = hull.name

        for coll in hull.users_collection:
            coll.objects.unlink(hull)
        collection.objects.link(hull)

        assign_object_styles(context, hull)

    return len(new_objects)
