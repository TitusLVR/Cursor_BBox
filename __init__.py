bl_info = {
    "name": "Cursor Aligned Bounding Box",
    "author": "Titus",
    "version": (1, 2, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Cursor BBox",
    "description": "Place cursor with raycast and create cursor-aligned bounding boxes with edge selection and face marking",
    "warning": "",
    "doc_url": "",
    "category": "Object",
}

import bpy

# Import modules in correct order
from . import preferences
from . import properties
from . import functions
from . import utils
from . import operators
from . import ui

# Import all classes that need to be registered
from .preferences import CursorBBoxPreferences
from .operators import (
    VIEW3D_OT_cursor_place_raycast,
    VIEW3D_OT_cursor_place_and_bbox,
    VIEW3D_OT_cursor_place_and_bbox_with_marking,
    VIEW3D_OT_create_cursor_bbox,
)
from .ui import VIEW3D_PT_cursor_bbox_panel

# Collect all classes for registration
classes = [
    CursorBBoxPreferences,
    VIEW3D_OT_cursor_place_raycast,
    VIEW3D_OT_cursor_place_and_bbox,
    VIEW3D_OT_cursor_place_and_bbox_with_marking,
    VIEW3D_OT_create_cursor_bbox,
    VIEW3D_PT_cursor_bbox_panel,
]

# Keymap storage
addon_keymaps = []

def register_keymap():
    """Register keyboard shortcuts"""
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = wm.keyconfigs.addon.keymaps.new(name='3D View', space_type='VIEW_3D')
        
        # Place cursor shortcut
        kmi = km.keymap_items.new(
            "view3d.cursor_place_raycast", 
            'C', 
            'PRESS', 
            ctrl=True, 
            shift=True
        )
        kmi.properties.align_to_face = True
        addon_keymaps.append((km, kmi))
        
        # Place cursor + bbox shortcut
        kmi = km.keymap_items.new(
            "view3d.cursor_place_and_bbox", 
            'B', 
            'PRESS', 
            ctrl=True, 
            shift=True, 
            alt=True
        )
        kmi.properties.push_value = 0.01
        kmi.properties.align_to_face = True
        addon_keymaps.append((km, kmi))

def unregister_keymap():
    """Unregister keyboard shortcuts"""
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

def register():
    # Register classes first (including preferences)
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register properties after classes
    properties.register()
    
    # Register keymap
    register_keymap()
    
    print("Cursor Aligned Bounding Box addon registered")

def unregister():
    # Disable edge highlighting, bbox preview, and face marking
    functions.disable_edge_highlight()
    functions.disable_bbox_preview()
    functions.disable_face_marking()
    
    # Unregister keymap
    unregister_keymap()
    
    # Unregister properties
    properties.unregister()
    
    # Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    print("Cursor Aligned Bounding Box addon unregistered")

if __name__ == "__main__":
    register()