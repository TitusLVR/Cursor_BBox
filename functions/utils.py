import bpy
import bmesh
from mathutils import Vector, Matrix
from bpy_extras import view3d_utils
import time
from functools import lru_cache

# ===== OPTIMIZED RAYCAST MANAGER =====

class RaycastCache:
    """Intelligent caching for raycast operations"""
    
    def __init__(self, cache_size=50, mouse_threshold=5, time_threshold=0.1):
        self.cache = {}
        self.cache_size = cache_size
        self.mouse_threshold = mouse_threshold  # pixels
        self.time_threshold = time_threshold    # seconds
        self.last_mouse_pos = None
        self.last_time = 0
        self.last_result = None
        
    def should_use_cache(self, mouse_x, mouse_y):
        """Check if we should use cached result"""
        current_time = time.time()
        
        if (self.last_mouse_pos and self.last_result and 
            current_time - self.last_time < self.time_threshold):
            
            dx = abs(mouse_x - self.last_mouse_pos[0])
            dy = abs(mouse_y - self.last_mouse_pos[1])
            
            if dx < self.mouse_threshold and dy < self.mouse_threshold:
                return True
        
        return False
    
    def get_cached_result(self, mouse_x, mouse_y):
        """Get cached raycast result if valid"""
        if self.should_use_cache(mouse_x, mouse_y):
            return self.last_result
        return None
    
    def cache_result(self, mouse_x, mouse_y, result):
        """Cache a raycast result"""
        self.last_mouse_pos = (mouse_x, mouse_y)
        self.last_time = time.time()
        self.last_result = result
        
        # Limit cache size
        if len(self.cache) > self.cache_size:
            # Remove oldest entries
            oldest_keys = list(self.cache.keys())[:len(self.cache) - self.cache_size + 10]
            for key in oldest_keys:
                del self.cache[key]
    
    def clear(self):
        """Clear all cached data"""
        self.cache.clear()
        self.last_mouse_pos = None
        self.last_result = None

# Global raycast cache
_raycast_cache = RaycastCache()

# ===== OPTIMIZED OBJECT FILTERING =====

@lru_cache(maxsize=32)
def get_visible_mesh_objects(context_hash):
    """Cached function to get visible mesh objects"""
    context = bpy.context
    visible_objects = []
    
    for obj in context.selected_objects:
        if (obj.type == 'MESH' and 
            obj.visible_get(view_layer=context.view_layer) and
            obj.data and len(obj.data.polygons) > 0):
            visible_objects.append(obj)
    
    return visible_objects

def get_context_hash():
    """Create a hash for current context state"""
    context = bpy.context
    selected_names = tuple(sorted(obj.name for obj in context.selected_objects))
    view_layer_name = context.view_layer.name
    return hash((selected_names, view_layer_name))

# ===== OPTIMIZED RAYCAST FUNCTIONS =====

def get_face_edges_from_raycast_optimized(context, event, use_depsgraph=False):
    """Optimized raycast with caching and early exits"""
    mouse_x = event.mouse_region_x
    mouse_y = event.mouse_region_y
    
    # Check cache first
    cached_result = _raycast_cache.get_cached_result(mouse_x, mouse_y)
    if cached_result is not None:
        return cached_result
    
    region = context.region
    region_3d = context.region_data
    
    # Get ray vectors
    view_vector = view3d_utils.region_2d_to_vector_3d(region, region_3d, (mouse_x, mouse_y))
    ray_origin = view3d_utils.region_2d_to_origin_3d(region, region_3d, (mouse_x, mouse_y))
    
    # Get visible mesh objects with caching
    context_hash = get_context_hash()
    visible_objects = get_visible_mesh_objects(context_hash)
    
    if not visible_objects:
        result = None
        _raycast_cache.cache_result(mouse_x, mouse_y, result)
        return result
    
    # Optimized raycast with early termination
    closest_result = None
    closest_distance = float('inf')
    
    depsgraph = context.view_layer.depsgraph
    
    for obj in visible_objects:
        # Quick bounds check first
        if not _point_in_object_bounds(ray_origin, view_vector, obj):
            continue
            
        # Get evaluated object
        obj_eval = obj.evaluated_get(depsgraph)
        if not obj_eval.data:
            continue
        
        # Transform ray to object space
        matrix_inv = obj.matrix_world.inverted()
        ray_origin_local = matrix_inv @ ray_origin
        ray_direction_local = matrix_inv.to_3x3() @ view_vector
        
        # Perform raycast
        hit, location_local, normal_local, face_index = obj_eval.ray_cast(
            ray_origin_local, ray_direction_local
        )
        
        if hit:
            # Transform back to world space
            location_world = obj.matrix_world @ location_local
            distance = (location_world - ray_origin).length
            
            # Early termination for very close hits
            if distance < closest_distance:
                closest_distance = distance
                normal_world = (obj.matrix_world.to_3x3() @ normal_local).normalized()
                closest_result = (True, location_world, normal_world, face_index, obj, obj.matrix_world)
                
                # Early exit for very close hits
                if distance < 0.001:
                    break
    
    # Process result
    if closest_result:
        # Pass use_depsgraph to process function
        result = _process_raycast_result(*closest_result, use_depsgraph=use_depsgraph)
    else:
        result = None
    
    # Cache the result
    _raycast_cache.cache_result(mouse_x, mouse_y, result)
    return result

def _point_in_object_bounds(ray_origin, ray_direction, obj, margin=0.1):
    """Quick bounds check to see if ray might hit object"""
    try:
        # Get object bounding box
        bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        
        # Simple bounds check - expand by margin
        min_bound = Vector((min(v.x for v in bbox), min(v.y for v in bbox), min(v.z for v in bbox)))
        max_bound = Vector((max(v.x for v in bbox), max(v.y for v in bbox), max(v.z for v in bbox)))
        
        min_bound -= Vector((margin, margin, margin))
        max_bound += Vector((margin, margin, margin))
        
        # Check if ray intersects expanded bounding box
        # Simple ray-box intersection test
        for i in range(3):
            if abs(ray_direction[i]) < 0.0001:
                if ray_origin[i] < min_bound[i] or ray_origin[i] > max_bound[i]:
                    return False
            else:
                t1 = (min_bound[i] - ray_origin[i]) / ray_direction[i]
                t2 = (max_bound[i] - ray_origin[i]) / ray_direction[i]
                
                if t1 > t2:
                    t1, t2 = t2, t1
                
                if t2 < 0:
                    return False
        
        return True
    except:
        return True  # If bounds check fails, assume hit is possible

def _process_raycast_result(hit, location, normal, face_index, obj, matrix, use_depsgraph=False):
    """Process raycast result into face data structure"""
    if not hit or not obj or obj.type != 'MESH':
        return None
    
    if use_depsgraph:
        try:
            depsgraph = bpy.context.view_layer.depsgraph
            obj_eval = obj.evaluated_get(depsgraph)
            mesh = obj_eval.data
        except:
             mesh = obj.data
    else:
        mesh = obj.data
    
    # Bounds check
    if face_index >= len(mesh.polygons):
        print(f"Warning: Face index {face_index} out of range")
        return None
    
    # Get face edges efficiently
    face = mesh.polygons[face_index]
    face_edges = []
    
    # Pre-transform vertices for this face only
    face_verts_world = [obj.matrix_world @ mesh.vertices[i].co for i in face.vertices]
    
    # Build edges from consecutive vertices
    for i in range(len(face_verts_world)):
        start_vert = face_verts_world[i]
        end_vert = face_verts_world[(i + 1) % len(face_verts_world)]
        
        edge_vector = (end_vert - start_vert).normalized()
        edge_center = (start_vert + end_vert) / 2
        edge_length = (end_vert - start_vert).length
        
        face_edges.append({
            'start': start_vert,
            'end': end_vert,
            'center': edge_center,
            'vector': edge_vector,
            'length': edge_length
        })
    
    return {
        'face_index': face_index,
        'face_normal': normal,
        'face_center': location, # Keep for backward compatibility, actually IS hit location
        'hit_location': location, # Explicit name
        'edges': face_edges,
        'object': obj
    }

# ===== OPTIMIZED CURSOR PLACEMENT =====

