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
from .ui.panel import CursorBBox_PT_main
from .ui.pie_menu import CursorBBox_MT_pie_menu

classes = [
    CursorBBoxPreferences,
    CursorBBox_OT_set_cursor,
    CursorBBox_OT_set_and_fit_box,
    CursorBBox_OT_interactive_box,
    CursorBBox_OT_create_box,
    CursorBBox_OT_interactive_hull,
    CursorBBox_OT_interactive_sphere,
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
    unregister_keymap()
    properties.unregister()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)