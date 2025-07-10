import bpy
import bmesh
from mathutils import Vector
import time
from functools import lru_cache
from .preferences import get_preferences
from .draw import (
    GPUDrawingManager, 
    generate_bbox_geometry_optimized,
    enable_edge_highlight,
    disable_edge_highlight,
    enable_bbox_preview,
    disable_bbox_preview,
    enable_face_marking,
    disable_face_marking,
    ensure_handlers_enabled,
    refresh_all_handlers
)

# ===== STATE MANAGEMENT =====

class CursorBBoxState:
    """Centralized state management"""
    
    def __init__(self):
        self.gpu_manager = GPUDrawingManager()
        self.handlers = {}
        self.marked_faces = {}
        self.marked_points = []
        self.current_edge_data = None
        self.current_bbox_data = None
        self.marked_faces_visual_cache = {}
        
        # Performance caches
        self.bbox_geometry_cache = {}
        self.coordinate_transform_cache = {}
        
    def cleanup(self):
        """Clean up all state and handlers"""
        self.disable_all_handlers()
        self.gpu_manager.clear_cache()
        self.marked_faces.clear()
        self.marked_points.clear()
        self.marked_faces_visual_cache.clear()
        self.bbox_geometry_cache.clear()
        self.coordinate_transform_cache.clear()
        self.current_edge_data = None
        self.current_bbox_data = None
    
    def disable_all_handlers(self):
        """Disable all GPU handlers"""
        for handler_name, handler in self.handlers.items():
            if handler is not None:
                bpy.types.SpaceView3D.draw_handler_remove(handler, 'WINDOW')
        self.handlers.clear()

# Global state instance
_state = CursorBBoxState()

# ===== POINT MANAGEMENT =====

def add_marked_point(location):
    """Add a point marker at the specified location"""
    global _state
    if location not in _state.marked_points:
        _state.marked_points.append(location.copy())
        
        # Clear point cache to force recreation
        _state.gpu_manager.clear_cache_key('marked_points')
        _state.gpu_manager.clear_cache_key('marked_points_only')
        
        # Ensure face marking handler is enabled to draw points
        if 'face_marking' not in _state.handlers:
            enable_face_marking(_state)
        
        print(f"Added point marker at {location} (Total: {len(_state.marked_points)})")

def remove_last_marked_point():
    """Remove the last added point marker"""
    global _state
    if _state.marked_points:
        removed = _state.marked_points.pop()
        
        # Clear point cache
        _state.gpu_manager.clear_cache_key('marked_points')
        _state.gpu_manager.clear_cache_key('marked_points_only')
        
        # Only disable if no marked faces AND no marked points
        if not _state.marked_points and not _state.marked_faces:
            disable_face_marking(_state)
        
        print(f"Removed point marker at {removed} (Remaining: {len(_state.marked_points)})")
        return removed
    return None

def clear_marked_points():
    """Clear all marked points"""
    global _state
    count = len(_state.marked_points)
    _state.marked_points.clear()
    
    # Clear point cache
    _state.gpu_manager.clear_cache_key('marked_points')
    _state.gpu_manager.clear_cache_key('marked_points_only')
    
    # Only disable face marking if no marked faces either
    if not _state.marked_faces:
        disable_face_marking(_state)
    
    print(f"Cleared {count} point markers")

def get_marked_points_info():
    """Get information about marked points"""
    global _state
    return {
        'count': len(_state.marked_points),
        'points': [tuple(p) for p in _state.marked_points]
    }

# ===== FACE MARKING =====

def mark_faces_batch(obj, face_indices):
    """Efficiently mark multiple faces at once"""
    global _state
    
    if obj.type != 'MESH':
        return
    
    # Always clear existing visual cache for this object first
    if obj.name in _state.marked_faces_visual_cache:
        del _state.marked_faces_visual_cache[obj.name]
    
    # Clear GPU cache for this object
    cache_key = 'marked_faces_' + obj.name
    _state.gpu_manager.clear_cache_key(cache_key)
    
    # If no faces to mark, we're done (cache already cleared)
    if not face_indices:
        return
    
    vertices = []
    mesh = obj.data
    obj_mat = obj.matrix_world
    
    # Process all faces in one pass
    for face_idx in face_indices:
        if face_idx >= len(mesh.polygons):
            continue
        
        face = mesh.polygons[face_idx]
        face_verts = [obj_mat @ mesh.vertices[i].co for i in face.vertices]
        
        # Triangulate if needed
        if len(face_verts) == 3:
            vertices.extend(face_verts)
        else:
            # Fan triangulation
            for i in range(1, len(face_verts) - 1):
                vertices.extend([face_verts[0], face_verts[i], face_verts[i + 1]])
    
    # Update visual cache with new vertices
    if vertices:
        _state.marked_faces_visual_cache[obj.name] = vertices

