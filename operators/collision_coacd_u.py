import bpy
import subprocess
import tempfile
import os
import sys
import json
import shutil

from ..functions.collision_io import export_mesh_as_obj
from ..functions import async_subprocess


# Helper script executed as a subprocess using Blender's Python.
# It imports coacd_u, reads an OBJ, runs decomposition, and writes the result.
_HELPER_SCRIPT = '''
import sys
import json
import numpy as np


def parse_obj(filepath):
    """Parse a simple OBJ file, returning vertices and faces."""
    vertices = []
    faces = []
    with open(filepath, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            if parts[0] == 'v' and len(parts) >= 4:
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif parts[0] == 'f':
                face = []
                for token in parts[1:]:
                    idx = int(token.split('/')[0]) - 1
                    face.append(idx)
                faces.append(face)
    return np.array(vertices, dtype=np.float64), np.array(faces, dtype=np.int32)


def write_obj(filepath, parts):
    """Write decomposed parts as a multi-object OBJ file."""
    vertex_offset = 0
    with open(filepath, 'w') as f:
        f.write("# CoACD-U decomposition output\\n")
        for i, (verts, tris) in enumerate(parts):
            f.write(f"o hull_{i:03d}\\n")
            for v in verts:
                f.write(f"v {float(v[0]):.6f} {float(v[1]):.6f} {float(v[2]):.6f}\\n")
            for face in tris:
                indices = " ".join(str(int(idx) + 1 + vertex_offset) for idx in face)
                f.write(f"f {indices}\\n")
            vertex_offset += len(verts)


params = json.load(open(sys.argv[1]))

try:
    import coacd_u as coacd
except ImportError:
    print("ERROR: coacd_u not found. Install from: https://github.com/Ultikynnys/CoACD/releases")
    sys.exit(1)

print("CoACD-U: Loading mesh...")
verts, faces = parse_obj(params["input"])
print(f"CoACD-U: {len(verts)} vertices, {len(faces)} faces")

mesh = coacd.Mesh(verts, faces)

print("CoACD-U: Running decomposition...")
parts = coacd.run_coacd(
    mesh,
    threshold=params["threshold"],
    max_convex_hull=params["max_convex_hull"],
    preprocess_mode=params["preprocess_mode"],
    preprocess_resolution=params["prep_resolution"],
    resolution=params["resolution"],
    mcts_nodes=params["mcts_nodes"],
    mcts_iterations=params["mcts_iterations"],
    mcts_max_depth=params["mcts_max_depth"],
    pca=params["pca"],
    merge=params["merge"],
    seed=params["seed"],
)

print(f"CoACD-U: Decomposed into {len(parts)} parts")
write_obj(params["output"], parts)
print("CoACD-U: Done")
'''


# Preset values keyed by enum identifier
# 10-step gradient from least detail preserved to most detail preserved
COACD_U_PRESETS = {
    'D01': {
        'threshold': 0.80,
        'prep_resolution': 20,
        'mcts_iterations': 60,
        'mcts_max_depth': 2,
        'mcts_nodes': 10,
        'resolution': 1000,
    },
    'D02': {
        'threshold': 0.50,
        'prep_resolution': 25,
        'mcts_iterations': 60,
        'mcts_max_depth': 2,
        'mcts_nodes': 10,
        'resolution': 1000,
    },
    'D03': {
        'threshold': 0.30,
        'prep_resolution': 30,
        'mcts_iterations': 70,
        'mcts_max_depth': 2,
        'mcts_nodes': 12,
        'resolution': 1200,
    },
    'D04': {
        'threshold': 0.15,
        'prep_resolution': 40,
        'mcts_iterations': 80,
        'mcts_max_depth': 2,
        'mcts_nodes': 15,
        'resolution': 1500,
    },
    'D05': {
        'threshold': 0.05,
        'prep_resolution': 50,
        'mcts_iterations': 150,
        'mcts_max_depth': 3,
        'mcts_nodes': 20,
        'resolution': 2000,
    },
    'D06': {
        'threshold': 0.035,
        'prep_resolution': 55,
        'mcts_iterations': 200,
        'mcts_max_depth': 3,
        'mcts_nodes': 22,
        'resolution': 2500,
    },
    'D07': {
        'threshold': 0.025,
        'prep_resolution': 60,
        'mcts_iterations': 250,
        'mcts_max_depth': 4,
        'mcts_nodes': 25,
        'resolution': 3500,
    },
    'D08': {
        'threshold': 0.018,
        'prep_resolution': 70,
        'mcts_iterations': 300,
        'mcts_max_depth': 4,
        'mcts_nodes': 28,
        'resolution': 5000,
    },
    'D09': {
        'threshold': 0.013,
        'prep_resolution': 85,
        'mcts_iterations': 400,
        'mcts_max_depth': 5,
        'mcts_nodes': 30,
        'resolution': 7000,
    },
    'D10': {
        'threshold': 0.01,
        'prep_resolution': 100,
        'mcts_iterations': 500,
        'mcts_max_depth': 5,
        'mcts_nodes': 35,
        'resolution': 10000,
    },
}


