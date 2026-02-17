bl_info = {
    "name": "Cursor Aligned Bounding Box",
    "author": "Titus",
    "version": (1, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Cursor BBox",
    "description": "Set cursor and fit bounding shapes (Box, Hull, Sphere) with face marking.",
    "warning": "",
    "doc_url": "",
    "category": "Object",
}

import bpy

# Import from new structure
from .settings import properties
from .settings.preferences import CursorBBoxPreferences
from .operators.set_cursor import CursorBBox_OT_set_cursor
from .operators.set_and_fit_box import CursorBBox_OT_set_and_fit_box
from .operators.interactive_box import CursorBBox_OT_interactive_box
from .operators.create_box import CursorBBox_OT_create_box
from .operators.interactive_hull import CursorBBox_OT_interactive_hull
from .operators.interactive_sphere import CursorBBox_OT_interactive_sphere
from .operators.collision_vhacd import CursorBBox_OT_collision_vhacd
from .operators.collision_coacd import CursorBBox_OT_collision_coacd
from .operators.collision_coacd_u import CursorBBox_OT_collision_coacd_u
from .ui.panel import CursorBBox_PT_main
from .ui.pie_menu import CursorBBox_MT_pie_menu


class CursorBBox_OT_cancel_decomposition(bpy.types.Operator):
    """Cancel all running decomposition jobs"""
    bl_idname = "cursor_bbox.cancel_decomposition"
    bl_label = "Cancel Decomposition"

    def execute(self, context):
        from .functions import async_subprocess
        async_subprocess.cancel_all()
        self.report({'INFO'}, "All decomposition jobs cancelled")
        return {'FINISHED'}


class CursorBBox_OT_install_coacd_u(bpy.types.Operator):
    """Download and install coacd_u from GitHub releases into Blender's Python"""
    bl_idname = "cursor_bbox.install_coacd_u"
    bl_label = "Install coacd_u"
    bl_description = (
        "Download the coacd_u wheel from GitHub releases "
        "and install it into Blender's bundled Python"
    )

    def execute(self, context):
        import subprocess
        import sys
        import json
        import urllib.request

        print("[CoACD-U] Starting installation...")

        # Ensure pip is available
        try:
            subprocess.run(
                [sys.executable, '-m', 'ensurepip', '--default-pip'],
                capture_output=True, timeout=60,
            )
        except Exception:
            pass

        # Fetch latest release info from GitHub
        print("[CoACD-U] Fetching latest release from GitHub...")
        try:
            req = urllib.request.Request(
                "https://api.github.com/repos/Ultikynnys/CoACD/releases/latest",
                headers={
                    'Accept': 'application/vnd.github.v3+json',
                    'User-Agent': 'Blender-CursorBBox-Addon',
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                release = json.loads(resp.read())
        except Exception as e:
            self.report({'ERROR'}, f"Failed to fetch release info: {e}")
            return {'CANCELLED'}

        # Determine platform key for wheel matching
        if sys.platform == 'win32':
            plat_key = 'win'
        elif sys.platform == 'linux':
            plat_key = 'linux'
        elif sys.platform == 'darwin':
            plat_key = 'macosx'
        else:
            plat_key = sys.platform

        wheel_url = None
        wheel_name = None
        for asset in release.get('assets', []):
            name = asset.get('name', '')
            if name.endswith('.whl') and plat_key in name:
                wheel_url = asset['browser_download_url']
                wheel_name = name
                break

        if not wheel_url:
            self.report(
                {'ERROR'},
                f"No wheel found for this platform. "
                f"Download manually from: https://github.com/Ultikynnys/CoACD/releases"
            )
            return {'CANCELLED'}

        # Install with pip
        print(f"[CoACD-U] Installing {wheel_name}...")
        try:
            popen_kwargs = {}
            if sys.platform == 'win32':
                popen_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--no-deps', wheel_url],
                capture_output=True, text=True, timeout=120,
                **popen_kwargs,
            )
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr)

            if result.returncode != 0:
                error_msg = (result.stderr or result.stdout or "Unknown error").strip()
                self.report({'ERROR'}, f"pip install failed. Check System Console for details.")
                print(f"[CoACD-U] pip error: {error_msg}")
                return {'CANCELLED'}

        except subprocess.TimeoutExpired:
            self.report({'ERROR'}, "Installation timed out after 120 seconds")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Installation failed: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, "coacd_u installed successfully! Restart Blender to use it.")
        print("[CoACD-U] Installation complete! Restart Blender to use it.")
        return {'FINISHED'}


classes = [
    CursorBBoxPreferences,
    CursorBBox_OT_set_cursor,
    CursorBBox_OT_set_and_fit_box,
    CursorBBox_OT_interactive_box,
    CursorBBox_OT_create_box,
    CursorBBox_OT_interactive_hull,
    CursorBBox_OT_interactive_sphere,
    CursorBBox_OT_collision_vhacd,
    CursorBBox_OT_collision_coacd,
    CursorBBox_OT_collision_coacd_u,
    CursorBBox_OT_cancel_decomposition,
    CursorBBox_OT_install_coacd_u,
    CursorBBox_PT_main,
    CursorBBox_MT_pie_menu,
]

addon_keymaps = []

def register_keymap():
    wm = bpy.context.window_manager
    if not wm:
        return
    kc = wm.keyconfigs.addon
    if not kc:
        return
    km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')

    kmi = km.keymap_items.new("wm.call_menu_pie", 'C', 'PRESS', shift=True, alt=True)
    kmi.properties.name = "CURSOR_BBOX_MT_pie_menu"
    addon_keymaps.append((km, kmi))

def unregister_keymap():
    for km, kmi in addon_keymaps:
        if km and kmi:
            km.keymap_items.remove(kmi)
    addon_keymaps.clear()

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    properties.register()
    register_keymap()

def unregister():
    from .functions import async_subprocess
    async_subprocess.cancel_all()
    unregister_keymap()
    properties.unregister()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)