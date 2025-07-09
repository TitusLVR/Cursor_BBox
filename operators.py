import bpy
import bmesh
from mathutils import Vector
from .utils import get_face_edges_from_raycast, select_edge_by_scroll, place_cursor_with_raycast_and_edge, snap_cursor_to_closest_element
from .functions import (
    cursor_aligned_bounding_box, 
    enable_edge_highlight, 
    disable_edge_highlight, 
    enable_bbox_preview, 
    disable_bbox_preview,
    enable_face_marking,
    disable_face_marking,
    mark_face,
    unmark_face,
    clear_marked_faces,
    update_marked_faces_bbox,
    rebuild_marked_faces_visual_data
)

class VIEW3D_OT_cursor_place_raycast(bpy.types.Operator):
    """Place cursor with raycast on mouse click with edge selection"""
    bl_idname = "view3d.cursor_place_raycast"
    bl_label = "Place Cursor with Raycast"
    bl_description = "Click to place cursor at surface position with face and edge alignment"
    bl_options = {'REGISTER', 'UNDO'}
    
    align_to_face: bpy.props.BoolProperty(
        name="Align to Face",
        description="Align cursor rotation to face normal",
        default=True
    )
    
    current_edge_index: bpy.props.IntProperty(default=0)
    current_face_data = None
    
    def modal(self, context, event):
        # Update status bar with modal controls
        context.area.header_text_set("LMB: Place Cursor | Scroll: Select Edge | S: Snap to Face Element | RMB/ESC: Cancel")
        
        # Allow navigation events to pass through
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.shift:
            return {'PASS_THROUGH'}
        if event.type == 'MIDDLEMOUSE':
            return {'PASS_THROUGH'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and (event.ctrl or event.shift):
            return {'PASS_THROUGH'}
        
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            result = place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, preview=False)
            
            if result['success']:
                self.report({'INFO'}, f"Cursor placed on {result['object'].name}")
            else:
                self.report({'WARNING'}, "No surface hit")
            
            disable_edge_highlight()
            disable_bbox_preview()
            context.area.header_text_set(None)  # Clear status bar
            return {'FINISHED'}
        
        elif event.type == 'WHEELUPMOUSE' and not event.shift and not event.ctrl:
            # Get face data first
            face_data = get_face_edges_from_raycast(context, event)
            if face_data:
                self.current_face_data = face_data
                self.current_edge_index = select_edge_by_scroll(
                    face_data, 1, self.current_edge_index
                )
                # Update cursor and highlight
                result = place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, preview=False)
                if result['success']:
                    context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'WHEELDOWNMOUSE' and not event.shift and not event.ctrl:
            # Get face data first
            face_data = get_face_edges_from_raycast(context, event)
            if face_data:
                self.current_face_data = face_data
                self.current_edge_index = select_edge_by_scroll(
                    face_data, -1, self.current_edge_index
                )
                # Update cursor and highlight
                result = place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, preview=False)
                if result['success']:
                    context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'MOUSEMOVE':
            # Update preview as mouse moves
            result = place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, preview=False)
            if result['success']:
                self.current_face_data = result['face_data']
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'S' and event.value == 'PRESS':
            # Snap cursor to closest vertex, edge midpoint, or face center from current face
            face_data = get_face_edges_from_raycast(context, event)
            result = snap_cursor_to_closest_element(context, event, face_data)
            if result['success']:
                if face_data:
                    self.report({'INFO'}, f"Cursor snapped to {result['type']} on {face_data['object'].name} ({result['distance']:.1f}px away)")
                else:
                    self.report({'INFO'}, f"Cursor snapped to {result['type']} ({result['distance']:.1f}px away)")
                context.area.tag_redraw()
            else:
                self.report({'WARNING'}, "No suitable snap target found")
            return {'RUNNING_MODAL'}
        
        elif event.type in {'ESC', 'RIGHTMOUSE'}:
            disable_edge_highlight()
            disable_bbox_preview()
            context.area.header_text_set(None)  # Clear status bar
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}
    
    def invoke(self, context, event):
        if context.area.type == 'VIEW_3D':
            self.current_edge_index = 0
            self.current_face_data = None
            enable_edge_highlight()
            enable_bbox_preview()
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Active space must be a View3D")
            return {'CANCELLED'}