def mark_face(obj, face_index):
    """Mark a single face"""
    global _state
    if obj not in _state.marked_faces:
        _state.marked_faces[obj] = set()
    _state.marked_faces[obj].add(face_index)
    mark_faces_batch(obj, _state.marked_faces[obj])
    
    # Ensure handlers are enabled when we have marked faces
    ensure_handlers_enabled(_state)

def unmark_face(obj, face_index):
    """Unmark a single face"""
    global _state
    if obj in _state.marked_faces and face_index in _state.marked_faces[obj]:
        _state.marked_faces[obj].remove(face_index)
        if not _state.marked_faces[obj]:
            # No more faces marked for this object
            del _state.marked_faces[obj]
            # Clear visual cache
            if obj.name in _state.marked_faces_visual_cache:
                del _state.marked_faces_visual_cache[obj.name]
            # Clear GPU cache
            cache_key = 'marked_faces_' + obj.name
            _state.gpu_manager.clear_cache_key(cache_key)
        else:
            # Rebuild visual data for remaining marked faces
            mark_faces_batch(obj, _state.marked_faces[obj])
    
    # Ensure proper handler state after unmarking
    ensure_handlers_enabled(_state)

def rebuild_marked_faces_visual_data(obj, face_indices):
    """Rebuild visual data for an object's marked faces"""
    global _state
    
    if not face_indices:
        # No faces to mark, clear everything
        if obj in _state.marked_faces:
            del _state.marked_faces[obj]
        if obj.name in _state.marked_faces_visual_cache:
            del _state.marked_faces_visual_cache[obj.name]
        # Clear GPU cache
        cache_key = 'marked_faces_' + obj.name
        _state.gpu_manager.clear_cache_key(cache_key)
        return
    
    # Update the marked faces set
    _state.marked_faces[obj] = set(face_indices)
    
    # Rebuild visual data
    mark_faces_batch(obj, face_indices)

def clear_marked_faces():
    """Clear all marked faces with proper cache cleanup"""
    global _state
    _state.marked_faces.clear()
    _state.marked_faces_visual_cache.clear()
    
    # Clear all marked face GPU caches
    _state.gpu_manager.clear_cache_prefix('marked_faces_')
    
    # Clear bbox data but don't disable the handler
    _state.current_bbox_data = None
    _state.gpu_manager.clear_cache_key('bbox_faces')
    _state.gpu_manager.clear_cache_key('bbox_edges')

def clear_all_markings():
    """Clear all marked faces and points"""
    global _state
    
    # Clear faces
    _state.marked_faces.clear()
    _state.marked_faces_visual_cache.clear()
    _state.gpu_manager.clear_cache_prefix('marked_faces_')
    
    # Clear points  
    _state.marked_points.clear()
    _state.gpu_manager.clear_cache_key('marked_points')
    _state.gpu_manager.clear_cache_key('marked_points_only')
    
    # Clear bbox data
    _state.current_bbox_data = None
    _state.gpu_manager.clear_cache_key('bbox_faces')
    _state.gpu_manager.clear_cache_key('bbox_edges')
    
    # Disable face marking handler since nothing is marked
    disable_face_marking(_state)
    
    print("Cleared all face and point markings")

def force_refresh_marked_faces():
    """Force refresh of all marked face visuals - utility function for debugging"""
    global _state
    
    # Clear all visual caches
    _state.marked_faces_visual_cache.clear()
    
    # Clear GPU caches
    _state.gpu_manager.clear_cache_prefix('marked_faces_')
    
    # Rebuild all marked faces
    for obj, face_indices in _state.marked_faces.items():
        if face_indices:
            mark_faces_batch(obj, face_indices)

# ===== BBOX CALCULATIONS =====

