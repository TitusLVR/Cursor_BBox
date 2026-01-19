import bpy
import bmesh
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
    get_faces_to_process,
    is_collection_instance,
    make_collection_instance_real,
    cleanup_collection_instance_temp
)
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

def create_bounding_sphere_from_marked(marked_faces_dict, marked_points=None, select_new_object=True, use_depsgraph=False):
    """Create a bounding sphere from marked faces and points"""
    from ..functions.utils import collect_vertices_from_marked_faces
    
    context = bpy.context
    cursor = context.scene.cursor
    cursor_matrix = cursor.matrix.copy()
    cursor_matrix_inv = cursor_matrix.inverted()
    
    # Store explicit reference to the original active object and selected objects
    original_active = context.view_layer.objects.active
    original_selected = list(context.selected_objects)
    
    # Collect vertices from marked faces using shared utility
    all_vertices = collect_vertices_from_marked_faces(marked_faces_dict, use_depsgraph=use_depsgraph, context=context)
    
    # Add marked points
    if marked_points:
        all_vertices.extend(marked_points)
        
    if not all_vertices:
        print("Error: No vertices found in marked faces or points.")
        return False

    # Transform to Local Space of Cursor for "Oriented" Bounding calculation
    local_verts = [cursor_matrix_inv @ v for v in all_vertices]

    # Calculate Center (BBox Center in Local Space)
    min_co = Vector(local_verts[0])
    max_co = Vector(local_verts[0])
    
    for v in local_verts:
        min_co.x = min(min_co.x, v.x)
        min_co.y = min(min_co.y, v.y)
        min_co.z = min(min_co.z, v.z)
        max_co.x = max(max_co.x, v.x)
        max_co.y = max(max_co.y, v.y)
        max_co.z = max(max_co.z, v.z)
        
    local_center = (min_co + max_co) / 2.0
    
    # Calculate Radius (Max Distance from Center in Local Space)
    radius = 0.0
    for v in local_verts:
        dist = (v - local_center).length
        if dist > radius:
            radius = dist
    
    # Calculate World Center for the Object
    world_center = cursor_matrix @ local_center

    # Create Sphere using BMesh (Ensures new object)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(
        bm, 
        u_segments=32, 
        v_segments=16, 
        radius=radius
    )
    
    # Note: No translation needed on BMesh if we place Object at world_center
    
    # Create new mesh and object
    sphere_name = context.scene.cursor_bbox_name_sphere if context.scene.cursor_bbox_name_sphere else "Sphere"
    mesh_data = bpy.data.meshes.new(sphere_name)
    bm.to_mesh(mesh_data)
    bm.free()
    
    obj = bpy.data.objects.new(sphere_name, mesh_data)
    
    # Set Orientation and Location
    obj.location = world_center
    obj.rotation_euler = cursor.rotation_euler
    
    # Set up object (collection, styles)
    from ..functions.utils import setup_new_object, restore_selection_state
    setup_new_object(context, obj, assign_styles=True, move_to_collection=True)
    
    # Handle Selection
    for o in context.selected_objects:
        o.select_set(False)
        
    if select_new_object:
        obj.select_set(True)
        context.view_layer.objects.active = obj
    else:
        obj.select_set(False)
    
    # Restore original selection state
    restore_selection_state(context, original_selected, original_active)
    
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
    use_depsgraph = False
    
    # Collection instance handling
    instance_data = {}  # Dictionary to store instance data per object {obj: instance_data}
    
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
    
    # Limitation Plane State
    limit_plane_mode = False
    limitation_plane_matrix = None
    cached_limit_intersections = []
    
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
        # Update status bar
        has_marked = bool(self.marked_faces)
        has_points = bool(self.marked_points)
        status_text = "Space: Create Sphere"
        if has_marked or has_points:
            parts = []
            if has_marked: parts.append("Faces")
            if has_points: parts.append(f"{len(self.marked_points)} Points")
            status_text += f" | Marked: {', '.join(parts)}"
        
        deps_state = "ON" if self.use_depsgraph else "OFF"
        coplanar_state = "ON" if context.scene.cursor_bbox_select_coplanar else "OFF"
        backface_state = "ON" if get_backface_rendering() else "OFF"
        preview_cull_state = "ON" if get_preview_culling() else "OFF"
        preview_cull_state = "ON" if get_preview_culling() else "OFF"
        
        if self.point_mode:
            snap_state = "ON" if self.snap_enabled else "OFF"
            limit_state = "ON" if self.limit_plane_mode else "OFF"
            context.area.header_text_set(
                f"-- POINT MODE -- | LMB: Add Point | S: Snap ({snap_state}) | Ctrl+Scroll: Snap Thresh ({self.snap_threshold}px) | C: Limit Plane ({limit_state}) | A: Exit Mode | ESC: Cancel"
            )
        else:
            context.area.header_text_set(
                f"{status_text} | LMB/F: Mark/Unmark | C: Coplanar ({coplanar_state}) | P: Backfaces ({backface_state}) | O: Preview Cull ({preview_cull_state}) | D: Depsgraph ({deps_state}) | Alt+Scroll: Edge | Ctrl+Scroll: Snap Thresh | 1-7: Angle Presets | Shift(+Ctrl): Angle ({int(round(degrees(context.scene.cursor_bbox_coplanar_angle)))}°) | A: Add Point Mode | S: Snap | Z: Clear"
            )
        
        # Toggle Depsgraph (D)
        if event.type == 'D' and event.value == 'PRESS':
            self.use_depsgraph = not self.use_depsgraph
            # Rebuild visuals with new setting
            for obj, faces in self.marked_faces.items():
                rebuild_marked_faces_visual_data(obj, faces, use_depsgraph=self.use_depsgraph)
            
            # Update Preview (Sphere)
            cursor_rotation = get_cursor_rotation_euler(context)
            update_marked_faces_sphere(self.marked_faces, 
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

        # Snap Threshold Adjustment (Ctrl + Scroll) - Must be before navigation pass-through
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
                context.area.header_text_set(
                    f"Space: Create Sphere{marking_status} | LMB/F: Mark/Unmark | Alt+Scroll: Edge | Ctrl+Scroll: Snap Thresh ({self.snap_threshold}px) | A: Add Point Mode | Z: Clear | RMB/ESC: Cancel"
                )
            
            return {'RUNNING_MODAL'}

        # Navigation
        if event.type == 'MIDDLEMOUSE' or (event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and not event.shift and not event.alt and not event.ctrl):
            return {'PASS_THROUGH'}
            
        # Create Sphere (Enter/Space)
        if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and event.value == 'PRESS':
            if self.marked_faces or self.marked_points:
                if create_bounding_sphere_from_marked(self.marked_faces, self.marked_points, select_new_object=False, use_depsgraph=self.use_depsgraph):
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
            if self.point_mode:
                # Add Point Logic
                
                # Get face data from raycast
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
                
                # Update Preview
                cursor_rotation = get_cursor_rotation_euler(context)
                update_marked_faces_sphere(self.marked_faces, 
                                         context.scene.cursor.location,
                                         cursor_rotation,
                                         marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            
            # Normal Mark Face Logic
            face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
            if face_data and face_data['object'] in self.original_selected_objects:
                obj = face_data['object']
                face_idx = face_data['face_index']
                
                # Also place cursor for feedback
                place_cursor_with_raycast_and_edge(context, event, self.align_to_face, self.current_edge_index, use_depsgraph=self.use_depsgraph)
                
                if obj not in self.marked_faces:
                    self.marked_faces[obj] = set()
                
                # Check if unmarking (if single face is already marked)
                is_unmarking = face_idx in self.marked_faces[obj]
                
                faces_to_process = get_faces_to_process(
                    obj, face_idx, context.scene.cursor_bbox_select_coplanar,
                    context.scene.cursor_bbox_coplanar_angle, use_depsgraph=self.use_depsgraph
                )

                for idx in faces_to_process:
                    if is_unmarking:
                        if idx in self.marked_faces[obj]:
                            self.marked_faces[obj].remove(idx)
                    else:
                        self.marked_faces[obj].add(idx)
                
                if not self.marked_faces[obj]:
                    del self.marked_faces[obj]
                    rebuild_marked_faces_visual_data(obj, set(), use_depsgraph=self.use_depsgraph)
                else:
                    rebuild_marked_faces_visual_data(obj, self.marked_faces[obj], use_depsgraph=self.use_depsgraph)
                
                # Update Preview (Use Sphere preview as it shows extent)
                cursor_rotation = get_cursor_rotation_euler(context)
                update_marked_faces_sphere(self.marked_faces, 
                                         context.scene.cursor.location,
                                         cursor_rotation,
                                         marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
            
        # Toggle Limitation Plane (C)
        elif event.type == 'C' and event.value == 'PRESS':
            self.limit_plane_mode = not self.limit_plane_mode
            if self.limit_plane_mode:
                enable_limitation_plane(context, self.limitation_plane_matrix)
                
                # Calculate and cache edge intersections for snapping
                self.cached_limit_intersections = []
                if context.active_object and context.active_object.type == 'MESH':
                    origin = self.limitation_plane_matrix.to_translation()
                    normal = self.limitation_plane_matrix.col[2][:3] 
                    self.cached_limit_intersections = calculate_plane_edge_intersections(
                        context.active_object, 
                        Vector(origin), 
                        Vector(normal),
                        use_depsgraph=self.use_depsgraph
                    )
                    self.report({'INFO'}, f"Limitation Plane ON | {len(self.cached_limit_intersections)} pts")
            else:
                clear_limitation_plane()
                disable_limitation_plane(context)
                self.cached_limit_intersections = []
                self.report({'INFO'}, "Limitation Plane OFF")
            
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
            
        # Add Point Mode Toggle (A)
        elif event.type == 'A' and event.value == 'PRESS':
            self.point_mode = not self.point_mode
            if self.point_mode:
                self.report({'INFO'}, "Entered Add Point Mode")
                self.current_face_data = None # Reset selection
                clear_preview_faces() 
            else:
                self.report({'INFO'}, "Exited Add Point Mode")
                clear_preview_point()
                self.limit_plane_mode = False
                clear_limitation_plane()
            
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
            
        # Left Mouse Click (Add Point in Mode OR Mark Face)
        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if self.point_mode:
                # Add point at current preview location (which is updated in mousemove)
                # Recalculate just in case
                face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
                loc = context.scene.cursor.location.copy()
                
                # If snap enabled, cursor is already at snap location from mousemove
                # If snap disabled, cursor is at hit location from mousemove
                # But mousemove might not have fired if just clicked A then Click without move?
                # So let's run the logic once to be sure
                
                if self.snap_enabled:
                     snap_result = snap_cursor_to_closest_element(context, event, face_data, use_depsgraph=self.use_depsgraph)
                     if snap_result['success']:
                         loc = context.scene.cursor.location.copy()
                         self.report({'INFO'}, f"Added point snapped to {snap_result['type']}")
                     elif face_data:
                         try:
                             loc = face_data['hit_location']
                         except:
                             pass
                else:
                    if face_data:
                        try:
                            loc = face_data['hit_location']
                        except:
                            pass
                
                self.marked_points.append(loc)
                add_marked_point(loc)
                
                # Update Sphere Preview
                cursor_rotation = get_cursor_rotation_euler(context)
                update_marked_faces_sphere(self.marked_faces, 
                                         context.scene.cursor.location,
                                         cursor_rotation,
                                         marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            
            # Normal Mark Face Logic (Only if not in Point Mode)
            # Match 'LEFTMOUSE' or 'F' handler logic from original
            # Note: The original code handled LEFTMOUSE and F together. 
            # We need to split them or handle the condition inside.
            
            # Since I replaced the 'A' block, I am before the LEFTMOUSE block.
            # I need to implement the LEFTMOUSE logic here? No, I am inserting this BEFORE existing blocks?
            # Wait, the tool 'ReplacementChunks' REPLACES content.
            # I see 'Add Point (A)' block is later in the file around line 358.
            # 'Mark Face (LMB or F)' is around line 295.
            # My 'EndLine' logic for replacement needs to be careful.
            
            # Let's REPLACE the 'A' handler first (lines 359-390).
            # AND I need to intercept LMB.
            # It is cleaner to modify the existing LMB handler to check for point mode.
            pass

        # Mark Face (LMB or F) - Modified to respect Point Mode
        # Mark Face (LMB or F) - Modified to respect Point Mode
        elif (event.type == 'LEFTMOUSE' and event.value == 'PRESS') or (event.type == 'F' and event.value == 'PRESS'):
            # If in point mode and it was a click (not F), check mode here.
            
            if self.point_mode and event.type == 'LEFTMOUSE':
                 # ... Add point logic ...
                 face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
                 loc = context.scene.cursor.location.copy()
                 
                 # Limit Plane Logic for Click
                 if self.limit_plane_mode and self.limitation_plane_matrix and face_data:
                     plane_origin = self.limitation_plane_matrix.to_translation()
                     plane_normal = self.limitation_plane_matrix.col[2].to_3d()
                     proj_pt = project_point_to_plane_intersection(
                         face_data['hit_location'], 
                         face_data['face_normal'],
                         plane_origin, 
                         plane_normal
                     )
                     if proj_pt:
                         loc = proj_pt
                     else:
                         # No intersection, abort or warn?
                         self.report({'WARNING'}, "Invalid placement (no intersection)")
                         return {'RUNNING_MODAL'}
                 
                 # Standard Snap Logic (Only if not limited or if limit allows combining?)
                 # For now, Limit Plane overrides standard snap if active.
                 elif self.snap_enabled:
                     snap_result = snap_cursor_to_closest_element(context, event, face_data, threshold=self.snap_threshold, use_depsgraph=self.use_depsgraph)
                     if snap_result['success']:
                         loc = context.scene.cursor.location.copy()
                 elif face_data:
                      try:
                         loc = face_data['hit_location']
                      except:
                         pass
                     
                 self.marked_points.append(loc)
                 add_marked_point(loc)
                 
                 # Update Preview
                 cursor_rotation = get_cursor_rotation_euler(context)
                 update_marked_faces_sphere(self.marked_faces, 
                                          context.scene.cursor.location,
                                          cursor_rotation,
                                          marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)
                 context.area.tag_redraw()
                 return {'RUNNING_MODAL'}
            
            # ... Normal marking logic ...

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
                    # Update Preview (Sphere) if needed
                    # Note: Sphere preview is based on MARKED faces, not hover cursor.
                    # BUT cursor rotation changes here. So we MUST update preview if markers exist.
                    if self.marked_faces or self.marked_points:
                        cursor_rotation = get_cursor_rotation_euler(context)
                        update_marked_faces_sphere(self.marked_faces, 
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
                    if self.marked_faces or self.marked_points:
                        cursor_rotation = get_cursor_rotation_euler(context)
                        update_marked_faces_sphere(self.marked_faces, 
                                                 context.scene.cursor.location,
                                                 cursor_rotation,
                                                 marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)

                    context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type == 'S' and event.value == 'PRESS':
            if self.point_mode:
                self.snap_enabled = not self.snap_enabled
                state_str = "ON" if self.snap_enabled else "OFF"
                self.report({'INFO'}, f"Point Snap: {state_str}")
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
                        update_marked_faces_sphere(self.marked_faces, 
                                                 context.scene.cursor.location,
                                                 cursor_rotation,
                                                 marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)
                    context.area.tag_redraw()
                else:
                    self.report({'WARNING'}, "No suitable snap target found")
            return {'RUNNING_MODAL'}

        # Mouse Move - Update Preview (Hover)
        elif event.type == 'MOUSEMOVE':
            if self.point_mode:
                # Point Mode Preview Logic
                face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
                current_loc = None
                
                if self.snap_enabled:
                    # Snap Logic - use intersection points if limit plane mode is enabled
                    intersection_pts = self.cached_limit_intersections if self.limit_plane_mode else None
                    snap_result = snap_cursor_to_closest_element(context, event, face_data, threshold=self.snap_threshold, intersection_points=intersection_pts, use_depsgraph=self.use_depsgraph)
                    if snap_result['success']:
                        current_loc = context.scene.cursor.location.copy() 
                    else:
                        # Fallback to raycast placement if no snap
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
                    # Standard raycast placement (location + rotation)
                    result = place_cursor_with_raycast_and_edge(
                        context, event, self.align_to_face, self.current_edge_index, preview=False, use_depsgraph=self.use_depsgraph
                    )
                    if result['success']:
                         current_loc = result['location']
                    else:
                         current_loc = None
                
                if current_loc:
                    update_preview_point(current_loc)
                    
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}

            # Normal Hover Logic
            result = place_cursor_with_raycast_and_edge(
                context, event, self.align_to_face, self.current_edge_index, preview=False, use_depsgraph=self.use_depsgraph
            )
            
            if result['success'] and result['face_data']['object'] in self.original_selected_objects:
                self.current_face_data = result['face_data']

                obj = result['face_data']['object']
                face_idx = result['face_data']['face_index']
                
                faces_to_preview = get_faces_to_process(
                    obj, face_idx, context.scene.cursor_bbox_select_coplanar,
                    context.scene.cursor_bbox_coplanar_angle, use_depsgraph=self.use_depsgraph
                )
                
                update_preview_faces(obj, faces_to_preview, use_depsgraph=self.use_depsgraph)
                
                # Also update sphere preview if we have marked stuff
                if self.marked_faces or self.marked_points:
                    cursor_rotation = get_cursor_rotation_euler(context)
                    update_marked_faces_sphere(self.marked_faces, 
                                             context.scene.cursor.location,
                                             cursor_rotation,
                                             marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)

                context.area.tag_redraw()
            else:
                clear_preview_faces()
                self.current_face_data = None
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
        elif event.type == 'ESC':
            disable_edge_highlight()
            disable_bbox_preview()
            disable_face_marking()
            clear_all_markings()
            clear_preview_faces()
            clear_preview_point()
            clear_limitation_plane()
            self.cleanup_all_instances(context)  # Clean up collection instances
            context.area.header_text_set(None)
            context.area.tag_redraw()
            return {'CANCELLED'}

        # Finished
        elif event.type == 'RIGHTMOUSE':
            disable_edge_highlight()
            disable_bbox_preview()
            disable_face_marking()
            clear_all_markings()
            clear_preview_faces()
            clear_preview_point()
            clear_limitation_plane()
            self.cleanup_all_instances(context)  # Clean up collection instances
            context.area.header_text_set(None)
            context.area.tag_redraw()
            return {'FINISHED'}
            
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        # Initialize properties
        self.marked_faces = {}
        self.align_to_face = context.scene.cursor_bbox_align_face
        self.marked_points = []
        self.point_mode = False
        self.snap_enabled = True
        self.limit_plane_mode = False
        self.limitation_plane_matrix = None
        self.instance_data = {}
        
        # Check for immediate execution in Edit Mode
        if context.mode == 'EDIT_MESH':
            self.marked_faces = get_selected_faces_from_edit_mode(context)
            
            if self.marked_faces:
                active_obj = context.active_object
                # Switch to Object Mode to allow object creation and selection operations
                bpy.ops.object.mode_set(mode='OBJECT')
                if create_bounding_sphere_from_marked(self.marked_faces, self.marked_points, select_new_object=False):
                    # Restore Edit Mode
                    if active_obj:
                        context.view_layer.objects.active = active_obj
                        bpy.ops.object.mode_set(mode='EDIT')

                    self.report({'INFO'}, "Created Bounding Sphere from selection")
                    return {'FINISHED'}
                else:
                    self.report({'WARNING'}, "Failed to create Bounding Sphere from selection")
                    # If failed, we might be in Object Mode now. Restore Edit Mode if possible
                    if active_obj:
                       context.view_layer.objects.active = active_obj
                       bpy.ops.object.mode_set(mode='EDIT')
                    pass

        if context.area.type == 'VIEW_3D':
            self.current_edge_index = 0
            self.current_face_data = None
            # self.marked_faces already initialized above
            self.align_to_face = context.scene.cursor_bbox_align_face
            
            self.original_selected_objects = set(context.selected_objects)
            if context.active_object:
                self.original_selected_objects.add(context.active_object)
            
            # Check for collection instances and handle them
            objects_with_instances = []
            for obj in self.original_selected_objects:
                if is_collection_instance(obj):
                    self.report({'INFO'}, f"Processing collection instance: {obj.name}")
                    objects_with_instances.append(obj)
            
            # Make instances real (process all instances keeping selection)
            for i, obj in enumerate(objects_with_instances):
                # Keep previous selection for all instances after the first one
                keep_previous = (i > 0)
                real_objs = self.handle_collection_instance(context, obj, keep_previous)
                if real_objs:
                    # Add real objects to the set of objects we can interact with
                    # Remove the instance object from original set
                    self.original_selected_objects.discard(obj)
                    # Add real objects
                    for real_obj in real_objs:
                        self.original_selected_objects.add(real_obj)
                
            clear_preview_faces()
            enable_face_marking()
            enable_edge_highlight()
            enable_bbox_preview()
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Active space must be a View3D")
            return {'CANCELLED'}
