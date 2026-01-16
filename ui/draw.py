import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from ..settings.preferences import get_preferences
from functools import lru_cache

# ===== GPU DRAWING MANAGER =====

class GPUDrawingManager:
    """Centralized GPU drawing with batch caching"""
    
    def __init__(self):
        self.batch_cache = {}
        self.shader_cache = {}
        self.last_data_hashes = {}
    
    def get_shader(self, shader_type):
        """Get cached shader"""
        if shader_type not in self.shader_cache:
            self.shader_cache[shader_type] = gpu.shader.from_builtin(shader_type)
        return self.shader_cache[shader_type]
    
    def get_cached_batch(self, cache_key, geometry_type, vertices):
        """Get cached GPU batch, create if not exists or data changed"""
        if not vertices:
            return None
            
        # Create hash of vertex data for change detection
        data_hash = hash(tuple(tuple(v) for v in vertices))
        
        # Check if we need to update the batch
        if (cache_key not in self.batch_cache or 
            self.last_data_hashes.get(cache_key) != data_hash):
            
            shader = self.get_shader('UNIFORM_COLOR')
            self.batch_cache[cache_key] = batch_for_shader(
                shader, geometry_type, {"pos": vertices}
            )
            self.last_data_hashes[cache_key] = data_hash
        
        return self.batch_cache[cache_key]
    
    def clear_cache(self):
        """Clear all cached batches"""
        self.batch_cache.clear()
        self.last_data_hashes.clear()
    
    def clear_cache_key(self, cache_key):
        """Clear specific cache entry"""
        if cache_key in self.batch_cache:
            del self.batch_cache[cache_key]
        if cache_key in self.last_data_hashes:
            del self.last_data_hashes[cache_key]
    
    def clear_cache_prefix(self, prefix):
        """Clear all cache entries with a specific prefix"""
        keys_to_remove = [key for key in self.batch_cache.keys() if key.startswith(prefix)]
        for key in keys_to_remove:
            self.clear_cache_key(key)

# ===== GEOMETRY GENERATION =====

@lru_cache(maxsize=32)
def get_cube_indices():
    """Cached cube geometry indices"""
    edge_indices = [
        (0, 1), (1, 2), (2, 3), (3, 0),  # Bottom
        (4, 5), (5, 6), (6, 7), (7, 4),  # Top
        (0, 4), (1, 5), (2, 6), (3, 7)   # Vertical
    ]
    
    face_indices = [
        (0, 1, 2), (2, 3, 0),  # Bottom
        (4, 7, 6), (6, 5, 4),  # Top
        (0, 4, 5), (5, 1, 0),  # Front
        (2, 6, 7), (7, 3, 2),  # Back
        (0, 3, 7), (7, 4, 0),  # Left
        (1, 5, 6), (6, 2, 1)   # Right
    ]
    
    return edge_indices, face_indices

def generate_bbox_geometry_optimized(center, dimensions, rotation_matrix, geometry_cache):
    """Optimized bbox geometry generation with caching"""
    # Create cache key
    cache_key = (
        tuple(center), 
        tuple(dimensions), 
        tuple(tuple(row) for row in rotation_matrix)
    )
    
    if cache_key in geometry_cache:
        return geometry_cache[cache_key]
    
    # Half dimensions
    hx, hy, hz = dimensions.x / 2, dimensions.y / 2, dimensions.z / 2
    
    # Local vertices (cached)
    local_verts = [
        Vector((-hx, -hy, -hz)), Vector(( hx, -hy, -hz)),
        Vector(( hx,  hy, -hz)), Vector((-hx,  hy, -hz)),
        Vector((-hx, -hy,  hz)), Vector(( hx, -hy,  hz)),
        Vector(( hx,  hy,  hz)), Vector((-hx,  hy,  hz))
    ]
    
    # Transform to world space (vectorized)
    world_verts = []
    for v in local_verts:
        rotated = rotation_matrix @ v
        world_pos = center + rotated
        world_verts.append(world_pos)
    
    # Get cached indices
    edge_indices, face_indices = get_cube_indices()
    
    # Create edge vertices
    edge_verts = []
    for i, j in edge_indices:
        edge_verts.extend([world_verts[i], world_verts[j]])
    
    # Create face vertices
    face_verts = []
    for i, j, k in face_indices:
        face_verts.extend([world_verts[i], world_verts[j], world_verts[k]])
    
    result = (edge_verts, face_verts)
    
    # Cache result (limit cache size)
    if len(geometry_cache) > 100:
        # Remove oldest entry
        geometry_cache.pop(next(iter(geometry_cache)))
    
    geometry_cache[cache_key] = result
    return result

# ===== DRAWING FUNCTIONS =====