def calculate_bbox_bounds_optimized(world_coords, cursor_location, cursor_rotation):
    """Optimized bounding box calculation with caching"""
    global _state
    
    # Create cache key
    coords_hash = hash(tuple(tuple(coord) for coord in world_coords))
    cursor_hash = hash((tuple(cursor_location), tuple(cursor_rotation)))
    cache_key = (coords_hash, cursor_hash)
    
    if cache_key in _state.coordinate_transform_cache:
        return _state.coordinate_transform_cache[cache_key]
    
    cursor_rot_mat = cursor_rotation.to_matrix()
    cursor_rot_mat_inv = cursor_rot_mat.inverted()
    
    # Vectorized coordinate transformation
    local_coords = [cursor_rot_mat_inv @ (p - cursor_location) for p in world_coords]
    
    # Fast min/max calculation
    if local_coords:
        x_coords = [lc.x for lc in local_coords]
        y_coords = [lc.y for lc in local_coords]
        z_coords = [lc.z for lc in local_coords]
        
        min_co = Vector((min(x_coords), min(y_coords), min(z_coords)))
        max_co = Vector((max(x_coords), max(y_coords), max(z_coords)))
    else:
        min_co = max_co = Vector()
    
    local_center = (min_co + max_co) / 2.0
    dimensions = max_co - min_co
    
    result = (local_center, dimensions, cursor_rot_mat)
    
    # Cache with size limit
    if len(_state.coordinate_transform_cache) > 50:
        _state.coordinate_transform_cache.pop(next(iter(_state.coordinate_transform_cache)))
    
    _state.coordinate_transform_cache[cache_key] = result
    return result

def update_marked_faces_bbox(marked_faces_dict, push_value, cursor_location, cursor_rotation, marked_points=None):
    """Optimized marked faces bbox update with proper cache handling"""
    global _state
    
    try:
        all_vertices = []

        # Collect vertices from marked faces
        for obj, face_indices in marked_faces_dict.items():
            if not face_indices or obj.type != 'MESH':
                continue

            mesh = obj.data
            obj_mat = obj.matrix_world

            # Batch process face vertices
            for face_idx in face_indices:
                if face_idx >= len(mesh.polygons):
                    continue

                face = mesh.polygons[face_idx]
                all_vertices.extend([obj_mat @ mesh.vertices[vert_idx].co for vert_idx in face.vertices])

        # Add marked points
        if marked_points:
            all_vertices.extend(marked_points)

        if not all_vertices:
            # No vertices means no bbox to show
            _state.current_bbox_data = None
            # Force clear bbox cache
            _state.gpu_manager.clear_cache_key('bbox_faces')
            _state.gpu_manager.clear_cache_key('bbox_edges')
            return

        # Re-enable bbox preview if it was disabled
        if 'bbox_preview' not in _state.handlers:
            enable_bbox_preview(_state)

        # Use optimized bounds calculation
        local_center, dimensions, cursor_rot_mat = calculate_bbox_bounds_optimized(
            all_vertices, cursor_location, cursor_rotation
        )

        # Apply push value with safety checks
        epsilon = 0.0001
        dimensions = Vector((
            max(dimensions.x, epsilon),
            max(dimensions.y, epsilon), 
            max(dimensions.z, epsilon)
        ))

        safe_push_value = float(push_value)
        if safe_push_value > 0 or abs(safe_push_value) * 2 < min(dimensions):
            dimensions += Vector((2 * safe_push_value,) * 3)

        dimensions = Vector((
            max(dimensions.x, epsilon),
            max(dimensions.y, epsilon),
            max(dimensions.z, epsilon)
        ))

        world_center = cursor_location + (cursor_rot_mat @ local_center)

        # Generate optimized geometry
        edge_verts, face_verts = generate_bbox_geometry_optimized(world_center, dimensions, cursor_rot_mat, _state.bbox_geometry_cache)

        _state.current_bbox_data = {
            'edges': edge_verts,
            'faces': face_verts,
            'center': world_center,
            'dimensions': dimensions
        }

        # Force clear bbox cache to ensure visual update
        _state.gpu_manager.clear_cache_key('bbox_faces')
        _state.gpu_manager.clear_cache_key('bbox_edges')

    except Exception as e:
        print(f"Error updating marked faces bbox: {e}")
        _state.current_bbox_data = None

# ===== MAIN FUNCTIONS =====

def update_edge_highlight(edge_vertices):
    """Update highlighted edge"""
    global _state
    _state.current_edge_data = {'vertices': edge_vertices}

