import bpy

class CursorBBox_MT_pie_menu(bpy.types.Menu):
    bl_label = "Cursor BBox Pie"
    bl_idname = "CURSOR_BBOX_MT_pie_menu"

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()
        scene = context.scene

        # West: Interactive Box
        op = pie.operator("cursor_bbox.interactive_box", text="Interactive Box", icon='CUBE')
        op.push_value = scene.cursor_bbox_push
        op.align_to_face = scene.cursor_bbox_align_face

        # East: Decomposition group
        col = pie.column()
        col.separator(factor=1.5)
        box = col.box().column(align=True)
        box.label(text="Decomposition", icon='MOD_MESHDEFORM')
        box.separator(factor=0.3)

        # Per-method Detail preset dropdown + run button, side by side.
        # The preset EnumProperty rewrites the method's detail values via its
        # own update callback (see settings/properties.py).
        for pg_name, op_id, label in (
            ("cursor_bbox_vhacd", "cursor_bbox.collision_vhacd", "V-HACD"),
            ("cursor_bbox_coacd", "cursor_bbox.collision_coacd", "CoACD"),
            ("cursor_bbox_coacd_u", "cursor_bbox.collision_coacd_u", "CoACD-U"),
        ):
            # Explicit 50/50 split: the pie's auto width-distribution can drop
            # the trailing operator on some rows, so allocate both cells.
            row = box.split(factor=0.5, align=True)
            row.prop(getattr(scene, pg_name), "preset", text="")
            row.operator(op_id, text=label)

        box.separator(factor=0.3)
        op = box.operator("cursor_bbox.hull_per_island", text="Hull Per Island")
        op.push_value = scene.cursor_bbox_push
        box.separator(factor=0.3)
        box.operator("cursor_bbox.use_active_collection", text="Use Active Collection", icon='EYEDROPPER')

        # South: Interactive Hull
        op = pie.operator("cursor_bbox.interactive_hull", text="Interactive Hull", icon='MESH_ICOSPHERE')
        op.push_value = scene.cursor_bbox_push

        # North: Auto Fit Box
        op = pie.operator("cursor_bbox.set_and_fit_box", text="Auto Fit Box", icon='PIVOT_BOUNDBOX')
        op.push_value = scene.cursor_bbox_push
        op.align_to_face = scene.cursor_bbox_align_face

        # Northwest: Set Cursor Only
        op = pie.operator("cursor_bbox.set_cursor", text="Set Cursor Only", icon='CURSOR')
        op.align_to_face = scene.cursor_bbox_align_face

        # Northeast: From Selection
        op = pie.operator("cursor_bbox.create_box", text="From Selection", icon='SELECT_SET')
        op.push_value = scene.cursor_bbox_push

        # Southwest: Interactive Sphere
        op = pie.operator("cursor_bbox.interactive_sphere", text="Interactive Sphere", icon='MESH_UVSPHERE')

        # Southeast: Check | Fix Convexity
        row = pie.row(align=True)
        row.operator("cursor_bbox.check_convexity", text="Check Convexity", icon='CHECKMARK')
        op = row.operator("cursor_bbox.fix_convexity", text="Fix", icon='SHADERFX')
        op.area_threshold = scene.cursor_bbox_fix_area_threshold
        op.weld_distance = scene.cursor_bbox_fix_weld_distance