def draw_edge_highlight(gpu_manager, current_edge_data):
    """Optimized edge highlighting with batch caching"""
    if not current_edge_data:
        return
    
    # Get preferences with fallbacks
    try:
        prefs = get_preferences()
        if prefs:
            color = (*prefs.edge_highlight_color, 1.0)
            width = prefs.edge_highlight_width
        else:
            color = (0.0, 1.0, 0.0, 1.0)
            width = 4.0
    except:
        color = (0.0, 1.0, 0.0, 1.0)
        width = 4.0
    
    # Get cached batch
    batch = gpu_manager.get_cached_batch(
        'edge_highlight', 'LINES', current_edge_data['vertices']
    )
    
    if not batch:
        return
    
    # Set up GPU state
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(width)
    
    # Get shader and draw
    shader = gpu_manager.get_shader('UNIFORM_COLOR')
    shader.uniform_float("color", color)
    batch.draw(shader)
    
    # Reset GPU state
    gpu.state.blend_set('NONE')
    gpu.state.line_width_set(1.0)

def draw_marked_points(gpu_manager, marked_points, base_color):
    """Draw marked points as dots only - SIMPLIFIED VERSION"""
    if not marked_points:
        return
    
    # Make points more visible than faces
    point_color = (base_color[0], base_color[1], base_color[2], min(1.0, base_color[3] + 0.4))
    
    # Draw dots using the point shader
    try:
        point_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        point_shader.uniform_float("color", (point_color[0], point_color[1], point_color[2], 1.0))  # Fully opaque
        
        # Set large point size for visibility
        gpu.state.point_size_set(12.0)  # Large, visible dots
        
        # Create batch for points
        point_batch = batch_for_shader(point_shader, 'POINTS', {"pos": marked_points})
        point_batch.draw(point_shader)
        
        # Reset point size
        gpu.state.point_size_set(1.0)
        
        gpu.state.point_size_set(1.0)
        
    except Exception as e:
        print(f"Error drawing point dots: {e}")


def draw_preview_faces(gpu_manager, preview_faces_visual_cache, show_backfaces=False):
    """Draw preview faces (hover highlight)"""
    if not preview_faces_visual_cache:
        return
        
    # Cyan color for preview, slightly transparent
    preview_color = (0.0, 1.0, 1.0, 0.2)
    
    # Set up GPU state
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('LESS_EQUAL') # Preview can be behind objects slightly, or on top?
    # Let's draw on top like marked faces to be visible
    gpu.state.depth_test_set('ALWAYS')
    
    # Handle backface culling
    if not show_backfaces:
        gpu.state.face_culling_set('BACK')
    else:
        gpu.state.face_culling_set('NONE')
    
    shader = gpu_manager.get_shader('UNIFORM_COLOR')
    shader.uniform_float("color", preview_color)
    
    for obj_name, face_vertices in preview_faces_visual_cache.items():
        if face_vertices:
            batch = gpu_manager.get_cached_batch(
                f'preview_faces_{obj_name}', 'TRIS', face_vertices
            )
            if batch:
                batch.draw(shader)
                
    # Reset GPU state
    gpu.state.blend_set('NONE')
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.face_culling_set('NONE')
def draw_marked_faces(gpu_manager, marked_faces_visual_cache, marked_points, show_backfaces=False, preview_point=None):
    """Optimized face marking with batch caching - draws on top"""
    if not marked_faces_visual_cache and not marked_points and not preview_point:
        return
    
    # Get color from preferences
    try:
        prefs = get_preferences()
        if prefs:
            face_color = (*prefs.face_marking_color, prefs.face_marking_alpha)
        else:
            face_color = (1.0, 0.0, 0.0, 0.3)
    except:
        face_color = (1.0, 0.0, 0.0, 0.3)
    
    # Set up GPU state for elements that should be visible on top
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('ALWAYS')  # Always draw on top
    
    # Handle backface culling
    if not show_backfaces:
        gpu.state.face_culling_set('BACK')
    else:
        gpu.state.face_culling_set('NONE')
    
    shader = gpu_manager.get_shader('UNIFORM_COLOR')
    
    # Draw marked faces
    if marked_faces_visual_cache:
        shader.uniform_float("color", face_color)
        
        for obj_name, face_vertices in marked_faces_visual_cache.items():
            if face_vertices:
                batch = gpu_manager.get_cached_batch(
                    f'marked_faces_{obj_name}', 'TRIS', face_vertices
                )
                if batch:
                    batch.draw(shader)
    
    # Reset culling for points
    gpu.state.face_culling_set('NONE')

    # Draw marked points as dots only
    if marked_points:
        draw_marked_points(gpu_manager, marked_points, face_color)
        
    # Draw preview point if exists (e.g. green)
    if preview_point:
        preview_color = (0.0, 1.0, 0.0, 1.0)
        draw_marked_points(gpu_manager, [preview_point], preview_color)
    
    # Reset GPU state
    gpu.state.blend_set('NONE')
    gpu.state.depth_test_set('LESS_EQUAL')

