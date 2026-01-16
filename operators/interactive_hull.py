import bpy
import bmesh
import mathutils
from mathutils import Vector
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
    clear_all_markings,
    update_marked_faces_convex_hull,
    update_preview_faces,
    clear_preview_faces,
    toggle_backface_rendering,
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


def create_convex_hull_from_marked(marked_faces_dict, marked_points=None, push_value=0.0, select_new_object=True, use_depsgraph=False):
    """Create a convex hull from marked faces and points"""
    from ..functions.utils import collect_vertices_from_marked_faces
    
    context = bpy.context
    
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
        
    # Create new mesh for convex hull
    bm = bmesh.new()
    for v in all_vertices:
        bm.verts.new(v)
    
    # Ensure vertices are valid
    bm.verts.ensure_lookup_table()
    
    # Calculate convex hull
    try:
        bmesh.ops.convex_hull(bm, input=bm.verts)
        
        # Remove any loose vertices that are not connected to faces
        # After convex_hull, some vertices may not be part of any face
        verts_to_remove = [v for v in bm.verts if not v.link_faces]
        if verts_to_remove:
            bmesh.ops.delete(bm, geom=verts_to_remove, context='VERTS')
        
        # Ensure lookup tables are valid after deletion
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        
        # Remove interior geometry and ensure normals
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        
        # Apply Push Value (Inflate along normals)
        if abs(push_value) > 0.0001:
            # Simple vertex normal calculation
            vert_normals = {v: Vector((0,0,0)) for v in bm.verts}
            for f in bm.faces:
                for v in f.verts:
                    vert_normals[v] += f.normal
            
            # Normalize and move
            for v in bm.verts:
                if vert_normals[v].length_squared > 0:
                    normal = vert_normals[v].normalized()
                    v.co += normal * push_value
        
        # Calculate Center (Centroid/Geometry Center) explicitly
        if len(bm.verts) > 0:
            center_of_geometry = Vector((0.0, 0.0, 0.0))
            for v in bm.verts:
                center_of_geometry += v.co
            center_of_geometry /= len(bm.verts)
            
            # Move geometry to local origin
            bmesh.ops.translate(bm, verts=bm.verts, vec=-center_of_geometry)
        else:
            center_of_geometry = Vector((0.0, 0.0, 0.0))
            
        # Create object
        mesh_data = bpy.data.meshes.new("ConvexHull")
        bm.to_mesh(mesh_data)
        bm.free()
        
        if not context.scene.cursor_bbox_name_hull:
             hull_name = "Convex"
        else:
             hull_name = context.scene.cursor_bbox_name_hull
             
        obj = bpy.data.objects.new(hull_name, mesh_data)
        
        # Set location to calculated center
        obj.location = center_of_geometry
        
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
        
    except Exception as e:
        print(f"Error creating convex hull: {e}")
        bm.free()
        return False

