import bpy
import bmesh
from mathutils import Vector
from math import radians, degrees
from ..functions.utils import get_face_edges_from_raycast, select_edge_by_scroll, place_cursor_with_raycast_and_edge, snap_cursor_to_closest_element, get_connected_coplanar_faces, ensure_cbb_collection, ensure_cbb_material, assign_object_styles
from ..functions.core import (
    enable_edge_highlight_wrapper as enable_edge_highlight,
    disable_edge_highlight_wrapper as disable_edge_highlight,
    enable_bbox_preview_wrapper as enable_bbox_preview,
    disable_bbox_preview_wrapper as disable_bbox_preview,
    enable_face_marking_wrapper as enable_face_marking,
    disable_face_marking_wrapper as disable_face_marking,
    mark_face,
    unmark_face,
    clear_marked_faces,
    update_marked_faces_bbox,
    rebuild_marked_faces_visual_data,
    add_marked_point,
    clear_marked_points,
    clear_all_markings,
    update_marked_faces_sphere,
    update_preview_faces,

    clear_preview_faces
)

def create_bounding_sphere_from_marked(marked_faces_dict, marked_points=None):
    """Create a bounding sphere from marked faces and points"""
    context = bpy.context
    all_vertices = []
    
    # Store explicit reference to the original active object and selected objects
    original_active = context.view_layer.objects.active
    original_selected = list(context.selected_objects)
    
    # Collect vertices from marked faces
    if marked_faces_dict:
        for obj, face_indices in marked_faces_dict.items():
            if not face_indices or obj.type != 'MESH':
                continue
            
            mesh = obj.data
            obj_mat_world = obj.matrix_world
            
            for face_idx in face_indices:
                if face_idx < len(mesh.polygons):
                    face = mesh.polygons[face_idx]
                    all_vertices.extend([obj_mat_world @ mesh.vertices[vert_idx].co 
                                       for vert_idx in face.vertices])
    
    # Add marked points
    if marked_points:
        all_vertices.extend(marked_points)
        
    if not all_vertices:
        print("Error: No vertices found in marked faces or points.")
        return False

    # Calculate Center (BBox Center)
    min_co = Vector(all_vertices[0])
    max_co = Vector(all_vertices[0])
    
    for v in all_vertices:
        min_co.x = min(min_co.x, v.x)
        min_co.y = min(min_co.y, v.y)
        min_co.z = min(min_co.z, v.z)
        max_co.x = max(max_co.x, v.x)
        max_co.y = max(max_co.y, v.y)
        max_co.z = max(max_co.z, v.z)
        
    center = (min_co + max_co) / 2.0
    
    # Calculate Radius (Max Distance from Center)
    radius = 0.0
    for v in all_vertices:
        dist = (v - center).length
        if dist > radius:
            radius = dist
            
    # Create Sphere
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=radius,
        enter_editmode=False,
        align='WORLD',
        location=center,
        segments=32,
        ring_count=16
    )
    
    obj = context.active_object
    obj.name = context.scene.cursor_bbox_name_sphere if context.scene.cursor_bbox_name_sphere else "Sphere"
    
    # Move to CBB_Collision collection
    cbb_coll = ensure_cbb_collection(context)
    for coll in obj.users_collection:
        coll.objects.unlink(obj)
    cbb_coll.objects.link(obj)
    
    # Assign Styles
    assign_object_styles(context, obj)
    
    # Handle Selection
    for o in context.selected_objects:
        o.select_set(False)
        
    for o in original_selected:
        try:
            o.select_set(True)
        except:
            pass
            
    obj.select_set(True)
    context.view_layer.objects.active = obj
    
    return True