def place_cursor_with_raycast_and_edge_optimized(context, event, align_to_face=True, edge_index=0, preview=True, use_depsgraph=False):
    """Optimized cursor placement with caching"""
    from .core import update_edge_highlight, update_bbox_preview
    from ..settings.preferences import get_preferences
    
    face_data = get_face_edges_from_raycast_optimized(context, event, use_depsgraph=use_depsgraph)
    
    if not face_data:
        return {
            'success': False,
            'location': None,
            'normal': None,
            'face_index': None,
            'object': None,
            'aligned_to_face': False,
            'face_data': None
        }
    
    cursor = context.scene.cursor
    location = face_data['face_center']
    normal = face_data['face_normal']
    
    cursor.location = location
    
    if align_to_face and face_data['edges']:
        # Clamp edge index
        edge_index = max(0, min(edge_index, len(face_data['edges']) - 1))
        selected_edge = face_data['edges'][edge_index]
        
        # Calculate rotation matrix efficiently
        z_axis = normal.normalized()
        x_axis = selected_edge['vector'].normalized()
        y_axis = z_axis.cross(x_axis).normalized()
        
        # Ensure right-handed coordinate system
        if x_axis.dot(y_axis.cross(z_axis)) < 0:
            y_axis = -y_axis
        
        rotation_matrix = Matrix((x_axis, y_axis, z_axis)).transposed()
        
        # Apply rotation based on cursor rotation mode
        if cursor.rotation_mode == 'QUATERNION':
            cursor.rotation_quaternion = rotation_matrix.to_quaternion()
        elif cursor.rotation_mode == 'AXIS_ANGLE':
            q = rotation_matrix.to_quaternion()
            axis, angle = q.to_axis_angle()
            cursor.rotation_axis_angle = [angle, axis.x, axis.y, axis.z]
        else:
            # Handle all Euler modes (XYZ, ZYX, etc.)
            cursor.rotation_euler = rotation_matrix.to_euler(cursor.rotation_mode)
        
        # Update highlights
        update_edge_highlight([selected_edge['start'], selected_edge['end']])
        
        # Update bbox preview with preference check
        try:
            prefs = get_preferences()
            if preview and prefs and prefs.bbox_preview_enabled:
                push_value = getattr(context.scene, 'cursor_bbox_push', 0.01)
                # Use the rotation matrix we just calculated, converted to Euler XYZ
                cursor_rotation_euler = rotation_matrix.to_euler('XYZ')
                update_bbox_preview(face_data['object'], push_value, cursor.location, cursor_rotation_euler)
        except:
            pass
    
    return {
        'success': True,
        'location': location,
        'normal': normal,
        'face_index': face_data['face_index'],
        'object': face_data['object'],
        'aligned_to_face': align_to_face,
        'face_data': face_data
    }

# ===== OPTIMIZED SNAP FUNCTIONS =====

def _closest_point_on_edge_screen(region, region_3d, edge_start, edge_end, mouse_x, mouse_y):
    """
    Get the 3D point on the edge segment that projects to the closest 2D point to the mouse.
    Returns (world_point, screen_distance_sq) or (None, float('inf')) if projection fails.
    """
    start_2d = view3d_utils.location_3d_to_region_2d(region, region_3d, edge_start)
    end_2d = view3d_utils.location_3d_to_region_2d(region, region_3d, edge_end)
    if start_2d is None or end_2d is None:
        return None, float('inf')
    dx = end_2d[0] - start_2d[0]
    dy = end_2d[1] - start_2d[1]
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-10:
        t = 0.5
        pt_2d = start_2d
    else:
        t = ((mouse_x - start_2d[0]) * dx + (mouse_y - start_2d[1]) * dy) / length_sq
        t = max(0.0, min(1.0, t))
        pt_2d = (start_2d[0] + t * dx, start_2d[1] + t * dy)
    dist_sq = (pt_2d[0] - mouse_x) ** 2 + (pt_2d[1] - mouse_y) ** 2
    world_pt = edge_start + t * (edge_end - edge_start)
    return world_pt, dist_sq

@lru_cache(maxsize=16)
def get_snap_elements_cached(obj_name, face_index, use_depsgraph=False):
    """Cache snap elements for a specific face"""
    obj = bpy.data.objects.get(obj_name)
    if not obj or obj.type != 'MESH':
        return []
    
    if use_depsgraph:
        try:
            depsgraph = bpy.context.view_layer.depsgraph
            obj_eval = obj.evaluated_get(depsgraph)
            mesh = obj_eval.data
        except:
            mesh = obj.data
    else:
        mesh = obj.data
    
    if face_index >= len(mesh.polygons):
        return []
    
    face = mesh.polygons[face_index]
    matrix_world = obj.matrix_world
    elements = []
    
    # Face vertices
    for vert_idx in face.vertices:
        vert = mesh.vertices[vert_idx]
        world_pos = matrix_world @ vert.co
        elements.append(('vertex', world_pos))
    
    # Edge midpoints
    for i in range(len(face.vertices)):
        vert1_idx = face.vertices[i]
        vert2_idx = face.vertices[(i + 1) % len(face.vertices)]
        
        vert1 = mesh.vertices[vert1_idx]
        vert2 = mesh.vertices[vert2_idx]
        
        midpoint_local = (vert1.co + vert2.co) / 2
        world_pos = matrix_world @ midpoint_local
        elements.append(('edge', world_pos))
    
    # Face center
    face_center_local = face.center
    world_pos = matrix_world @ face_center_local
    elements.append(('face', world_pos))
    
    return elements

def _snap_mode_allows(snap_mode, element_type):
    """snap_mode: 0=all, 1=vertex, 2=edge, 3=face. Return True if element_type is allowed."""
    if snap_mode == 0:
        return True
    if snap_mode == 1:
        return element_type == 'vertex'
    if snap_mode == 2:
        return element_type == 'edge'
    if snap_mode == 3:
        return element_type == 'face'
    return True

