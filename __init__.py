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
import atexit
from bpy.app.handlers import persistent

# Import modules in correct order
from . import preferences
from . import properties
from . import draw  # NEW: GPU drawing functions
from . import functions  # Logic functions only
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

# Performance monitoring
performance_stats = {
    'raycast_calls': 0,
    'cache_hits': 0,
    'total_time': 0.0
}

# ===== PERFORMANCE MONITORING =====

def log_performance_stats():
    """Log performance statistics"""
    if performance_stats['raycast_calls'] > 0:
        avg_time = performance_stats['total_time'] / performance_stats['raycast_calls']
        hit_rate = performance_stats['cache_hits'] / performance_stats['raycast_calls'] * 100
        
        print(f"Cursor BBox Performance Stats:")
        print(f"  Raycast calls: {performance_stats['raycast_calls']}")
        print(f"  Cache hit rate: {hit_rate:.1f}%")
        print(f"  Average time per call: {avg_time*1000:.2f}ms")

# ===== APP HANDLERS =====

@persistent
def load_post_handler(dummy):
    """Handler for when a file is loaded"""
    # Clear all caches when loading new file
    try:
        from .utils import clear_all_caches
        from .functions import _state
        clear_all_caches()
        _state.cleanup()
        print("Cursor BBox: Cleared caches after file load")
    except:
        pass

@persistent 
def save_pre_handler(dummy):
    """Handler before saving file"""
    # Clean up temporary data before save
    try:
        from .functions import _state
        _state.cleanup()
    except:
        pass

@persistent
def depsgraph_update_post_handler(scene, depsgraph):
    """Handler for scene updates"""
    # Update spatial grid when objects change
    try:
        if depsgraph.id_type_updated('OBJECT'):
            from .utils import update_spatial_grid
            context = bpy.context
            if context and context.area and context.area.type == 'VIEW_3D':
                update_spatial_grid(context)
    except:
        pass

# ===== KEYMAP FUNCTIONS =====

def register_keymap():
    """Register keyboard shortcuts with error handling"""
    try:
        wm = bpy.context.window_manager
        if not wm:
            return
            
        kc = wm.keyconfigs.addon
        if not kc:
            return
            
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        
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
        
        print("Cursor BBox: Keymaps registered successfully")
        
    except Exception as e:
        print(f"Cursor BBox: Error registering keymaps: {e}")

def unregister_keymap():
    """Unregister keyboard shortcuts with error handling"""
    try:
        for km, kmi in addon_keymaps:
            if km and kmi:
                km.keymap_items.remove(kmi)
        addon_keymaps.clear()
        print("Cursor BBox: Keymaps unregistered successfully")
    except Exception as e:
        print(f"Cursor BBox: Error unregistering keymaps: {e}")

# ===== CLEANUP FUNCTIONS =====

def cleanup_addon_completely():
    """Complete cleanup of all addon data"""
    try:
        # Disable all drawing handlers and clear state
        from .functions import _state
        _state.cleanup()
        
        # Clear all utility caches
        from .utils import cleanup_utils
        cleanup_utils()
        
        # Log performance stats
        log_performance_stats()
        
        print("Cursor BBox: Complete cleanup finished")
        
    except Exception as e:
        print(f"Cursor BBox: Error during cleanup: {e}")

def emergency_cleanup():
    """Emergency cleanup function for Python shutdown"""
    try:
        cleanup_addon_completely()
    except:
        pass  # Ignore errors during shutdown

# ===== REGISTRATION FUNCTIONS =====

def register():
    """Register addon with enhanced error handling and optimization setup"""
    try:
        # Register classes first (including preferences)
        for cls in classes:
            try:
                bpy.utils.register_class(cls)
            except Exception as e:
                print(f"Cursor BBox: Error registering class {cls}: {e}")
                # Continue with other classes
        
        # Register properties after classes
        try:
            properties.register()
        except Exception as e:
            print(f"Cursor BBox: Error registering properties: {e}")
        
        # Register keymap
        register_keymap()
        
        # Register app handlers for performance optimization
        try:
            if load_post_handler not in bpy.app.handlers.load_post:
                bpy.app.handlers.load_post.append(load_post_handler)
            
            if save_pre_handler not in bpy.app.handlers.save_pre:
                bpy.app.handlers.save_pre.append(save_pre_handler)
            
            if depsgraph_update_post_handler not in bpy.app.handlers.depsgraph_update_post:
                bpy.app.handlers.depsgraph_update_post.append(depsgraph_update_post_handler)
            
            print("Cursor BBox: App handlers registered")
            
        except Exception as e:
            print(f"Cursor BBox: Error registering app handlers: {e}")
        
        # Register emergency cleanup
        atexit.register(emergency_cleanup)
        
        print("Cursor Aligned Bounding Box addon registered successfully (Split Architecture Edition)")
        
    except Exception as e:
        print(f"Cursor BBox: Critical error during registration: {e}")

