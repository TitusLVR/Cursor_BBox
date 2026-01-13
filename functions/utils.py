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

def get_face_edges_from_raycast_optimized(context, event):
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
        result = _process_raycast_result(*closest_result)
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

def _process_raycast_result(hit, location, normal, face_index, obj, matrix):
    """Process raycast result into face data structure"""
    if not hit or not obj or obj.type != 'MESH':
        return None
    
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

def place_cursor_with_raycast_and_edge_optimized(context, event, align_to_face=True, edge_index=0, preview=True):
    """Optimized cursor placement with caching"""
    from .core import update_edge_highlight, update_bbox_preview
    from ..settings.preferences import get_preferences
    
    face_data = get_face_edges_from_raycast_optimized(context, event)
    
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
        cursor.rotation_euler = rotation_matrix.to_euler()
        
        # Update highlights
        update_edge_highlight([selected_edge['start'], selected_edge['end']])
        
        # Update bbox preview with preference check
        try:
            prefs = get_preferences()
            if preview and prefs and prefs.bbox_preview_enabled:
                push_value = getattr(context.scene, 'cursor_bbox_push', 0.01)
                update_bbox_preview(face_data['object'], push_value, cursor.location, cursor.rotation_euler)
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

@lru_cache(maxsize=16)
def get_snap_elements_cached(obj_name, face_index):
    """Cache snap elements for a specific face"""
    obj = bpy.data.objects.get(obj_name)
    if not obj or obj.type != 'MESH':
        return []
    
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

def snap_cursor_to_closest_element_optimized(context, event, face_data=None):
    """Optimized cursor snapping with caching"""
    region = context.region
    region_3d = context.region_data
    
    mouse_x = event.mouse_region_x
    mouse_y = event.mouse_region_y
    
    closest_point = None
    closest_distance = float('inf')
    closest_type = None
    
    if face_data:
        # Use cached snap elements for the specific face
        elements = get_snap_elements_cached(face_data['object'].name, face_data['face_index'])
        
        for element_type, world_pos in elements:
            screen_pos = view3d_utils.location_3d_to_region_2d(region, region_3d, world_pos)
            if screen_pos:
                screen_distance = ((screen_pos[0] - mouse_x) ** 2 + (screen_pos[1] - mouse_y) ** 2) ** 0.5
                if screen_distance < closest_distance:
                    closest_distance = screen_distance
                    closest_point = world_pos
                    closest_type = element_type
    else:
        # Fall back to all selected objects (original behavior)
        context_hash = get_context_hash()
        selected_objects = get_visible_mesh_objects(context_hash)
        
        if not selected_objects:
            return {'success': False}
        
        depsgraph = context.view_layer.depsgraph
        
        for obj in selected_objects:
            obj_eval = obj.evaluated_get(depsgraph)
            if not obj_eval.data:
                continue
            
            mesh = obj_eval.data
            matrix_world = obj.matrix_world
            
            # Check vertices (sample only if many vertices)
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
    if closest_point and closest_distance < 50:  # 50 pixel threshold
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

def get_face_edges_from_raycast(context, event):
    """Legacy function name - redirects to optimized version"""
    return get_face_edges_from_raycast_optimized(context, event)

def select_edge_by_scroll(face_data, scroll_direction, current_edge_index):
    """Legacy function name - redirects to optimized version"""
    return select_edge_by_scroll_optimized(face_data, scroll_direction, current_edge_index)

def place_cursor_with_raycast_and_edge(context, event, align_to_face=True, edge_index=0, preview=True):
    """Legacy function name - redirects to optimized version"""
    return place_cursor_with_raycast_and_edge_optimized(context, event, align_to_face, edge_index, preview)

def snap_cursor_to_closest_element(context, event, face_data=None):
    """Legacy function name - redirects to optimized version"""
    return snap_cursor_to_closest_element_optimized(context, event, face_data)

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

def get_connected_coplanar_faces(obj, start_face_index, angle_tolerance_radians):
    """Find connected faces that are coplanar within tolerance"""
    if obj.type != 'MESH':
        return set()
    
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