def update_bbox_preview(target_obj, push_value, cursor_location, cursor_rotation):
    """Optimized bbox preview update"""
    global _state
    
    if not target_obj or target_obj.type != 'MESH':
        _state.current_bbox_data = None
        return
    
    try:
        context = bpy.context
        
        # Get vertices efficiently
        if context.mode == 'EDIT_MESH' and target_obj == context.active_object:
            obj_eval = target_obj.evaluated_get(context.view_layer.depsgraph)
            mesh = obj_eval.data
            bm = bmesh.from_edit_mesh(mesh)
            bm.verts.ensure_lookup_table()

            selected_verts_indices = {vert.index for face in bm.faces if face.select for vert in face.verts}

            if not selected_verts_indices:
                _state.current_bbox_data = None
                return

            obj_mat_world = target_obj.matrix_world
            world_coords = [obj_mat_world @ bm.verts[i].co for i in selected_verts_indices]
        else:
            obj_eval = target_obj.evaluated_get(context.view_layer.depsgraph)
            mesh = obj_eval.data
            obj_mat_world = target_obj.matrix_world
            world_coords = [obj_mat_world @ v.co for v in mesh.vertices]
        
        if not world_coords:
            _state.current_bbox_data = None
            return
        
        # Use optimized bounds calculation
        local_center, dimensions, cursor_rot_mat = calculate_bbox_bounds_optimized(
            world_coords, cursor_location, cursor_rotation
        )
        
        # Apply push value
        epsilon = 0.0001
        dimensions = Vector((
            max(dimensions.x, epsilon),
            max(dimensions.y, epsilon),
            max(dimensions.z, epsilon)
        ))
        
        safe_push_value = float(push_value)
        if safe_push_value > 0 or abs(safe_push_value) * 2 < min(dimensions):
            dimensions += Vector((2 * safe_push_value,) * 3)
        
        dimensions = Vector((
            max(dimensions.x, epsilon),
            max(dimensions.y, epsilon),
            max(dimensions.z, epsilon)
        ))
        
        world_center = cursor_location + (cursor_rot_mat @ local_center)
        
        # Generate geometry using optimized function
        edge_verts, face_verts = generate_bbox_geometry_optimized(world_center, dimensions, cursor_rot_mat, _state.bbox_geometry_cache)
        
        _state.current_bbox_data = {
            'edges': edge_verts,
            'faces': face_verts,
            'center': world_center,
            'dimensions': dimensions
        }
    
    except Exception as e:
        print(f"Error updating bbox preview: {e}")
        _state.current_bbox_data = None

# ===== BOUNDING BOX CREATION =====

