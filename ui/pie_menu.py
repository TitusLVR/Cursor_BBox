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
        box.operator("cursor_bbox.collision_vhacd", text="V-HACD")
        box.operator("cursor_bbox.collision_coacd", text="CoACD")
        box.operator("cursor_bbox.collision_coacd_u", text="CoACD-U")

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

        # Southeast: (empty)
        pie.separator()
