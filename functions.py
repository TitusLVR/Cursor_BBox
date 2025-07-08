import bpy
import bmesh
from mathutils import Vector
import math
import gpu
import gpu_extras.batch
from gpu_extras.batch import batch_for_shader
from .preferences import get_preferences

# ===== GLOBAL VARIABLES =====
edge_highlight_handler = None
bbox_preview_handler = None
current_edge_data = None
current_bbox_data = None

# ===== GPU DRAWING FUNCTIONS =====

def draw_edge_highlight():
    """Draw highlighted edge using GPU module"""
    global current_edge_data
    
    if current_edge_data is None:
        return
    
    # Get preferences for color and width with fallbacks
    try:
        from .preferences import get_preferences
        prefs = get_preferences()
        if prefs:
            color = (*prefs.edge_highlight_color, 1.0)  # Add alpha
            width = prefs.edge_highlight_width
        else:
            # Fallback values
            color = (0.0, 1.0, 0.0, 1.0)  # Green
            width = 4.0
    except:
        # Fallback values if preferences not available
        color = (0.0, 1.0, 0.0, 1.0)  # Green
        width = 4.0
    
    # Create shader
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
    # Set up GPU state
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(width)
    
    # Create batch for line drawing
    batch = batch_for_shader(shader, 'LINES', {"pos": current_edge_data['vertices']})
    
    # Set color
    shader.uniform_float("color", color)
    
    # Draw the line
    batch.draw(shader)
    
    # Reset GPU state
    gpu.state.blend_set('NONE')
    gpu.state.line_width_set(1.0)

def draw_bbox_preview():
    """Draw bounding box preview using GPU module"""
    global current_bbox_data
    
    if current_bbox_data is None:
        return
    
    # Get preferences for preview settings with fallbacks
    try:
        from .preferences import get_preferences
        prefs = get_preferences()
        if prefs:
            wireframe_color = (*prefs.bbox_preview_color, prefs.bbox_preview_alpha)
            face_color = (*prefs.bbox_preview_color, prefs.bbox_preview_alpha * 0.2)  # More transparent for faces
            line_width = prefs.bbox_preview_line_width
            show_faces = prefs.bbox_preview_show_faces
        else:
            # Fallback values
            wireframe_color = (1.0, 1.0, 0.0, 0.8)  # Yellow
            face_color = (1.0, 1.0, 0.0, 0.1)
            line_width = 2.0
            show_faces = True
    except:
        # Fallback values if preferences not available
        wireframe_color = (1.0, 1.0, 0.0, 0.8)  # Yellow
        face_color = (1.0, 1.0, 0.0, 0.1)
        line_width = 2.0
        show_faces = True
    
    # Create shader
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
    # Set up GPU state
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('LESS_EQUAL')
    
    # Draw faces if enabled
    if show_faces and current_bbox_data.get('faces'):
        face_batch = batch_for_shader(shader, 'TRIS', {"pos": current_bbox_data['faces']})
        shader.uniform_float("color", face_color)
        face_batch.draw(shader)
    
    # Draw wireframe
    if current_bbox_data.get('edges'):
        gpu.state.line_width_set(line_width)
        edge_batch = batch_for_shader(shader, 'LINES', {"pos": current_bbox_data['edges']})
        shader.uniform_float("color", wireframe_color)
        edge_batch.draw(shader)
    
    # Reset GPU state
    gpu.state.blend_set('NONE')
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.line_width_set(1.0)

