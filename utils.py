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
    
    depsgraph = context.evaluated_depsgraph_get()
    result, location, normal, face_index, obj, matrix = context.scene.ray_cast(
        depsgraph, ray_origin, view_vector
    )
    
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

def place_cursor_with_raycast_and_edge(context, event, align_to_face=True, edge_index=0):
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
            if prefs and prefs.bbox_preview_enabled:
                # Use default push value from scene or preferences
                push_value = context.scene.cursor_bbox_push if hasattr(context.scene, 'cursor_bbox_push') else 0.01
                update_bbox_preview(face_data['object'], push_value, cursor.location, cursor.rotation_euler)
        except:
            pass  # Ignore errors in preview update
    
    return {
        'success': True,
        'location': location,
        'normal': normal,
        'face_index': face_data['face_index'],
        'object': face_data['object'],
        'aligned_to_face': align_to_face,
        'face_data': face_data
    }