def unregister():
    """Unregister addon with complete cleanup"""
    try:
        # Perform complete cleanup first
        cleanup_addon_completely()
        
        # Unregister app handlers
        try:
            handlers_to_remove = [
                (bpy.app.handlers.load_post, load_post_handler),
                (bpy.app.handlers.save_pre, save_pre_handler),
                (bpy.app.handlers.depsgraph_update_post, depsgraph_update_post_handler)
            ]
            
            for handler_list, handler_func in handlers_to_remove:
                if handler_func in handler_list:
                    handler_list.remove(handler_func)
            
            print("Cursor BBox: App handlers unregistered")
            
        except Exception as e:
            print(f"Cursor BBox: Error unregistering app handlers: {e}")
        
        # Unregister keymap
        unregister_keymap()
        
        # Unregister properties
        try:
            properties.unregister()
        except Exception as e:
            print(f"Cursor BBox: Error unregistering properties: {e}")
        
        # Unregister classes
        for cls in reversed(classes):
            try:
                bpy.utils.unregister_class(cls)
            except Exception as e:
                print(f"Cursor BBox: Error unregistering class {cls}: {e}")
                # Continue with other classes
        
        # Unregister emergency cleanup
        try:
            atexit.unregister(emergency_cleanup)
        except:
            pass  # May not be registered
        
        print("Cursor Aligned Bounding Box addon unregistered successfully")
        
    except Exception as e:
        print(f"Cursor BBox: Critical error during unregistration: {e}")

# ===== ADDON UTILITIES =====

def get_addon_version():
    """Get current addon version"""
    return bl_info["version"]

def get_performance_info():
    """Get current performance information"""
    try:
        from .utils import get_performance_stats
        utils_stats = get_performance_stats()
        
        return {
            'addon_stats': performance_stats.copy(),
            'cache_stats': utils_stats,
            'version': get_addon_version()
        }
    except:
        return {'error': 'Unable to get performance info'}

def force_cache_clear():
    """Force clear all caches - utility function"""
    try:
        from .utils import clear_all_caches
        from .functions import _state
        
        clear_all_caches()
        _state.cleanup()
        print("Cursor BBox: All caches cleared manually")
        return True
    except Exception as e:
        print(f"Cursor BBox: Error clearing caches: {e}")
        return False

# ===== MODULE TEST =====

if __name__ == "__main__":
    # Test registration when run directly
    try:
        register()
        print("Cursor BBox: Test registration successful")
    except Exception as e:
        print(f"Cursor BBox: Test registration failed: {e}")

# ===== ADDON PREFERENCES INTEGRATION =====

def update_performance_settings():
    """Update performance settings based on preferences"""
    try:
        from .preferences import get_preferences
        prefs = get_preferences()
        
        if prefs:
            # Update cache sizes based on preferences
            from .utils import _raycast_cache
            
            # Adaptive cache sizing based on scene complexity
            scene = bpy.context.scene
            if scene:
                total_objects = len([obj for obj in scene.objects if obj.type == 'MESH'])
                
                if total_objects > 100:
                    _raycast_cache.cache_size = 100
                    _raycast_cache.mouse_threshold = 3
                elif total_objects > 50:
                    _raycast_cache.cache_size = 75
                    _raycast_cache.mouse_threshold = 4
                else:
                    _raycast_cache.cache_size = 50
                    _raycast_cache.mouse_threshold = 5
                
                print(f"Cursor BBox: Adjusted cache size to {_raycast_cache.cache_size} for {total_objects} objects")
    
    except Exception as e:
        print(f"Cursor BBox: Error updating performance settings: {e}")

# ===== SCENE UPDATE CALLBACK =====

def on_scene_update():
    """Called when scene updates significantly"""
    update_performance_settings()

# ===== DEBUG UTILITIES =====

def print_debug_info():
    """Print debug information about addon state"""
    try:
        print("=== Cursor BBox Debug Info ===")
        print(f"Version: {get_addon_version()}")
        
        perf_info = get_performance_info()
        print(f"Performance: {perf_info}")
        
        from .functions import _state
        print(f"Active handlers: {list(_state.handlers.keys())}")
        print(f"Marked faces: {len(_state.marked_faces)}")
        print(f"Marked points: {len(_state.marked_points)}")
        
        from .utils import _raycast_cache, _spatial_grid
        print(f"Raycast cache size: {len(_raycast_cache.cache)}")
        print(f"Spatial grid objects: {len(_spatial_grid.objects)}")
        
        print("==============================")
        
    except Exception as e:
        print(f"Debug info error: {e}")

# Export debug function for console use
def debug():
    """Console-friendly debug function"""
    print_debug_info()