def generate_bbox_geometry(center, dimensions, rotation_matrix):
    """Generate vertices, edges, and faces for bounding box preview"""
    # Half dimensions
    hx, hy, hz = dimensions.x / 2, dimensions.y / 2, dimensions.z / 2
    
    # Local vertices of the cube
    local_verts = [
        Vector((-hx, -hy, -hz)),  # 0
        Vector(( hx, -hy, -hz)),  # 1
        Vector(( hx,  hy, -hz)),  # 2
        Vector((-hx,  hy, -hz)),  # 3
        Vector((-hx, -hy,  hz)),  # 4
        Vector(( hx, -hy,  hz)),  # 5
        Vector(( hx,  hy,  hz)),  # 6
        Vector((-hx,  hy,  hz)),  # 7
    ]
    
    # Transform vertices to world space
    world_verts = []
    for v in local_verts:
        rotated = rotation_matrix @ v
        world_pos = center + rotated
        world_verts.append(world_pos)
    
    # Edge indices (lines between vertices)
    edge_indices = [
        # Bottom face
        (0, 1), (1, 2), (2, 3), (3, 0),
        # Top face  
        (4, 5), (5, 6), (6, 7), (7, 4),
        # Vertical edges
        (0, 4), (1, 5), (2, 6), (3, 7)
    ]
    
    # Create edge vertices for GPU drawing
    edge_verts = []
    for i, j in edge_indices:
        edge_verts.extend([world_verts[i], world_verts[j]])
    
    # Face indices (triangles)
    face_indices = [
        # Bottom (-Z)
        (0, 1, 2), (2, 3, 0),
        # Top (+Z)  
        (4, 7, 6), (6, 5, 4),
        # Front (-Y)
        (0, 4, 5), (5, 1, 0),
        # Back (+Y)
        (2, 6, 7), (7, 3, 2),
        # Left (-X)
        (0, 3, 7), (7, 4, 0),
        # Right (+X)
        (1, 5, 6), (6, 2, 1)
    ]
    
    # Create face vertices for GPU drawing
    face_verts = []
    for i, j, k in face_indices:
        face_verts.extend([world_verts[i], world_verts[j], world_verts[k]])
    
    return edge_verts, face_verts

def update_bbox_preview(target_obj, push_value, cursor_location, cursor_rotation):
    """Update the bounding box preview data"""
    global current_bbox_data
    
    if not target_obj or target_obj.type != 'MESH':
        current_bbox_data = None
        return
    
    try:
        # Calculate bounding box dimensions similar to the main function
        context = bpy.context
        cursor_rot_mat = cursor_rotation.to_matrix()
        cursor_rot_mat_inv = cursor_rot_mat.inverted()
        
        # Get object vertices in world space
        if context.mode == 'EDIT_MESH' and target_obj == context.active_object:
            # Edit mode - use selected faces
            obj_eval = target_obj.evaluated_get(context.view_layer.depsgraph)
            mesh = obj_eval.data
            bm = bmesh.from_edit_mesh(mesh)
            bm.verts.ensure_lookup_table()

            selected_verts_indices = set()
            for face in bm.faces:
                if face.select:
                    for vert in face.verts:
                        selected_verts_indices.add(vert.index)

            if not selected_verts_indices:
                current_bbox_data = None
                return

            obj_mat_world = target_obj.matrix_world
            world_coords = [obj_mat_world @ bm.verts[i].co for i in selected_verts_indices]
        else:
            # Object mode - use all vertices
            obj_eval = target_obj.evaluated_get(context.view_layer.depsgraph)
            mesh = obj_eval.data
            obj_mat_world = target_obj.matrix_world
            world_coords = [obj_mat_world @ v.co for v in mesh.vertices]
        
        if not world_coords:
            current_bbox_data = None
            return
        
        # Transform to cursor space
        local_coords = [cursor_rot_mat_inv @ (p - cursor_location) for p in world_coords]
        
        # Calculate bounds
        min_co = Vector((math.inf, math.inf, math.inf))
        max_co = Vector((-math.inf, -math.inf, -math.inf))
        
        for lc in local_coords:
            min_co.x = min(min_co.x, lc.x)
            min_co.y = min(min_co.y, lc.y)
            min_co.z = min(min_co.z, lc.z)
            max_co.x = max(max_co.x, lc.x)
            max_co.y = max(max_co.y, lc.y)
            max_co.z = max(max_co.z, lc.z)
        
        # Calculate center and dimensions
        local_center = (min_co + max_co) / 2.0
        dimensions = max_co - min_co
        
        # Apply push value
        epsilon = 0.0001
        dimensions.x = max(dimensions.x, epsilon)
        dimensions.y = max(dimensions.y, epsilon)
        dimensions.z = max(dimensions.z, epsilon)
        
        safe_push_value = float(push_value)
        if safe_push_value > 0 or abs(safe_push_value) * 2 < min(dimensions):
            dimensions.x += 2 * safe_push_value
            dimensions.y += 2 * safe_push_value
            dimensions.z += 2 * safe_push_value
        
        dimensions.x = max(dimensions.x, epsilon)
        dimensions.y = max(dimensions.y, epsilon)
        dimensions.z = max(dimensions.z, epsilon)
        
        # World center
        world_center = cursor_location + (cursor_rot_mat @ local_center)
        
        # Generate preview geometry
        edge_verts, face_verts = generate_bbox_geometry(world_center, dimensions, cursor_rot_mat)
        
        current_bbox_data = {
            'edges': edge_verts,
            'faces': face_verts,
            'center': world_center,
            'dimensions': dimensions
        }
    
    except Exception as e:
        print(f"Error updating bbox preview: {e}")
        current_bbox_data = None