class VIEW3D_OT_cursor_place_and_bbox_with_marking(bpy.types.Operator):
    """Place cursor and create bounding box with face marking support"""
    bl_idname = "view3d.cursor_place_and_bbox_marking"
    bl_label = "Place Cursor and Create BBox with Face Marking"
    bl_description = "Click to place cursor with edge alignment, mark faces with F, and create bounding box"
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
            f"LMB: Create BBox{marking_status} | Scroll: Select Edge | "
            f"F: Mark/Unmark Face | A: Add Point | S: Snap to Face Element | Z: Clear All | RMB/ESC: Cancel"
        )
        
        # Allow navigation events to pass through
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.shift:
            return {'PASS_THROUGH'}
        if event.type == 'MIDDLEMOUSE':
            return {'PASS_THROUGH'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and (event.ctrl or event.shift):
            return {'PASS_THROUGH'}
        
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            result = place_cursor_with_raycast_and_edge(
                context, event, self.align_to_face, self.current_edge_index, preview=False
            )
            
            if result['success']:
                # Create bounding box based on marked faces and/or points
                if self.marked_faces or self.marked_points:
                    # Create bbox from marked faces and points
                    cursor_aligned_bounding_box(self.push_value, marked_faces=self.marked_faces, marked_points=self.marked_points)
                    face_count = sum(len(faces) for faces in self.marked_faces.values())
                    point_count = len(self.marked_points)
                    parts = []
                    if face_count > 0:
                        parts.append(f"{face_count} faces")
                    if point_count > 0:
                        parts.append(f"{point_count} points")
                    self.report({'INFO'}, f"Bounding box created from {', '.join(parts)}")
                else:
                    # Create bbox from object under cursor
                    cursor_aligned_bounding_box(self.push_value, result['object'])
                    self.report({'INFO'}, f"Cursor placed on {result['object'].name} and bounding box created")
            else:
                self.report({'WARNING'}, "No surface hit")
            
            return {'RUNNING_MODAL'}  # Continue modal instead of finishing
        
        elif event.type == 'F' and event.value == 'PRESS':
            # Mark/unmark face under cursor
            face_data = get_face_edges_from_raycast(context, event)
            if face_data:
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
                clear_marked_faces()
                self.marked_faces.clear()
                self.marked_points.clear()
                self.report({'INFO'}, "Cleared all marked faces and points")
                # Reset to regular object bbox preview
                result = place_cursor_with_raycast_and_edge(
                    context, event, self.align_to_face, self.current_edge_index
                )
                context.area.tag_redraw()
            
            return {'RUNNING_MODAL'}
        
        elif event.type == 'WHEELUPMOUSE' and not event.shift and not event.ctrl:
            face_data = get_face_edges_from_raycast(context, event)
            if face_data:
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
            if face_data:
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
            if result['success']:
                self.current_face_data = result['face_data']
                # Update bbox preview - show marked faces and points bbox if any, otherwise object bbox
                if self.marked_faces or self.marked_points:
                    # Update preview with marked faces and points
                    update_marked_faces_bbox(self.marked_faces, self.push_value,
                                           context.scene.cursor.location,
                                           context.scene.cursor.rotation_euler,
                                           marked_points=self.marked_points)
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'S' and event.value == 'PRESS':
            # Snap cursor to closest vertex, edge midpoint, or face center from current face
            face_data = get_face_edges_from_raycast(context, event)
            result = snap_cursor_to_closest_element(context, event, face_data)
            if result['success']:
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
        
        elif event.type in {'ESC', 'RIGHTMOUSE'}:
            disable_edge_highlight()
            disable_bbox_preview()
            disable_face_marking()
            clear_marked_faces()
            context.area.header_text_set(None)  # Clear status bar
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}
    
    def invoke(self, context, event):
        if context.area.type == 'VIEW_3D':
            self.current_edge_index = 0
            self.current_face_data = None
            self.marked_faces = {}
            self.marked_points = []
            enable_edge_highlight()
            enable_bbox_preview()
            enable_face_marking()
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Active space must be a View3D")
            return {'CANCELLED'}