class CursorBBox_OT_interactive_sphere(bpy.types.Operator):
    """Create bounding sphere from marked faces"""
    bl_idname = "cursor_bbox.interactive_sphere"
    bl_label = "Interactive Sphere"
    bl_description = "Fit a Sphere around marked faces"
    bl_options = {'REGISTER', 'UNDO'}
    
    marked_faces = {}
    marked_points = []
    original_selected_objects = set()
    
    def modal(self, context, event):
        # Update status bar
        has_marked = bool(self.marked_faces)
        has_points = bool(self.marked_points)
        status_text = "Space: Create Sphere"
        if has_marked or has_points:
            parts = []
            if has_marked: parts.append("Faces")
            if has_points: parts.append(f"{len(self.marked_points)} Points")
            status_text += f" | Marked: {', '.join(parts)}"
        
        context.area.header_text_set(
            f"{status_text} | LMB: Mark/Unmark | C: Toggle Coplanar | Shift(+Ctrl)+Scroll: Angle ({int(round(degrees(context.scene.cursor_bbox_coplanar_angle)))}°) | A: Add Point | Z: Clear | RMB/ESC: Cancel"
        )
        
        # Coplanar Angle Adjustment (Shift + Scroll)
        if event.shift and event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            current_deg = degrees(context.scene.cursor_bbox_coplanar_angle)
            step = 1 if event.ctrl else 5
            
            if event.type == 'WHEELUPMOUSE':
                new_angle_deg = current_deg + step
            else:
                new_angle_deg = current_deg - step
                
            new_angle_deg = max(0.0, min(180.0, new_angle_deg))
            context.scene.cursor_bbox_coplanar_angle = radians(new_angle_deg)
            
            self.report({'INFO'}, f"Coplanar Angle: {int(round(new_angle_deg))}°")
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        # Navigation
        if event.type == 'MIDDLEMOUSE' or (event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and not event.shift):
            return {'PASS_THROUGH'}
            
        # Create Sphere (Enter/Space)
        if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and event.value == 'PRESS':
            if self.marked_faces or self.marked_points:
                if create_bounding_sphere_from_marked(self.marked_faces, self.marked_points):
                    self.report({'INFO'}, "Created Bounding Sphere. Ready for new selection.")
                    clear_all_markings()
                    clear_preview_faces()
                    self.marked_faces.clear()
                    self.marked_points.clear()
                    context.area.tag_redraw()
                    return {'RUNNING_MODAL'}
                else:
                    self.report({'WARNING'}, "Failed to create Sphere")
            else:
                self.report({'WARNING'}, "Nothing marked")
            return {'RUNNING_MODAL'}
            
        # Mark Face (LMB or F)
        elif (event.type == 'LEFTMOUSE' and event.value == 'PRESS') or (event.type == 'F' and event.value == 'PRESS'):
            face_data = get_face_edges_from_raycast(context, event)
            if face_data and face_data['object'] in self.original_selected_objects:
                obj = face_data['object']
                face_idx = face_data['face_index']
                
                if obj not in self.marked_faces:
                    self.marked_faces[obj] = set()
                
                # Check if unmarking (if single face is already marked)
                is_unmarking = face_idx in self.marked_faces[obj]
                
                if context.scene.cursor_bbox_select_coplanar:
                     angle_rad = context.scene.cursor_bbox_coplanar_angle
                     coplanar_indices = get_connected_coplanar_faces(obj, face_idx, angle_rad)
                     faces_to_process = coplanar_indices if coplanar_indices else {face_idx}
                else:
                     faces_to_process = {face_idx}

                for idx in faces_to_process:
                    if is_unmarking:
                        if idx in self.marked_faces[obj]:
                            self.marked_faces[obj].remove(idx)
                    else:
                        self.marked_faces[obj].add(idx)
                
                if not self.marked_faces[obj]:
                    del self.marked_faces[obj]
                    rebuild_marked_faces_visual_data(obj, set())
                else:
                    rebuild_marked_faces_visual_data(obj, self.marked_faces[obj])
                
                # Update Preview (Use Sphere preview as it shows extent)
                update_marked_faces_sphere(self.marked_faces, marked_points=self.marked_points)
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
            
        # Toggle Coplanar Selection (C)
        elif event.type == 'C' and event.value == 'PRESS':
            context.scene.cursor_bbox_select_coplanar = not context.scene.cursor_bbox_select_coplanar
            state = "ON" if context.scene.cursor_bbox_select_coplanar else "OFF"
            self.report({'INFO'}, f"Coplanar Selection: {state}")
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
            
        # Add Point (A)
        elif event.type == 'A' and event.value == 'PRESS':
            # Try to get point under mouse
            face_data = get_face_edges_from_raycast(context, event)
            
            if face_data:
                # Use the hit location (intersection point)
                loc = face_data['hit_location']
            else:
                # Fallback to cursor location if no valid hit
                loc = context.scene.cursor.location.copy()
                
            self.marked_points.append(loc)
            add_marked_point(loc)
            update_marked_faces_sphere(self.marked_faces, marked_points=self.marked_points)
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        # Mouse Move - Update Preview (Hover)
        elif event.type == 'MOUSEMOVE':
            face_data = get_face_edges_from_raycast(context, event)
            if face_data and face_data['object'] in self.original_selected_objects:
                obj = face_data['object']
                face_idx = face_data['face_index']
                
                if context.scene.cursor_bbox_select_coplanar:
                     angle_rad = context.scene.cursor_bbox_coplanar_angle
                     coplanar_indices = get_connected_coplanar_faces(obj, face_idx, angle_rad)
                     faces_to_preview = coplanar_indices if coplanar_indices else {face_idx}
                else:
                     faces_to_preview = {face_idx}
                
                update_preview_faces(obj, faces_to_preview)
                context.area.tag_redraw()
            else:
                clear_preview_faces()
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
            
        # Clear (Z)
        elif event.type == 'Z' and event.value == 'PRESS':
            clear_all_markings()
            self.marked_faces.clear()
            self.marked_points.clear()
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
            
        # Cancel
        elif event.type in {'ESC', 'RIGHTMOUSE'}:
            disable_edge_highlight()
            disable_bbox_preview()
            disable_face_marking()
            clear_all_markings()
            clear_preview_faces()
            context.area.header_text_set(None)
            context.area.tag_redraw()
            return {'CANCELLED'}
            
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        if context.area.type == 'VIEW_3D':
            self.marked_faces = {}
            self.marked_points = []
            
            self.original_selected_objects = set(context.selected_objects)
            if context.active_object:
                self.original_selected_objects.add(context.active_object)
                
            clear_preview_faces()
            enable_face_marking()
            enable_edge_highlight()
            enable_bbox_preview()
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Active space must be a View3D")
            return {'CANCELLED'}