def draw_bbox_preview(gpu_manager, current_bbox_data, use_culling=False):
    """Optimized bbox preview with batch caching - draws behind marked faces"""
    if not current_bbox_data:
        return
    
    # Get preferences
    try:
        prefs = get_preferences()
        if prefs:
            wireframe_color = (*prefs.bbox_preview_color, prefs.bbox_preview_alpha)
            face_color = (*prefs.bbox_preview_color, prefs.bbox_preview_alpha * 0.2)
            line_width = prefs.bbox_preview_line_width
            show_faces = prefs.bbox_preview_show_faces
        else:
            wireframe_color = (1.0, 1.0, 0.0, 0.8)
            face_color = (1.0, 1.0, 0.0, 0.1)
            line_width = 2.0
            show_faces = True
    except:
        wireframe_color = (1.0, 1.0, 0.0, 0.8)
        face_color = (1.0, 1.0, 0.0, 0.1)
        line_width = 2.0
        show_faces = True
    
    # Set up GPU state - draw behind other elements
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('LESS_EQUAL')  # Normal depth testing
    
    # Handle backface culling
    if use_culling:
        gpu.state.face_culling_set('BACK')
    else:
        gpu.state.face_culling_set('NONE')
    
    shader = gpu_manager.get_shader('UNIFORM_COLOR')
    
    # Draw faces if enabled (behind everything)
    if show_faces and current_bbox_data.get('faces'):
        face_batch = gpu_manager.get_cached_batch(
            'bbox_faces', 'TRIS', current_bbox_data['faces']
        )
        if face_batch:
            shader.uniform_float("color", face_color)
            face_batch.draw(shader)
    
    # Draw wireframe (slightly forward but still behind marked faces)
    if current_bbox_data.get('edges'):
        gpu.state.line_width_set(line_width)
        edge_batch = gpu_manager.get_cached_batch(
            'bbox_edges', 'LINES', current_bbox_data['edges']
        )
        if edge_batch:
            shader.uniform_float("color", wireframe_color)
            edge_batch.draw(shader)
    
    # Reset GPU state
    gpu.state.blend_set('NONE')
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.face_culling_set('NONE')
    gpu.state.line_width_set(1.0)

# ===== HANDLER WRAPPER FUNCTIONS =====

def create_edge_highlight_handler(state):
    """Create edge highlight drawing handler"""
    def draw_edge_highlight_wrapper():
        draw_edge_highlight(state.gpu_manager, state.current_edge_data)
    return draw_edge_highlight_wrapper

def create_face_marking_handler(state):
    """Create face marking drawing handler"""
    def draw_marked_faces_wrapper():
        # Draw preview first (so marked faces draw on top if they overlap)
        if hasattr(state, 'preview_faces_visual_cache'):
             draw_preview_faces(state.gpu_manager, state.preview_faces_visual_cache, show_backfaces=getattr(state, 'show_backfaces', False))
        draw_marked_faces(state.gpu_manager, state.marked_faces_visual_cache, state.marked_points, show_backfaces=getattr(state, 'show_backfaces', False), preview_point=getattr(state, 'preview_point', None))
    return draw_marked_faces_wrapper

def create_bbox_preview_handler(state):
    """Create bbox preview drawing handler"""
    def draw_bbox_preview_wrapper():
        draw_bbox_preview(state.gpu_manager, state.current_bbox_data, use_culling=getattr(state, 'preview_culling', False))
    return draw_bbox_preview_wrapper

# ===== HANDLER MANAGEMENT =====

def enable_edge_highlight(state):
    """Enable edge highlighting"""
    if 'edge_highlight' not in state.handlers:
        handler_func = create_edge_highlight_handler(state)
        state.handlers['edge_highlight'] = bpy.types.SpaceView3D.draw_handler_add(
            handler_func, (), 'WINDOW', 'POST_VIEW'
        )

def disable_edge_highlight(state):
    """Disable edge highlighting"""
    if 'edge_highlight' in state.handlers:
        bpy.types.SpaceView3D.draw_handler_remove(state.handlers['edge_highlight'], 'WINDOW')
        del state.handlers['edge_highlight']
    state.current_edge_data = None