def snap_cursor_to_closest_element_optimized(context, event, face_data=None, threshold=120, intersection_points=None, use_depsgraph=False, snap_mode=0):
    """Optimized cursor snapping with caching. snap_mode: 0=all, 1=vertex, 2=edge, 3=face."""
    region = context.region
    region_3d = context.region_data
    
    mouse_x = event.mouse_region_x
    mouse_y = event.mouse_region_y
    
    closest_point = None
    closest_distance = float('inf')
    closest_type = None
    
    # Check intersection points if provided (always available as snap targets when limitation plane is on)
    if intersection_points:
        for p in intersection_points:
            screen_pos = view3d_utils.location_3d_to_region_2d(region, region_3d, p)
            if screen_pos:
                screen_distance = ((screen_pos[0] - mouse_x) ** 2 + (screen_pos[1] - mouse_y) ** 2) ** 0.5
                if screen_distance < closest_distance:
                    closest_distance = screen_distance
                    closest_point = p
                    closest_type = 'intersection'

    if face_data:
        # Use cached snap elements for vertices and face; for edges use closest point along edge
        elements = get_snap_elements_cached(face_data['object'].name, face_data['face_index'], use_depsgraph=use_depsgraph)
        
        for element_type, world_pos in elements:
            if element_type == 'edge':
                # Edges handled below via closest point on segment
                continue
            if not _snap_mode_allows(snap_mode, element_type):
                continue
            screen_pos = view3d_utils.location_3d_to_region_2d(region, region_3d, world_pos)
            if screen_pos:
                screen_distance = ((screen_pos[0] - mouse_x) ** 2 + (screen_pos[1] - mouse_y) ** 2) ** 0.5
                if screen_distance < closest_distance:
                    closest_distance = screen_distance
                    closest_point = world_pos
                    closest_type = element_type

        # Snap to closest point on each edge (so cursor moves along the edge)
        if face_data.get('edges') and _snap_mode_allows(snap_mode, 'edge'):
            for edge in face_data['edges']:
                world_pt, dist_sq = _closest_point_on_edge_screen(
                    region, region_3d,
                    edge['start'], edge['end'],
                    mouse_x, mouse_y
                )
                if world_pt is not None:
                    screen_distance = dist_sq ** 0.5
                    if screen_distance < closest_distance:
                        closest_distance = screen_distance
                        closest_point = world_pt
                        closest_type = 'edge'
    else:
        # Fall back to all selected objects (original behavior)
        context_hash = get_context_hash()
        selected_objects = get_visible_mesh_objects(context_hash)
        
        if not selected_objects:
            return {'success': False}
        
        depsgraph = context.view_layer.depsgraph
        
        for obj in selected_objects:
            if use_depsgraph:
                obj_eval = obj.evaluated_get(depsgraph)
                if not obj_eval.data:
                    continue
                mesh = obj_eval.data
            else:
                mesh = obj.data
                if not mesh:
                    continue
            
            matrix_world = obj.matrix_world
            
            # Check vertices (sample only if many vertices)
            if _snap_mode_allows(snap_mode, 'vertex'):
                vertex_step = max(1, len(mesh.vertices) // 100)  # Sample every nth vertex for performance
                for i in range(0, len(mesh.vertices), vertex_step):
                    vert = mesh.vertices[i]
                    world_pos = matrix_world @ vert.co
                    screen_pos = view3d_utils.location_3d_to_region_2d(region, region_3d, world_pos)
                    if screen_pos:
                        screen_distance = ((screen_pos[0] - mouse_x) ** 2 + (screen_pos[1] - mouse_y) ** 2) ** 0.5
                        if screen_distance < closest_distance:
                            closest_distance = screen_distance
                            closest_point = world_pos
                            closest_type = 'vertex'
            
            # Check edge midpoints (sample for performance)
            if _snap_mode_allows(snap_mode, 'edge'):
                edge_step = max(1, len(mesh.edges) // 50)
                for i in range(0, len(mesh.edges), edge_step):
                    edge = mesh.edges[i]
                    vert1 = mesh.vertices[edge.vertices[0]]
                    vert2 = mesh.vertices[edge.vertices[1]]
                    midpoint_local = (vert1.co + vert2.co) / 2
                    world_pos = matrix_world @ midpoint_local
                    
                    screen_pos = view3d_utils.location_3d_to_region_2d(region, region_3d, world_pos)
                    if screen_pos:
                        screen_distance = ((screen_pos[0] - mouse_x) ** 2 + (screen_pos[1] - mouse_y) ** 2) ** 0.5
                        if screen_distance < closest_distance:
                            closest_distance = screen_distance
                            closest_point = world_pos
                            closest_type = 'edge'
            
            # Check face centers (sample for performance)
            if _snap_mode_allows(snap_mode, 'face'):
                face_step = max(1, len(mesh.polygons) // 25)
                for i in range(0, len(mesh.polygons), face_step):
                    face = mesh.polygons[i]
                    face_center_local = face.center
                    world_pos = matrix_world @ face_center_local
                    
                    screen_pos = view3d_utils.location_3d_to_region_2d(region, region_3d, world_pos)
                    if screen_pos:
                        screen_distance = ((screen_pos[0] - mouse_x) ** 2 + (screen_pos[1] - mouse_y) ** 2) ** 0.5
                        if screen_distance < closest_distance:
                            closest_distance = screen_distance
                            closest_point = world_pos
                            closest_type = 'face'
    
    # Snap threshold check
    if closest_point and closest_distance < threshold:
        context.scene.cursor.location = closest_point
        return {
            'success': True,
            'location': closest_point,
            'type': closest_type,
            'distance': closest_distance
        }
    
    return {'success': False}

# ===== OPTIMIZED EDGE SELECTION =====

def select_edge_by_scroll_optimized(face_data, scroll_direction, current_edge_index):
    """Optimized edge selection with bounds checking"""
    if not face_data or not face_data.get('edges'):
        return 0
    
    edge_count = len(face_data['edges'])
    
    if scroll_direction > 0:  # Scroll up
        return (current_edge_index + 1) % edge_count
    else:  # Scroll down
        return (current_edge_index - 1) % edge_count

# ===== PERFORMANCE UTILITIES =====

def clear_all_caches():
    """Clear all performance caches"""
    global _raycast_cache
    _raycast_cache.clear()
    
    # Clear function caches
    get_visible_mesh_objects.cache_clear()
    get_snap_elements_cached.cache_clear()

def get_performance_stats():
    """Get cache performance statistics"""
    return {
        'raycast_cache_size': len(_raycast_cache.cache),
        'visible_objects_cache_info': get_visible_mesh_objects.cache_info(),
        'snap_elements_cache_info': get_snap_elements_cached.cache_info()
    }

# ===== LEGACY COMPATIBILITY FUNCTIONS =====

def get_face_edges_from_raycast(context, event, use_depsgraph=False):
    """Legacy function name - redirects to optimized version"""
    return get_face_edges_from_raycast_optimized(context, event, use_depsgraph=use_depsgraph)

def select_edge_by_scroll(face_data, scroll_direction, current_edge_index):
    """Legacy function name - redirects to optimized version"""
    return select_edge_by_scroll_optimized(face_data, scroll_direction, current_edge_index)

def place_cursor_with_raycast_and_edge(context, event, align_to_face=True, edge_index=0, preview=True, use_depsgraph=False):
    """Legacy function name - redirects to optimized version"""
    return place_cursor_with_raycast_and_edge_optimized(context, event, align_to_face, edge_index, preview, use_depsgraph=use_depsgraph)

def snap_cursor_to_closest_element(context, event, face_data=None, threshold=120, intersection_points=None, use_depsgraph=False, snap_mode=0):
    """Legacy function name - redirects to optimized version"""
    return snap_cursor_to_closest_element_optimized(context, event, face_data, threshold=threshold, intersection_points=intersection_points, use_depsgraph=use_depsgraph, snap_mode=snap_mode)

# ===== BATCH PROCESSING UTILITIES =====

def batch_process_vertices(objects, transform_func, batch_size=1000):
    """Process vertices in batches for better performance"""
    results = []
    
    for obj in objects:
        if obj.type != 'MESH':
            continue
            
        mesh = obj.data
        matrix_world = obj.matrix_world
        
        # Process vertices in batches
        for i in range(0, len(mesh.vertices), batch_size):
            batch_end = min(i + batch_size, len(mesh.vertices))
            batch_vertices = mesh.vertices[i:batch_end]
            
            # Transform batch
            batch_results = []
            for vert in batch_vertices:
                world_pos = matrix_world @ vert.co
                result = transform_func(world_pos)
                if result is not None:
                    batch_results.append(result)
            
            results.extend(batch_results)
    
    return results

def get_object_bounds_fast(obj):
    """Fast object bounds calculation using bound_box"""
    if obj.type != 'MESH':
        return None
    
    try:
        # Use Blender's cached bound_box
        bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        
        min_bound = Vector((
            min(corner.x for corner in bbox_corners),
            min(corner.y for corner in bbox_corners),
            min(corner.z for corner in bbox_corners)
        ))
        
        max_bound = Vector((
            max(corner.x for corner in bbox_corners),
            max(corner.y for corner in bbox_corners),
            max(corner.z for corner in bbox_corners)
        ))
        
        return min_bound, max_bound
    except:
        return None

# ===== SPATIAL OPTIMIZATION =====

class SpatialGrid:
    """Simple spatial grid for faster object queries"""
    
    def __init__(self, grid_size=10.0):
        self.grid_size = grid_size
        self.grid = {}
        self.objects = {}
    
    def _get_grid_key(self, position):
        """Get grid key for a position"""
        return (
            int(position.x // self.grid_size),
            int(position.y // self.grid_size),
            int(position.z // self.grid_size)
        )
    
    def add_object(self, obj):
        """Add object to spatial grid"""
        bounds = get_object_bounds_fast(obj)
        if not bounds:
            return
        
        min_bound, max_bound = bounds
        
        # Get all grid cells this object spans
        min_key = self._get_grid_key(min_bound)
        max_key = self._get_grid_key(max_bound)
        
        grid_cells = []
        for x in range(min_key[0], max_key[0] + 1):
            for y in range(min_key[1], max_key[1] + 1):
                for z in range(min_key[2], max_key[2] + 1):
                    grid_cells.append((x, y, z))
        
        # Add to grid
        for cell in grid_cells:
            if cell not in self.grid:
                self.grid[cell] = []
            self.grid[cell].append(obj)
        
        self.objects[obj.name] = grid_cells
    
    def remove_object(self, obj):
        """Remove object from spatial grid"""
        if obj.name in self.objects:
            for cell in self.objects[obj.name]:
                if cell in self.grid and obj in self.grid[cell]:
                    self.grid[cell].remove(obj)
                    if not self.grid[cell]:
                        del self.grid[cell]
            del self.objects[obj.name]
    
    def get_nearby_objects(self, position, radius=None):
        """Get objects near a position"""
        if radius is None:
            radius = self.grid_size
        
        # Get grid cells to check
        cells_to_check = set()
        grid_radius = int(radius // self.grid_size) + 1
        
        center_key = self._get_grid_key(position)
        
        for x in range(center_key[0] - grid_radius, center_key[0] + grid_radius + 1):
            for y in range(center_key[1] - grid_radius, center_key[1] + grid_radius + 1):
                for z in range(center_key[2] - grid_radius, center_key[2] + grid_radius + 1):
                    cells_to_check.add((x, y, z))
        
        # Collect unique objects
        nearby_objects = set()
        for cell in cells_to_check:
            if cell in self.grid:
                nearby_objects.update(self.grid[cell])
        
        return list(nearby_objects)
    
    def clear(self):
        """Clear the spatial grid"""
        self.grid.clear()
        self.objects.clear()

# Global spatial grid instance
_spatial_grid = SpatialGrid()

def update_spatial_grid(context):
    """Update spatial grid with current objects"""
    global _spatial_grid
    _spatial_grid.clear()
    
    context_hash = get_context_hash()
    visible_objects = get_visible_mesh_objects(context_hash)
    
    for obj in visible_objects:
        _spatial_grid.add_object(obj)

def get_nearby_objects_for_raycast(ray_origin, max_distance=None):
    """Get objects near ray origin for optimized raycasting"""
    return _spatial_grid.get_nearby_objects(ray_origin, max_distance)

# ===== ADVANCED OPTIMIZATION FEATURES =====

class AdaptivePerformanceManager:
    """Manages performance settings based on scene complexity"""
    
    def __init__(self):
        self.last_update_time = 0
        self.update_interval = 5.0  # Update every 5 seconds
        self.performance_level = 'medium'
        
    def update_performance_settings(self, context):
        """Update performance settings based on current scene"""
        current_time = time.time()
        if current_time - self.last_update_time < self.update_interval:
            return
        
        self.last_update_time = current_time
        
        # Analyze scene complexity
        total_objects = len([obj for obj in context.scene.objects if obj.type == 'MESH'])
        total_faces = sum(len(obj.data.polygons) for obj in context.scene.objects 
                         if obj.type == 'MESH' and obj.data)
        
        # Adjust performance level
        if total_faces > 100000 or total_objects > 500:
            self.performance_level = 'low'
            self._apply_low_performance_settings()
        elif total_faces > 50000 or total_objects > 200:
            self.performance_level = 'medium'
            self._apply_medium_performance_settings()
        else:
            self.performance_level = 'high'
            self._apply_high_performance_settings()
    
    def _apply_low_performance_settings(self):
        """Apply settings for complex scenes"""
        global _raycast_cache
        _raycast_cache.cache_size = 25
        _raycast_cache.mouse_threshold = 8
        _raycast_cache.time_threshold = 0.2
    
    def _apply_medium_performance_settings(self):
        """Apply settings for medium complexity scenes"""
        global _raycast_cache
        _raycast_cache.cache_size = 50
        _raycast_cache.mouse_threshold = 5
        _raycast_cache.time_threshold = 0.1
    
    def _apply_high_performance_settings(self):
        """Apply settings for simple scenes"""
        global _raycast_cache
        _raycast_cache.cache_size = 100
        _raycast_cache.mouse_threshold = 3
        _raycast_cache.time_threshold = 0.05

# Global performance manager
_performance_manager = AdaptivePerformanceManager()

def update_adaptive_performance(context):
    """Update adaptive performance settings"""
    global _performance_manager
    _performance_manager.update_performance_settings(context)

# ===== DEBUGGING AND PROFILING =====

class PerformanceProfiler:
    """Simple performance profiler for debugging"""
    
    def __init__(self):
        self.timings = {}
        self.call_counts = {}
    
    def profile(self, func_name):
        """Decorator to profile function execution time"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                result = func(*args, **kwargs)
                end_time = time.perf_counter()
                
                execution_time = end_time - start_time
                
                if func_name not in self.timings:
                    self.timings[func_name] = []
                    self.call_counts[func_name] = 0
                
                self.timings[func_name].append(execution_time)
                self.call_counts[func_name] += 1
                
                # Keep only last 100 timings to prevent memory growth
                if len(self.timings[func_name]) > 100:
                    self.timings[func_name] = self.timings[func_name][-100:]
                
                return result
            return wrapper
        return decorator
    
    def get_stats(self):
        """Get performance statistics"""
        stats = {}
        for func_name, timings in self.timings.items():
            if timings:
                avg_time = sum(timings) / len(timings)
                max_time = max(timings)
                min_time = min(timings)
                stats[func_name] = {
                    'calls': self.call_counts[func_name],
                    'avg_time_ms': avg_time * 1000,
                    'max_time_ms': max_time * 1000,
                    'min_time_ms': min_time * 1000
                }
        return stats
    
    def clear(self):
        """Clear all profiling data"""
        self.timings.clear()
        self.call_counts.clear()

# Global profiler instance
_profiler = PerformanceProfiler()

def get_profiling_stats():
    """Get current profiling statistics"""
    return _profiler.get_stats()

# ===== GEOMETRY UTILS =====

def project_point_to_plane_intersection(hit_location, face_normal, plane_origin, plane_normal):
    """
    Project a point (hit_location on Face Plane) onto the line of intersection 
    between Face Plane and Cursor Plane (plane_origin, plane_normal).
    
    Returns:
        Vector: The projected point on the intersection line, or None if planes are parallel.
    """
    # Plane 1: Face Plane (P - hit_location) . face_normal = 0
    # Plane 2: Cursor Plane (P - plane_origin) . plane_normal = 0
    
    # Direction of intersection line L
    line_dir = face_normal.cross(plane_normal)
    
    # If cross product is near zero, planes are parallel
    if line_dir.length_squared < 1e-6:
        return None
        
    line_dir.normalize()
    
    # finding a point on the line (intersection of planes)
    # We have a system of linear equations for P(x,y,z):
    # N1 . P = d1  => face_normal . P = face_normal . hit_location
    # N2 . P = d2  => plane_normal . P = plane_normal . plane_origin
    
    # Let's find a point P0 on this line.
    # We can solve this using cross products or general linear system solver.
    # A robust way:
    # L = N1 x N2
    # P0 = (d1 * (N2 x L) + d2 * (L x N1)) / |L|^2
    # from http://geomalgorithms.com/a05-_intersect-1.html
    
    d1 = face_normal.dot(hit_location)
    d2 = plane_normal.dot(plane_origin)
    L_sq = line_dir.length_squared # Already normalized so 1.0, but for safety
    if L_sq < 1e-6: return None
    
    n2_cross_l = plane_normal.cross(line_dir)
    l_cross_n1 = line_dir.cross(face_normal)
    
    p0 = (d1 * n2_cross_l + d2 * l_cross_n1) / line_dir.length_squared
    
    # Now we have the line: P(t) = P0 + t * line_dir
    # We want to project hit_location onto this line.
    # P_proj = P0 + dot(hit_location - P0, line_dir) * line_dir
    
    t = (hit_location - p0).dot(line_dir)
    p_proj = p0 + t * line_dir
    
    return p_proj

def clear_profiling_data():
    """Clear all profiling data"""
    _profiler.clear()

# Apply profiling to key functions (optional - enable for debugging)
# Uncomment these lines to enable profiling
# get_face_edges_from_raycast_optimized = _profiler.profile('raycast')( get_face_edges_from_raycast_optimized)
# place_cursor_with_raycast_and_edge_optimized = _profiler.profile('cursor_place')( place_cursor_with_raycast_and_edge_optimized)
# snap_cursor_to_closest_element_optimized = _profiler.profile('snap')( snap_cursor_to_closest_element_optimized)

# ===== MEMORY MANAGEMENT =====

class MemoryManager:
    """Manages memory usage and cleanup"""
    
    def __init__(self):
        self.cleanup_threshold = 1000  # Number of operations before cleanup
        self.operation_count = 0
        
    def increment_operations(self):
        """Track operation count for periodic cleanup"""
        self.operation_count += 1
        if self.operation_count >= self.cleanup_threshold:
            self.periodic_cleanup()
            self.operation_count = 0
    
    def periodic_cleanup(self):
        """Perform periodic memory cleanup"""
        global _raycast_cache, _spatial_grid
        
        # Cleanup old cache entries
        if len(_raycast_cache.cache) > _raycast_cache.cache_size:
            _raycast_cache.clear()
        
        # Clear function caches if they get too large
        cache_info = get_visible_mesh_objects.cache_info()
        if cache_info.currsize > 50:
            get_visible_mesh_objects.cache_clear()
        
        cache_info = get_snap_elements_cached.cache_info()
        if cache_info.currsize > 20:
            get_snap_elements_cached.cache_clear()
        
        print("Cursor BBox: Performed periodic memory cleanup")
    
    def force_cleanup(self):
        """Force immediate cleanup of all caches"""
        clear_all_caches()
        _spatial_grid.clear()
        _profiler.clear()
        self.operation_count = 0
        print("Cursor BBox: Performed forced memory cleanup")

# Global memory manager
_memory_manager = MemoryManager()

# ===== ERROR HANDLING AND RECOVERY =====

def safe_raycast_wrapper(func):
    """Wrapper for safe raycast operations with error recovery"""
    def wrapper(*args, **kwargs):
        try:
            _memory_manager.increment_operations()
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Cursor BBox raycast error: {e}")
            # Clear caches and try once more
            clear_all_caches()
            try:
                return func(*args, **kwargs)
            except Exception as e2:
                print(f"Cursor BBox raycast recovery failed: {e2}")
                return None
    return wrapper

# Apply safe wrapper to critical functions
get_face_edges_from_raycast_optimized = safe_raycast_wrapper(get_face_edges_from_raycast_optimized)
place_cursor_with_raycast_and_edge_optimized = safe_raycast_wrapper(place_cursor_with_raycast_and_edge_optimized)

# ===== CONTEXT CHANGE DETECTION =====

class ContextChangeDetector:
    """Detects when Blender context changes significantly"""
    
    def __init__(self):
        self.last_context_hash = None
        self.last_scene_update = 0
        
    def context_changed(self, context):
        """Check if context has changed significantly"""
        current_hash = get_context_hash()
        if current_hash != self.last_context_hash:
            self.last_context_hash = current_hash
            return True
        return False
    
    def scene_updated(self, scene):
        """Check if scene has been updated"""
        current_time = time.time()
        if current_time - self.last_scene_update > 1.0:  # 1 second threshold
            self.last_scene_update = current_time
            return True
        return False

# Global context detector
_context_detector = ContextChangeDetector()

def handle_context_change(context):
    """Handle significant context changes"""
    global _context_detector, _raycast_cache, _spatial_grid
    
    if _context_detector.context_changed(context):
        # Clear relevant caches when context changes
        _raycast_cache.clear()
        get_visible_mesh_objects.cache_clear()
        update_spatial_grid(context)
        update_adaptive_performance(context)
        print("Cursor BBox: Context changed, cleared caches")

# ===== FINAL CLEANUP FUNCTIONS =====

def cleanup_utils():
    """Clean up all utils caches and data"""
    global _raycast_cache, _spatial_grid, _memory_manager, _profiler, _performance_manager
    
    # Clear all caches
    clear_all_caches()
    _spatial_grid.clear()
    _profiler.clear()
    
    # Reset managers
    _memory_manager.operation_count = 0
    _performance_manager.last_update_time = 0
    
    print("Cursor BBox utils: Complete cleanup finished")

def get_utils_debug_info():
    """Get comprehensive debug information"""
    return {
        'raycast_cache': {
            'size': len(_raycast_cache.cache),
            'last_result_exists': _raycast_cache.last_result is not None,
            'last_mouse_pos': _raycast_cache.last_mouse_pos
        },
        'function_caches': {
            'visible_objects': get_visible_mesh_objects.cache_info()._asdict(),
            'snap_elements': get_snap_elements_cached.cache_info()._asdict()
        },
        'spatial_grid': {
            'objects_count': len(_spatial_grid.objects),
            'grid_cells': len(_spatial_grid.grid)
        },
        'performance': {
            'level': _performance_manager.performance_level,
            'operation_count': _memory_manager.operation_count
        },
        'profiling': get_profiling_stats()
    }

# ===== CONFIGURATION =====

def configure_performance(cache_size=50, mouse_threshold=5, time_threshold=0.1):
    """Configure performance parameters"""
    global _raycast_cache
    _raycast_cache.cache_size = cache_size
    _raycast_cache.mouse_threshold = mouse_threshold
    _raycast_cache.time_threshold = time_threshold
    print(f"Cursor BBox: Performance configured - cache:{cache_size}, mouse:{mouse_threshold}px, time:{time_threshold}s")

def enable_profiling(enable=True):
    """Enable or disable performance profiling"""
    global get_face_edges_from_raycast_optimized, place_cursor_with_raycast_and_edge_optimized, snap_cursor_to_closest_element_optimized
    
    if enable:
        # Apply profiling decorators
        get_face_edges_from_raycast_optimized = _profiler.profile('raycast')(get_face_edges_from_raycast_optimized)
        place_cursor_with_raycast_and_edge_optimized = _profiler.profile('cursor_place')(place_cursor_with_raycast_and_edge_optimized)
        snap_cursor_to_closest_element_optimized = _profiler.profile('snap')(snap_cursor_to_closest_element_optimized)
        print("Cursor BBox: Profiling enabled")
    else:
        # Note: Can't easily remove decorators, but can clear data
        _profiler.clear()
        print("Cursor BBox: Profiling data cleared")

# ===== EXPORT FUNCTIONS FOR CONSOLE USE =====

def debug():
    """Console-friendly debug function"""
    print("=== Cursor BBox Utils Debug ===")
    debug_info = get_utils_debug_info()
    for section, data in debug_info.items():
        print(f"{section}: {data}")
    print("==============================")

def clear_caches():
    """Console-friendly cache clearing"""
    clear_all_caches()
    print("All caches cleared")

def performance_stats():
    """Console-friendly performance stats"""
    stats = get_performance_stats()
    print("=== Performance Stats ===")
    for key, value in stats.items():
        print(f"{key}: {value}")
    print("========================")

# ===== INITIALIZATION =====

def initialize_utils():
    """Initialize utils system"""
    global _raycast_cache, _spatial_grid, _memory_manager, _performance_manager, _profiler
    
    # Reset all systems
    _raycast_cache.clear()
    _spatial_grid.clear()
    _memory_manager.operation_count = 0
    _performance_manager.last_update_time = 0
    _profiler.clear()
    
    print("Cursor BBox utils initialized")
# Auto-initialize when module is imported
initialize_utils()

def debug_point_system():
    """Comprehensive debug function for point drawing system"""
    from .functions import _state
    
    print("=== Cursor BBox Point System Debug ===")
    print(f"Global marked points: {len(_state.marked_points)}")
    if _state.marked_points:
        for i, point in enumerate(_state.marked_points):
            print(f"  Point {i}: {tuple(point)}")
    
    print(f"Active handlers: {list(_state.handlers.keys())}")
    print(f"Face marking handler active: {'face_marking' in _state.handlers}")
    print(f"GPU cache keys: {list(_state.gpu_manager.batch_cache.keys())}")
    
    # Check if any point-related caches exist
    point_caches = [key for key in _state.gpu_manager.batch_cache.keys() if 'point' in key]
    print(f"Point-related caches: {point_caches}")
    
    # Check marked faces
    print(f"Marked faces objects: {len(_state.marked_faces)}")
    print(f"Visual cache objects: {len(_state.marked_faces_visual_cache)}")
    
    if _state.marked_points and 'face_marking' not in _state.handlers:
        print("ERROR: Points exist but face_marking handler is missing!")
        from .functions import enable_face_marking
        enable_face_marking()
        print("Enabled face_marking handler")
    
    print("=====================================")

def force_enable_point_drawing():
    """Force enable point drawing - useful for troubleshooting"""
    from .functions import _state, enable_face_marking
    
    if _state.marked_points:
        print(f"Force enabling drawing for {len(_state.marked_points)} points")
        
        # Clear point caches
        _state.gpu_manager.clear_cache_key('marked_points')
        _state.gpu_manager.clear_cache_key('marked_points_only')
        
        # Ensure handler is active
        if 'face_marking' not in _state.handlers:
            enable_face_marking()
            print("Face marking handler enabled")
        
        # Force redraw
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        print("Point drawing force-enabled")
    else:
        print("No points to draw")

# ===== COPLANAR SELECTION UTILITIES =====

def get_connected_coplanar_faces(obj, start_face_index, angle_tolerance_radians, use_depsgraph=False):
    """Find connected faces that are coplanar within tolerance"""
    if obj.type != 'MESH':
        return set()
    
    if use_depsgraph:
        try:
            depsgraph = bpy.context.view_layer.depsgraph
            obj_eval = obj.evaluated_get(depsgraph)
            mesh = obj_eval.data
        except:
             mesh = obj.data
    else:
        mesh = obj.data

    if start_face_index >= len(mesh.polygons):
        return set()

    # Create BVH/BMesh for connectivity
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    
    if start_face_index >= len(bm.faces):
        bm.free()
        return set()
        
    start_face = bm.faces[start_face_index]
    start_normal = start_face.normal.copy()
    
    visited = set()
    coplanar_indices = set()
    queue = [start_face]
    
    visited.add(start_face)
    coplanar_indices.add(start_face.index)
    
    while queue:
        current_face = queue.pop(0)
        
        for edge in current_face.edges:
            for neighbor in edge.link_faces:
                if neighbor not in visited:
                    visited.add(neighbor)
                    
                    # Check angle - compare to start face to maintain planarity stability
                    # 100.0 is default safe return for parallel check, though angle() handles robustly
                    try:
                        angle = start_normal.angle(neighbor.normal)
                    except ValueError:
                        angle = 0.0 # Exactly parallel or zero length normal
                    
                    if angle < angle_tolerance_radians:
                        coplanar_indices.add(neighbor.index)
                        queue.append(neighbor)
    
    bm.free()
    return coplanar_indices

def ensure_cbb_collection(context):
    """Ensure the CBB_Collision collection exists and return it"""
    collection_name = context.scene.cursor_bbox_collection_name
    
    # Check if collection exists
    if collection_name in bpy.data.collections:
        return bpy.data.collections[collection_name]
    
    # Create new collection
    new_collection = bpy.data.collections.new(collection_name)
    context.scene.collection.children.link(new_collection)
    return new_collection

def ensure_cbb_material(context):
    """Ensure the Cursor BBox Material exists and return it"""
    mat_name = "Cursor BBox Material"
    
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        
    # Ensure it uses the color from properties
    if mat.use_nodes and hasattr(context.scene, "cursor_bbox_material_color"):
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            color = list(context.scene.cursor_bbox_material_color) + [1.0]
            bsdf.inputs['Base Color'].default_value = color
            mat.diffuse_color = color
            
    return mat

def assign_object_styles(context, obj):
    """Assign materials and colors to object"""
    # Assign Material if enabled
    if getattr(context.scene, "cursor_bbox_use_material", False):
        try:
            mat = ensure_cbb_material(context)
            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)
        except Exception as e:
            print(f"Failed to assign material: {e}")
    
    # Assign Object Color (Independent)
    try:
        # We assume property exists if it's registered
        # But use getattr with default to be safe against attribute errors
        color_prop = getattr(context.scene, "cursor_bbox_material_color", (1.0, 0.5, 0.0))
        # Ensure it's a list/tuple
        color = list(color_prop) + [1.0]
        obj.color = color
    except Exception as e:
        print(f"Failed to assign object color: {e}")

def calculate_plane_edge_intersections(obj, plane_origin, plane_normal, use_depsgraph=False):
    """
    Calculate intersection points between object edges and a plane.
    Returns a list of world-space intersection points.
    """
    if not obj or obj.type != 'MESH':
        return []
    
    if use_depsgraph:
        try:
            depsgraph = bpy.context.view_layer.depsgraph
            obj_eval = obj.evaluated_get(depsgraph)
            mesh = obj_eval.data
        except:
            mesh = obj.data
    else:
        mesh = obj.data
    
    matrix = obj.matrix_world
    
    # Plane equation: (P - P0) . N = 0  => P . N = P0 . N = d
    d = plane_origin.dot(plane_normal)
    
    intersections = []
    
    for edge in mesh.edges:
        v1_local = mesh.vertices[edge.vertices[0]].co
        v2_local = mesh.vertices[edge.vertices[1]].co
        
        v1_world = matrix @ v1_local
        v2_world = matrix @ v2_local
        
        # Check intersection
        # t = (d - v1.N) / ((v2 - v1).N)
        
        vec = v2_world - v1_world
        denom = vec.dot(plane_normal)
        
        if abs(denom) > 1e-6: # Not parallel
            val1 = v1_world.dot(plane_normal)
            t = (d - val1) / denom
            if 0.0 <= t <= 1.0: # segment intersection
                p = v1_world + vec * t
                intersections.append(p)
                
    return intersections


def best_fit_plane_from_points(points):
    """
    Compute a best-fit plane from a list of 3D points (centroid + normal via PCA).
    Returns (origin, normal) as world-space Vector, or (None, None) if insufficient points.
    """
    if not points or len(points) < 3:
        return None, None
    n = len(points)
    centroid = Vector((0.0, 0.0, 0.0))
    for p in points:
        centroid += p
    centroid /= n
    # Build 3x3 covariance matrix (we only need it for smallest eigenvector)
    xx = yy = zz = xy = xz = yz = 0.0
    for p in points:
        dx = p.x - centroid.x
        dy = p.y - centroid.y
        dz = p.z - centroid.z
        xx += dx * dx
        yy += dy * dy
        zz += dz * dz
        xy += dx * dy
        xz += dx * dz
        yz += dy * dz
    # Smallest eigenvector of covariance matrix = plane normal (power iteration on (trace*I - M))
    trace = xx + yy + zz
    if trace < 1e-12:
        return None, None
    v = Vector((1.0, 0.0, 0.0))
    for _ in range(20):
        v_new = Vector((
            trace * v.x - (xx * v.x + xy * v.y + xz * v.z),
            trace * v.y - (xy * v.x + yy * v.y + yz * v.z),
            trace * v.z - (xz * v.x + yz * v.y + zz * v.z)
        ))
        length = v_new.length
        if length < 1e-9:
            return centroid, Vector((0, 0, 1))
        v = v_new / length
    return centroid, v.normalized()


def matrix_from_plane(origin, normal):
    """Build a 4x4 matrix with Z = normal, origin as translation."""
    z_axis = normal.normalized()
    if abs(z_axis.z) < 0.9:
        x_axis = Vector((0, 0, 1)).cross(z_axis).normalized()
    else:
        x_axis = Vector((1, 0, 0)).cross(z_axis).normalized()
    y_axis = z_axis.cross(x_axis).normalized()
    m = Matrix(((x_axis.x, y_axis.x, z_axis.x, origin.x),
                (x_axis.y, y_axis.y, z_axis.y, origin.y),
                (x_axis.z, y_axis.z, z_axis.z, origin.z),
                (0, 0, 0, 1)))
    return m


def calculate_plane_edge_intersections_multi(objects, plane_origin, plane_normal, use_depsgraph=False):
    """Intersections of a plane with edges of multiple mesh objects. Returns combined list of world-space points."""
    result = []
    for obj in objects:
        if obj and obj.type == 'MESH':
            result.extend(calculate_plane_edge_intersections(obj, plane_origin, plane_normal, use_depsgraph=use_depsgraph))
    return result


# ===== OPERATOR UTILITY FUNCTIONS =====

# Principal plane names for cursor alignment (cycle with R in point mode)
CURSOR_PLANE_ALIGNMENTS = ('XY', 'YZ', 'XZ')

def get_principal_plane_rotation_matrix(plane):
    """
    Return a 3x3 rotation matrix that aligns the cursor to a principal plane.
    plane: 'XY' (Z up), 'YZ' (X up), 'XZ' (Y up).
    Cursor Z axis becomes the plane normal (world axis).
    """
    if plane == 'XY':
        # Z = world Z
        return Matrix(((1, 0, 0), (0, 1, 0), (0, 0, 1)))
    if plane == 'YZ':
        # Z = world X (cursor lies in YZ plane)
        return Matrix(((0, 0, -1), (0, 1, 0), (1, 0, 0)))
    if plane == 'XZ':
        # Z = world Y (cursor lies in XZ plane)
        return Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
    return Matrix.Identity(3)

def set_cursor_rotation_to_principal_plane(context, plane):
    """Set cursor rotation to align to principal plane (XY, YZ, or XZ). Keeps cursor location."""
    cursor = context.scene.cursor
    rot_3x3 = get_principal_plane_rotation_matrix(plane)
    if cursor.rotation_mode == 'QUATERNION':
        cursor.rotation_quaternion = rot_3x3.to_quaternion()
    elif cursor.rotation_mode == 'AXIS_ANGLE':
        q = rot_3x3.to_quaternion()
        axis, angle = q.to_axis_angle()
        cursor.rotation_axis_angle = [angle, axis.x, axis.y, axis.z]
    else:
        cursor.rotation_euler = rot_3x3.to_euler(cursor.rotation_mode)
    return plane

def get_cursor_rotation_euler(context):
    """
    Extract cursor rotation as Euler XYZ, handling all rotation modes.
    
    Args:
        context: Blender context
        
    Returns:
        mathutils.Euler: Cursor rotation as Euler XYZ
    """
    cursor = context.scene.cursor
    
    if cursor.rotation_mode == 'QUATERNION':
        return cursor.rotation_quaternion.to_euler('XYZ')
    elif cursor.rotation_mode == 'AXIS_ANGLE':
        rot_mat = cursor.matrix.to_3x3()
        return rot_mat.to_euler('XYZ')
    else:
        if cursor.rotation_mode != 'XYZ':
            return cursor.rotation_euler.to_matrix().to_euler('XYZ')
        else:
            return cursor.rotation_euler

def get_selected_faces_from_edit_mode(context):
    """
    Get selected faces from objects in edit mode.
    
    Args:
        context: Blender context
        
    Returns:
        dict: Dictionary mapping objects to sets of selected face indices
    """
    import bmesh
    
    marked_faces = {}
    
    objects_in_edit = [o for o in context.selected_objects if o.type == 'MESH' and o.mode == 'EDIT']
    if context.active_object and context.active_object.mode == 'EDIT' and context.active_object not in objects_in_edit:
        objects_in_edit.append(context.active_object)
    
    for obj in objects_in_edit:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        selected_indices = {f.index for f in bm.faces if f.select}
        if selected_indices:
            marked_faces[obj] = selected_indices
    
    return marked_faces

def calculate_point_location(context, event, face_data, snap_enabled, limit_plane_mode, 
                            limitation_plane_matrix, cached_limit_intersections, 
                            snap_threshold, use_depsgraph=False, snap_mode=0):
    """
    Calculate point location for point mode, handling snap and limit plane logic.
    
    Args:
        context: Blender context
        event: Blender event
        face_data: Face data from raycast
        snap_enabled: Whether snapping is enabled
        limit_plane_mode: Whether limit plane mode is active
        limitation_plane_matrix: Matrix of the limitation plane
        cached_limit_intersections: Cached intersection points
        snap_threshold: Snap threshold in pixels
        use_depsgraph: Whether to use depsgraph
        snap_mode: 0=all, 1=vertex, 2=edge, 3=face
        
    Returns:
        tuple: (location, success_message) or (None, None) if failed
    """
    loc = None
    message = None
    
    if snap_enabled:
        # First update cursor position for proper snapping
        if face_data:
            # Place cursor at hit location first
            place_cursor_with_raycast_and_edge(
                context, event, True, 0, preview=False, use_depsgraph=use_depsgraph
            )
        
        # Snap Logic - use intersection points if limit plane mode is enabled
        intersection_pts = cached_limit_intersections if limit_plane_mode else None
        snap_result = snap_cursor_to_closest_element(
            context, event, face_data, threshold=snap_threshold, 
            intersection_points=intersection_pts, use_depsgraph=use_depsgraph, snap_mode=snap_mode
        )
        if snap_result['success']:
            loc = context.scene.cursor.location.copy()
            message = f"Added point snapped to {snap_result['type']}"
        elif face_data:
            try:
                loc = face_data['hit_location']
            except:
                pass
        else:
            loc = context.scene.cursor.location.copy()
    elif limit_plane_mode and limitation_plane_matrix and face_data:
        # Limit Plane Logic (no snap)
        plane_origin = limitation_plane_matrix.to_translation()
        plane_normal = limitation_plane_matrix.col[2].to_3d()
        proj_pt = project_point_to_plane_intersection(
            face_data['hit_location'], 
            face_data['face_normal'],
            plane_origin, 
            plane_normal
        )
        if proj_pt:
            loc = proj_pt
        else:
            return None, "Cannot place point: intersection fail"
    else:
        # No snap, use raycast location
        if face_data:
            try:
                loc = face_data['hit_location']
            except:
                # Fallback to cursor location
                loc = context.scene.cursor.location.copy()
        else:
            loc = context.scene.cursor.location.copy()
    
    return loc, message

def get_faces_to_process(obj, face_idx, use_coplanar, coplanar_angle_rad, use_depsgraph=False):
    """
    Get faces to process based on coplanar selection settings.
    
    Args:
        obj: Object containing the face
        face_idx: Starting face index
        use_coplanar: Whether to use coplanar selection
        coplanar_angle_rad: Coplanar angle tolerance in radians
        use_depsgraph: Whether to use depsgraph
        
    Returns:
        set: Set of face indices to process
    """
    if use_coplanar:
        coplanar_indices = get_connected_coplanar_faces(
            obj, face_idx, coplanar_angle_rad, use_depsgraph=use_depsgraph
        )
        return coplanar_indices if coplanar_indices else {face_idx}
    else:
        return {face_idx}

# ===== MESH EVALUATION UTILITIES =====

def get_evaluated_mesh(obj, use_depsgraph=False, context=None):
    """
    Get mesh data from object, optionally using depsgraph evaluation.
    
    Args:
        obj: Blender object to get mesh from
        use_depsgraph: Whether to use depsgraph evaluation
        context: Blender context (optional, uses bpy.context if not provided)
        
    Returns:
        tuple: (mesh, obj_matrix_world) where mesh is the mesh data and obj_matrix_world is the object's world matrix
    """
    if context is None:
        context = bpy.context
    
    if use_depsgraph:
        try:
            depsgraph = context.view_layer.depsgraph
            eval_obj = obj.evaluated_get(depsgraph)
            mesh = eval_obj.data
        except:
            mesh = obj.data
    else:
        mesh = obj.data
    
    obj_matrix_world = obj.matrix_world
    return mesh, obj_matrix_world


def compute_thickness_selection_to_cursor(marked_faces_dict, cursor_location, use_depsgraph=False, context=None):
    """
    Signed distance from cursor to the selection (marked faces) along the average face normal.
    Used in thickness mode: thickness so that extruded faces reach the cursor.
    
    Args:
        marked_faces_dict: {obj: set(face_indices)}
        cursor_location: World-space cursor position (Vector).
        use_depsgraph: Whether to use depsgraph evaluation
        context: Blender context (optional)
    
    Returns:
        float: Signed distance (cursor - selection plane along normal). Positive = cursor in front of selection.
    """
    if context is None:
        context = bpy.context
    if not marked_faces_dict:
        return 0.0
    
    sum_center = Vector((0, 0, 0))
    sum_normal = Vector((0, 0, 0))
    n = 0
    for obj, face_indices in marked_faces_dict.items():
        if not face_indices or obj.type != 'MESH':
            continue
        mesh, obj_matrix_world = get_evaluated_mesh(obj, use_depsgraph=use_depsgraph, context=context)
        mat_3x3 = obj_matrix_world.to_3x3()
        for face_idx in face_indices:
            if face_idx >= len(mesh.polygons):
                continue
            face = mesh.polygons[face_idx]
            world_center = obj_matrix_world @ face.center
            world_normal = (mat_3x3 @ face.normal).normalized()
            sum_center += world_center
            sum_normal += world_normal
            n += 1
    if n == 0:
        return 0.0
    avg_center = sum_center / n
    avg_normal = sum_normal / n
    if avg_normal.length_squared < 1e-10:
        return 0.0
    avg_normal.normalize()
    return (Vector(cursor_location) - avg_center).dot(avg_normal)


def collect_vertices_from_marked_faces(marked_faces_dict, use_depsgraph=False, context=None, face_thickness=0.0):
    """
    Collect all world-space vertices from marked faces dictionary.
    
    When face_thickness is non-zero, also adds vertices offset along each face's
    normal (extrusion-like), so the convex hull can wrap both original and
    thickened faces. This is separate from push offset (which scales the final hull).
    
    Args:
        marked_faces_dict: Dictionary mapping objects to sets of face indices
        use_depsgraph: Whether to use depsgraph evaluation
        context: Blender context (optional, uses bpy.context if not provided)
        face_thickness: Offset along face normals; can be positive (outward) or negative (inward). 0 = no extra points.
        
    Returns:
        list: List of Vector objects representing world-space vertex positions
    """
    if context is None:
        context = bpy.context
    
    all_vertices = []
    
    if not marked_faces_dict:
        return all_vertices
    
    use_thickness = abs(face_thickness) > 1e-6
    
    for obj, face_indices in marked_faces_dict.items():
        if not face_indices or obj.type != 'MESH':
            continue
        
        mesh, obj_matrix_world = get_evaluated_mesh(obj, use_depsgraph=use_depsgraph, context=context)
        mat_3x3 = obj_matrix_world.to_3x3()
        
        # Collect vertices from all marked faces
        for face_idx in face_indices:
            if face_idx >= len(mesh.polygons):
                continue
            
            face = mesh.polygons[face_idx]
            world_verts = [obj_matrix_world @ mesh.vertices[vert_idx].co for vert_idx in face.vertices]
            all_vertices.extend(world_verts)
            
            if use_thickness:
                # Face normal in world space (no translation)
                face_normal = (mat_3x3 @ face.normal).normalized()
                for v in world_verts:
                    all_vertices.append(v + face_normal * face_thickness)
    
    return all_vertices

# ===== SELECTION STATE MANAGEMENT =====

class SelectionState:
    """Context manager for preserving and restoring Blender selection state"""
    
    def __init__(self, context):
        self.context = context
        self.original_selected = list(context.selected_objects)
        self.original_active = context.view_layer.objects.active
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.restore()
        return False
    
    def restore(self):
        """Restore the original selection state"""
        # Restore selection
        for obj in self.original_selected:
            try:
                obj.select_set(True)
            except:
                pass  # Object may have been deleted
        
        # Restore active object
        if self.original_active:
            try:
                self.context.view_layer.objects.active = self.original_active
            except:
                pass  # Object may have been deleted
    
    def deselect_all(self):
        """Deselect all objects"""
        bpy.ops.object.select_all(action='DESELECT')

def preserve_selection_state(context):
    """
    Create a context manager for preserving selection state.
    
    Usage:
        with preserve_selection_state(context) as state:
            state.deselect_all()
            # ... do operations ...
        # Selection is automatically restored
    
    Args:
        context: Blender context
        
    Returns:
        SelectionState: Context manager instance
    """
    return SelectionState(context)

# ===== OBJECT SETUP UTILITIES =====

def move_object_to_cbb_collection(context, obj):
    """
    Move an object to the CBB collection, unlinking from all other collections.
    
    Args:
        context: Blender context
        obj: Object to move
    """
    cbb_coll = ensure_cbb_collection(context)
    
    # Unlink from all existing collections
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    
    # Link to CBB collection
    cbb_coll.objects.link(obj)

def setup_new_object(context, obj, assign_styles=True, move_to_collection=True):
    """
    Set up a newly created object with collection, styles, and common properties.
    
    Args:
        context: Blender context
        obj: Object to set up
        assign_styles: Whether to assign material and color styles
        move_to_collection: Whether to move object to CBB collection
    """
    if move_to_collection:
        move_object_to_cbb_collection(context, obj)
    
    if assign_styles:
        assign_object_styles(context, obj)

def restore_selection_state(context, original_selected, original_active):
    """
    Restore selection state from saved values.
    
    Args:
        context: Blender context
        original_selected: List of originally selected objects
        original_active: Originally active object
    """
    # Restore selection
    for obj in original_selected:
        try:
            obj.select_set(True)
        except:
            pass  # Object may have been deleted
    
    # Restore active object
    if original_active:
        try:
            context.view_layer.objects.active = original_active
        except:
            pass  # Object may have been deleted

# ===== COLLECTION INSTANCE / LINKED ASSET HANDLING =====

def is_collection_instance(obj):
    """
    Check if an object is a collection instance.
    
    Args:
        obj: Object to check
        
    Returns:
        bool: True if object is a collection instance
    """
    return obj and hasattr(obj, 'instance_collection') and obj.instance_collection is not None

def make_collection_instance_real(context, instance_obj, keep_previous_selection=False):
    """
    Make a collection instance real by duplicating and converting it to mesh objects.
    Creates a temporary collection first, then duplicates the instance into it.
    
    Args:
        context: Blender context
        instance_obj: The collection instance object
        keep_previous_selection: If True, don't deselect previously selected objects (for multiple instances)
        
    Returns:
        dict: Contains 'temp_collection', 'real_objects', and 'original_object'
              Returns None if operation fails
    """
    if not is_collection_instance(instance_obj):
        return None
    
    # Store currently selected objects (may include real objects from previous instances)
    previously_selected = list(context.selected_objects) if keep_previous_selection else []
    original_active = context.view_layer.objects.active
    
    try:
        # 1. Create temporary collection FIRST
        temp_coll_name = f"_TEMP_CBB_Instance_{instance_obj.name}"
        temp_collection = bpy.data.collections.new(temp_coll_name)
        context.scene.collection.children.link(temp_collection)
        
        # 2. Deselect all (including previous real objects, we'll reselect them later)
        for obj in context.selected_objects:
            obj.select_set(False)
        
        # 3. Select and activate the instance object
        instance_obj.select_set(True)
        context.view_layer.objects.active = instance_obj
        
        # 4. Duplicate the instance
        bpy.ops.object.duplicate()
        duplicated_obj = context.active_object
        
        # 5. Move the duplicate into temp collection immediately
        for coll in list(duplicated_obj.users_collection):
            coll.objects.unlink(duplicated_obj)
        temp_collection.objects.link(duplicated_obj)
        
        # 6. Make the duplicated instance real with hierarchy
        # This converts the instance to actual mesh objects
        # All created objects will be in the temp collection
        bpy.ops.object.duplicates_make_real(use_base_parent=True, use_hierarchy=True)
        
        # 7. Collect all created real objects (they're now all selected)
        real_objects = list(context.selected_objects)
        
        # 8. Ensure all real objects are in temp collection and nowhere else
        for obj in real_objects:
            # Unlink from any other collections
            for coll in list(obj.users_collection):
                if coll != temp_collection:
                    coll.objects.unlink(obj)
            # Make sure it's in temp collection
            if obj.name not in temp_collection.objects:
                temp_collection.objects.link(obj)
        
        # 9. Re-select previously selected objects (from other instances)
        if keep_previous_selection:
            for obj in previously_selected:
                try:
                    obj.select_set(True)
                except:
                    pass
        
        # Real objects from this instance are already selected from make_real
        # So now all real objects from all instances are selected
        
        # 10. Hide the original instance object
        instance_obj.hide_set(True)
        
        return {
            'temp_collection': temp_collection,
            'real_objects': real_objects,
            'original_object': instance_obj
        }
        
    except Exception as e:
        print(f"Error making collection instance real: {e}")
        # Clean up temp collection if it was created
        if 'temp_collection' in locals():
            try:
                context.scene.collection.children.unlink(temp_collection)
                bpy.data.collections.remove(temp_collection)
            except:
                pass
        # Restore selection even on error
        for obj in context.selected_objects:
            obj.select_set(False)
        if keep_previous_selection:
            for obj in previously_selected:
                try:
                    obj.select_set(True)
                except:
                    pass
        if original_active:
            try:
                context.view_layer.objects.active = original_active
            except:
                pass
        return None

def cleanup_collection_instance_temp(context, instance_data):
    """
    Clean up temporary collection and objects created by make_collection_instance_real.
    Simply deletes the entire temp collection with all its contents.
    
    Args:
        context: Blender context
        instance_data: Dictionary returned by make_collection_instance_real
    """
    if not instance_data:
        return
    
    temp_collection = instance_data.get('temp_collection')
    original_object = instance_data.get('original_object')
    
    # Unhide the original instance object
    if original_object:
        try:
            original_object.hide_set(False)
        except:
            pass
    
    if temp_collection:
        try:
            # Delete all objects in the collection
            # This is cleaner than individually deleting each object
            for obj in list(temp_collection.objects):
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except:
                    pass
            
            # Unlink collection from scene
            if temp_collection.name in context.scene.collection.children:
                context.scene.collection.children.unlink(temp_collection)
            
            # Remove the collection itself
            bpy.data.collections.remove(temp_collection)
        except Exception as e:
            print(f"Error cleaning up temp collection: {e}")
            pass