class CursorBBox_OT_interactive_hull(bpy.types.Operator):
    """Create convex hull from marked faces"""
    bl_idname = "cursor_bbox.interactive_hull"
    bl_label = "Interactive Hull"
    bl_description = "Fit a Convex Hull around marked faces"
    bl_options = {'REGISTER', 'UNDO'}
    
    push_value: bpy.props.FloatProperty(
        name="Push Value",
        description="How much to push convex hull faces outward",
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
    
    # Limitation Plane State
    limit_plane_mode = False
    limitation_plane_matrix = None
    cached_limit_intersections = []
    
    marked_faces = {}
    marked_points = []
    original_selected_objects = set()
    use_depsgraph = False
    
    def modal(self, context, event):
        # Update status bar
        has_marked = bool(self.marked_faces)
        has_points = bool(self.marked_points)
        status_text = "Space: Create Hull"
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
                f"{status_text} | LMB: Mark/Unmark | C: Coplanar ({coplanar_state}) | P: Backfaces ({backface_state}) | O: Preview Cull ({preview_cull_state}) | D: Depsgraph ({deps_state}) | 1-7: Angle Presets | Shift+Scroll: Angle ({int(round(degrees(context.scene.cursor_bbox_coplanar_angle)))}°) | Ctrl+Scroll: Snap Thresh | A: Add Point Mode | Z: Clear"
            )
        
        # Limit Plane Toggle (C) - Point Mode Only
        if self.point_mode and event.type == 'C' and event.value == 'PRESS':
             self.limit_plane_mode = not self.limit_plane_mode
             if self.limit_plane_mode:
                 # LOCK plane to current cursor
                 self.limitation_plane_matrix = context.scene.cursor.matrix.copy()
                 update_limitation_plane(self.limitation_plane_matrix)
                 enable_limitation_plane(context, self.limitation_plane_matrix)
                
                 # Calculate and cache edge intersections for snapping
                 self.cached_limit_intersections = []
                 if context.active_object and context.active_object.type == 'MESH':
                     origin = self.limitation_plane_matrix.to_translation()
                     normal = self.limitation_plane_matrix.col[2][:3] 
                     self.cached_limit_intersections = calculate_plane_edge_intersections(
                         context.active_object, 
                         mathutils.Vector(origin), 
                         mathutils.Vector(normal),
                         use_depsgraph=self.use_depsgraph
                     )
                     self.report({'INFO'}, f"Limitation Plane ON | {len(self.cached_limit_intersections)} pts")
             else:
                 self.limit_plane_mode = False
                 self.limitation_plane_matrix = None
                 clear_limitation_plane()
                 disable_limitation_plane(context)
                 self.cached_limit_intersections = []
                 self.report({'INFO'}, "Limitation Plane OFF")
             context.area.tag_redraw()
             return {'RUNNING_MODAL'}
        
        # Toggle Depsgraph (D)
        if event.type == 'D' and event.value == 'PRESS':
            self.use_depsgraph = not self.use_depsgraph
            # Rebuild visuals with new setting
            for obj, faces in self.marked_faces.items():
                rebuild_marked_faces_visual_data(obj, faces, use_depsgraph=self.use_depsgraph)
            
            # Update Preview
            update_marked_faces_convex_hull(self.marked_faces, self.push_value, 
                                   marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)
            
            # Need to update preview if active
            # update_marked_faces_convex_hull likely needs update too - but I can't edit it yet as I haven't seen it in core.py fully.
            # Assuming it takes dict. It calculates hull from points.
            # But the POINTS come from `marked_faces` dict logic inside it?
            # Actually `update_marked_faces_convex_hull` is imported from core?
            # Yes, line 22. 
            # I must assume I need to update THAT function signature in `core.py` as well.
            # For now let's pass it if possible, but python will error if sig mismatch.
            # So I will edit `core.py` next for `update_marked_faces_convex_hull`.
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
             
        elif event.type == 'S' and event.value == 'PRESS':
            if self.point_mode:
                self.snap_enabled = not self.snap_enabled
                state_str = "ON" if self.snap_enabled else "OFF"
                self.report({'INFO'}, f"Point Snap: {state_str}")
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
            
            # Determine step size: 1 degree if Ctrl is held, otherwise 5 degrees
            step = 1 if event.ctrl else 5
            
            if event.type == 'WHEELUPMOUSE':
                new_angle_deg = current_deg + step
            else:
                new_angle_deg = current_deg - step
                
            # Clamp and set
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
                    f"Space: Create Hull{marking_status} | LMB: Mark/Unmark | Ctrl+Scroll: Snap Thresh ({self.snap_threshold}px) | A: Point Mode | Z: Clear | RMB/ESC: Cancel"
                )
            
            return {'RUNNING_MODAL'}

        # Navigation (Pass through unless Shift is held for angle adjustment or Ctrl for snap threshold)
        if event.type == 'MIDDLEMOUSE' or (event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and not event.shift and not event.ctrl):
            return {'PASS_THROUGH'}
            
        # Create Hull (Enter/Space)
        if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and event.value == 'PRESS':
            
            if self.marked_faces or self.marked_points:
                if create_convex_hull_from_marked(self.marked_faces, self.marked_points, self.push_value, select_new_object=False, use_depsgraph=self.use_depsgraph):
                    self.report({'INFO'}, "Created Convex Hull. Ready for new selection.")
                    # Clear markings after successful creation
                    clear_all_markings()
                    clear_preview_faces()
                    self.marked_faces.clear()
                    self.marked_points.clear()
                    # Ensure preview is cleared visually
                    context.area.tag_redraw()
                    return {'RUNNING_MODAL'}
                else:
                    self.report({'WARNING'}, "Failed to create Convex Hull")
            else:
                # If nothing marked, pass through to allow standard selection/interaction or warn?
                # The user instruction suggests this tool is FOR marked stuff.
                # But to maintain consistency, we just return running modal if nothing is marked.
                pass
                
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
                
                # Update Preview
                update_marked_faces_convex_hull(self.marked_faces, self.push_value, 
                                       marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}

            # Normal Mark Face Logic
            face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
            if face_data and face_data['object'] in self.original_selected_objects:
                obj = face_data['object']
                obj = face_data['object']
                face_idx = face_data['face_index']
                
                if obj not in self.marked_faces:
                    self.marked_faces[obj] = set()
                
                if face_idx in self.marked_faces[obj]:
                    # Unmark logic
                    faces_to_process = get_faces_to_process(
                        obj, face_idx, context.scene.cursor_bbox_select_coplanar,
                        context.scene.cursor_bbox_coplanar_angle, use_depsgraph=self.use_depsgraph
                    )

                    for idx in faces_to_process:
                        if idx in self.marked_faces[obj]:
                            self.marked_faces[obj].remove(idx)
                    
                    if not self.marked_faces[obj]:
                        del self.marked_faces[obj]
                        # Visual cleanup handled by rebuild or unmark (but unmark is single)
                        # Rebuild is safer for batch changes
                        # But unmark_face clears specific cache or triggers rebuild if empty.
                        # Ideally we need batch unmark.
                        # Let's just rebuild whole object visual
                        clear_marked_faces() # Too aggressive? No.
                        # We deleted the key above. So we just need to clear visuals for this obj.
                        # rebuild_marked_faces_visual_data handles empty/deleted key too?
                        rebuild_marked_faces_visual_data(obj, set(), use_depsgraph=self.use_depsgraph)
                    else:
                        rebuild_marked_faces_visual_data(obj, self.marked_faces[obj], use_depsgraph=self.use_depsgraph)
                else:
                    # Mark logic
                    faces_to_process = get_faces_to_process(
                        obj, face_idx, context.scene.cursor_bbox_select_coplanar,
                        context.scene.cursor_bbox_coplanar_angle, use_depsgraph=self.use_depsgraph
                    )
                         
                    for idx in faces_to_process:
                        self.marked_faces[obj].add(idx)
                    
                    # Batch update visual
                    rebuild_marked_faces_visual_data(obj, self.marked_faces[obj], use_depsgraph=self.use_depsgraph)
                
                # Update Preview
                update_marked_faces_convex_hull(self.marked_faces, self.push_value, 
                                       marked_points=self.marked_points, use_depsgraph=self.use_depsgraph)
                
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
            
        # Toggle Coplanar Selection (C)
        elif event.type == 'C' and event.value == 'PRESS':
            context.scene.cursor_bbox_select_coplanar = not context.scene.cursor_bbox_select_coplanar
            state = "ON" if context.scene.cursor_bbox_select_coplanar else "OFF"
            self.report({'INFO'}, f"Coplanar Selection: {state}")
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
            
        # Add Point Mode Toggle (A)
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
            
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        # Mouse Move - Update Preview (Hover)
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
                else:
                    clear_preview_point()
                
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}

            # Normal Hover Logic
            face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
            if face_data and face_data['object'] in self.original_selected_objects:
                obj = face_data['object']
                obj = face_data['object']
                face_idx = face_data['face_index']
                
                # Determine what would be selected
                faces_to_preview = get_faces_to_process(
                    obj, face_idx, context.scene.cursor_bbox_select_coplanar,
                    context.scene.cursor_bbox_coplanar_angle, use_depsgraph=self.use_depsgraph
                )
                
                update_preview_faces(obj, faces_to_preview, use_depsgraph=self.use_depsgraph)
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
        elif event.type == 'ESC':
            disable_edge_highlight()
            disable_bbox_preview()
            disable_face_marking()
            clear_all_markings()
            clear_preview_faces()
            clear_preview_point()
            clear_limitation_plane()
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
            context.area.header_text_set(None)
            context.area.tag_redraw()
            return {'FINISHED'}
            
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
                if create_convex_hull_from_marked(self.marked_faces, self.marked_points, self.push_value, select_new_object=False):
                    # Restore Edit Mode
                    if active_obj:
                        context.view_layer.objects.active = active_obj
                        bpy.ops.object.mode_set(mode='EDIT')
                        
                    self.report({'INFO'}, "Created Convex Hull from selection")
                    return {'FINISHED'}
                else:
                     self.report({'WARNING'}, "Failed to create Convex Hull from selection")
                     # If failed, we might be in Object Mode now. Restore Edit Mode if possible
                     if active_obj:
                        context.view_layer.objects.active = active_obj
                        bpy.ops.object.mode_set(mode='EDIT')
                     pass

        if context.area.type == 'VIEW_3D':
            # self.marked_faces and properties already initialized above
            
            # Store original selected objects to restrict interaction
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
