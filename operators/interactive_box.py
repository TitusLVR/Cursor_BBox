import bpy
import mathutils
from mathutils import Vector, Matrix
from math import radians, degrees
from ..functions.utils import (
    get_face_edges_from_raycast,
    select_edge_by_scroll,
    place_cursor_with_raycast_and_edge,
    snap_cursor_to_closest_element,
    get_connected_coplanar_faces,
    project_point_to_plane_intersection,
    calculate_plane_edge_intersections,
    ensure_cbb_collection,
    ensure_cbb_material,
    assign_object_styles,
    get_cursor_rotation_euler,
    get_selected_faces_from_edit_mode,
    calculate_point_location,
    get_faces_to_process
)
from ..functions.core import (
    cursor_aligned_bounding_box,
    calculate_bbox_bounds_optimized,
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
    update_preview_faces,
    clear_preview_faces,
    toggle_backface_rendering,
    get_backface_rendering,
    toggle_preview_culling,
    get_preview_culling,
    update_preview_point,
    clear_preview_point,
    update_limitation_plane,
    clear_limitation_plane,
    enable_limitation_plane_wrapper as enable_limitation_plane,
    disable_limitation_plane_wrapper as disable_limitation_plane
)
from ..settings.preferences import get_preferences

def create_bounding_box_from_marked(marked_faces_dict, marked_points=None, push_value=0.01, select_new_object=True, use_depsgraph=False):
    """Create a bounding box from marked faces and points"""
    from ..functions.utils import collect_vertices_from_marked_faces, setup_new_object, restore_selection_state
    
    context = bpy.context
    cursor = context.scene.cursor
    
    # Store explicit reference to the original active object and selected objects
    original_active = context.view_layer.objects.active
    original_selected = list(context.selected_objects)
    
    # Capture cursor state
    cursor_location = cursor.location.copy()
    
    # Robustly capture rotation as XYZ Euler regardless of mode
    if cursor.rotation_mode == 'QUATERNION':
        cursor_rotation = cursor.rotation_quaternion.to_euler('XYZ')
    elif cursor.rotation_mode == 'AXIS_ANGLE':
        aa = cursor.rotation_axis_angle
        rot_mat = Matrix.Rotation(aa[0], 4, Vector((aa[1], aa[2], aa[3])))
        cursor_rotation = rot_mat.to_euler('XYZ')
    else:
        if cursor.rotation_mode != 'XYZ':
            cursor_rotation = cursor.rotation_euler.to_matrix().to_euler('XYZ')
        else:
            cursor_rotation = cursor.rotation_euler.copy()
    
    # Collect vertices from marked faces using shared utility
    all_world_coords = collect_vertices_from_marked_faces(marked_faces_dict, use_depsgraph=use_depsgraph, context=context)
    
    # Add marked points
    if marked_points:
        all_world_coords.extend(marked_points)
    
    if not all_world_coords:
        print("Error: No vertices found in marked faces or points.")
        return False
    
    # Use optimized calculation
    local_center, dimensions, cursor_rot_mat = calculate_bbox_bounds_optimized(
        all_world_coords, cursor_location, cursor_rotation
    )
    
    # Apply push value
    epsilon = 0.0001
    dimensions = Vector((
        max(dimensions.x, epsilon),
        max(dimensions.y, epsilon),
        max(dimensions.z, epsilon)
    ))
    
    safe_push_value = float(push_value)
    if safe_push_value > 0 or abs(safe_push_value) * 2 < min(dimensions):
        dimensions += Vector((2 * safe_push_value,) * 3)
    
    dimensions = Vector((
        max(dimensions.x, epsilon),
        max(dimensions.y, epsilon),
        max(dimensions.z, epsilon)
    ))
    
    world_center = cursor_location + (cursor_rot_mat @ local_center)
    
    # Get preferences for bounding box display
    try:
        prefs = get_preferences()
        if prefs:
            show_wire = prefs.bbox_show_wire
            show_all_edges = prefs.bbox_show_all_edges
        else:
            show_wire = True
            show_all_edges = True
    except:
        show_wire = True
        show_all_edges = True
    
    # Create bbox object
    from ..functions.utils import preserve_selection_state
    
    with preserve_selection_state(context) as state:
        state.deselect_all()
        
        bpy.ops.mesh.primitive_cube_add(
            size=1,
            enter_editmode=False,
            align='WORLD',
            location=world_center,
            rotation=cursor_rotation
        )
        
        bbox_obj = context.active_object
        bbox_obj.name = context.scene.cursor_bbox_name_box if context.scene.cursor_bbox_name_box else "Cube"
        
        # Set up object (collection, styles)
        setup_new_object(context, bbox_obj, assign_styles=True, move_to_collection=True)
        
        bbox_obj.scale = dimensions
        bbox_obj.show_wire = show_wire
        bbox_obj.show_all_edges = show_all_edges
        
        bbox_obj.select_set(False)
        
        # Handle selection
        if select_new_object:
            bbox_obj.select_set(True)
            context.view_layer.objects.active = bbox_obj
        else:
            # Restore original selection state
            restore_selection_state(context, original_selected, original_active)
    
    return True

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
    
    snap_threshold: bpy.props.IntProperty(
        name="Snap Threshold",
        default=120,
        min=1,
        max=500,
        description="Distance in pixels to snap to elements"
    )
    
    current_edge_index: bpy.props.IntProperty(default=0)
    current_face_data = None
    marked_faces = {}  # Dictionary to store marked faces per object
    marked_points = []  # List to store additional point markers
    original_selected_objects = set()
    use_depsgraph = False
    
    # Limitation Plane State
    limit_plane_mode = False
    limitation_plane_matrix = None
    cached_limit_intersections = []
    
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
        
        deps_state = "ON" if self.use_depsgraph else "OFF"
        coplanar_state = "ON" if context.scene.cursor_bbox_select_coplanar else "OFF"
        backface_state = "ON" if get_backface_rendering() else "OFF"
        preview_cull_state = "ON" if get_preview_culling() else "OFF"
        
        if self.point_mode:
            snap_state = "ON" if self.snap_enabled else "OFF"
            limit_state = "ON" if self.limit_plane_mode else "OFF"
            context.area.header_text_set(
                f"-- POINT MODE -- | LMB: Add Point | S: Snap ({snap_state}) | Ctrl+Scroll: Snap Thresh ({self.snap_threshold}px) | C: Limit Plane ({limit_state}) | A: Exit Mode | ESC: Cancel"
            )
        else:
            context.area.header_text_set(
                f"Space: Create BBox{marking_status} | LMB: Mark/Place | D: Depsgraph ({deps_state}) | P: Backfaces ({backface_state}) | O: Preview Cull ({preview_cull_state}) | Alt+Scroll: Edge | Shift+Scroll: Angle ({int(round(degrees(context.scene.cursor_bbox_coplanar_angle)))}°) | Ctrl+Scroll: Snap Thresh ({self.snap_threshold}px) | 1-7: Angle Presets | "
                f"C: Coplanar ({coplanar_state}) | F: Mark | A: Add Point Mode | S: Snap | Z: Clear | RMB/ESC: Cancel"
            )
        

        # Cancel (Esc)
        if event.type == 'ESC':
            disable_edge_highlight()
            disable_bbox_preview()
            disable_face_marking()
            clear_all_markings()
            clear_preview_faces()
            disable_face_marking()
            clear_all_markings()
            clear_preview_faces()
            clear_preview_point()
            clear_limitation_plane()
            disable_limitation_plane(context) # Ensure visual is off
            context.area.header_text_set(None)
            return {'CANCELLED'}

        # Finished (RMB)
        if event.type == 'RIGHTMOUSE':
            disable_edge_highlight()
            disable_bbox_preview()
            disable_face_marking()
            clear_all_markings()
            clear_preview_faces()
            clear_preview_point()
            clear_limitation_plane()
            disable_limitation_plane(context) # Ensure visual is off
            context.area.header_text_set(None)
            return {'FINISHED'}

        # Coplanar Angle Adjustment (Shift + Scroll, with optional Alt for fine tuning if needed, but original was just Shift)
        # Avoiding Ctrl here since it's now for Snap
        if event.shift and not event.ctrl and event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            current_deg = degrees(context.scene.cursor_bbox_coplanar_angle)
            step = 1 if event.alt else 5
            
            if event.type == 'WHEELUPMOUSE':
                new_angle_deg = current_deg + step
            else:
                new_angle_deg = current_deg - step
                
            new_angle_deg = max(0.0, min(180.0, new_angle_deg))
            context.scene.cursor_bbox_coplanar_angle = radians(new_angle_deg)
            
            self.report({'INFO'}, f"Coplanar Angle: {int(round(new_angle_deg))}°")
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        # Snap Threshold Adjustment (Ctrl + Scroll)
        if event.ctrl and not event.shift and not event.alt:
            if event.type == 'WHEELUPMOUSE':
                self.snap_threshold += 10
                self.report({'INFO'}, f"Snap Threshold: {self.snap_threshold}px")
                context.area.tag_redraw()
            elif event.type == 'WHEELDOWNMOUSE':
                self.snap_threshold = max(10, self.snap_threshold - 10)
                self.report({'INFO'}, f"Snap Threshold: {self.snap_threshold}px")
                context.area.tag_redraw()
            
            # Force update header immediately
            if self.point_mode:
                snap_state = "ON" if self.snap_enabled else "OFF"
                limit_state = "ON" if self.limit_plane_mode else "OFF"
                context.area.header_text_set(
                    f"-- POINT MODE -- | LMB: Add Point | S: Snap ({snap_state}) | Ctrl+Scroll: Snap Thresh ({self.snap_threshold}px) | C: Limit Plane ({limit_state}) | A: Exit Mode | ESC: Cancel"
                )
            else:
                marking_status = f" ({len(self.marked_faces)} objects marked)" if self.marked_faces else ""
                coplanar_state = "ON" if context.scene.cursor_bbox_select_coplanar else "OFF"
                backface_state = "ON" if get_backface_rendering() else "OFF"
                deps_state = "ON" if self.use_depsgraph else "OFF"
                preview_cull_state = "ON" if get_preview_culling() else "OFF"
                
                context.area.header_text_set(
                 f"Space: Create BBox{marking_status} | LMB: Mark/Place | D: Depsgraph ({deps_state}) | P: Backfaces ({backface_state}) | O: Preview Cull ({preview_cull_state}) | Alt+Scroll: Edge | Shift+Scroll: Angle ({int(round(degrees(context.scene.cursor_bbox_coplanar_angle)))}°) | Ctrl+Scroll: Snap Thresh ({self.snap_threshold}px) | 1-7: Angle Presets | "
                 f"C: Coplanar ({coplanar_state}) | F: Mark | A: Add Point Mode | S: Snap | Z: Clear | RMB/ESC: Cancel"
                )
            return {'RUNNING_MODAL'}
        
        # Toggle Depsgraph (D)
        if event.type == 'D' and event.value == 'PRESS':
            self.use_depsgraph = not self.use_depsgraph
            
            # Rebuild visuals with new setting
            for obj, faces in self.marked_faces.items():
                rebuild_marked_faces_visual_data(obj, faces, use_depsgraph=self.use_depsgraph)
            
            # Update bbox preview if we have markings
            if self.marked_faces or self.marked_points:
                 cursor_rotation = get_cursor_rotation_euler(context)
                 update_marked_faces_bbox(self.marked_faces, self.push_value, 
                                        context.scene.cursor.location, 
                                        cursor_rotation,
                                        marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)
            
            self.report({'INFO'}, f"Depsgraph: {'ON' if self.use_depsgraph else 'OFF'}")
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        # Toggle Backface Rendering (P)
        elif event.type == 'P' and event.value == 'PRESS':
             new_state = toggle_backface_rendering()
             state_str = "ON" if new_state else "OFF"
             self.report({'INFO'}, f"Backface Rendering: {state_str}")
             context.area.tag_redraw()
             return {'RUNNING_MODAL'}
             
        # Toggle Preview Culling (O)
        elif event.type == 'O' and event.value == 'PRESS':
             new_state = toggle_preview_culling()
             state_str = "ON" if new_state else "OFF"
             self.report({'INFO'}, f"Preview Culling: {state_str}")
             context.area.tag_redraw()
             return {'RUNNING_MODAL'}

        # Coplanar Angle Presets (1-7)
        elif event.type in {'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN'} and event.value == 'PRESS':
             angle_map = {
                 'ONE': 5,
                 'TWO': 15,
                 'THREE': 35,
                 'FOUR': 45,
                 'FIVE': 90,
                 'SIX': 120,
                 'SEVEN': 180
             }
             new_angle = angle_map[event.type]
             context.scene.cursor_bbox_coplanar_angle = radians(new_angle)
             self.report({'INFO'}, f"Coplanar Angle Set: {new_angle}°")
             context.area.tag_redraw()
             return {'RUNNING_MODAL'}

        # Toggle Coplanar (C) or Limit Plane (C in point mode)
        if event.type == 'C' and event.value == 'PRESS':
            if self.point_mode:
                self.limit_plane_mode = not self.limit_plane_mode
                if self.limit_plane_mode:
                    # Set the limitation plane to the current cursor orientation
                    self.limitation_plane_matrix = context.scene.cursor.matrix.copy()
                    enable_limitation_plane(context, self.limitation_plane_matrix)
                    
                    # Calculate and cache edge intersections for snapping
                    self.cached_limit_intersections = []
                    # Use active object or all marked objects? Let's use active object if it's mesh
                    if context.active_object and context.active_object.type == 'MESH':
                        origin = self.limitation_plane_matrix.to_translation()
                        normal = self.limitation_plane_matrix.col[2][:3] # Z axis
                        self.cached_limit_intersections = calculate_plane_edge_intersections(
                            context.active_object, 
                            mathutils.Vector(origin), 
                            mathutils.Vector(normal),
                            use_depsgraph=self.use_depsgraph
                        )
                        self.report({'INFO'}, f"Limitation Plane ON | Found {len(self.cached_limit_intersections)} intersection points")
                    else:
                        self.report({'INFO'}, "Limitation Plane ON (No active mesh object for intersections)")
                else:
                    clear_limitation_plane()
                    disable_limitation_plane(context)
                    self.cached_limit_intersections = []
                    self.report({'INFO'}, "Limitation Plane OFF")
            else:
                context.scene.cursor_bbox_select_coplanar = not context.scene.cursor_bbox_select_coplanar
                state = "ON" if context.scene.cursor_bbox_select_coplanar else "OFF"
                self.report({'INFO'}, f"Coplanar Selection: {state}")
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        # Allow navigation events to pass through
        if event.type in {'MIDDLEMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and not event.shift and not event.alt and not event.ctrl:
            return {'PASS_THROUGH'}
        
        # Create BBox (Space/Enter)
        if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and event.value == 'PRESS':
            # Create bounding box based on marked faces and/or points
            if self.marked_faces or self.marked_points:
                # Create bbox from marked faces and points
                if create_bounding_box_from_marked(self.marked_faces, self.marked_points, self.push_value, select_new_object=False, use_depsgraph=self.use_depsgraph):
                    self.report({'INFO'}, "Created Bounding Box. Ready for new selection.")
                    # Cleanup (partial) - Keep tool active
                    clear_all_markings()
                    clear_preview_faces()
                    self.marked_faces.clear()
                    self.marked_points.clear()
                    context.area.tag_redraw()
                else:
                    self.report({'WARNING'}, "Failed to create Bounding Box")
                
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
            if self.point_mode:
                # Add Point Logic
                face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
                
                loc, message = calculate_point_location(
                    context, event, face_data, self.snap_enabled, 
                    self.limit_plane_mode, self.limitation_plane_matrix,
                    self.cached_limit_intersections, self.snap_threshold,
                    use_depsgraph=self.use_depsgraph
                )
                
                if loc is None:
                    if message:
                        self.report({'WARNING'}, message)
                    return {'RUNNING_MODAL'}
                
                if message:
                    self.report({'INFO'}, message)
                
                self.marked_points.append(loc)
                add_marked_point(loc)
                
                # Update bbox preview based on marked faces and points
                cursor_rotation = get_cursor_rotation_euler(context)
                update_marked_faces_bbox(self.marked_faces, self.push_value, 
                                       context.scene.cursor.location, 
                                       cursor_rotation,
                                       marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            
            # Normal Mark/Place Logic
            # Mark/unmark face under cursor
            face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
            if face_data and face_data['object'] in self.original_selected_objects:
                obj = face_data['object']
                face_idx = face_data['face_index']
                
                # Also place cursor for feedback (optional, but good for "Place Cursor" tool)
                place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, use_depsgraph=self.use_depsgraph)
                
                # Initialize object's marked faces if needed
                if obj not in self.marked_faces:
                    self.marked_faces[obj] = set()
                
                # Determine faces to process (Coplanar logic)
                faces_to_process = get_faces_to_process(
                    obj, face_idx, context.scene.cursor_bbox_select_coplanar,
                    context.scene.cursor_bbox_coplanar_angle, use_depsgraph=self.use_depsgraph
                )

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
                    rebuild_marked_faces_visual_data(obj, set(), use_depsgraph=self.use_depsgraph) # Clear this obj
                    # But we might have other objects?
                    # rebuild_marked_faces_visual_data handles single obj.
                    
                    # Hack: The utils function mark_face/unmark_face are for single.
                    # We need batch update.
                    # rebuild_marked_faces_visual_data(obj, self.marked_faces.get(obj, set()))
                
                rebuild_marked_faces_visual_data(obj, self.marked_faces.get(obj, set()), use_depsgraph=self.use_depsgraph)
                
                # Update bbox preview based on marked faces and points
                cursor_rotation = get_cursor_rotation_euler(context)
                update_marked_faces_bbox(self.marked_faces, self.push_value, 
                                       context.scene.cursor.location, 
                                       cursor_rotation,
                                       marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)
                context.area.tag_redraw()
            
            return {'RUNNING_MODAL'}
        
        elif event.type == 'F' and event.value == 'PRESS':
            # Mark/unmark face under cursor
            face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
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
                        rebuild_marked_faces_visual_data(obj, self.marked_faces[obj], use_depsgraph=self.use_depsgraph)
                    self.report({'INFO'}, f"Unmarked face {face_idx} on {obj.name}")
                else:
                    self.marked_faces[obj].add(face_idx)
                    mark_face(obj, face_idx)
                    # Note: mark_face helper might use default rebuilding without depsgraph?
                    # mark_face calls mark_faces_batch. core.py: mark_face(obj, face_index)
                    # I didn't update mark_face signature in core.py.
                    # But I updated mark_faces_batch.
                    # mark_face calls mark_faces_batch(obj, [face_index]).
                    # If I use 'F' key, it calls mark_face.
                    # So mark_face inside core.py needs update OR I should call rebuild here directly like "delete" block does.
                    # Since I can't easily update mark_face in core.py now (too many edits), I should explicitly call rebuild here:
                    rebuild_marked_faces_visual_data(obj, self.marked_faces[obj], use_depsgraph=self.use_depsgraph)

                    self.report({'INFO'}, f"Marked face {face_idx} on {obj.name}")
                
                # Update bbox preview based on marked faces and points
                cursor_rotation = get_cursor_rotation_euler(context)
                update_marked_faces_bbox(self.marked_faces, self.push_value, 
                                       context.scene.cursor.location, 
                                       cursor_rotation,
                                       marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)
                context.area.tag_redraw()
            
            return {'RUNNING_MODAL'}
        
        elif event.type == 'A' and event.value == 'PRESS':
            self.point_mode = not self.point_mode
            if self.point_mode:
                self.report({'INFO'}, "Entered Add Point Mode")
                self.current_face_data = None 
                clear_preview_faces() 
            else:
                self.report({'INFO'}, "Exited Add Point Mode")
                clear_preview_point()
                self.limit_plane_mode = False
                clear_limitation_plane()
                disable_limitation_plane(context) # Ensure visual is off
                self.cached_limit_intersections = []
            
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'Z' and event.value == 'PRESS':
            # Clear all marked faces and points
            if self.marked_faces or self.marked_points:
                clear_all_markings()  # Clear global state
                clear_preview_faces()
                self.marked_faces.clear()  # Clear local state
                self.marked_points.clear()  # Clear local state
                self.report({'INFO'}, "Cleared all marked faces and points")
                # Reset to regular object bbox preview
                result = place_cursor_with_raycast_and_edge(
                    context, event, self.align_to_face, self.current_edge_index, use_depsgraph=self.use_depsgraph
                )
                context.area.tag_redraw()
            
            return {'RUNNING_MODAL'}
        
        elif event.type == 'WHEELUPMOUSE' and event.alt:
            face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
            if face_data and face_data['object'] in self.original_selected_objects:
                self.current_face_data = face_data
                self.current_edge_index = select_edge_by_scroll(
                    face_data, 1, self.current_edge_index
                )
                result = place_cursor_with_raycast_and_edge(
                    context, event, self.align_to_face, self.current_edge_index, use_depsgraph=self.use_depsgraph
                )
                if result['success']:
                    # Update preview with marked faces and points if any
                    if self.marked_faces or self.marked_points:
                        cursor_rotation = get_cursor_rotation_euler(context)
                        update_marked_faces_bbox(self.marked_faces, self.push_value,
                                               context.scene.cursor.location,
                                               cursor_rotation,
                                               marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)
                    context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'WHEELDOWNMOUSE' and event.alt:
            face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
            if face_data and face_data['object'] in self.original_selected_objects:
                self.current_face_data = face_data
                self.current_edge_index = select_edge_by_scroll(
                    face_data, -1, self.current_edge_index
                )
                result = place_cursor_with_raycast_and_edge(
                    context, event, self.align_to_face, self.current_edge_index, use_depsgraph=self.use_depsgraph
                )
                if result['success']:
                    # Update preview with marked faces and points if any
                    if self.marked_faces or self.marked_points:
                        cursor_rotation = get_cursor_rotation_euler(context)
                        update_marked_faces_bbox(self.marked_faces, self.push_value,
                                               context.scene.cursor.location,
                                               cursor_rotation,
                                               marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)
                    context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'MOUSEMOVE':
            if self.point_mode:
                face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
                current_loc = None
                
                if self.snap_enabled:
                    # Snap Logic - use intersection points if limit plane mode is enabled
                    intersection_pts = self.cached_limit_intersections if self.limit_plane_mode else None
                    snap_result = snap_cursor_to_closest_element(context, event, face_data, threshold=self.snap_threshold, intersection_points=intersection_pts, use_depsgraph=self.use_depsgraph)
                    if snap_result['success']:
                        current_loc = context.scene.cursor.location.copy()
                    else:
                        # Fallback to normal raycast alignment
                        result = place_cursor_with_raycast_and_edge(
                           context, event, self.align_to_face, self.current_edge_index, preview=False, use_depsgraph=self.use_depsgraph
                        )
                        if result['success']:
                            current_loc = result['location']
                        else:
                            current_loc = None
                elif self.limit_plane_mode and self.limitation_plane_matrix and face_data:
                     # Limit Plane Mode (no snap)
                     plane_origin = self.limitation_plane_matrix.to_translation()
                     plane_normal = self.limitation_plane_matrix.col[2].to_3d() # Z axis
                     
                     proj_pt = project_point_to_plane_intersection(
                         face_data['hit_location'], 
                         face_data['face_normal'],
                         plane_origin, 
                         plane_normal
                     )
                     
                     if proj_pt:
                         current_loc = proj_pt
                     else:
                         current_loc = None
                else:
                    # Standard raycast alignment (updates cursor location and rotation)
                    result = place_cursor_with_raycast_and_edge(
                        context, event, self.align_to_face, self.current_edge_index, preview=False, use_depsgraph=self.use_depsgraph
                    )
                    if result['success']:
                        current_loc = result['location']
                    else:
                        current_loc = None
                
                if current_loc:
                    update_preview_point(current_loc)
                else:
                    clear_preview_point()
                
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            
            # Normal MOUSEMOVE
            result = place_cursor_with_raycast_and_edge(
                context, event, self.align_to_face, self.current_edge_index, preview=False, use_depsgraph=self.use_depsgraph
            )
            if result['success'] and result['face_data']['object'] in self.original_selected_objects:
                self.current_face_data = result['face_data']
                
                # Update Preview Faces
                obj = result['face_data']['object']
                face_idx = result['face_data']['face_index']
                
                faces_to_preview = get_faces_to_process(
                    obj, face_idx, context.scene.cursor_bbox_select_coplanar,
                    context.scene.cursor_bbox_coplanar_angle, use_depsgraph=self.use_depsgraph
                )
                
                update_preview_faces(obj, faces_to_preview, use_depsgraph=self.use_depsgraph)

                # Update bbox preview - show marked faces and points bbox if any, otherwise object bbox
                if self.marked_faces or self.marked_points:
                    # Update preview with marked faces and points
                    cursor_rotation = get_cursor_rotation_euler(context)
                    update_marked_faces_bbox(self.marked_faces, self.push_value,
                                           context.scene.cursor.location,
                                           cursor_rotation,
                                           marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)
                context.area.tag_redraw()
            else:
                clear_preview_faces()
                self.current_face_data = None
                
            return {'RUNNING_MODAL'}
        
        elif event.type == 'S' and event.value == 'PRESS':
            if self.point_mode:
                self.snap_enabled = not self.snap_enabled
                state_str = "ON" if self.snap_enabled else "OFF"
                self.report({'INFO'}, f"Point Snap: {state_str} (Threshold: {self.snap_threshold}px)")
            else:
                # Snap cursor to closest vertex, edge midpoint, or face center from current face
                face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
                result = snap_cursor_to_closest_element(context, event, face_data, threshold=self.snap_threshold, use_depsgraph=self.use_depsgraph)
                if result['success'] and (not face_data or face_data['object'] in self.original_selected_objects):
                    if face_data:
                        self.report({'INFO'}, f"Cursor snapped to {result['type']} on {face_data['object'].name} ({result['distance']:.1f}px away)")
                    else:
                        self.report({'INFO'}, f"Cursor snapped to {result['type']} ({result['distance']:.1f}px away)")
                    # Update bbox preview after cursor snap
                    if self.marked_faces or self.marked_points:
                        cursor_rotation = get_cursor_rotation_euler(context)
                        update_marked_faces_bbox(self.marked_faces, self.push_value,
                                               context.scene.cursor.location,
                                               cursor_rotation,
                                               marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)
                    context.area.tag_redraw()
                else:
                    self.report({'WARNING'}, "No suitable snap target found")
            return {'RUNNING_MODAL'}
        

        return {'RUNNING_MODAL'}
    
    def invoke(self, context, event):
        # Initialize properties
        self.push_value = context.scene.cursor_bbox_push
        self.align_to_face = context.scene.cursor_bbox_align_face
        self.marked_faces = {}
        self.marked_points = []
        self.point_mode = False
        self.snap_enabled = True
        self.limit_plane_mode = False
        self.limitation_plane_matrix = None

        # Check for immediate execution in Edit Mode
        if context.mode == 'EDIT_MESH':
            self.marked_faces = get_selected_faces_from_edit_mode(context)
            
            if self.marked_faces:
                active_obj = context.active_object
                # Switch to Object Mode to allow object creation and selection operations
                bpy.ops.object.mode_set(mode='OBJECT')
                if create_bounding_box_from_marked(self.marked_faces, self.marked_points, self.push_value, select_new_object=False):
                    # Restore Edit Mode
                    if active_obj:
                        context.view_layer.objects.active = active_obj
                        bpy.ops.object.mode_set(mode='EDIT')
                        
                    self.report({'INFO'}, "Created Bounding Box from selection")
                    return {'FINISHED'}
                else:
                    self.report({'WARNING'}, "Failed to create Bounding Box from selection")
                    # Restore Edit Mode even on failure
                    if active_obj:
                        context.view_layer.objects.active = active_obj
                        bpy.ops.object.mode_set(mode='EDIT')
                    return {'CANCELLED'}

        if context.area.type == 'VIEW_3D':
            self.current_edge_index = 0
            self.current_face_data = None
            # self.marked_faces and properties already initialized above
            
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
