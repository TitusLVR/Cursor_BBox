import bpy
from ..functions.utils import get_face_edges_from_raycast, select_edge_by_scroll, place_cursor_with_raycast_and_edge, snap_cursor_to_closest_element
from ..functions.core import (
    cursor_aligned_bounding_box,
    enable_edge_highlight_wrapper as enable_edge_highlight,
    disable_edge_highlight_wrapper as disable_edge_highlight,
    enable_bbox_preview_wrapper as enable_bbox_preview,
    disable_bbox_preview_wrapper as disable_bbox_preview
)

class CursorBBox_OT_set_and_fit_box(bpy.types.Operator):
    """Place cursor and create bounding box in one action with edge selection"""
    bl_idname = "cursor_bbox.set_and_fit_box"
    bl_label = "Set & Fit Box"
    bl_description = "Set cursor and immediately fit a Bounding Box"
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
