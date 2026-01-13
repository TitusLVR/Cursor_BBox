import bpy
import bmesh
from mathutils import Vector
from math import radians, degrees
from ..functions.utils import get_face_edges_from_raycast, select_edge_by_scroll, place_cursor_with_raycast_and_edge, snap_cursor_to_closest_element, get_connected_coplanar_faces, ensure_cbb_collection
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
    clear_preview_faces
)

def create_convex_hull_from_marked(marked_faces_dict, marked_points=None, push_value=0.0):
    """Create a convex hull from marked faces and points"""
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
        
    # Create new mesh for convex hull
    bm = bmesh.new()
    for v in all_vertices:
        bm.verts.new(v)
    
    # Ensure vertices are valid
    bm.verts.ensure_lookup_table()
    
    # Calculate convex hull
    try:
        bmesh.ops.convex_hull(bm, input=bm.verts)
        
        # Remove interior geometry and ensure normals
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        
        # Apply Push Value (Inflate along normals)
        if abs(push_value) > 0.0001:
            # Simple vertex normal calculation
            # Note: bmesh doesn't maintain vertex normals automatically valid after ops without update
            # But we can approximate by averaging face normals
            
            # Create a dictionary for vert normals
            vert_normals = {v: Vector((0,0,0)) for v in bm.verts}
            for f in bm.faces:
                for v in f.verts:
                    vert_normals[v] += f.normal
            
            # Normalize and move
            for v in bm.verts:
                if vert_normals[v].length_squared > 0:
                    normal = vert_normals[v].normalized()
                    v.co += normal * push_value
                    
        # Create object
        mesh_data = bpy.data.meshes.new("ConvexHull")
        bm.to_mesh(mesh_data)
        bm.free()
        
        if not context.scene.cursor_bbox_name_hull: # Fallback if property not initialized? No, default handles it.
             hull_name = "Convex"
        else:
             hull_name = context.scene.cursor_bbox_name_hull
             
        obj = bpy.data.objects.new(hull_name, mesh_data)
        cbb_coll = ensure_cbb_collection(context)
        cbb_coll.objects.link(obj)
        
        # Handle Selection: Keep original ACTIVE and SELECTED
        
        # Deselect everything first to ensure clean state for the new object (optional, but good for clarity)
        # But user wants to KEEP selection.
        
        # Strategy: 
        # 1. Ensure new object is selected (so user sees it)
        # 2. Ensure original objects are selected
        # 3. Ensure original active is active.
        
        for o in context.selected_objects:
            o.select_set(False)
            
        # Select original objects
        for o in original_selected:
            try:
                o.select_set(True)
            except:
                pass
                
        # Select new Hull
        obj.select_set(True)
        
        # Restore active object
        if original_active:
            context.view_layer.objects.active = original_active
        else:
            # If no original active, make hull active
            context.view_layer.objects.active = obj
        
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
    
    marked_faces = {}
    marked_points = []
    original_selected_objects = set()
    
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
        
        context.area.header_text_set(
            f"{status_text} | LMB: Mark/Unmark | C: Toggle | Shift(+Ctrl)+Scroll: Angle ({int(round(degrees(context.scene.cursor_bbox_coplanar_angle)))}°) | A: Add Point | Z: Clear"
        )
        
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

        # Navigation (Pass through unless Shift is held for angle adjustment)
        if event.type == 'MIDDLEMOUSE' or (event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and not event.shift):
            return {'PASS_THROUGH'}
            
        # Create Hull (Enter/Space)
        if event.type in {'RET', 'NUMPAD_ENTER', 'SPACE'} and event.value == 'PRESS':
            
            if self.marked_faces or self.marked_points:
                if create_convex_hull_from_marked(self.marked_faces, self.marked_points, self.push_value):
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
            face_data = get_face_edges_from_raycast(context, event)
            if face_data and face_data['object'] in self.original_selected_objects:
                obj = face_data['object']
                obj = face_data['object']
                face_idx = face_data['face_index']
                
                if obj not in self.marked_faces:
                    self.marked_faces[obj] = set()
                
                if face_idx in self.marked_faces[obj]:
                    # Unmark logic
                    if context.scene.cursor_bbox_select_coplanar:
                         # Unmark coplanar group
                         angle_rad = context.scene.cursor_bbox_coplanar_angle
                         coplanar_indices = get_connected_coplanar_faces(obj, face_idx, angle_rad)
                         faces_to_process = coplanar_indices if coplanar_indices else {face_idx}
                    else:
                         faces_to_process = {face_idx}

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
                        rebuild_marked_faces_visual_data(obj, set())
                    else:
                        rebuild_marked_faces_visual_data(obj, self.marked_faces[obj])
                else:
                    # Mark logic
                    if context.scene.cursor_bbox_select_coplanar:
                         angle_rad = context.scene.cursor_bbox_coplanar_angle
                         coplanar_indices = get_connected_coplanar_faces(obj, face_idx, angle_rad)
                         faces_to_process = coplanar_indices if coplanar_indices else {face_idx}
                    else:
                         faces_to_process = {face_idx}
                         
                    for idx in faces_to_process:
                        self.marked_faces[obj].add(idx)
                    
                    # Batch update visual
                    rebuild_marked_faces_visual_data(obj, self.marked_faces[obj])
                
                # Update Preview
                update_marked_faces_convex_hull(self.marked_faces, self.push_value, 
                                       marked_points=self.marked_points)
                
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
            
            # Update Preview
            update_marked_faces_convex_hull(self.marked_faces, self.push_value, 
                                   marked_points=self.marked_points)

            context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        # Mouse Move - Update Preview (Hover)
        elif event.type == 'MOUSEMOVE':
            face_data = get_face_edges_from_raycast(context, event)
            if face_data and face_data['object'] in self.original_selected_objects:
                obj = face_data['object']
                obj = face_data['object']
                face_idx = face_data['face_index']
                
                # Determine what would be selected
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
            # Initialize from Scene properties
            self.push_value = context.scene.cursor_bbox_push

            self.marked_faces = {}
            self.marked_points = []
            
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