def is_coacd_u_available():
    """Check whether the coacd_u Python package is importable."""
    try:
        import coacd_u  # noqa: F401
        return True
    except ImportError:
        return False


class CursorBBox_OT_collision_coacd_u(bpy.types.Operator):
    """Decompose selected mesh(es) into convex hulls using CoACD-U (Ultikynnys variant, 3-10x faster)"""
    bl_idname = "cursor_bbox.collision_coacd_u"
    bl_label = "CoACD-U Decomposition"
    bl_description = (
        "Fast collision-aware approximate convex decomposition "
        "using CoACD-U (Ultikynnys variant, 3-10x faster, PCA bug fixed)"
    )
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
        if not is_coacd_u_available():
            self.report(
                {'ERROR'},
                "coacd_u not installed. Install the wheel from "
                "https://github.com/Ultikynnys/CoACD/releases "
                "into Blender's Python."
            )
            return {'CANCELLED'}

        mesh_objects = [o for o in context.selected_objects if o.type == 'MESH']
        if not mesh_objects:
            self.report({'ERROR'}, "No mesh objects selected")
            return {'CANCELLED'}

        pg = context.scene.cursor_bbox_coacd_u

        # Save selection state (export_mesh_as_obj changes it)
        original_selected = list(context.selected_objects)
        original_active = context.view_layer.objects.active

        launched = 0
        for obj in mesh_objects:
            if self._launch_job(context, obj, pg):
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
                f"CoACD-U: Started {launched} job(s). "
                f"Open Window > Toggle System Console for progress."
            )
        else:
            self.report({'WARNING'}, "CoACD-U: Failed to start any jobs")

        return {'FINISHED'}

    def _launch_job(self, context, obj, pg):
        """Export mesh, write helper script + params, launch as subprocess."""
        temp_dir = tempfile.mkdtemp(prefix="coacd_u_")
        export_path = os.path.join(temp_dir, "input.obj")
        output_path = os.path.join(temp_dir, "output.obj")
        script_path = os.path.join(temp_dir, "run_coacd_u.py")
        params_path = os.path.join(temp_dir, "params.json")

        export_mesh_as_obj(context, obj, export_path)

        # Write the helper script
        with open(script_path, 'w') as f:
            f.write(_HELPER_SCRIPT)

        # Write parameters as JSON (avoids shell-escaping issues on Windows)
        params = {
            'input': export_path,
            'output': output_path,
            'threshold': pg.threshold,
            'max_convex_hull': pg.max_convex_hull,
            'preprocess_mode': pg.preprocess_mode,
            'prep_resolution': pg.prep_resolution,
            'resolution': pg.resolution,
            'mcts_nodes': pg.mcts_nodes,
            'mcts_iterations': pg.mcts_iterations,
            'mcts_max_depth': pg.mcts_max_depth,
            'pca': pg.pca,
            'merge': pg.merge,
            'seed': pg.seed,
        }
        with open(params_path, 'w') as f:
            json.dump(params, f)

        try:
            popen_kwargs = {}
            if sys.platform == 'win32':
                popen_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

            process = subprocess.Popen(
                [sys.executable, script_path, params_path],
                cwd=temp_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True, bufsize=1,
                **popen_kwargs,
            )

            async_subprocess.submit(
                process, temp_dir, output_path,
                obj.name, "CoACD-U", "CoACD_U",
            )
            return True

        except Exception as e:
            self.report({'ERROR'}, f"Failed to start CoACD-U for '{obj.name}': {e}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False