def cursor_aligned_bounding_box(push_value, target_obj=None, marked_faces=None, marked_points=None):
    """Main bounding box creation function - optimized version"""
    context = bpy.context
    cursor = context.scene.cursor
    cursor_rotation_mode = context.scene.cursor.rotation_mode
    context.scene.cursor.rotation_mode = 'XYZ'
    
    # Get preferences for bounding box display
    try:
        prefs = get_preferences()
        if prefs:
            show_wire = prefs.bbox_show_wire
            show_all_edges = prefs.bbox_show_all_edges
        else:
            show_wire = True
            show_all_edges = True
    except:
        show_wire = True
        show_all_edges = True
    
    try:
        # Handle marked faces or points
        if marked_faces or marked_points:
            all_world_coords = []
            
            if marked_faces:
                for obj, face_indices in marked_faces.items():
                    mesh = obj.data
                    obj_mat_world = obj.matrix_world
                    
                    for face_idx in face_indices:
                        if face_idx < len(mesh.polygons):
                            face = mesh.polygons[face_idx]
                            all_world_coords.extend([
                                obj_mat_world @ mesh.vertices[vert_idx].co 
                                for vert_idx in face.vertices
                            ])
            
            if marked_points:
                all_world_coords.extend(marked_points)
            
            if not all_world_coords:
                print("Error: No vertices found in marked faces or points.")
                return
            
            # Use optimized calculation
            local_center, dimensions, cursor_rot_mat = calculate_bbox_bounds_optimized(
                all_world_coords, cursor.location, cursor.rotation_euler
            )
            
            # Apply push value
            epsilon = 0.0001
            dimensions = Vector((
                max(dimensions.x, epsilon),
                max(dimensions.y, epsilon),
                max(dimensions.z, epsilon)
            ))
            
            safe_push_value = float(push_value)
            if safe_push_value > 0 or abs(safe_push_value) * 2 < min(dimensions):
                dimensions += Vector((2 * safe_push_value,) * 3)
            
            dimensions = Vector((
                max(dimensions.x, epsilon),
                max(dimensions.y, epsilon),
                max(dimensions.z, epsilon)
            ))
            
            world_center = cursor.matrix @ local_center
            
            # Create bbox object
            original_selected = list(context.selected_objects)
            original_active = context.view_layer.objects.active
            
            bpy.ops.object.select_all(action='DESELECT')
            
            bpy.ops.mesh.primitive_cube_add(
                size=1,
                enter_editmode=False,
                align='WORLD',
                location=world_center,
                rotation=cursor.rotation_euler
            )
            
            bbox_obj = context.active_object
            name_parts = []
            if marked_faces:
                name_parts.append("Faces")
            if marked_points:
                name_parts.append("Points")
            bbox_obj.name = f"CursorBBox_{'_'.join(name_parts)}" if name_parts else "CursorBBox_Marked"
            bbox_obj.scale = dimensions
            bbox_obj.show_wire = show_wire
            bbox_obj.show_all_edges = show_all_edges
            
            bbox_obj.select_set(False)
            
            # Restore selection
            for obj in original_selected:
                obj.select_set(True)
            if original_active:
                context.view_layer.objects.active = original_active
        
        else:
            # Handle target object or selected objects
            obj = target_obj if target_obj else context.active_object
            
            if obj and obj.type == "MESH":
                original_mode = context.mode
                original_active = context.view_layer.objects.active
                original_selected = list(context.selected_objects)
                
                # Switch to target object if needed
                if obj != original_active:
                    bpy.ops.object.select_all(action='DESELECT')
                    obj.select_set(True)
                    context.view_layer.objects.active = obj
                    if original_mode == 'EDIT_MESH':
                        bpy.ops.object.mode_set(mode='EDIT')
                
                # Get coordinates based on mode
                if context.mode == 'EDIT_MESH':
                    # Edit mode - selected faces
                    obj_eval = obj.evaluated_get(context.view_layer.depsgraph)
                    mesh = obj_eval.data
                    bm = bmesh.from_edit_mesh(mesh)
                    bm.verts.ensure_lookup_table()

                    selected_verts_indices = {
                        vert.index for face in bm.faces if face.select for vert in face.verts
                    }

                    if not selected_verts_indices:
                        print("Error: No faces selected.")
                        return

                    obj_mat_world = obj.matrix_world
                    world_coords = [obj_mat_world @ bm.verts[i].co for i in selected_verts_indices]
                    
                    if not world_coords:
                        print("Error: Could not retrieve vertex coordinates.")
                        return

                    # Use optimized calculation
                    local_center, dimensions, cursor_rot_mat = calculate_bbox_bounds_optimized(
                        world_coords, cursor.location, cursor.rotation_euler
                    )

                    # Apply push value
                    epsilon = 0.0001
                    dimensions = Vector((
                        max(dimensions.x, epsilon),
                        max(dimensions.y, epsilon),
                        max(dimensions.z, epsilon)
                    ))

                    safe_push_value = float(push_value)
                    if safe_push_value > 0 or abs(safe_push_value) * 2 < min(dimensions):
                        dimensions += Vector((2 * safe_push_value,) * 3)

                    dimensions = Vector((
                        max(dimensions.x, epsilon),
                        max(dimensions.y, epsilon),
                        max(dimensions.z, epsilon)
                    ))

                    world_center = cursor.matrix @ local_center

                    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
                    bpy.ops.object.mode_set(mode='OBJECT')

                    bpy.ops.mesh.primitive_cube_add(
                        size=1,
                        enter_editmode=False,
                        align='WORLD',
                        location=world_center,
                        rotation=cursor.rotation_euler
                    )

                    bbox_obj = context.active_object
                    bbox_obj.name = "CursorBBox"
                    bbox_obj.scale = dimensions
                    bbox_obj.show_wire = show_wire
                    bbox_obj.show_all_edges = show_all_edges

                    bbox_obj.select_set(False)
                    
                    # Restore state
                    obj.select_set(True)
                    context.view_layer.objects.active = obj
                    if original_mode == 'EDIT_MESH':
                        bpy.ops.object.mode_set(mode='EDIT')

                else:
                    # Object mode
                    if target_obj:
                        mesh_objects = [target_obj]
                    else:
                        mesh_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']

                    # Collect all vertices
                    all_world_coords = []
                    for mesh_obj in mesh_objects:
                        obj_eval = mesh_obj.evaluated_get(context.view_layer.depsgraph)
                        mesh = obj_eval.data
                        obj_mat_world = mesh_obj.matrix_world
                        all_world_coords.extend([obj_mat_world @ v.co for v in mesh.vertices])

                    if not all_world_coords:
                        print("Error: Selected mesh object(s) have no vertices.")
                        return

                    # Use optimized calculation
                    local_center, dimensions, cursor_rot_mat = calculate_bbox_bounds_optimized(
                        all_world_coords, cursor.location, cursor.rotation_euler
                    )

                    # Apply push value with safety checks
                    epsilon = 0.000001
                    dimensions = Vector((
                        max(dimensions.x, epsilon),
                        max(dimensions.y, epsilon),
                        max(dimensions.z, epsilon)
                    ))

                    safe_push = float(push_value)
                    current_min_dim = min(dimensions)

                    if safe_push < 0 and abs(safe_push) * 2 >= current_min_dim:
                        print(f"Warning: Negative push value ({safe_push:.4f} BU) too large, clamping.")
                        safe_push = -(current_min_dim / 2.0) * 0.999

                    dimensions += Vector((2 * safe_push,) * 3)
                    dimensions = Vector((
                        max(dimensions.x, epsilon),
                        max(dimensions.y, epsilon),
                        max(dimensions.z, epsilon)
                    ))

                    world_center = cursor.matrix @ local_center

                    bpy.ops.object.select_all(action='DESELECT')

                    bpy.ops.mesh.primitive_cube_add(
                        size=1,
                        enter_editmode=False,
                        align='WORLD',
                        location=world_center,
                        rotation=cursor.rotation_euler
                    )

                    bbox_obj = context.active_object
                    bbox_obj.name = "CursorBBox"
                    bbox_obj.scale = dimensions
                    bbox_obj.show_wire = show_wire
                    bbox_obj.show_all_edges = show_all_edges

                    bbox_obj.select_set(False)

                    # Restore selection
                    for sel_obj in original_selected:
                        if sel_obj.name in [o.name for o in mesh_objects]:
                            sel_obj.select_set(True)

                    if original_active and original_active in mesh_objects:
                        context.view_layer.objects.active = original_active
                    elif mesh_objects:
                        context.view_layer.objects.active = mesh_objects[0]

    finally:
        context.scene.cursor.rotation_mode = cursor_rotation_mode