class VIEW3D_OT_cursor_place_and_bbox(bpy.types.Operator):
    """Place cursor and create bounding box in one action with edge selection"""
    bl_idname = "view3d.cursor_place_and_bbox"
    bl_label = "Place Cursor and Create BBox"
    bl_description = "Click to place cursor with edge alignment and automatically create cursor-aligned bounding box"
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
    
    def modal(self, context, event):
        # Update status bar with modal controls
        context.area.header_text_set("LMB: Place Cursor & Create BBox | Scroll: Select Edge | S: Snap to Face Element | C: Create BBox | RMB/ESC: Cancel")
        
        # Allow navigation events to pass through
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.shift:
            return {'PASS_THROUGH'}
        if event.type == 'MIDDLEMOUSE':
            return {'PASS_THROUGH'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and (event.ctrl or event.shift):
            return {'PASS_THROUGH'}
        
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            result = place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, preview=False)
            
            if result['success']:
                cursor_aligned_bounding_box(self.push_value, result['object'])
                self.report({'INFO'}, f"Cursor placed on {result['object'].name} and bounding box created")
            else:
                self.report({'WARNING'}, "No surface hit")
            
            return {'RUNNING_MODAL'}  # Continue modal instead of finishing
        
        elif event.type == 'C' and event.value == 'PRESS':
            # Create bounding box with current cursor settings
            result = place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, preview=False)
            
            if result['success']:
                cursor_aligned_bounding_box(self.push_value, result['object'])
                self.report({'INFO'}, f"Bounding box created for {result['object'].name}")
            else:
                self.report({'WARNING'}, "No surface hit")
            
            return {'RUNNING_MODAL'}  # Continue modal
        
        elif event.type == 'WHEELUPMOUSE' and not event.shift and not event.ctrl:
            face_data = get_face_edges_from_raycast(context, event)
            if face_data:
                self.current_face_data = face_data
                self.current_edge_index = select_edge_by_scroll(
                    face_data, 1, self.current_edge_index
                )
                result = place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, preview=True)
                if result['success']:
                    context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'WHEELDOWNMOUSE' and not event.shift and not event.ctrl:
            face_data = get_face_edges_from_raycast(context, event)
            if face_data:
                self.current_face_data = face_data
                self.current_edge_index = select_edge_by_scroll(
                    face_data, -1, self.current_edge_index
                )
                result = place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, preview=True)
                if result['success']:
                    context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'MOUSEMOVE':
            result = place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, preview=True)
            if result['success']:
                self.current_face_data = result['face_data']
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'S' and event.value == 'PRESS':
            # Snap cursor to closest vertex, edge midpoint, or face center from current face
            face_data = get_face_edges_from_raycast(context, event)
            result = snap_cursor_to_closest_element(context, event, face_data)
            if result['success']:
                if face_data:
                    self.report({'INFO'}, f"Cursor snapped to {result['type']} on {face_data['object'].name} ({result['distance']:.1f}px away)")
                else:
                    self.report({'INFO'}, f"Cursor snapped to {result['type']} ({result['distance']:.1f}px away)")
                context.area.tag_redraw()
            else:
                self.report({'WARNING'}, "No suitable snap target found")
            return {'RUNNING_MODAL'}
        
        elif event.type in {'ESC', 'RIGHTMOUSE'}:
            disable_edge_highlight()
            disable_bbox_preview()
            context.area.header_text_set(None)  # Clear status bar
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}
    
    def invoke(self, context, event):
        if context.area.type == 'VIEW_3D':
            self.current_edge_index = 0
            self.current_face_data = None
            enable_edge_highlight()
            enable_bbox_preview()
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Active space must be a View3D")
            return {'CANCELLED'}


class VIEW3D_OT_create_cursor_bbox(bpy.types.Operator):
    """Create cursor-aligned bounding box"""
    bl_idname = "view3d.create_cursor_bbox"
    bl_label = "Create Cursor-Aligned BBox"
    bl_description = "Create bounding box aligned to current cursor position and rotation"
    bl_options = {'REGISTER', 'UNDO'}
    
    push_value: bpy.props.FloatProperty(
        name="Push Value",
        description="How much to push bounding box faces outward",
        default=0.01,
        min=-1.0,
        max=1.0,
        precision=3
    )
    
    def execute(self, context):
        cursor_aligned_bounding_box(self.push_value)
        self.report({'INFO'}, "Cursor-aligned bounding box created")
        return {'FINISHED'}