import bpy
from math import radians, degrees
from ..functions.utils import get_face_edges_from_raycast, select_edge_by_scroll, place_cursor_with_raycast_and_edge, snap_cursor_to_closest_element, get_connected_coplanar_faces
from ..functions.core import (
    cursor_aligned_bounding_box,
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
    add_marked_point,
    clear_marked_points,
    clear_all_markings,
    update_preview_faces,
    clear_preview_faces
)

class CursorBBox_OT_interactive_box(bpy.types.Operator):
    """Place cursor and create bounding box with face marking support"""
    bl_idname = "cursor_bbox.interactive_box"
    bl_label = "Interactive Box"
    bl_description = "Fit a Bounding Box around marked faces or active object"
    bl_options = {'REGISTER', 'UNDO'}
    
    push_value: bpy.props.FloatProperty(
        name="Push Value",
        description="How much to push bounding box faces outward",
        default=0.01,
        min=-1.0,
        max=1.0,
        precision=3
    )
    
    align_to_face: bpy.props.BoolProperty(
        name="Align to Face",
        description="Align cursor rotation to face normal",
        default=True
    )
    
    current_edge_index: bpy.props.IntProperty(default=0)
    current_face_data = None
    marked_faces = {}  # Dictionary to store marked faces per object
    marked_points = []  # List to store additional point markers
    original_selected_objects = set()
    
    def modal(self, context, event):
        # Update status bar with modal controls
        has_marked = bool(self.marked_faces)
        has_points = bool(self.marked_points)
        marking_status = ""
        if has_marked or has_points:
            parts = []
            if has_marked:
                parts.append("Faces")
            if has_points:
                parts.append(f"{len(self.marked_points)} Points")
            marking_status = f" | Marked: {', '.join(parts)}"
        
        context.area.header_text_set(
            f"Space: Create BBox{marking_status} | LMB: Mark/Place | Scroll: Edge | Shift+Scroll: Angle ({int(round(degrees(context.scene.cursor_bbox_coplanar_angle)))}°) | "
            f"C: Coplanar | F: Mark | A: Add Point | S: Snap | Z: Clear | RMB/ESC: Cancel"
        )
        

        # Cancel (RMB or Esc)
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            disable_edge_highlight()
            disable_bbox_preview()
            disable_face_marking()
            clear_all_markings()
            clear_preview_faces()
            context.area.header_text_set(None)
            return {'CANCELLED'}

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

        # Toggle Coplanar (C)
        if event.type == 'C' and event.value == 'PRESS':
            context.scene.cursor_bbox_select_coplanar = not context.scene.cursor_bbox_select_coplanar
            state = "ON" if context.scene.cursor_bbox_select_coplanar else "OFF"
            self.report({'INFO'}, f"Coplanar Selection: {state}")
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        # Allow navigation events to pass through
        if event.type in {'MIDDLEMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and (event.ctrl or event.shift):
            return {'PASS_THROUGH'}
        
        # Create BBox (Space/Enter)
        if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and event.value == 'PRESS':
            # Create bounding box based on marked faces and/or points
            if self.marked_faces or self.marked_points:
                # Create bbox from marked faces and points
                cursor_aligned_bounding_box(self.push_value, marked_faces=self.marked_faces, marked_points=self.marked_points)
                
                # Cleanup (partial) - Keep tool active
                clear_all_markings()
                clear_preview_faces()
                self.marked_faces.clear()
                self.marked_points.clear()
                context.area.tag_redraw()
                
                self.report({'INFO'}, "Created Bounding Box. Ready for new selection.")
                return {'RUNNING_MODAL'}
            else:
                # If nothing marked, maybe create on object under cursor? Or do nothing?
                if self.current_face_data:
                     # Create bbox from object under cursor (using current face data from hover)
                     cursor_aligned_bounding_box(self.push_value, self.current_face_data['object'])
                     self.report({'INFO'}, "Created Bounding Box on active object")
                     clear_preview_faces()
                     return {'RUNNING_MODAL'}
                else:
                     self.report({'WARNING'}, "Nothing marked or selected")
            
            return {'RUNNING_MODAL'}
        
        # Mark Face (LMB)
        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # Mark/unmark face under cursor
            face_data = get_face_edges_from_raycast(context, event)
            if face_data and face_data['object'] in self.original_selected_objects:
                obj = face_data['object']
                face_idx = face_data['face_index']
                
                # Also place cursor for feedback (optional, but good for "Place Cursor" tool)
                place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index)
                
                # Initialize object's marked faces if needed
                if obj not in self.marked_faces:
                    self.marked_faces[obj] = set()
                
                # Determine faces to process (Coplanar logic)
                if context.scene.cursor_bbox_select_coplanar:
                     angle_rad = context.scene.cursor_bbox_coplanar_angle
                     coplanar_indices = get_connected_coplanar_faces(obj, face_idx, angle_rad)
                     faces_to_process = coplanar_indices if coplanar_indices else {face_idx}
                else:
                     faces_to_process = {face_idx}

                # Check if we are marking or unmarking based on the clicked face
                # If clicked face is marked, we unmark group. Else mark group.
                is_unmarking = face_idx in self.marked_faces[obj]
                
                for idx in faces_to_process:
                    if is_unmarking:
                        if idx in self.marked_faces[obj]:
                            self.marked_faces[obj].remove(idx)
                    else:
                        self.marked_faces[obj].add(idx)

                # Rebuild visual
                if not self.marked_faces[obj]:
                    del self.marked_faces[obj]
                    unmark_face(obj, face_idx) # This might not clear enough if we did batch unmark? 
                    # use clear and rebuild to be safe
                    clear_marked_faces() # Global clear is too strong if multiple objects
                    rebuild_marked_faces_visual_data(obj, set()) # Clear this obj
                    # But we might have other objects?
                    # rebuild_marked_faces_visual_data handles single obj.
                    
                    # Hack: The utils function mark_face/unmark_face are for single.
                    # We need batch update.
                    # rebuild_marked_faces_visual_data(obj, self.marked_faces.get(obj, set()))
                
                rebuild_marked_faces_visual_data(obj, self.marked_faces.get(obj, set()))
                
                # Update bbox preview based on marked faces and points
                update_marked_faces_bbox(self.marked_faces, self.push_value, 
                                       context.scene.cursor.location, 
                                       context.scene.cursor.rotation_euler,
                                       marked_points=self.marked_points)
                context.area.tag_redraw()
            
            return {'RUNNING_MODAL'}
        
        elif event.type == 'F' and event.value == 'PRESS':
            # Mark/unmark face under cursor
            face_data = get_face_edges_from_raycast(context, event)
            if face_data and face_data['object'] in self.original_selected_objects:
                obj = face_data['object']
                face_idx = face_data['face_index']
                
                # Initialize object's marked faces if needed
                if obj not in self.marked_faces:
                    self.marked_faces[obj] = set()
                
                # Toggle face marking
                if face_idx in self.marked_faces[obj]:
                    self.marked_faces[obj].remove(face_idx)
                    if not self.marked_faces[obj]:
                        del self.marked_faces[obj]
                        # Clear visual data for this object
                        unmark_face(obj, face_idx)
                    else:
                        # Rebuild visual data for remaining marked faces
                        rebuild_marked_faces_visual_data(obj, self.marked_faces[obj])
                    self.report({'INFO'}, f"Unmarked face {face_idx} on {obj.name}")
                else:
                    self.marked_faces[obj].add(face_idx)
                    mark_face(obj, face_idx)
                    self.report({'INFO'}, f"Marked face {face_idx} on {obj.name}")
                
                # Update bbox preview based on marked faces and points
                update_marked_faces_bbox(self.marked_faces, self.push_value, 
                                       context.scene.cursor.location, 
                                       context.scene.cursor.rotation_euler,
                                       marked_points=self.marked_points)
                context.area.tag_redraw()
            
            return {'RUNNING_MODAL'}
        
        elif event.type == 'A' and event.value == 'PRESS':
            # Add point marker at current cursor location
            cursor_location = context.scene.cursor.location.copy()
            self.marked_points.append(cursor_location)
            
            # Also call the global function to ensure handlers
            add_marked_point(cursor_location)
            
            self.report({'INFO'}, f"Added point marker at cursor location ({len(self.marked_points)} total points)")
            
            # Update bbox preview to include the new point
            if self.marked_faces or self.marked_points:
                # Update preview with marked faces and points
                update_marked_faces_bbox(self.marked_faces, self.push_value, 
                                       context.scene.cursor.location, 
                                       context.scene.cursor.rotation_euler,
                                       marked_points=self.marked_points)
            context.area.tag_redraw()
            
            return {'RUNNING_MODAL'}
        
        elif event.type == 'Z' and event.value == 'PRESS':
            # Clear all marked faces and points
            if self.marked_faces or self.marked_points:
                clear_all_markings()  # Clear global state
                clear_preview_faces()
                self.marked_faces.clear()  # Clear local state
                self.marked_faces.clear()  # Clear local state
                self.marked_points.clear()  # Clear local state
                self.report({'INFO'}, "Cleared all marked faces and points")
                # Reset to regular object bbox preview
                result = place_cursor_with_raycast_and_edge(
                    context, event, self.align_to_face, self.current_edge_index
                )
                context.area.tag_redraw()
            
            return {'RUNNING_MODAL'}
        
        elif event.type == 'WHEELUPMOUSE' and not event.shift and not event.ctrl:
            face_data = get_face_edges_from_raycast(context, event)
            if face_data and face_data['object'] in self.original_selected_objects:
                self.current_face_data = face_data
                self.current_edge_index = select_edge_by_scroll(
                    face_data, 1, self.current_edge_index
                )
                result = place_cursor_with_raycast_and_edge(
                    context, event, self.align_to_face, self.current_edge_index
                )
                if result['success']:
                    # Update preview with marked faces and points if any
                    if self.marked_faces or self.marked_points:
                        update_marked_faces_bbox(self.marked_faces, self.push_value,
                                               context.scene.cursor.location,
                                               context.scene.cursor.rotation_euler,
                                               marked_points=self.marked_points)
                    context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'WHEELDOWNMOUSE' and not event.shift and not event.ctrl:
            face_data = get_face_edges_from_raycast(context, event)
            if face_data and face_data['object'] in self.original_selected_objects:
                self.current_face_data = face_data
                self.current_edge_index = select_edge_by_scroll(
                    face_data, -1, self.current_edge_index
                )
                result = place_cursor_with_raycast_and_edge(
                    context, event, self.align_to_face, self.current_edge_index
                )
                if result['success']:
                    # Update preview with marked faces and points if any
                    if self.marked_faces or self.marked_points:
                        update_marked_faces_bbox(self.marked_faces, self.push_value,
                                               context.scene.cursor.location,
                                               context.scene.cursor.rotation_euler,
                                               marked_points=self.marked_points)
                    context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'MOUSEMOVE':
            result = place_cursor_with_raycast_and_edge(
                context, event, self.align_to_face, self.current_edge_index, preview=False
            )
            if result['success'] and result['face_data']['object'] in self.original_selected_objects:
                self.current_face_data = result['face_data']
                
                # Update Preview Faces
                obj = result['face_data']['object']
                face_idx = result['face_data']['face_index']
                
                if context.scene.cursor_bbox_select_coplanar:
                     angle_rad = context.scene.cursor_bbox_coplanar_angle
                     coplanar_indices = get_connected_coplanar_faces(obj, face_idx, angle_rad)
                     faces_to_preview = coplanar_indices if coplanar_indices else {face_idx}
                else:
                     faces_to_preview = {face_idx}
                
                update_preview_faces(obj, faces_to_preview)

                # Update bbox preview - show marked faces and points bbox if any, otherwise object bbox
                if self.marked_faces or self.marked_points:
                    # Update preview with marked faces and points
                    update_marked_faces_bbox(self.marked_faces, self.push_value,
                                           context.scene.cursor.location,
                                           context.scene.cursor.rotation_euler,
                                           marked_points=self.marked_points)
                context.area.tag_redraw()
            else:
                clear_preview_faces()
                self.current_face_data = None
                
            return {'RUNNING_MODAL'}
        
        elif event.type == 'S' and event.value == 'PRESS':
            # Snap cursor to closest vertex, edge midpoint, or face center from current face
            face_data = get_face_edges_from_raycast(context, event)
            result = snap_cursor_to_closest_element(context, event, face_data)
            if result['success'] and (not face_data or face_data['object'] in self.original_selected_objects):
                if face_data:
                    self.report({'INFO'}, f"Cursor snapped to {result['type']} on {face_data['object'].name} ({result['distance']:.1f}px away)")
                else:
                    self.report({'INFO'}, f"Cursor snapped to {result['type']} ({result['distance']:.1f}px away)")
                # Update bbox preview after cursor snap
                if self.marked_faces or self.marked_points:
                    update_marked_faces_bbox(self.marked_faces, self.push_value,
                                           context.scene.cursor.location,
                                           context.scene.cursor.rotation_euler,
                                           marked_points=self.marked_points)
                context.area.tag_redraw()
            else:
                self.report({'WARNING'}, "No suitable snap target found")
            return {'RUNNING_MODAL'}
        

        return {'RUNNING_MODAL'}
    
    def invoke(self, context, event):
        if context.area.type == 'VIEW_3D':
            # Initialize from Scene properties
            self.push_value = context.scene.cursor_bbox_push
            self.align_to_face = context.scene.cursor_bbox_align_face

            self.current_edge_index = 0
            self.current_face_data = None
            self.marked_faces = {}
            self.marked_points = []
            
            # Store original selected objects to restrict interaction
            self.original_selected_objects = set(context.selected_objects)
            if context.active_object:
                self.original_selected_objects.add(context.active_object)
                
            clear_preview_faces()
            enable_edge_highlight()
            enable_bbox_preview()
            enable_face_marking()
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Active space must be a View3D")
            return {'CANCELLED'}
