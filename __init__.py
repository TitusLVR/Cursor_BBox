bl_info = {
    "name": "Cursor Aligned Bounding Box",
    "author": "Titus",
    "version": (1, 4, 0),  # Incremented for structure update
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Cursor BBox",
    "description": "Place cursor with raycast and create cursor-aligned bounding boxes with edge selection and face marking - Optimized Edition with Split Architecture",
    "warning": "",
    "doc_url": "",
    "category": "Object",
}

import bpy

from . import properties

from .preferences import CursorBBoxPreferences
from .operators import (
    VIEW3D_OT_cursor_place_raycast,
    VIEW3D_OT_cursor_place_and_bbox,
    VIEW3D_OT_cursor_place_and_bbox_with_marking,
    VIEW3D_OT_create_cursor_bbox,
)
from .ui import VIEW3D_PT_cursor_bbox_panel

classes = [
    CursorBBoxPreferences,
    VIEW3D_OT_cursor_place_raycast,
    VIEW3D_OT_cursor_place_and_bbox,
    VIEW3D_OT_cursor_place_and_bbox_with_marking,
    VIEW3D_OT_create_cursor_bbox,
    VIEW3D_PT_cursor_bbox_panel,
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
    kmi = km.keymap_items.new("view3d.cursor_place_raycast", 'C', 'PRESS', ctrl=True, shift=True)
    kmi.properties.align_to_face = True
    addon_keymaps.append((km, kmi))
    kmi = km.keymap_items.new("view3d.cursor_place_and_bbox", 'B', 'PRESS', ctrl=True, shift=True, alt=True)
    kmi.properties.push_value = 0.01
    kmi.properties.align_to_face = True
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