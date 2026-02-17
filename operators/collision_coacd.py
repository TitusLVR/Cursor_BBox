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
COACD_PRESETS = {
    'D01': {
        'threshold': 0.80,
        'prep_resolution': 20,
        'mcts_iteration': 60,
        'mcts_depth': 2,
        'mcts_nodes': 10,
        'hausdorff_resolution': 1000,
    },
    'D02': {
        'threshold': 0.50,
        'prep_resolution': 25,
        'mcts_iteration': 60,
        'mcts_depth': 2,
        'mcts_nodes': 10,
        'hausdorff_resolution': 1000,
    },
    'D03': {
        'threshold': 0.30,
        'prep_resolution': 30,
        'mcts_iteration': 70,
        'mcts_depth': 2,
        'mcts_nodes': 12,
        'hausdorff_resolution': 1200,
    },
    'D04': {
        'threshold': 0.15,
        'prep_resolution': 40,
        'mcts_iteration': 80,
        'mcts_depth': 2,
        'mcts_nodes': 15,
        'hausdorff_resolution': 1500,
    },
    'D05': {
        'threshold': 0.05,
        'prep_resolution': 50,
        'mcts_iteration': 150,
        'mcts_depth': 3,
        'mcts_nodes': 20,
        'hausdorff_resolution': 2000,
    },
    'D06': {
        'threshold': 0.035,
        'prep_resolution': 55,
        'mcts_iteration': 200,
        'mcts_depth': 3,
        'mcts_nodes': 22,
        'hausdorff_resolution': 2500,
    },
    'D07': {
        'threshold': 0.025,
        'prep_resolution': 60,
        'mcts_iteration': 250,
        'mcts_depth': 4,
        'mcts_nodes': 25,
        'hausdorff_resolution': 3500,
    },
    'D08': {
        'threshold': 0.018,
        'prep_resolution': 70,
        'mcts_iteration': 300,
        'mcts_depth': 4,
        'mcts_nodes': 28,
        'hausdorff_resolution': 5000,
    },
    'D09': {
        'threshold': 0.013,
        'prep_resolution': 85,
        'mcts_iteration': 400,
        'mcts_depth': 5,
        'mcts_nodes': 30,
        'hausdorff_resolution': 7000,
    },
    'D10': {
        'threshold': 0.01,
        'prep_resolution': 100,
        'mcts_iteration': 500,
        'mcts_depth': 5,
        'mcts_nodes': 35,
        'hausdorff_resolution': 10000,
    },
}


class CursorBBox_OT_collision_coacd(bpy.types.Operator):
    """Decompose selected mesh(es) into convex hulls using CoACD"""
    bl_idname = "cursor_bbox.collision_coacd"
    bl_label = "CoACD Decomposition"
    bl_description = "Collision-aware approximate convex decomposition using CoACD (SIGGRAPH 2022)"
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
        coacd_path = bpy.path.abspath(prefs.coacd_executable)

        if not coacd_path or not os.path.isfile(coacd_path):
            self.report(
                {'ERROR'},
                "CoACD executable not found. Set path in: "
                "Edit > Preferences > Add-ons > Cursor BBox > Tools"
            )
            return {'CANCELLED'}

        mesh_objects = [o for o in context.selected_objects if o.type == 'MESH']
        if not mesh_objects:
            self.report({'ERROR'}, "No mesh objects selected")
            return {'CANCELLED'}

        pg = context.scene.cursor_bbox_coacd

        # Save selection state (export_mesh_as_obj changes it)
        original_selected = list(context.selected_objects)
        original_active = context.view_layer.objects.active

        launched = 0
        for obj in mesh_objects:
            if self._launch_job(context, obj, coacd_path, pg):
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
                f"CoACD: Started {launched} job(s). "
                f"Open Window > Toggle System Console for progress."
            )
        else:
            self.report({'WARNING'}, "CoACD: Failed to start any jobs")

        return {'FINISHED'}

    def _launch_job(self, context, obj, coacd_path, pg):
        """Export mesh, launch CoACD as a non-blocking process."""
        temp_dir = tempfile.mkdtemp(prefix="coacd_")
        export_path = os.path.join(temp_dir, "input.obj")
        output_path = os.path.join(temp_dir, "output.obj")

        export_mesh_as_obj(context, obj, export_path)

        cmd = [
            coacd_path,
            '-i', export_path,
            '-o', output_path,
            '-t', str(pg.threshold),
            '-pm', pg.preprocess_mode,
            '-pr', str(pg.prep_resolution),
            '-mi', str(pg.mcts_iteration),
            '-md', str(pg.mcts_depth),
            '-mn', str(pg.mcts_nodes),
            '-r', str(pg.hausdorff_resolution),
            '-k', str(pg.rv_k),
            '-am', pg.approximate_mode,
        ]

        if pg.max_convex_hull != -1:
            cmd.extend(['-c', str(pg.max_convex_hull)])
        if pg.no_merge:
            cmd.append('-nm')
        if pg.pca:
            cmd.append('--pca')
        if pg.decimate:
            cmd.append('-d')
            cmd.extend(['-dt', str(pg.max_ch_vertex)])
        if pg.extrude:
            cmd.append('-ex')
            cmd.extend(['-em', str(pg.extrude_margin)])
        if pg.seed > 0:
            cmd.extend(['--seed', str(pg.seed)])

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
                process, temp_dir, output_path,
                obj.name, "CoACD", "CoACD",
            )
            return True

        except Exception as e:
            self.report({'ERROR'}, f"Failed to start CoACD for '{obj.name}': {e}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False
