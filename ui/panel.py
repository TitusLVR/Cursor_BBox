import bpy

from ..functions import async_subprocess


class CursorBBox_PT_main(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport N-Panel"""
    bl_label = "Cursor BBox"
    bl_idname = "CURSOR_BBOX_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Cursor BBox"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.use_property_split = True
        layout.use_property_decorate = False

        # --- Main Actions ---
        col = layout.column(align=True)
        col.label(text="Smart Actions", icon='MODIFIER')
        
        row = col.row(align=True)
        row.scale_y = 1.5
        op = row.operator("cursor_bbox.set_and_fit_box", text="Auto Fit Box", icon='PIVOT_BOUNDBOX')
        op.push_value = scene.cursor_bbox_push
        op.align_to_face = scene.cursor_bbox_align_face
        
        col.separator()

        # --- Generators ---
        # --- Generators ---
        col.label(text="Generators", icon='GEOMETRY_NODES')
        
        # Interactive Tools Group
        subcol = col.column(align=True)
        subcol.scale_y = 1.2
        
        op = subcol.operator("cursor_bbox.interactive_box", text="Interactive Box", icon='CUBE')
        op.push_value = scene.cursor_bbox_push
        op.align_to_face = scene.cursor_bbox_align_face
        
        op = subcol.operator("cursor_bbox.interactive_hull", text="Interactive Hull", icon='MESH_ICOSPHERE')
        op.push_value = scene.cursor_bbox_push
        
        op = subcol.operator("cursor_bbox.interactive_sphere", text="Interactive Sphere", icon='MESH_UVSPHERE')

        col.separator()
        
        # From Selection
        op = col.operator("cursor_bbox.create_box", text="From Selection", icon='SELECT_SET')
        op.push_value = scene.cursor_bbox_push

        layout.separator()

        # --- Collision Decomposition ---
        col = layout.column(align=True)
        col.label(text="Collision Decomposition", icon='MOD_MESHDEFORM')

        # Running-job status banner
        busy = async_subprocess.is_busy()
        if busy:
            status_box = col.box()
            status_col = status_box.column(align=True)
            for line in async_subprocess.get_status_lines():
                status_col.label(text=line, icon='SORTTIME')
            status_col.label(text="See System Console for output", icon='CONSOLE')
            status_col.operator(
                "cursor_bbox.cancel_decomposition",
                text="Cancel All", icon='CANCEL',
            )
            col.separator(factor=0.5)

        # ---- V-HACD foldable section ----
        vhacd = scene.cursor_bbox_vhacd
        box = col.box()
        row = box.row(align=True)
        row.prop(
            vhacd, "show_expanded",
            icon='TRIA_DOWN' if vhacd.show_expanded else 'TRIA_RIGHT',
            emboss=False, text="V-HACD",
        )
        if vhacd.show_expanded:
            sub = box.column(align=True)
            sub.prop(vhacd, "preset", text="Detail")
            sub.separator(factor=0.5)

            sub.prop(vhacd, "max_convex_hulls")
            sub.prop(vhacd, "resolution")
            sub.prop(vhacd, "min_volume_error")
            sub.prop(vhacd, "max_recursion_depth")
            sub.prop(vhacd, "max_vertices_per_hull")

            sub.separator(factor=0.5)
            sub.prop(vhacd, "fill_mode")
            sub.prop(vhacd, "shrink_wrap")
            sub.prop(vhacd, "min_edge_length")
            sub.prop(vhacd, "find_best_plane")

            sub.separator(factor=0.5)
            row = sub.row(align=True)
            row.scale_y = 1.3
            row.enabled = not busy
            row.operator("cursor_bbox.collision_vhacd", text="Run V-HACD", icon='PLAY')

        # ---- CoACD foldable section ----
        coacd = scene.cursor_bbox_coacd
        box = col.box()
        row = box.row(align=True)
        row.prop(
            coacd, "show_expanded",
            icon='TRIA_DOWN' if coacd.show_expanded else 'TRIA_RIGHT',
            emboss=False, text="CoACD",
        )
        if coacd.show_expanded:
            sub = box.column(align=True)
            sub.prop(coacd, "preset", text="Detail")
            sub.separator(factor=0.5)

            sub.prop(coacd, "threshold")
            sub.prop(coacd, "max_convex_hull")
            sub.prop(coacd, "approximate_mode")

            sub.separator(factor=0.5)
            sub.label(text="Preprocessing", icon='MODIFIER')
            sub.prop(coacd, "preprocess_mode")
            sub.prop(coacd, "prep_resolution")
            sub.prop(coacd, "pca")

            sub.separator(factor=0.5)
            sub.label(text="MCTS Search", icon='VIEWZOOM')
            sub.prop(coacd, "mcts_iteration")
            sub.prop(coacd, "mcts_depth")
            sub.prop(coacd, "mcts_nodes")

            sub.separator(factor=0.5)
            sub.label(text="Advanced", icon='PREFERENCES')
            sub.prop(coacd, "hausdorff_resolution")
            sub.prop(coacd, "rv_k")
            sub.prop(coacd, "no_merge")
            sub.prop(coacd, "decimate")
            if coacd.decimate:
                sub.prop(coacd, "max_ch_vertex")
            sub.prop(coacd, "extrude")
            if coacd.extrude:
                sub.prop(coacd, "extrude_margin")
            sub.prop(coacd, "seed")

            sub.separator(factor=0.5)
            row = sub.row(align=True)
            row.scale_y = 1.3
            row.enabled = not busy
            row.operator("cursor_bbox.collision_coacd", text="Run CoACD", icon='PLAY')

        # ---- CoACD-U foldable section ----
        coacd_u = scene.cursor_bbox_coacd_u
        box = col.box()
        row = box.row(align=True)
        row.prop(
            coacd_u, "show_expanded",
            icon='TRIA_DOWN' if coacd_u.show_expanded else 'TRIA_RIGHT',
            emboss=False, text="CoACD-U (Fast)",
        )
        if coacd_u.show_expanded:
            sub = box.column(align=True)
            sub.prop(coacd_u, "preset", text="Detail")
            sub.separator(factor=0.5)

            sub.prop(coacd_u, "threshold")
            sub.prop(coacd_u, "max_convex_hull")

            sub.separator(factor=0.5)
            sub.label(text="Preprocessing", icon='MODIFIER')
            sub.prop(coacd_u, "preprocess_mode")
            sub.prop(coacd_u, "prep_resolution")
            sub.prop(coacd_u, "pca")

            sub.separator(factor=0.5)
            sub.label(text="MCTS Search", icon='VIEWZOOM')
            sub.prop(coacd_u, "mcts_iterations")
            sub.prop(coacd_u, "mcts_max_depth")
            sub.prop(coacd_u, "mcts_nodes")

            sub.separator(factor=0.5)
            sub.label(text="Advanced", icon='PREFERENCES')
            sub.prop(coacd_u, "resolution")
            sub.prop(coacd_u, "merge")
            sub.prop(coacd_u, "seed")

            sub.separator(factor=0.5)
            row = sub.row(align=True)
            row.scale_y = 1.3
            row.enabled = not busy
            row.operator("cursor_bbox.collision_coacd_u", text="Run CoACD-U", icon='PLAY')

        layout.separator()

        # --- Utilities ---
        col = layout.column(align=True)
        col.label(text="Utilities", icon='TOOL_SETTINGS')
        
        row = col.row(align=True)
        op = row.operator("cursor_bbox.set_cursor", text="Set Cursor Only", icon='CURSOR')
        op.align_to_face = scene.cursor_bbox_align_face

        layout.separator()

        # --- Settings ---
        # Minimalist collapsible box or clear section
        box = layout.box()
        # Header with icon
        row = box.row()
        row.alignment = 'LEFT'
        row.label(text="Parameters", icon='PREFERENCES')
        
        col = box.column(align=True)
        col.prop(scene, 'cursor_bbox_push', text="Push Offset")
        col.prop(scene, 'cursor_bbox_align_face', text="Align to Face", toggle=True)        
        
        col.separator()        
        # Coplanar Logic
        row = col.row(align=True)
        row.prop(scene, 'cursor_bbox_select_coplanar', text="Auto-Select Coplanar", toggle=True)
        
        col.separator()
        col.prop(scene, 'cursor_bbox_use_material', text="Use Material")
        col.prop(scene, 'cursor_bbox_material_color', text="Color")
        
        if scene.cursor_bbox_select_coplanar:
            sub = col.column(align=True)
            sub.prop(scene, 'cursor_bbox_coplanar_angle', text="Angle Threshold")
            
        col.separator()
        
        # Naming & Collection
        row = col.row()
        row.alignment = 'LEFT'
        row.label(text="Naming & Collection", icon='OUTLINER_COLLECTION')
        
        col.prop(scene, 'cursor_bbox_collection_name', text="Collection")
        col.prop(scene, 'cursor_bbox_name_box', text="Bounding Box")
        col.prop(scene, 'cursor_bbox_name_sphere', text="Bounding Sphere")
        col.prop(scene, 'cursor_bbox_name_hull', text="Convex Hull")
        
        col.separator()
        
        # Hull-specific settings
        row = col.row()
        row.alignment = 'LEFT'
        row.label(text="Hull Options", icon='MESH_ICOSPHERE')
        
        col.prop(scene, 'cursor_bbox_hull_dissolve_angle', text="Dissolve Angle")
        col.prop(scene, 'cursor_bbox_hull_use_triangulate', text="Triangulate", toggle=True)
        
        # Show triangulation method options only if triangulation is enabled
        if scene.cursor_bbox_hull_use_triangulate:
            sub = col.column(align=True)
            sub.prop(scene, 'cursor_bbox_hull_triangulate_quads', text="Quad Method")
            sub.prop(scene, 'cursor_bbox_hull_triangulate_ngons', text="N-gon Method")

        # Subtle preferences button
        row = box.row()
        row.alignment = 'RIGHT'
        row.operator("preferences.addon_show", text="", icon='SETTINGS', emboss=False).module = __package__.split('.')[0]