def enable_edge_highlight():
    """Enable edge highlighting"""
    global edge_highlight_handler
    if edge_highlight_handler is None:
        edge_highlight_handler = bpy.types.SpaceView3D.draw_handler_add(
            draw_edge_highlight, (), 'WINDOW', 'POST_VIEW'
        )

def disable_edge_highlight():
    """Disable edge highlighting"""
    global edge_highlight_handler, current_edge_data
    if edge_highlight_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(edge_highlight_handler, 'WINDOW')
        edge_highlight_handler = None
    current_edge_data = None

def disable_bbox_preview():
    """Disable bounding box preview"""
    global bbox_preview_handler, current_bbox_data
    if bbox_preview_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(bbox_preview_handler, 'WINDOW')
        bbox_preview_handler = None
    current_bbox_data = None

def enable_bbox_preview():
    """Enable bounding box preview"""
    global bbox_preview_handler
    if bbox_preview_handler is None:
        bbox_preview_handler = bpy.types.SpaceView3D.draw_handler_add(
            draw_bbox_preview, (), 'WINDOW', 'POST_VIEW'
        )

def disable_bbox_preview():
    """Disable bounding box preview"""
    global bbox_preview_handler, current_bbox_data
    if bbox_preview_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(bbox_preview_handler, 'WINDOW')
        bbox_preview_handler = None
    current_bbox_data = None

def update_edge_highlight(edge_vertices):
    """Update the highlighted edge"""
    global current_edge_data
    current_edge_data = {'vertices': edge_vertices}

# ===== CORE FUNCTIONS =====

