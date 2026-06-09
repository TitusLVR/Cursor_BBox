import bpy
import bmesh
from mathutils import Vector, Matrix
from math import radians, degrees
from ..functions.utils import (
    restore_selection_state,
    set_cursor_rotation_to_principal_plane,
    CURSOR_PLANE_ALIGNMENTS,
    get_face_edges_from_raycast,
    select_edge_by_scroll,
    place_cursor_with_raycast_and_edge,
    snap_cursor_to_closest_element,
    get_connected_coplanar_faces,
    project_point_to_plane_intersection,
    calculate_plane_edge_intersections,
    calculate_plane_edge_intersections_multi,
    ensure_cbb_collection,
    ensure_cbb_material,
    assign_object_styles,
    get_cursor_rotation_euler,
    get_selected_faces_from_edit_mode,
    calculate_point_location,
    get_faces_to_process,
    is_collection_instance,
    make_collection_instance_real,
    cleanup_collection_instance_temp,
    build_all_faces_dict
)
from ..functions.core import (
    enable_edge_highlight_wrapper as enable_edge_highlight,
    disable_edge_highlight_wrapper as disable_edge_highlight,
    enable_bbox_preview_wrapper as enable_bbox_preview,
    disable_bbox_preview_wrapper as disable_bbox_preview,
    enable_face_marking_wrapper as enable_face_marking,
    disable_face_marking_wrapper as disable_face_marking,
    mark_face,
    mark_faces_batch,
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
    update_snap_targets_preview,
    clear_snap_targets_preview,
    update_limitation_plane,
    clear_limitation_plane,
    enable_limitation_plane_wrapper as enable_limitation_plane,
    disable_limitation_plane_wrapper as disable_limitation_plane
)
from ..settings.preferences import get_preferences
from ..ui.hud.controller import HUDController
from ..ui.hud.items import HUDItem, HUDSection, HUDParam, ItemState
from ..functions.undo_stack import OperatorUndoStack

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
    # Snap mode: 0=all, 1=vertex, 2=edge, 3=face (keys 1, 2, 3 in point mode)
    snap_mode: bpy.props.IntProperty(name="Snap Mode", default=1, min=0, max=3)  # 1=vertex default
    # Cursor plane alignment in point mode: 0=XY, 1=YZ, 2=XZ (R cycles)
    cursor_plane_align: bpy.props.IntProperty(name="Cursor Plane", default=0, min=0, max=2)
    
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
    
    # --- undo/redo --------------------------------------------------
    def _snapshot(self):
        return {
            'marked_faces': {obj: set(faces)
                             for obj, faces in self.marked_faces.items()},
            'marked_points': [Vector(p) for p in self.marked_points],
        }

    def _restore_snapshot(self, snap, context):
        self.marked_faces = {obj: set(faces)
                             for obj, faces in snap['marked_faces'].items()}
        self.marked_points = [Vector(p) for p in snap['marked_points']]
        clear_all_markings()
        for obj, faces in self.marked_faces.items():
            if faces:
                mark_faces_batch(obj, faces, use_depsgraph=self.use_depsgraph)
        for p in self.marked_points:
            add_marked_point(p)
        if self.marked_faces or self.marked_points:
            cursor_rotation = get_cursor_rotation_euler(context)
            update_marked_faces_sphere(
                self.marked_faces,
                context.scene.cursor.location, cursor_rotation,
                marked_points=self.marked_points,
                use_depsgraph=self.use_depsgraph)
        else:
            clear_preview_faces()
        if context.area is not None:
            context.area.tag_redraw()

    def _push_undo(self):
        self.undo_stack.push(self._snapshot())

    def _setup_hud(self, context):
        """Build the HUDOverlay + HelpOverlay shown while this modal runs."""
        self.hud_ctl = HUDController("interactive_sphere", "Interactive Sphere")
        self.hud_ctl.help.add_section(HUDSection("Object Mode", [
            HUDItem("Mark / unmark face", "LMB"),
            HUDItem("Mark all polygons", "Ctrl+A"),
            HUDItem("Create sphere", "SPACE"),
            HUDItem("Enter point mode", "A"),
            HUDItem("Toggle coplanar", "C"),
            HUDItem("Toggle depsgraph", "D"),
            HUDItem("Toggle backface render", "P"),
            HUDItem("Toggle preview culling", "O"),
            HUDItem("Clear markings", "Z"),
            HUDItem("Coplanar angle 1°/5°", "Shift+Wheel"),
            HUDItem("Undo / Redo", "Ctrl+Z / Ctrl+Shift+Z"),
            HUDItem("Confirm", "RMB"),
            HUDItem("Cancel", "ESC"),
        ]))
        self.hud_ctl.help.add_section(HUDSection("Point Mode", [
            HUDItem("Add point", "LMB"),
            HUDItem("Snap on/off", "S"),
            HUDItem("Snap to Vert / Edge / Face", "1 / 2 / 3"),
            HUDItem("Cycle cursor plane", "R"),
            HUDItem("Set cursor location", "E"),
            HUDItem("Snap threshold", "Ctrl+Wheel"),
            HUDItem("Toggle limit plane", "C"),
            HUDItem("Exit point mode", "A"),
        ]))
        from ..functions.utils import CURSOR_PLANE_ALIGNMENTS as _PLANES
        _mode_names = ("All", "Vert", "Edge", "Face")
        self.hud_ctl.hud.add_param(HUDParam(
            "Mode", lambda: "POINT" if self.point_mode else "MARK"))
        self.hud_ctl.hud.add_param(HUDParam(
            "Marked faces",
            lambda: sum(len(v) for v in self.marked_faces.values()),
            kind="int"))
        self.hud_ctl.hud.add_param(HUDParam(
            "Marked points",
            lambda: len(self.marked_points),
            kind="int"))
        self.hud_ctl.hud.add_param(HUDParam(
            "Coplanar angle°",
            lambda: int(round(degrees(context.scene.cursor_bbox_coplanar_angle))),
            kind="int"))
        self.hud_ctl.hud.add_param(HUDParam(
            "Depsgraph", lambda: self.use_depsgraph, kind="bool"))
        self.hud_ctl.hud.add_param(HUDParam(
            "Backface", lambda: get_backface_rendering(), kind="bool"))
        self.hud_ctl.hud.add_param(HUDParam(
            "Preview cull", lambda: get_preview_culling(), kind="bool"))
        self.hud_ctl.hud.add_param(HUDParam(
            "Snap", lambda: self.snap_enabled, kind="bool",
            visible_getter=lambda: self.point_mode))
        self.hud_ctl.hud.add_param(HUDParam(
            "Snap mode",
            lambda: _mode_names[getattr(self, 'snap_mode', 1)],
            visible_getter=lambda: self.point_mode))
        self.hud_ctl.hud.add_param(HUDParam(
            "Snap threshold px",
            lambda: getattr(self, 'snap_threshold', 0),
            kind="int",
            visible_getter=lambda: self.point_mode))
        self.hud_ctl.hud.add_param(HUDParam(
            "Cursor plane",
            lambda: _PLANES[getattr(self, 'cursor_plane_align', 0)],
            visible_getter=lambda: self.point_mode))
        self.hud_ctl.hud.add_param(HUDParam(
            "Limit plane",
            lambda: self.limit_plane_mode,
            kind="bool",
            visible_getter=lambda: self.point_mode))
        self.hud_ctl.attach(context)

    def modal(self, context, event):
        # HUD: capture event for cursor-follow + forward toggle/drag events.
        if hasattr(self, 'hud_ctl') and self.hud_ctl is not None:
            self.hud_ctl.update_event(event, context)
            if self.hud_ctl.handle_events(context, event):
                return {'RUNNING_MODAL'}

        # Undo / Redo (Ctrl+Z / Ctrl+Shift+Z)
        if (event.type == 'Z' and event.value == 'PRESS'
                and event.ctrl and not event.alt):
            if event.shift:
                snap = self.undo_stack.pop_redo(self._snapshot())
                if snap is not None:
                    self._restore_snapshot(snap, context)
                    self.report({'INFO'}, "Redo")
                else:
                    self.report({'INFO'}, "Nothing to redo")
            else:
                snap = self.undo_stack.pop_undo(self._snapshot())
                if snap is not None:
                    self._restore_snapshot(snap, context)
                    self.report({'INFO'}, "Undo")
                else:
                    self.report({'INFO'}, "Nothing to undo")
            return {'RUNNING_MODAL'}

        # Mark all polygons of all selected objects (Ctrl+A)
        if (event.type == 'A' and event.value == 'PRESS'
                and event.ctrl and not self.point_mode):
            self._push_undo()
            self.marked_faces = build_all_faces_dict(
                self.original_selected_objects, use_depsgraph=self.use_depsgraph)
            clear_all_markings()
            for obj, faces in self.marked_faces.items():
                if faces:
                    mark_faces_batch(obj, faces, use_depsgraph=self.use_depsgraph)
            cursor_rotation = get_cursor_rotation_euler(context)
            update_marked_faces_sphere(self.marked_faces,
                                       context.scene.cursor.location,
                                       cursor_rotation,
                                       marked_points=self.marked_points,
                                       use_depsgraph=self.use_depsgraph)
            total = sum(len(v) for v in self.marked_faces.values())
            self.report({'INFO'}, f"Marked all polygons ({total}) of selected objects")
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        # Snap mode 1=Vertex, 2=Edge, 3=Face (point mode only)
        if self.point_mode and event.value == 'PRESS':
            if event.type in ('ONE', 'NUMPAD_1'):
                self.snap_mode = 1
                self.report({'INFO'}, "Snap: Vertex only")
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            if event.type in ('TWO', 'NUMPAD_2'):
                self.snap_mode = 2
                self.report({'INFO'}, "Snap: Edge only")
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
            if event.type in ('THREE', 'NUMPAD_3'):
                self.snap_mode = 3
                self.report({'INFO'}, "Snap: Face only")
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}
        
        # Reset cursor rotation to principal plane (R) - point mode only
        if self.point_mode and event.type == 'R' and event.value == 'PRESS':
            self.cursor_plane_align = (self.cursor_plane_align + 1) % 3
            plane = CURSOR_PLANE_ALIGNMENTS[self.cursor_plane_align]
            set_cursor_rotation_to_principal_plane(context, plane)
            if self.limit_plane_mode:
                self.limitation_plane_matrix = context.scene.cursor.matrix.copy()
                update_limitation_plane(self.limitation_plane_matrix)
                origin = self.limitation_plane_matrix.to_translation()
                normal = Vector(self.limitation_plane_matrix.col[2][:3])
                self.cached_limit_intersections = []
                if self.marked_faces:
                    objects = list(self.marked_faces.keys())
                    self.cached_limit_intersections = calculate_plane_edge_intersections_multi(
                        objects, origin, normal, use_depsgraph=self.use_depsgraph
                    )
                elif context.active_object and context.active_object.type == 'MESH':
                    self.cached_limit_intersections = calculate_plane_edge_intersections(
                        context.active_object, origin, normal, use_depsgraph=self.use_depsgraph
                    )
            self.report({'INFO'}, f"Cursor: {plane}")
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        # E: Set cursor location only (to current hover/snap position) and update limitation plane
        if self.point_mode and event.type == 'E' and event.value == 'PRESS':
            face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
            if face_data:
                cursor = context.scene.cursor
                if self.snap_enabled:
                    intersection_pts = self.cached_limit_intersections if self.limit_plane_mode else None
                    snap_result = snap_cursor_to_closest_element(
                        context, event, face_data, threshold=self.snap_threshold,
                        intersection_points=intersection_pts, use_depsgraph=self.use_depsgraph, snap_mode=self.snap_mode
                    )
                    if not snap_result['success']:
                        cursor.location = face_data['hit_location'].copy()
                elif self.limit_plane_mode and self.limitation_plane_matrix:
                    plane_origin = self.limitation_plane_matrix.to_translation()
                    plane_normal = self.limitation_plane_matrix.col[2].to_3d()
                    proj_pt = project_point_to_plane_intersection(
                        face_data['hit_location'], face_data['face_normal'], plane_origin, plane_normal
                    )
                    if proj_pt:
                        cursor.location = proj_pt
                    else:
                        cursor.location = face_data['hit_location'].copy()
                else:
                    cursor.location = face_data['hit_location'].copy()
                if self.limit_plane_mode:
                    self.limitation_plane_matrix = cursor.matrix.copy()
                    update_limitation_plane(self.limitation_plane_matrix)
                    origin = self.limitation_plane_matrix.to_translation()
                    normal = Vector(self.limitation_plane_matrix.col[2][:3])
                    self.cached_limit_intersections = []
                    if self.marked_faces:
                        objects = list(self.marked_faces.keys())
                        self.cached_limit_intersections = calculate_plane_edge_intersections_multi(
                            objects, origin, normal, use_depsgraph=self.use_depsgraph
                        )
                    elif context.active_object and context.active_object.type == 'MESH':
                        self.cached_limit_intersections = calculate_plane_edge_intersections(
                            context.active_object, origin, normal, use_depsgraph=self.use_depsgraph
                        )
                self.report({'INFO'}, "Cursor location updated")
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        
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
            
            return {'RUNNING_MODAL'}

        # Navigation
        if event.type == 'MIDDLEMOUSE' or (event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and not event.shift and not event.alt and not event.ctrl):
            return {'PASS_THROUGH'}
            
        # Create Sphere (Enter/Space)
        if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and event.value == 'PRESS':
            if self.marked_faces or self.marked_points:
                self._push_undo()
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
                    use_depsgraph=self.use_depsgraph, snap_mode=self.snap_mode
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
                # Always align limitation plane to cursor when pressing C
                self.limitation_plane_matrix = context.scene.cursor.matrix.copy()
                update_limitation_plane(self.limitation_plane_matrix)
                enable_limitation_plane(context, self.limitation_plane_matrix)
                # Calculate and cache edge intersections for snapping
                self.cached_limit_intersections = []
                origin = self.limitation_plane_matrix.to_translation()
                normal = Vector(self.limitation_plane_matrix.col[2][:3])
                if self.marked_faces:
                    objects = list(self.marked_faces.keys())
                    self.cached_limit_intersections = calculate_plane_edge_intersections_multi(
                        objects, origin, normal, use_depsgraph=self.use_depsgraph
                    )
                elif context.active_object and context.active_object.type == 'MESH':
                    self.cached_limit_intersections = calculate_plane_edge_intersections(
                        context.active_object, origin, normal, use_depsgraph=self.use_depsgraph
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
        elif event.type == 'A' and event.value == 'PRESS' and not event.ctrl:
            self.point_mode = not self.point_mode
            if self.point_mode:
                self.report({'INFO'}, "Entered Add Point Mode")
                self.current_face_data = None # Reset selection
                clear_preview_faces()
            else:
                self.report({'INFO'}, "Exited Add Point Mode")
                clear_preview_point()
                clear_snap_targets_preview()
                self.limit_plane_mode = False
                clear_limitation_plane()
            
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
            
        # Left Mouse Click (Add Point in Mode OR Mark Face)
        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self._push_undo()
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
                     snap_result = snap_cursor_to_closest_element(context, event, face_data, threshold=self.snap_threshold, use_depsgraph=self.use_depsgraph, snap_mode=self.snap_mode)
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
                     snap_result = snap_cursor_to_closest_element(context, event, face_data, threshold=self.snap_threshold, use_depsgraph=self.use_depsgraph, snap_mode=self.snap_mode)
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
                if not self.snap_enabled:
                    clear_snap_targets_preview()
                state_str = "ON" if self.snap_enabled else "OFF"
                self.report({'INFO'}, f"Point Snap: {state_str}")
            else:
                 # Snap cursor to closest vertex, edge midpoint, or face center from current face
                face_data = get_face_edges_from_raycast(context, event, use_depsgraph=self.use_depsgraph)
                result = snap_cursor_to_closest_element(context, event, face_data, threshold=self.snap_threshold, use_depsgraph=self.use_depsgraph, snap_mode=self.snap_mode)
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
                    snap_result = snap_cursor_to_closest_element(context, event, face_data, threshold=self.snap_threshold, intersection_points=intersection_pts, use_depsgraph=self.use_depsgraph, snap_mode=self.snap_mode)
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
                if self.snap_enabled and (face_data or (self.limit_plane_mode and self.cached_limit_intersections)):
                    intersection_pts = self.cached_limit_intersections if self.limit_plane_mode else None
                    update_snap_targets_preview(face_data, self.snap_mode, intersection_points=intersection_pts)
                else:
                    clear_snap_targets_preview()
                    
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
            if self.marked_faces or self.marked_points:
                self._push_undo()
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
            clear_snap_targets_preview()
            clear_limitation_plane()
            self.cleanup_all_instances(context)  # Clean up collection instances
            restore_selection_state(context, self._restore_selected, self._restore_active)
            if hasattr(self, 'hud_ctl') and self.hud_ctl is not None:
                self.hud_ctl.detach(context)
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
            clear_snap_targets_preview()
            clear_limitation_plane()
            self.cleanup_all_instances(context)  # Clean up collection instances
            restore_selection_state(context, self._restore_selected, self._restore_active)
            if hasattr(self, 'hud_ctl') and self.hud_ctl is not None:
                self.hud_ctl.detach(context)
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
        self.undo_stack = OperatorUndoStack()

        # Get use_depsgraph from preferences
        prefs = get_preferences()
        if prefs:
            self.use_depsgraph = prefs.use_depsgraph
        else:
            self.use_depsgraph = True # Default fallback
        
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
            # Store for restoration on finish/cancel (do not lose selection)
            self._restore_selected = list(context.selected_objects)
            self._restore_active = context.view_layer.objects.active
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
            self._setup_hud(context)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Active space must be a View3D")
            return {'CANCELLED'}
