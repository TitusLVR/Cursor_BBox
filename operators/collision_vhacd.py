import bpy
import subprocess
import tempfile
import os
import sys
import shutil

from ..functions.collision_io import export_mesh_as_obj
from ..functions import async_subprocess

# Preset values keyed by enum identifier
# 10-step gradient from least detail preserved to most detail preserved
# Hulls scale: 2 → 4 → 8 → 16 → 32 → 64 → 128 → 256 → 384 → 512
VHACD_PRESETS = {
    'D01': {
        'max_convex_hulls': 2,
        'resolution': 50000,
        'min_volume_error': 10.0,
        'max_recursion_depth': 3,
        'max_vertices_per_hull': 32,
        'min_edge_length': 5,
        'find_best_plane': False,
    },
    'D02': {
        'max_convex_hulls': 4,
        'resolution': 100000,
        'min_volume_error': 7.0,
        'max_recursion_depth': 4,
        'max_vertices_per_hull': 48,
        'min_edge_length': 4,
        'find_best_plane': False,
    },
    'D03': {
        'max_convex_hulls': 8,
        'resolution': 200000,
        'min_volume_error': 4.0,
        'max_recursion_depth': 6,
        'max_vertices_per_hull': 64,
        'min_edge_length': 4,
        'find_best_plane': False,
    },
    'D04': {
        'max_convex_hulls': 16,
        'resolution': 400000,
        'min_volume_error': 2.5,
        'max_recursion_depth': 8,
        'max_vertices_per_hull': 96,
        'min_edge_length': 3,
        'find_best_plane': False,
    },
    'D05': {
        'max_convex_hulls': 32,
        'resolution': 600000,
        'min_volume_error': 1.0,
        'max_recursion_depth': 10,
        'max_vertices_per_hull': 128,
        'min_edge_length': 2,
        'find_best_plane': False,
    },
    'D06': {
        'max_convex_hulls': 64,
        'resolution': 1000000,
        'min_volume_error': 0.5,
        'max_recursion_depth': 11,
        'max_vertices_per_hull': 192,
        'min_edge_length': 2,
        'find_best_plane': False,
    },
    'D07': {
        'max_convex_hulls': 128,
        'resolution': 2000000,
        'min_volume_error': 0.2,
        'max_recursion_depth': 12,
        'max_vertices_per_hull': 256,
        'min_edge_length': 2,
        'find_best_plane': True,
    },
    'D08': {
        'max_convex_hulls': 256,
        'resolution': 4000000,
        'min_volume_error': 0.1,
        'max_recursion_depth': 13,
        'max_vertices_per_hull': 512,
        'min_edge_length': 1,
        'find_best_plane': True,
    },
    'D09': {
        'max_convex_hulls': 384,
        'resolution': 7000000,
        'min_volume_error': 0.05,
        'max_recursion_depth': 14,
        'max_vertices_per_hull': 1024,
        'min_edge_length': 1,
        'find_best_plane': True,
    },
    'D10': {
        'max_convex_hulls': 512,
        'resolution': 10000000,
        'min_volume_error': 0.01,
        'max_recursion_depth': 15,
        'max_vertices_per_hull': 2048,
        'min_edge_length': 1,
        'find_best_plane': True,
    },
}


class CursorBBox_OT_collision_vhacd(bpy.types.Operator):
    """Decompose selected mesh(es) into convex hulls using V-HACD"""
    bl_idname = "cursor_bbox.collision_vhacd"
    bl_label = "V-HACD Decomposition"
    bl_description = "Approximate convex decomposition using V-HACD (Voxelized Hierarchical ACD)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if async_subprocess.is_busy():
            cls.poll_message_set("A decomposition job is already running")
            return False
        if context.mode != 'OBJECT':
            return False
        return any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        prefs = context.preferences.addons["Cursor_BBox"].preferences
        vhacd_path = bpy.path.abspath(prefs.vhacd_executable)

        if not vhacd_path or not os.path.isfile(vhacd_path):
            self.report(
                {'ERROR'},
                "V-HACD executable not found. Set path in: "
                "Edit > Preferences > Add-ons > Cursor BBox > Tools"
            )
            return {'CANCELLED'}

        mesh_objects = [o for o in context.selected_objects if o.type == 'MESH']
        if not mesh_objects:
            self.report({'ERROR'}, "No mesh objects selected")
            return {'CANCELLED'}

        pg = context.scene.cursor_bbox_vhacd

        # Save selection state (export_mesh_as_obj changes it)
        original_selected = list(context.selected_objects)
        original_active = context.view_layer.objects.active

        launched = 0
        for obj in mesh_objects:
            if self._launch_job(context, obj, vhacd_path, pg):
                launched += 1

        # Restore selection
        bpy.ops.object.select_all(action='DESELECT')
        for obj in original_selected:
            try:
                obj.select_set(True)
            except Exception:
                pass
        context.view_layer.objects.active = original_active

        if launched > 0:
            self.report(
                {'INFO'},
                f"V-HACD: Started {launched} job(s). "
                f"Open Window > Toggle System Console for progress."
            )
        else:
            self.report({'WARNING'}, "V-HACD: Failed to start any jobs")

        return {'FINISHED'}

    def _launch_job(self, context, obj, vhacd_path, pg):
        """Export mesh, launch V-HACD as a non-blocking process."""
        temp_dir = tempfile.mkdtemp(prefix="vhacd_")
        export_path = os.path.join(temp_dir, "input.obj")
        result_path = os.path.join(temp_dir, "decomp.obj")

        export_mesh_as_obj(context, obj, export_path)

        cmd = [
            vhacd_path,
            export_path,
            '-h', str(pg.max_convex_hulls),
            '-r', str(pg.resolution),
            '-e', str(pg.min_volume_error),
            '-d', str(pg.max_recursion_depth),
            '-v', str(pg.max_vertices_per_hull),
            '-s', 'true' if pg.shrink_wrap else 'false',
            '-f', pg.fill_mode,
            '-l', str(pg.min_edge_length),
            '-p', 'true' if pg.find_best_plane else 'false',
            '-g', 'true',
        ]

        try:
            popen_kwargs = {}
            if sys.platform == 'win32':
                popen_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

            process = subprocess.Popen(
                cmd, cwd=temp_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, bufsize=1,
                **popen_kwargs,
            )

            async_subprocess.submit(
                process, temp_dir, result_path,
                obj.name, "V-HACD", "VHACD",
            )
            return True

        except Exception as e:
            self.report({'ERROR'}, f"Failed to start V-HACD for '{obj.name}': {e}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False