def cursor_aligned_bounding_box(push_value, target_obj=None):
    """Create cursor-aligned bounding box with optional target object"""
    context = bpy.context
    obj = target_obj if target_obj else context.active_object
    cursor = context.scene.cursor
    cursor_rotation_mode = context.scene.cursor.rotation_mode
    context.scene.cursor.rotation_mode = 'XYZ'
    
    # Get preferences for bounding box display with fallbacks
    try:
        from .preferences import get_preferences
        prefs = get_preferences()
        if prefs:
            show_wire = prefs.bbox_show_wire
            show_all_edges = prefs.bbox_show_all_edges
        else:
            show_wire = True
            show_all_edges = True
    except:
        # Fallback values if preferences not available
        show_wire = True
        show_all_edges = True
    if obj and obj.type == "MESH":
        # Store original mode and selection state
        original_mode = context.mode
        original_active = context.view_layer.objects.active
        original_selected = [o for o in context.selected_objects]
        
        # Switch to the target object if it's not active
        if obj != original_active:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            if original_mode == 'EDIT_MESH':
                bpy.ops.object.mode_set(mode='EDIT')
        
        if context.mode == 'EDIT_MESH':
            # Edit mode - work with selected faces
            obj_eval = obj.evaluated_get(context.view_layer.depsgraph)
            mesh = obj_eval.data
            bm = bmesh.from_edit_mesh(mesh)
            bm.verts.ensure_lookup_table()

            selected_verts_indices = set()
            selected_face_found = False
            for face in bm.faces:
                if face.select:
                    selected_face_found = True
                    for vert in face.verts:
                        selected_verts_indices.add(vert.index)

            if not selected_face_found:
                print("Error: No faces selected.")
                bmesh.update_edit_mesh(mesh)
                return

            obj_mat_world = obj.matrix_world
            world_coords = [obj_mat_world @ bm.verts[i].co for i in selected_verts_indices]

            if not world_coords:
                print("Error: Could not retrieve vertex coordinates.")
                bmesh.update_edit_mesh(mesh)
                return

            cursor_loc = cursor.location
            cursor_rot_mat = cursor.rotation_euler.to_matrix()
            cursor_rot_mat_inv = cursor_rot_mat.inverted()

            local_coords = [cursor_rot_mat_inv @ (p - cursor_loc) for p in world_coords]

            if not local_coords:
                print("Error: No local coordinates calculated.")
                bmesh.update_edit_mesh(mesh)
                return

            min_co = Vector(( math.inf,  math.inf,  math.inf))
            max_co = Vector((-math.inf, -math.inf, -math.inf))

            for lc in local_coords:
                min_co.x = min(min_co.x, lc.x)
                min_co.y = min(min_co.y, lc.y)
                min_co.z = min(min_co.z, lc.z)
                max_co.x = max(max_co.x, lc.x)
                max_co.y = max(max_co.y, lc.y)
                max_co.z = max(max_co.z, lc.z)

            local_center = (min_co + max_co) / 2.0
            dimensions = max_co - min_co

            epsilon = 0.0001
            dimensions.x = max(dimensions.x, epsilon)
            dimensions.y = max(dimensions.y, epsilon)
            dimensions.z = max(dimensions.z, epsilon)

            safe_push_value = float(push_value)
            if safe_push_value > 0 or abs(safe_push_value) * 2 < min(dimensions):
                dimensions.x += 2 * safe_push_value
                dimensions.y += 2 * safe_push_value
                dimensions.z += 2 * safe_push_value
            else:
                print(f"Warning: Push value ({safe_push_value}) is too large negative, ignored.")

            dimensions.x = max(dimensions.x, epsilon)
            dimensions.y = max(dimensions.y, epsilon)
            dimensions.z = max(dimensions.z, epsilon)

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
            
            # Restore original selection and mode
            obj.select_set(True)
            context.view_layer.objects.active = obj
            if original_mode == 'EDIT_MESH':
                bpy.ops.object.mode_set(mode='EDIT')

        else:
            # Object mode - work with the target object or all selected objects
            if target_obj:
                mesh_objects = [target_obj]
            else:
                selected_objects = context.selected_objects
                mesh_objects = [obj for obj in selected_objects if obj.type == 'MESH']

            original_active = context.view_layer.objects.active
            original_selection_names = [obj.name for obj in mesh_objects]

            all_world_coords = []
            for obj in mesh_objects:
                obj_eval = obj.evaluated_get(context.view_layer.depsgraph)
                mesh = obj_eval.data
                obj_mat_world = obj.matrix_world
                all_world_coords.extend([obj_mat_world @ v.co for v in mesh.vertices])

            if not all_world_coords:
                print("Error: Selected mesh object(s) have no vertices.")
                return

            cursor_loc = cursor.location
            cursor_rot_mat = cursor.rotation_euler.to_matrix()
            cursor_rot_mat_inv = cursor_rot_mat.inverted()

            local_coords = [cursor_rot_mat_inv @ (p - cursor_loc) for p in all_world_coords]

            if not local_coords:
                print("Error: No local coordinates calculated.")
                return

            min_co = Vector(( math.inf,  math.inf,  math.inf))
            max_co = Vector((-math.inf, -math.inf, -math.inf))

            for lc in local_coords:
                min_co.x = min(min_co.x, lc.x)
                min_co.y = min(min_co.y, lc.y)
                min_co.z = min(min_co.z, lc.z)
                max_co.x = max(max_co.x, lc.x)
                max_co.y = max(max_co.y, lc.y)
                max_co.z = max(max_co.z, lc.z)

            local_center = (min_co + max_co) / 2.0
            dimensions = max_co - min_co

            epsilon = 0.000001
            dimensions.x = max(dimensions.x, epsilon)
            dimensions.y = max(dimensions.y, epsilon)
            dimensions.z = max(dimensions.z, epsilon)

            safe_push = float(push_value)
            current_min_dim = min(dimensions)

            if safe_push < 0 and abs(safe_push) * 2 >= current_min_dim:
                print(f"Warning: Negative push value ({safe_push:.4f} BU) too large, would invert dimensions. Clamping push.")
                safe_push = - (current_min_dim / 2.0) * 0.999

            dimensions.x += 2 * safe_push
            dimensions.y += 2 * safe_push
            dimensions.z += 2 * safe_push

            dimensions.x = max(dimensions.x, epsilon)
            dimensions.y = max(dimensions.y, epsilon)
            dimensions.z = max(dimensions.z, epsilon)

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

            # Restore original selection
            for obj_name in original_selection_names:
                obj = bpy.data.objects.get(obj_name)
                if obj:
                    obj.select_set(True)

            if original_active and original_active.name in original_selection_names:
                context.view_layer.objects.active = original_active
            elif original_selection_names:
                first_obj = bpy.data.objects.get(original_selection_names[0])
                if first_obj:
                    context.view_layer.objects.active = first_obj

    context.scene.cursor.rotation_mode = cursor_rotation_mode