import bpy
import bmesh
from mathutils import Vector, Matrix
import time
from functools import lru_cache
from ..settings.preferences import get_preferences
from .utils import ensure_cbb_collection, ensure_cbb_material, assign_object_styles
from ..ui.draw import (
    GPUDrawingManager, 
    generate_bbox_geometry_optimized,
    enable_edge_highlight,
    disable_edge_highlight,
    enable_bbox_preview,
    disable_bbox_preview,
    enable_face_marking,
    disable_face_marking,
    ensure_handlers_enabled,
    refresh_all_handlers,
    enable_limitation_plane,
    disable_limitation_plane
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
        self.preview_faces_visual_cache = {}
        
        # Performance caches
        self.bbox_geometry_cache = {}
        self.coordinate_transform_cache = {}

        # Visual settings
        self.show_backfaces = False
        self.preview_culling = False # Default OFF (Double Sided)
        self.preview_point = None
        self.limitation_plane_matrix = None
        
    def cleanup(self):
        """Clean up all state and handlers"""
        self.disable_all_handlers()
        self.gpu_manager.clear_cache()
        self.marked_faces.clear()
        self.marked_points.clear()
        self.marked_faces_visual_cache.clear()
        self.preview_faces_visual_cache.clear()
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

def mark_faces_batch(obj, face_indices, use_depsgraph=False):
    """Efficiently mark multiple faces at once, optionally using evaluated mesh"""
    global _state
    from .utils import get_evaluated_mesh
    
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
    
    # Get evaluated mesh using shared utility
    mesh, obj_mat = get_evaluated_mesh(obj, use_depsgraph=use_depsgraph)
    
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

def rebuild_marked_faces_visual_data(obj, face_indices, use_depsgraph=False):
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
    mark_faces_batch(obj, face_indices, use_depsgraph=use_depsgraph)

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

def update_preview_faces(obj, face_indices, use_depsgraph=False):
    """Update faces preview (transient highlight)"""
    global _state
    from .utils import get_evaluated_mesh
    
    # Clear previous preview
    _state.preview_faces_visual_cache.clear()
    _state.gpu_manager.clear_cache_prefix('preview_faces_')
    
    if not obj or not face_indices or obj.type != 'MESH':
        return
        
    vertices = []
    
    # Get evaluated mesh using shared utility
    mesh, obj_mat = get_evaluated_mesh(obj, use_depsgraph=use_depsgraph)
    
    # Process faces
    for face_idx in face_indices:
        if face_idx >= len(mesh.polygons):
            continue
        
        face = mesh.polygons[face_idx]
        face_verts = [obj_mat @ mesh.vertices[i].co for i in face.vertices]
        
        # Triangulate
        if len(face_verts) == 3:
            vertices.extend(face_verts)
        else:
            # Fan triangulation (continuing previous snippet logic)
            for i in range(1, len(face_verts) - 1):
                vertices.extend([face_verts[0], face_verts[i], face_verts[i + 1]])
    
    if vertices:
        _state.preview_faces_visual_cache[obj.name] = vertices
    
    # Ensure handlers enabled
    if 'face_marking' not in _state.handlers:
        enable_face_marking(_state)

def clear_preview_faces():
    """Clear face preview"""
    global _state
    _state.preview_faces_visual_cache.clear()

def update_preview_point(location):
    """Update preview point location"""
    global _state
    # Ensure handlers (specifically face marking which handles points)
    ensure_handlers_enabled(_state)
    _state.preview_point = location

def clear_preview_point():
    """Clear preview point"""
    global _state
    _state.preview_point = None

def update_limitation_plane(matrix):
    """Update limitation plane matrix"""
    global _state
    if 'limitation_plane' not in _state.handlers:
        enable_limitation_plane(_state)
    _state.limitation_plane_matrix = matrix

def clear_limitation_plane():
    """Clear limitation plane"""
    global _state
    _state.limitation_plane_matrix = None
    if 'limitation_plane' in _state.handlers:
        disable_limitation_plane(_state)

# ===== DRAWING STATE HELPERS =====

def toggle_backface_rendering():
    """Toggle backface rendering state"""
    global _state
    _state.show_backfaces = not _state.show_backfaces
    return _state.show_backfaces

def get_backface_rendering():
    """Get current backface rendering state"""
    global _state
    return _state.show_backfaces

def toggle_preview_culling():
    """Toggle preview backface culling state"""
    global _state
    _state.preview_culling = not _state.preview_culling
    return _state.preview_culling

def get_preview_culling():
    """Get current preview backface culling state"""
    global _state
    return _state.preview_culling

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

def update_marked_faces_bbox(marked_faces_dict, push_value, cursor_location, cursor_rotation, marked_points=None, use_depsgraph=False):
    """Optimized marked faces bbox update with proper cache handling"""
    global _state
    from .utils import collect_vertices_from_marked_faces
    
    try:
        # Collect vertices from marked faces using shared utility
        all_vertices = collect_vertices_from_marked_faces(marked_faces_dict, use_depsgraph=use_depsgraph)

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

        _state.gpu_manager.clear_cache_key('bbox_edges')

    except Exception as e:
        print(f"Error updating marked faces bbox: {e}")
        _state.current_bbox_data = None


def update_marked_faces_convex_hull(marked_faces_dict, push_value, marked_points=None, use_depsgraph=False):
    """Update preview with convex hull of marked faces/points"""
    global _state
    from .utils import collect_vertices_from_marked_faces
    
    try:
        # Collect vertices from marked faces using shared utility
        all_vertices = collect_vertices_from_marked_faces(marked_faces_dict, use_depsgraph=use_depsgraph)

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

        # Calculate Convex Hull
        bm = bmesh.new()
        for v in all_vertices:
            bm.verts.new(v)
        bm.verts.ensure_lookup_table()
        
        # Calculate hull
        ret = bmesh.ops.convex_hull(bm, input=bm.verts)
        
        # Remove interior/unused geometry from convex hull operation
        # Use set to avoid duplicates (geom_unused is a subset of geom_interior)
        geom_to_remove = list(set(ret.get('geom_interior', []) + ret.get('geom_unused', [])))
        if geom_to_remove:
            bmesh.ops.delete(bm, geom=geom_to_remove, context='VERTS')
        
        # Ensure lookup tables are valid after deletion
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        
        # Apply dissolve_limit to clean up planar faces
        import bpy
        from math import radians
        dissolve_angle_deg = bpy.context.scene.cursor_bbox_hull_dissolve_angle
        dissolve_angle_rad = radians(dissolve_angle_deg)
        
        if dissolve_angle_deg > 0:
            bmesh.ops.dissolve_limit(
                bm,
                angle_limit=dissolve_angle_rad,
                use_dissolve_boundaries=True,
                verts=list(bm.verts),
                edges=list(bm.edges),
                delimit={'NORMAL'}
            )
            
            # Ensure lookup tables after dissolve
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            
            # Recalculate normals after dissolve
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

        # Apply push value (inflate)
        if abs(push_value) > 0.0001:
            vert_normals = {v: Vector((0,0,0)) for v in bm.verts}
            for f in bm.faces:
                for v in f.verts:
                    vert_normals[v] += f.normal
            
            for v in bm.verts:
                if vert_normals[v].length_squared > 0:
                    normal = vert_normals[v].normalized()
                    v.co += normal * push_value

        # Prepare for drawing (n-gons and triangles will be visible in preview)
        # Note: GPU drawing handles n-gons automatically, no need to triangulate
        face_verts = []
        for f in bm.faces:
             for v in f.verts:
                 face_verts.append(v.co.copy())
        
        edge_verts = []
        for e in bm.edges:
            edge_verts.append(e.verts[0].co.copy())
            edge_verts.append(e.verts[1].co.copy())
            
        bm.free()

        _state.current_bbox_data = {
            'edges': edge_verts,
            'faces': face_verts,
            'center': Vector((0,0,0)), 
            'dimensions': Vector((0,0,0))
        }

        # Force clear bbox cache to ensure visual update
        _state.gpu_manager.clear_cache_key('bbox_faces')
        _state.gpu_manager.clear_cache_key('bbox_edges')

    except Exception as e:
        print(f"Error updating convex hull preview: {e}")
        _state.current_bbox_data = None

def update_marked_faces_sphere(marked_faces_dict, cursor_location, cursor_rotation, marked_points=None, use_depsgraph=False):
    """Update preview with bounding sphere of marked faces/points (Cursor Aligned)"""
    global _state
    from .utils import collect_vertices_from_marked_faces
    
    try:
        # Collect vertices from marked faces using shared utility
        all_vertices = collect_vertices_from_marked_faces(marked_faces_dict, use_depsgraph=use_depsgraph)

        # Add marked points
        if marked_points:
            all_vertices.extend(marked_points)

        if not all_vertices:
            _state.current_bbox_data = None
            _state.gpu_manager.clear_cache_key('bbox_faces')
            _state.gpu_manager.clear_cache_key('bbox_edges')
            return

        # Re-enable bbox preview if it was disabled
        if 'bbox_preview' not in _state.handlers:
            enable_bbox_preview(_state)

        # Transform to Local Space of Cursor for "Oriented" Bounding calculation
        cursor_rot_mat = cursor_rotation.to_matrix()
        cursor_matrix = Matrix.Translation(cursor_location) @ cursor_rot_mat.to_4x4()
        cursor_matrix_inv = cursor_matrix.inverted()
        
        local_verts = [cursor_matrix_inv @ v for v in all_vertices]

        # Calculate Center (BBox Center in Local Space)
        min_co = Vector(local_verts[0])
        max_co = Vector(local_verts[0])
        
        for v in local_verts:
            min_co.x = min(min_co.x, v.x)
            min_co.y = min(min_co.y, v.y)
            min_co.z = min(min_co.z, v.z)
            max_co.x = max(max_co.x, v.x)
            max_co.y = max(max_co.y, v.y)
            max_co.z = max(max_co.z, v.z)
            
        local_center = (min_co + max_co) / 2.0
        
        # Calculate Radius (Max Distance from Center in Local Space)
        radius = 0.0
        for v in local_verts:
            dist = (v - local_center).length
            if dist > radius:
                radius = dist
        
        radius = max(radius, 0.05)
        
        # Calculate World Center for the Sphere
        world_center = cursor_matrix @ local_center
                
        # Generate Sphere Geometry
        bm = bmesh.new()
        
        # Create unit sphere at origin
        try:
            bmesh.ops.create_uvsphere(
                bm, 
                u_segments=32, 
                v_segments=16, 
                diameter=1.0
            )
        except TypeError:
             # Fallback if arguments differ (e.g. radius instead of diameter)
            bmesh.ops.create_uvsphere(
                bm, 
                u_segments=32, 
                v_segments=16, 
                radius=0.5
            )
        
        # Scale, Rotate and Translate
        # Matrix multiplication order: Translation @ Rotation @ Scale (applied right to left typically for vectors? 
        # In blender python matrix multiplication A @ B corresponds to applying B then A if transforming column vector v as (A @ B) @ v.
        # So we want Scale first, then Rotate, then Translate.
        # mat = T @ R @ S
        mat = Matrix.Translation(world_center) @ cursor_rot_mat.to_4x4() @ Matrix.Scale(radius * 2, 4)
        
        bmesh.ops.transform(bm, matrix=mat, verts=list(bm.verts))
        
        # Extract edges BEFORE triangulation to keep quad wireframe look
        edge_verts = []
        for e in bm.edges:
            edge_verts.append(e.verts[0].co.copy())
            edge_verts.append(e.verts[1].co.copy())
            
        # Triangulate for face drawing
        bmesh.ops.triangulate(bm, faces=bm.faces)
        
        face_verts = []
        for f in bm.faces:
             for v in f.verts:
                 face_verts.append(v.co.copy())
            
        bm.free()

        _state.current_bbox_data = {
            'edges': edge_verts,
            'faces': face_verts,
            'center': world_center,
            'dimensions': Vector((radius*2, radius*2, radius*2))
        }

        # Force clear bbox cache to ensure visual update
        _state.gpu_manager.clear_cache_key('bbox_faces')
        _state.gpu_manager.clear_cache_key('bbox_edges')

    except Exception as e:
        print(f"Error updating sphere preview: {e}")
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

def cursor_aligned_bounding_box(push_value, target_obj=None, marked_faces=None, marked_points=None, use_depsgraph=False):
    """Main bounding box creation function - optimized version"""
    context = bpy.context
    cursor = context.scene.cursor
    # Capture cursor state before any potential mode changes
    # Capture cursor state before any potential mode changes
    cursor_location = cursor.location.copy()
    
    # Robustly capture rotation as XYZ Euler regardless of mode
    if cursor.rotation_mode == 'QUATERNION':
        cursor_rotation = cursor.rotation_quaternion.to_euler('XYZ')
    elif cursor.rotation_mode == 'AXIS_ANGLE':
        aa = cursor.rotation_axis_angle
        # Matrix.Rotation(angle, size, axis)
        rot_mat = Matrix.Rotation(aa[0], 4, Vector((aa[1], aa[2], aa[3])))
        cursor_rotation = rot_mat.to_euler('XYZ')
    else:
        # Euler modes
        if cursor.rotation_mode != 'XYZ':
             cursor_rotation = cursor.rotation_euler.to_matrix().to_euler('XYZ')
        else:
             cursor_rotation = cursor.rotation_euler.copy()
    
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
            from .utils import collect_vertices_from_marked_faces
            
            # Collect vertices from marked faces using shared utility
            all_world_coords = collect_vertices_from_marked_faces(marked_faces, use_depsgraph=use_depsgraph, context=context)
            
            if marked_points:
                all_world_coords.extend(marked_points)
            
            if not all_world_coords:
                print("Error: No vertices found in marked faces or points.")
                return
            
            # Use optimized calculation
            local_center, dimensions, cursor_rot_mat = calculate_bbox_bounds_optimized(
                all_world_coords, cursor_location, cursor_rotation
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
            
            # Create bbox object
            from .utils import preserve_selection_state, setup_new_object
            
            with preserve_selection_state(context) as state:
                state.deselect_all()
                
                bpy.ops.mesh.primitive_cube_add(
                    size=1,
                    enter_editmode=False,
                    align='WORLD',
                    location=world_center,
                    rotation=cursor_rotation
                )
                
                bbox_obj = context.active_object
                bbox_obj.name = context.scene.cursor_bbox_name_box if context.scene.cursor_bbox_name_box else "Cube"
                
                # Set up object (collection, styles)
                setup_new_object(context, bbox_obj, assign_styles=True, move_to_collection=True)

                bbox_obj.scale = dimensions
                bbox_obj.show_wire = show_wire
                bbox_obj.show_all_edges = show_all_edges
                
                bbox_obj.select_set(False)
        
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

                    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
                    bpy.ops.object.mode_set(mode='OBJECT')

                    bpy.ops.mesh.primitive_cube_add(
                        size=1,
                        enter_editmode=False,
                        align='WORLD',
                        location=world_center,
                        rotation=cursor_rotation
                    )

                    bbox_obj = context.active_object
                    bbox_obj.name = context.scene.cursor_bbox_name_box if context.scene.cursor_bbox_name_box else "Cube"

                    # Set up object (collection, styles)
                    from .utils import setup_new_object
                    setup_new_object(context, bbox_obj, assign_styles=False, move_to_collection=True)
                    
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
                        all_world_coords, cursor_location, cursor_rotation
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

                    world_center = cursor_location + (cursor_rot_mat @ local_center)

                    from .utils import preserve_selection_state, setup_new_object
                    
                    with preserve_selection_state(context) as state:
                        state.deselect_all()
                        
                        bpy.ops.mesh.primitive_cube_add(
                            size=1,
                            enter_editmode=False,
                            align='WORLD',
                            location=world_center,
                            rotation=cursor_rotation
                        )

                        bbox_obj = context.active_object
                        bbox_obj.name = context.scene.cursor_bbox_name_box if context.scene.cursor_bbox_name_box else "Cube"

                        # Set up object (collection, styles)
                        setup_new_object(context, bbox_obj, assign_styles=True, move_to_collection=True)

                        bbox_obj.scale = dimensions
                        bbox_obj.show_wire = show_wire
                        bbox_obj.show_all_edges = show_all_edges

                        bbox_obj.select_set(False)
                        
                        # Restore selection for mesh objects
                        for sel_obj in original_selected:
                            if sel_obj.name in [o.name for o in mesh_objects]:
                                sel_obj.select_set(True)

                        if original_active and original_active in mesh_objects:
                            context.view_layer.objects.active = original_active
                        elif mesh_objects:
                            context.view_layer.objects.active = mesh_objects[0]

    finally:
        context.scene.cursor.rotation_mode = cursor_rotation_mode

def world_oriented_bounding_box(push_value, target_obj=None, marked_faces=None, marked_points=None, use_depsgraph=False):
    """Create a bounding box aligned to world axes (no rotation)"""
    context = bpy.context
    cursor = context.scene.cursor
    
    # Save current cursor rotation
    cursor_rotation_mode = cursor.rotation_mode
    if cursor.rotation_mode == 'QUATERNION':
        saved_rotation = cursor.rotation_quaternion.copy()
    elif cursor.rotation_mode == 'AXIS_ANGLE':
        saved_rotation = cursor.rotation_axis_angle.copy()
    else:
        saved_rotation = cursor.rotation_euler.copy()
    
    # Set cursor rotation to zero (world axes)
    cursor.rotation_mode = 'XYZ'
    cursor.rotation_euler = (0.0, 0.0, 0.0)
    
    try:
        # Create bounding box with world orientation
        cursor_aligned_bounding_box(push_value, target_obj, marked_faces, marked_points, use_depsgraph)
    finally:
        # Restore cursor rotation
        cursor.rotation_mode = cursor_rotation_mode
        if cursor_rotation_mode == 'QUATERNION':
            cursor.rotation_quaternion = saved_rotation
        elif cursor_rotation_mode == 'AXIS_ANGLE':
            cursor.rotation_axis_angle = saved_rotation
        else:
            cursor.rotation_euler = saved_rotation

def get_object_rotation_euler(obj):
    """Get object's world rotation as Euler XYZ, handling all rotation modes"""
    # Use matrix_world to get the object's actual world rotation
    # This accounts for parent transforms and gives the true orientation
    rot_mat = obj.matrix_world.to_3x3()
    return rot_mat.to_euler('XYZ')

def update_world_oriented_bbox_preview(target_obj, push_value, use_depsgraph=False):
    """Update preview with world-oriented bounding box (zero rotation)"""
    from mathutils import Euler
    context = bpy.context
    cursor = context.scene.cursor
    
    # Use zero rotation for world orientation
    world_rotation = Euler((0.0, 0.0, 0.0), 'XYZ')
    update_bbox_preview(target_obj, push_value, cursor.location, world_rotation)

def update_local_oriented_bbox_preview(target_obj, push_value, use_depsgraph=False):
    """Update preview with local-oriented bounding box (object's rotation)"""
    context = bpy.context
    cursor = context.scene.cursor
    
    if not target_obj or target_obj.type != 'MESH':
        return
    
    # Get object's local rotation
    obj_rotation = get_object_rotation_euler(target_obj)
    update_bbox_preview(target_obj, push_value, cursor.location, obj_rotation)

def local_oriented_bounding_box(push_value, target_obj=None, marked_faces=None, marked_points=None, use_depsgraph=False):
    """Create a bounding box aligned to the object's local coordinate system"""
    context = bpy.context
    cursor = context.scene.cursor
    
    # Determine target object
    obj = target_obj if target_obj else context.active_object
    
    if not obj or obj.type != 'MESH':
        # If no object, fall back to cursor-aligned
        cursor_aligned_bounding_box(push_value, target_obj, marked_faces, marked_points, use_depsgraph)
        return
    
    # Get object's local rotation
    obj_rotation = get_object_rotation_euler(obj)
    
    # Save current cursor rotation
    cursor_rotation_mode = cursor.rotation_mode
    if cursor.rotation_mode == 'QUATERNION':
        saved_rotation = cursor.rotation_quaternion.copy()
    elif cursor.rotation_mode == 'AXIS_ANGLE':
        saved_rotation = cursor.rotation_axis_angle.copy()
    else:
        saved_rotation = cursor.rotation_euler.copy()
    
    # Set cursor rotation to object's rotation
    cursor.rotation_mode = 'XYZ'
    cursor.rotation_euler = obj_rotation
    
    try:
        # Create bounding box with object's local orientation
        cursor_aligned_bounding_box(push_value, target_obj, marked_faces, marked_points, use_depsgraph)
    finally:
        # Restore cursor rotation
        cursor.rotation_mode = cursor_rotation_mode
        if cursor_rotation_mode == 'QUATERNION':
            cursor.rotation_quaternion = saved_rotation
        elif cursor_rotation_mode == 'AXIS_ANGLE':
            cursor.rotation_axis_angle = saved_rotation
        else:
            cursor.rotation_euler = saved_rotation

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

def enable_limitation_plane_wrapper(context, matrix):
    """Wrapper for enable_limitation_plane - accepts context and matrix"""
    global _state
    if 'limitation_plane' not in _state.handlers:
        enable_limitation_plane(_state)
    _state.limitation_plane_matrix = matrix

def disable_limitation_plane_wrapper(context):
    """Wrapper for disable_limitation_plane - accepts context"""
    global _state
    if 'limitation_plane' in _state.handlers:
        disable_limitation_plane(_state)
    _state.limitation_plane_matrix = None