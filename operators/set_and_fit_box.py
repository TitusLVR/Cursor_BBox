import bpy
from ..functions.utils import (
    get_face_edges_from_raycast, 
    select_edge_by_scroll, 
    place_cursor_with_raycast_and_edge, 
    snap_cursor_to_closest_element,
    is_collection_instance,
    make_collection_instance_real,
    cleanup_collection_instance_temp
)
from ..functions.core import (
    cursor_aligned_bounding_box,
    world_oriented_bounding_box,
    local_oriented_bounding_box,
    update_world_oriented_bbox_preview,
    update_local_oriented_bbox_preview,
    update_bbox_preview,
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
    use_depsgraph = False
    bbox_mode = None  # None, 'world', 'local', 'cursor'
    preview_target_obj = None
    
    # Collection instance handling
    instance_data = {}  # Dictionary to store instance data per object {obj: instance_data}
    
    def handle_collection_instance(self, context, obj, keep_previous_selection=False):
        """
        Check if object is a collection instance and make it real if needed.
        
        Args:
            context: Blender context
            obj: Object to check
            keep_previous_selection: Whether to keep previously selected objects
            
        Returns:
            Object or list of objects to use for operations
        """
        if is_collection_instance(obj):
            # Make instance real and store data for cleanup
            instance_info = make_collection_instance_real(context, obj, keep_previous_selection)
            if instance_info:
                self.instance_data[obj] = instance_info
                # Return the real objects for processing
                return instance_info['real_objects']
            else:
                self.report({'WARNING'}, f"Failed to make instance real for {obj.name}")
                return None
        return [obj]
    
    def cleanup_all_instances(self, context):
        """Clean up all temporary collection instances."""
        for obj, instance_info in self.instance_data.items():
            cleanup_collection_instance_temp(context, instance_info)
        self.instance_data.clear()
    
    def modal(self, context, event):
        # Update status bar with modal controls
        deps_state = "ON" if self.use_depsgraph else "OFF"
        mode_text = ""
        if self.bbox_mode == 'world':
            mode_text = " [World Preview]"
        elif self.bbox_mode == 'local':
            mode_text = " [Local Preview]"
        context.area.header_text_set(f"LMB: Place Cursor & Create BBox | Alt+Scroll: Select Edge | S: Snap | C: Create BBox | W: World Preview | Q: Local Preview | D: Depsgraph ({deps_state}){mode_text} | Space: Create/Finish | RMB/ESC: Cancel")
        
        # Allow navigation events to pass through
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.shift:
            return {'PASS_THROUGH'}
        if event.type == 'MIDDLEMOUSE':
            return {'PASS_THROUGH'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and (event.ctrl or event.shift):
            return {'PASS_THROUGH'}
        # Allow scroll for navigation (without modifiers)
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and not event.alt and not event.ctrl and not event.shift:
            return {'PASS_THROUGH'}
        
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            result = place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, preview=False, use_depsgraph=self.use_depsgraph)
            
            if result['success']:
                cursor_aligned_bounding_box(self.push_value, result['object'], use_depsgraph=self.use_depsgraph)
                self.report({'INFO'}, f"Cursor placed on {result['object'].name} and bounding box created")
            else:
                self.report({'WARNING'}, "No surface hit")
            
            return {'RUNNING_MODAL'}  # Continue modal instead of finishing
        
        elif event.type == 'C' and event.value == 'PRESS':
            # Create bounding box with current cursor settings
            result = place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, preview=False, use_depsgraph=self.use_depsgraph)
            
            if result['success']:
                cursor_aligned_bounding_box(self.push_value, result['object'], use_depsgraph=self.use_depsgraph)
                self.report({'INFO'}, f"Bounding box created for {result['object'].name}")
            else:
                self.report({'WARNING'}, "No surface hit")
            
            return {'RUNNING_MODAL'}  # Continue modal
        
        elif event.type == 'WHEELUPMOUSE' and event.alt:
            face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
            if face_data:
                self.current_face_data = face_data
                self.current_edge_index = select_edge_by_scroll(
                    face_data, 1, self.current_edge_index
                )
                result = place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, preview=True, use_depsgraph=self.use_depsgraph)
                if result['success']:
                    context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'WHEELDOWNMOUSE' and event.alt:
            face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
            if face_data:
                self.current_face_data = face_data
                self.current_edge_index = select_edge_by_scroll(
                    face_data, -1, self.current_edge_index
                )
                result = place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, preview=True, use_depsgraph=self.use_depsgraph)
                if result['success']:
                    context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'MOUSEMOVE':
            result = place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, preview=True, use_depsgraph=self.use_depsgraph)
            if result['success']:
                self.current_face_data = result['face_data']
            
            # Update preview based on current mode (even if raycast failed, if we have a target)
            if self.bbox_mode == 'world' and self.preview_target_obj:
                update_world_oriented_bbox_preview(self.preview_target_obj, self.push_value, self.use_depsgraph)
                context.area.tag_redraw()
            elif self.bbox_mode == 'local' and self.preview_target_obj:
                update_local_oriented_bbox_preview(self.preview_target_obj, self.push_value, self.use_depsgraph)
                context.area.tag_redraw()
            
            return {'RUNNING_MODAL'}
        
        elif event.type == 'S' and event.value == 'PRESS':
            # Snap cursor to closest vertex, edge midpoint, or face center from current face
            face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
            result = snap_cursor_to_closest_element(context, event, face_data, use_depsgraph=self.use_depsgraph)
            if result['success']:
                if face_data:
                    self.report({'INFO'}, f"Cursor snapped to {result['type']} on {face_data['object'].name} ({result['distance']:.1f}px away)")
                else:
                    self.report({'INFO'}, f"Cursor snapped to {result['type']} ({result['distance']:.1f}px away)")
                context.area.tag_redraw()
            else:
                self.report({'WARNING'}, "No suitable snap target found")
            return {'RUNNING_MODAL'}
        
        # Toggle Depsgraph (D)
        elif event.type == 'D' and event.value == 'PRESS':
            self.use_depsgraph = not self.use_depsgraph
            self.report({'INFO'}, f"Depsgraph: {'ON' if self.use_depsgraph else 'OFF'}")
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        # World Oriented Preview Toggle (W)
        elif event.type == 'W' and event.value == 'PRESS':
            # Toggle off if already in world mode
            if self.bbox_mode == 'world':
                self.bbox_mode = None
                self.preview_target_obj = None
                # Clear preview
                from ..functions.core import _state
                _state.current_bbox_data = None
                self.report({'INFO'}, "World-oriented preview OFF")
                context.area.tag_redraw()
            else:
                # Toggle on - use existing target if available, otherwise get new one
                if self.preview_target_obj and self.bbox_mode:
                    # Switch mode using existing target
                    self.bbox_mode = 'world'
                    update_world_oriented_bbox_preview(self.preview_target_obj, self.push_value, self.use_depsgraph)
                    self.report({'INFO'}, f"World-oriented preview ON for {self.preview_target_obj.name} (Press Space to create)")
                    context.area.tag_redraw()
                else:
                    # Get new target object
                    result = place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, preview=False, use_depsgraph=self.use_depsgraph)
                    
                    if result['success']:
                        self.bbox_mode = 'world'
                        self.preview_target_obj = result['object']
                        update_world_oriented_bbox_preview(result['object'], self.push_value, self.use_depsgraph)
                        self.report({'INFO'}, f"World-oriented preview ON for {result['object'].name} (Press Space to create)")
                        context.area.tag_redraw()
                    else:
                        self.report({'WARNING'}, "No surface hit - cannot enable preview")
            
            return {'RUNNING_MODAL'}
        
        # Local Oriented Preview Toggle (Q)
        elif event.type == 'Q' and event.value == 'PRESS':
            # Toggle off if already in local mode
            if self.bbox_mode == 'local':
                self.bbox_mode = None
                self.preview_target_obj = None
                # Clear preview
                from ..functions.core import _state
                _state.current_bbox_data = None
                self.report({'INFO'}, "Local-oriented preview OFF")
                context.area.tag_redraw()
            else:
                # Toggle on - use existing target if available, otherwise get new one
                if self.preview_target_obj and self.bbox_mode:
                    # Switch mode using existing target
                    self.bbox_mode = 'local'
                    update_local_oriented_bbox_preview(self.preview_target_obj, self.push_value, self.use_depsgraph)
                    self.report({'INFO'}, f"Local-oriented preview ON for {self.preview_target_obj.name} (Press Space to create)")
                    context.area.tag_redraw()
                else:
                    # Get new target object
                    result = place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, preview=False, use_depsgraph=self.use_depsgraph)
                    
                    if result['success']:
                        self.bbox_mode = 'local'
                        self.preview_target_obj = result['object']
                        update_local_oriented_bbox_preview(result['object'], self.push_value, self.use_depsgraph)
                        self.report({'INFO'}, f"Local-oriented preview ON for {result['object'].name} (Press Space to create)")
                        context.area.tag_redraw()
                    else:
                        self.report({'WARNING'}, "No surface hit - cannot enable preview")
            
            return {'RUNNING_MODAL'}
        
        # Create/Finish operator (Space)
        elif event.type == 'SPACE' and event.value == 'PRESS':
            # If we have a preview mode active, create the bounding box
            if self.bbox_mode == 'world' and self.preview_target_obj:
                world_oriented_bounding_box(self.push_value, self.preview_target_obj, use_depsgraph=self.use_depsgraph)
                self.report({'INFO'}, f"World-oriented bounding box created for {self.preview_target_obj.name}")
                self.bbox_mode = None
                self.preview_target_obj = None
                return {'RUNNING_MODAL'}  # Continue modal
            elif self.bbox_mode == 'local' and self.preview_target_obj:
                local_oriented_bounding_box(self.push_value, self.preview_target_obj, use_depsgraph=self.use_depsgraph)
                self.report({'INFO'}, f"Local-oriented bounding box created for {self.preview_target_obj.name}")
                self.bbox_mode = None
                self.preview_target_obj = None
                return {'RUNNING_MODAL'}  # Continue modal
            else:
                # No preview active, finish operator
                disable_edge_highlight()
                disable_bbox_preview()
                context.area.header_text_set(None)  # Clear status bar
                return {'FINISHED'}
        
        elif event.type == 'ESC':
            self.bbox_mode = None
            self.preview_target_obj = None
            disable_edge_highlight()
            disable_bbox_preview()
            self.cleanup_all_instances(context)  # Clean up collection instances
            context.area.header_text_set(None)  # Clear status bar
            return {'CANCELLED'}

        elif event.type == 'RIGHTMOUSE':
            self.bbox_mode = None
            self.preview_target_obj = None
            disable_edge_highlight()
            disable_bbox_preview()
            self.cleanup_all_instances(context)  # Clean up collection instances
            context.area.header_text_set(None)  # Clear status bar
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}
    
    def invoke(self, context, event):
        if context.area.type == 'VIEW_3D':
            self.current_edge_index = 0
            self.current_face_data = None
            self.bbox_mode = None
            self.preview_target_obj = None
            self.instance_data = {}
            
            # Check for collection instances in selected objects
            selected_objects_list = list(context.selected_objects)
            for i, obj in enumerate(selected_objects_list):
                if is_collection_instance(obj):
                    self.report({'INFO'}, f"Processing collection instance: {obj.name}")
                    # Keep previous selection for all instances after the first one
                    keep_previous = (i > 0)
                    real_objs = self.handle_collection_instance(context, obj, keep_previous)
                    if not real_objs:
                        self.report({'WARNING'}, f"Failed to process instance: {obj.name}")
            
            enable_edge_highlight()
            enable_bbox_preview()
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Active space must be a View3D")
            return {'CANCELLED'}