# ===== CLEANUP FUNCTION =====

def cleanup_addon_state():
    """Clean up all addon state - call this on unregister"""
    global _state
    _state.cleanup()

# ===== DEBUGGING FUNCTION =====

def debug_point_drawing():
    """Debug function to check point drawing state"""
    global _state
    
    print("=== Point Drawing Debug ===")
    print(f"Marked points count: {len(_state.marked_points)}")
    print(f"Marked points: {[tuple(p) for p in _state.marked_points]}")
    print(f"Face marking handler active: {'face_marking' in _state.handlers}")
    print(f"BBox preview handler active: {'bbox_preview' in _state.handlers}")
    print(f"GPU cache keys: {list(_state.gpu_manager.batch_cache.keys())}")
    
    if _state.marked_points:
        print("Points exist - face_marking handler should be active!")
        if 'face_marking' not in _state.handlers:
            print("ERROR: Points exist but face_marking handler is not active!")
            enable_face_marking(_state)
    
    print("============================")

# ===== WRAPPER FUNCTIONS FOR DRAWING HANDLERS =====

def enable_edge_highlight_wrapper():
    """Wrapper for enable_edge_highlight"""
    global _state
    enable_edge_highlight(_state)

def disable_edge_highlight_wrapper():
    """Wrapper for disable_edge_highlight"""
    global _state
    disable_edge_highlight(_state)

def enable_bbox_preview_wrapper():
    """Wrapper for enable_bbox_preview"""
    global _state
    enable_bbox_preview(_state)

def disable_bbox_preview_wrapper():
    """Wrapper for disable_bbox_preview"""
    global _state
    disable_bbox_preview(_state)

def enable_face_marking_wrapper():
    """Wrapper for enable_face_marking"""
    global _state
    enable_face_marking(_state)

def disable_face_marking_wrapper():
    """Wrapper for disable_face_marking"""
    global _state
    disable_face_marking(_state)

def ensure_handlers_enabled_wrapper():
    """Wrapper for ensure_handlers_enabled"""
    global _state
    ensure_handlers_enabled(_state)

def refresh_all_handlers_wrapper():
    """Wrapper for refresh_all_handlers"""
    global _state
    refresh_all_handlers(_state)