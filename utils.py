import bpy
import bmesh
from mathutils import Vector, Matrix
from bpy_extras import view3d_utils

def get_face_edges_from_raycast(context, event):
    """Get all edges of the face hit by raycast"""
    region = context.region
    region_3d = context.region_data
    
    mouse_x = event.mouse_region_x
    mouse_y = event.mouse_region_y
    
    view_vector = view3d_utils.region_2d_to_vector_3d(region, region_3d, (mouse_x, mouse_y))
    ray_origin = view3d_utils.region_2d_to_origin_3d(region, region_3d, (mouse_x, mouse_y))
    
    # Get only selected mesh objects for raycast
    selected_objects = []
    
    for obj in context.selected_objects:
        # Only work with selected mesh objects
        if obj.type != 'MESH':
            continue
            
        # Make sure object is visible (basic check)
        if not obj.visible_get(view_layer=context.view_layer):
            continue
        
        selected_objects.append(obj)
    
    # If no selected mesh objects, return None
    if not selected_objects:
        return None
    
    # Try raycast on each selected object and find the closest hit
    closest_result = None
    closest_distance = float('inf')
    
    depsgraph = context.view_layer.depsgraph
    
    for obj in selected_objects:
        # Get object's evaluated mesh
        obj_eval = obj.evaluated_get(depsgraph)
        if not obj_eval.data:
            continue
            
        # Transform ray to object space
        matrix_inv = obj.matrix_world.inverted()
        ray_origin_local = matrix_inv @ ray_origin
        ray_direction_local = matrix_inv.to_3x3() @ view_vector
        
        # Perform raycast on object
        result, location_local, normal_local, face_index = obj_eval.ray_cast(
            ray_origin_local, ray_direction_local
        )
        
        if result:
            # Transform results back to world space
            location_world = obj.matrix_world @ location_local
            normal_world = (obj.matrix_world.to_3x3() @ normal_local).normalized()
            
            # Check if this hit is closer than previous hits
            distance = (location_world - ray_origin).length
            if distance < closest_distance:
                closest_distance = distance
                closest_result = (True, location_world, normal_world, face_index, obj, obj.matrix_world)
    
    if closest_result:
        result, location, normal, face_index, obj, matrix = closest_result
    else:
        return None
    
    if not result or not obj or obj.type != 'MESH':
        return None
    
    # Use the original object's mesh data (not evaluated) to match face indices
    mesh = obj.data
    
    # Ensure face_index is within bounds
    if face_index >= len(mesh.polygons):
        print(f"Warning: Face index {face_index} out of range for mesh with {len(mesh.polygons)} faces")
        return None
    
    # Get face edges
    face = mesh.polygons[face_index]
    face_edges = []
    
    for edge_key in face.edge_keys:
        edge_start = obj.matrix_world @ mesh.vertices[edge_key[0]].co
        edge_end = obj.matrix_world @ mesh.vertices[edge_key[1]].co
        edge_vector = (edge_end - edge_start).normalized()
        edge_center = (edge_start + edge_end) / 2
        
        face_edges.append({
            'start': edge_start,
            'end': edge_end,
            'center': edge_center,
            'vector': edge_vector,
            'length': (edge_end - edge_start).length
        })
    
    return {
        'face_index': face_index,
        'face_normal': normal,
        'face_center': location,
        'edges': face_edges,
        'object': obj
    }

def select_edge_by_scroll(face_data, scroll_direction, current_edge_index):
    """Select edge based on scroll direction"""
    if not face_data or not face_data['edges']:
        return 0
    
    edge_count = len(face_data['edges'])
    
    if scroll_direction > 0:  # Scroll up
        return (current_edge_index + 1) % edge_count
    else:  # Scroll down
        return (current_edge_index - 1) % edge_count

def place_cursor_with_raycast_and_edge(context, event, align_to_face=True, edge_index=0, preview=True):
    """Places and orients the 3D cursor based on mouse raycast with edge alignment"""
    from .functions import update_edge_highlight, update_bbox_preview
    from .preferences import get_preferences
    
    face_data = get_face_edges_from_raycast(context, event)
    
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
        # Clamp edge index to valid range
        edge_index = max(0, min(edge_index, len(face_data['edges']) - 1))
        selected_edge = face_data['edges'][edge_index]
        
        # Z-axis is the face normal
        z_axis = normal.normalized()
        
        # X-axis is the edge direction
        x_axis = selected_edge['vector'].normalized()
        
        # Y-axis is perpendicular to both
        y_axis = z_axis.cross(x_axis).normalized()
        
        # Ensure right-handed coordinate system
        if x_axis.dot(y_axis.cross(z_axis)) < 0:
            y_axis = -y_axis
        
        rotation_matrix = Matrix((x_axis, y_axis, z_axis)).transposed()
        cursor.rotation_euler = rotation_matrix.to_euler()
        
        # Update edge highlight
        update_edge_highlight([selected_edge['start'], selected_edge['end']])
        
        # Update bbox preview if enabled
        try:
            prefs = get_preferences()
            if preview and prefs and prefs.bbox_preview_enabled:
                push_value = context.scene.cursor_bbox_push if hasattr(context.scene, 'cursor_bbox_push') else 0.01
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

