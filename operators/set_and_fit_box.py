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
    
    # Selection state preservation
    original_selected_objects = []  # Original selection at operator start (for exit)
    original_active_object = None
    current_working_selection = []  # Current selection including real objects (for during operator)
    
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
    
    def restore_selection(self, context):
        """Restore original selection state (with original instances, not real objects)."""
        try:
            # Deselect all first
            bpy.ops.object.select_all(action='DESELECT')
            
            # Restore original selection (the instances, not the real objects)
            for obj in self.original_selected_objects:
                if obj and obj.name in bpy.data.objects:
                    obj.select_set(True)
            
            # Restore active object
            if self.original_active_object and self.original_active_object.name in bpy.data.objects:
                context.view_layer.objects.active = self.original_active_object
        except Exception as e:
            print(f"Error restoring selection: {e}")
    
    def restore_working_selection(self, context):
        """Restore current working selection (with real objects during operator)."""
        try:
            # Deselect all first
            bpy.ops.object.select_all(action='DESELECT')
            
            # Restore working selection (includes real objects from instances)
            for obj in self.current_working_selection:
                if obj and obj.name in bpy.data.objects:
                    try:
                        obj.select_set(True)
                    except:
                        pass  # Object might have been deleted
            
            # Set an active object if we have any selected
            if self.current_working_selection:
                for obj in self.current_working_selection:
                    if obj and obj.name in bpy.data.objects:
                        context.view_layer.objects.active = obj
                        break
        except Exception as e:
            print(f"Error restoring working selection: {e}")
    
    def update_working_selection(self, context):
        """Update the current working selection to match context.selected_objects."""
        self.current_working_selection = list(context.selected_objects)
    
    def modal(self, context, event):
        # Update status bar with modal controls
        deps_state = "ON" if self.use_depsgraph else "OFF"
        mode_text = ""
        if self.bbox_mode == 'world':
            mode_text = " [World Preview]"
        elif self.bbox_mode == 'local':
            mode_text = " [Local Preview]"
        context.area.header_text_set(f"LMB: Place Cursor | Alt+Scroll: Select Edge | S: Snap | A: Create All | W: World | Q: Local | D: Depsgraph ({deps_state}){mode_text} | Space: Create | RMB/ESC: Cancel")
        
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
                # Store the targeted object for cursor-aligned mode
                self.preview_target_obj = result['object']
                self.report({'INFO'}, f"Cursor placed on {result['object'].name} (Press Space to create box)")
            else:
                self.report({'WARNING'}, "No surface hit")
                self.preview_target_obj = None
            
            return {'RUNNING_MODAL'}  # Continue modal instead of finishing
        
        elif event.type == 'C' and event.value == 'PRESS':
            # Create bounding box with current cursor settings for selected objects
            # Don't pass target_obj so it uses selected objects instead
            cursor_aligned_bounding_box(self.push_value, use_depsgraph=self.use_depsgraph)
            self.report({'INFO'}, f"Bounding box created for selected objects")
            
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
        
        # Create boxes for ALL selected objects (A)
        elif event.type == 'A' and event.value == 'PRESS':
            # Get selected mesh objects
            all_selected = list(context.selected_objects)
            mesh_objects = [obj for obj in all_selected if obj.type == 'MESH' and obj.data and len(obj.data.vertices) > 0]
            
            if not mesh_objects:
                self.report({'WARNING'}, f"No valid mesh objects selected (total selected: {len(all_selected)})")
                return {'RUNNING_MODAL'}
            
            # Create cursor-aligned box for EACH individual object
            boxes_created = 0
            
            for obj in mesh_objects:
                try:
                    # Create box for this individual object
                    cursor_aligned_bounding_box(self.push_value, target_obj=obj, use_depsgraph=self.use_depsgraph)
                    boxes_created += 1
                except Exception as e:
                    print(f"Error creating box for {obj.name}: {e}")
            
            if boxes_created > 0:
                self.report({'INFO'}, f"Created {boxes_created} cursor-aligned bounding box(es) for all selected")
                # Restore working selection
                self.restore_working_selection(context)
            else:
                self.report({'ERROR'}, "Failed to create any bounding boxes")
            
            return {'RUNNING_MODAL'}
        
        # World Oriented Preview Toggle (W)
        elif event.type == 'W' and event.value == 'PRESS':
            # Toggle world constraint on/off
            if self.bbox_mode == 'world':
                # Turn off
                self.bbox_mode = None
                self.preview_target_obj = None
                from ..functions.core import _state
                _state.current_bbox_data = None
                self.report({'INFO'}, "World-oriented constraint OFF")
                context.area.tag_redraw()
            else:
                # Turn on
                self.bbox_mode = 'world'
                # No need to set preview_target_obj, we'll use whatever is selected when Space is pressed
                self.report({'INFO'}, "World-oriented constraint ON (Press Space to create)")
                context.area.tag_redraw()
            
            return {'RUNNING_MODAL'}
        
        # Local Oriented Preview Toggle (Q)
        elif event.type == 'Q' and event.value == 'PRESS':
            # Toggle local constraint on/off
            if self.bbox_mode == 'local':
                # Turn off
                self.bbox_mode = None
                self.preview_target_obj = None
                from ..functions.core import _state
                _state.current_bbox_data = None
                self.report({'INFO'}, "Local-oriented constraint OFF")
                context.area.tag_redraw()
            else:
                # Turn on
                self.bbox_mode = 'local'
                # No need to set preview_target_obj, we'll use whatever is selected when Space is pressed
                self.report({'INFO'}, "Local-oriented constraint ON (Press Space to create)")
                context.area.tag_redraw()
            
            return {'RUNNING_MODAL'}
        
        # Create box (Space) - W/Q are constraints for both preview and creation
        elif event.type == 'SPACE' and event.value == 'PRESS':
            # Get selected mesh objects
            all_selected = list(context.selected_objects)
            mesh_objects = [obj for obj in all_selected if obj.type == 'MESH' and obj.data and len(obj.data.vertices) > 0]
            
            if not mesh_objects:
                self.report({'WARNING'}, f"No valid mesh objects selected (total selected: {len(all_selected)})")
                return {'RUNNING_MODAL'}
            
            # Create bounding box based on current constraint mode (W/Q)
            if self.bbox_mode == 'world':
                # World-oriented constraint: create for all selected objects
                try:
                    world_oriented_bounding_box(self.push_value, use_depsgraph=self.use_depsgraph)
                    self.report({'INFO'}, f"World-oriented bounding box created for {len(mesh_objects)} object(s)")
                    # Restore working selection
                    self.restore_working_selection(context)
                except Exception as e:
                    self.report({'ERROR'}, f"Failed to create world-oriented box: {str(e)}")
                    print(f"Error: {e}")
                    import traceback
                    traceback.print_exc()
                
                return {'RUNNING_MODAL'}
                
            elif self.bbox_mode == 'local':
                # Local-oriented constraint: create for all selected objects
                try:
                    local_oriented_bounding_box(self.push_value, use_depsgraph=self.use_depsgraph)
                    self.report({'INFO'}, f"Local-oriented bounding box created for {len(mesh_objects)} object(s)")
                    # Restore working selection
                    self.restore_working_selection(context)
                except Exception as e:
                    self.report({'ERROR'}, f"Failed to create local-oriented box: {str(e)}")
                    print(f"Error: {e}")
                    import traceback
                    traceback.print_exc()
                
                return {'RUNNING_MODAL'}
                
            else:
                # No constraint: create cursor-aligned box for the TARGETED object (from last click)
                if not self.preview_target_obj:
                    self.report({'WARNING'}, "No object targeted. Click on an object first.")
                    return {'RUNNING_MODAL'}
                
                try:
                    # Create box for the targeted object only
                    cursor_aligned_bounding_box(self.push_value, target_obj=self.preview_target_obj, use_depsgraph=self.use_depsgraph)
                    self.report({'INFO'}, f"Cursor-aligned bounding box created for {self.preview_target_obj.name}")
                    # Restore working selection
                    self.restore_working_selection(context)
                    # Clear target so user must click again for next box
                    self.preview_target_obj = None
                except Exception as e:
                    self.report({'ERROR'}, f"Failed to create bounding box: {str(e)}")
                    print(f"Error creating box for {self.preview_target_obj.name}: {e}")
                    import traceback
                    traceback.print_exc()
                
                return {'RUNNING_MODAL'}
        
        elif event.type == 'ESC':
            self.bbox_mode = None
            self.preview_target_obj = None
            disable_edge_highlight()
            disable_bbox_preview()
            self.cleanup_all_instances(context)  # Clean up collection instances
            self.restore_selection(context)  # Restore original selection
            context.area.header_text_set(None)  # Clear status bar
            return {'CANCELLED'}

        elif event.type == 'RIGHTMOUSE':
            self.bbox_mode = None
            self.preview_target_obj = None
            disable_edge_highlight()
            disable_bbox_preview()
            self.cleanup_all_instances(context)  # Clean up collection instances
            self.restore_selection(context)  # Restore original selection
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
            
            # Store original selection state (for final restoration on exit)
            self.original_selected_objects = list(context.selected_objects)
            self.original_active_object = context.view_layer.objects.active
            
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
            
            # Update working selection to reflect current state (after instances are made real)
            self.update_working_selection(context)
            
            enable_edge_highlight()
            enable_bbox_preview()
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Active space must be a View3D")
            return {'CANCELLED'}
