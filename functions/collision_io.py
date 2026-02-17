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


def import_obj_as_new_objects(filepath):
    """
    Import an OBJ file and return a list of newly created Blender objects.

    Tracks existing objects before import and returns only the delta.

    Args:
        filepath: Absolute path to the .obj file.

    Returns:
        list[bpy.types.Object]: Newly imported objects (may be empty).
    """
    existing = set(bpy.data.objects[:])

    bpy.ops.wm.obj_import(
        filepath=filepath,
        up_axis='Y',
        forward_axis='NEGATIVE_Z',
    )

    return [o for o in bpy.data.objects if o not in existing]


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