def snap_cursor_to_closest_element(context, event, face_data=None):
    """Snap cursor to closest vertex, edge midpoint, or face center from the specified face"""
    region = context.region
    region_3d = context.region_data
    
    mouse_x = event.mouse_region_x
    mouse_y = event.mouse_region_y
    
    # If no face_data provided, fall back to searching all selected objects
    if not face_data:
        # Get selected mesh objects
        selected_objects = []
        for obj in context.selected_objects:
            if obj.type == 'MESH' and obj.visible_get(view_layer=context.view_layer):
                selected_objects.append(obj)
        
        if not selected_objects:
            return {'success': False}
    else:
        # Use only the object and face from face_data
        selected_objects = [face_data['object']]
    
    closest_point = None
    closest_distance = float('inf')
    closest_type = None  # 'vertex', 'edge', or 'face'
    
    depsgraph = context.view_layer.depsgraph
    
    for obj in selected_objects:
        obj_eval = obj.evaluated_get(depsgraph)
        if not obj_eval.data:
            continue
        
        mesh = obj_eval.data
        matrix_world = obj.matrix_world
        
        if face_data and obj == face_data['object']:
            # Only check elements from the specific face
            face_index = face_data['face_index']
            if face_index >= len(mesh.polygons):
                continue
                
            face = mesh.polygons[face_index]
            
            # Check face vertices only
            for vert_idx in face.vertices:
                vert = mesh.vertices[vert_idx]
                world_pos = matrix_world @ vert.co
                # Project to screen space to check distance from mouse
                screen_pos = view3d_utils.location_3d_to_region_2d(region, region_3d, world_pos)
                if screen_pos:
                    screen_distance = ((screen_pos[0] - mouse_x) ** 2 + (screen_pos[1] - mouse_y) ** 2) ** 0.5
                    if screen_distance < closest_distance:
                        closest_distance = screen_distance
                        closest_point = world_pos
                        closest_type = 'vertex'
            
            # Check face edges only (edges that belong to this face)
            for edge_idx in face.edge_keys:
                # edge_keys gives us vertex index pairs for the face edges
                vert1 = mesh.vertices[edge_idx[0]]
                vert2 = mesh.vertices[edge_idx[1]]
                midpoint_local = (vert1.co + vert2.co) / 2
                world_pos = matrix_world @ midpoint_local
                
                # Project to screen space to check distance from mouse
                screen_pos = view3d_utils.location_3d_to_region_2d(region, region_3d, world_pos)
                if screen_pos:
                    screen_distance = ((screen_pos[0] - mouse_x) ** 2 + (screen_pos[1] - mouse_y) ** 2) ** 0.5
                    if screen_distance < closest_distance:
                        closest_distance = screen_distance
                        closest_point = world_pos
                        closest_type = 'edge'
            
            # Check face center
            face_center_local = face.center
            world_pos = matrix_world @ face_center_local
            
            # Project to screen space to check distance from mouse
            screen_pos = view3d_utils.location_3d_to_region_2d(region, region_3d, world_pos)
            if screen_pos:
                screen_distance = ((screen_pos[0] - mouse_x) ** 2 + (screen_pos[1] - mouse_y) ** 2) ** 0.5
                if screen_distance < closest_distance:
                    closest_distance = screen_distance
                    closest_point = world_pos
                    closest_type = 'face'
        else:
            # Original behavior - check all vertices, edges, and faces
            # Check vertices
            for vert in mesh.vertices:
                world_pos = matrix_world @ vert.co
                # Project to screen space to check distance from mouse
                screen_pos = view3d_utils.location_3d_to_region_2d(region, region_3d, world_pos)
                if screen_pos:
                    screen_distance = ((screen_pos[0] - mouse_x) ** 2 + (screen_pos[1] - mouse_y) ** 2) ** 0.5
                    if screen_distance < closest_distance:
                        closest_distance = screen_distance
                        closest_point = world_pos
                        closest_type = 'vertex'
            
            # Check edge midpoints
            for edge in mesh.edges:
                vert1 = mesh.vertices[edge.vertices[0]]
                vert2 = mesh.vertices[edge.vertices[1]]
                midpoint_local = (vert1.co + vert2.co) / 2
                world_pos = matrix_world @ midpoint_local
                
                # Project to screen space to check distance from mouse
                screen_pos = view3d_utils.location_3d_to_region_2d(region, region_3d, world_pos)
                if screen_pos:
                    screen_distance = ((screen_pos[0] - mouse_x) ** 2 + (screen_pos[1] - mouse_y) ** 2) ** 0.5
                    if screen_distance < closest_distance:
                        closest_distance = screen_distance
                        closest_point = world_pos
                        closest_type = 'edge'
            
            # Check face centers
            for face in mesh.polygons:
                face_center_local = face.center
                world_pos = matrix_world @ face_center_local
                
                # Project to screen space to check distance from mouse
                screen_pos = view3d_utils.location_3d_to_region_2d(region, region_3d, world_pos)
                if screen_pos:
                    screen_distance = ((screen_pos[0] - mouse_x) ** 2 + (screen_pos[1] - mouse_y) ** 2) ** 0.5
                    if screen_distance < closest_distance:
                        closest_distance = screen_distance
                        closest_point = world_pos
                        closest_type = 'face'
    
    if closest_point and closest_distance < 50:  # 50 pixel threshold
        # Set cursor location
        context.scene.cursor.location = closest_point
        return {
            'success': True,
            'location': closest_point,
            'type': closest_type,
            'distance': closest_distance
        }
    
    return {'success': False}