def enable_bbox_preview(state):
    """Enable bounding box preview"""
    if 'bbox_preview' not in state.handlers:
        handler_func = create_bbox_preview_handler(state)
        state.handlers['bbox_preview'] = bpy.types.SpaceView3D.draw_handler_add(
            handler_func, (), 'WINDOW', 'POST_VIEW'
        )

def disable_bbox_preview(state):
    """Disable bounding box preview"""
    if 'bbox_preview' in state.handlers:
        bpy.types.SpaceView3D.draw_handler_remove(state.handlers['bbox_preview'], 'WINDOW')
        del state.handlers['bbox_preview']
    state.current_bbox_data = None

def enable_face_marking(state):
    """Enable face marking display"""
    if 'face_marking' not in state.handlers:
        handler_func = create_face_marking_handler(state)
        state.handlers['face_marking'] = bpy.types.SpaceView3D.draw_handler_add(
            handler_func, (), 'WINDOW', 'POST_VIEW'
        )
        print("Face marking handler enabled")

def disable_face_marking(state):
    """Disable face marking display"""
    if 'face_marking' in state.handlers:
        bpy.types.SpaceView3D.draw_handler_remove(state.handlers['face_marking'], 'WINDOW')
        del state.handlers['face_marking']
        print("Face marking handler disabled")

def ensure_handlers_enabled(state):
    """Ensure all necessary handlers are enabled"""
    # Check if we have marked faces or points and need face marking handler
    if (state.marked_faces or state.marked_points) and 'face_marking' not in state.handlers:
        enable_face_marking(state)
    
    # Check if we need bbox preview
    if (state.current_bbox_data or state.marked_faces or state.marked_points) and 'bbox_preview' not in state.handlers:
        enable_bbox_preview(state)
        
    if getattr(state, 'limitation_plane_matrix', None) and 'limitation_plane' not in state.handlers:
        enable_limitation_plane(state)

def enable_limitation_plane(state):
    """Enable limitation plane drawing"""
    if 'limitation_plane' not in state.handlers:
        handler = create_limitation_plane_handler(state)
        state.handlers['limitation_plane'] = bpy.types.SpaceView3D.draw_handler_add(
            handler, (), 'WINDOW', 'POST_VIEW'
        )

def disable_limitation_plane(state):
    """Disable limitation plane drawing"""
    if 'limitation_plane' in state.handlers:
        bpy.types.SpaceView3D.draw_handler_remove(state.handlers['limitation_plane'], 'WINDOW')
        del state.handlers['limitation_plane']

def refresh_all_handlers(state):
    """Refresh all handlers - useful for recovery from errors"""
    # Disable all first
    state.disable_all_handlers()
    
    # Re-enable based on current state
    if state.current_edge_data:
        enable_edge_highlight(state)
    
    ensure_handlers_enabled(state)

def draw_limitation_plane(gpu_manager, matrix):
    """Draw limitation plane grid"""
    if not matrix:
        return
        
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('LESS_EQUAL')
    
    # Plane color (transparent blue-ish)
    color = (0.2, 0.6, 1.0, 0.15)
    grid_color = (0.3, 0.7, 1.0, 0.4)
    
    shader = gpu_manager.get_shader('UNIFORM_COLOR')
    
    # Draw Grid/Plane
    size = 10.0
    steps = 10
    
    lines = []
    
    def t(x, y):
        return matrix @ Vector((x, y, 0))
    
    for i in range(-steps, steps + 1):
        d = (i / steps) * size
        lines.append(t(-size, d))
        lines.append(t(size, d))
        lines.append(t(d, -size))
        lines.append(t(d, size))
        
    gpu.state.line_width_set(1.0)
    shader.uniform_float("color", grid_color)
    batch = batch_for_shader(shader, 'LINES', {"pos": lines})
    batch.draw(shader)
    
    # Draw Quad
    tris = [
        t(-size, -size), t(size, -size), t(-size, size),
        t(-size, size), t(size, -size), t(size, size)
    ]
    
    shader.uniform_float("color", color)
    gpu.state.face_culling_set('NONE')
    batch_quad = batch_for_shader(shader, 'TRIS', {"pos": tris})
    batch_quad.draw(shader)
    
    gpu.state.blend_set('NONE')
    gpu.state.line_width_set(1.0)
    gpu.state.face_culling_set('BACK')

def create_limitation_plane_handler(state):
    """Create handler for limitation plane"""
    def draw_limitation_plane_wrapper():
        draw_limitation_plane(state.gpu_manager, getattr(state, 'limitation_plane_matrix', None))
    return draw_limitation_plane_wrapper
    if state.current_bbox_data or state.marked_faces or state.marked_points:
        enable_bbox_preview(state)
        
    if state.marked_faces_visual_cache or state.marked_points:
        enable_face_marking(state)