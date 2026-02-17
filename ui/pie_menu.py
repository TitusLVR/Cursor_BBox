import bpy
from ..operators.interactive_box import CursorBBox_OT_interactive_box
from ..operators.interactive_hull import CursorBBox_OT_interactive_hull
from ..operators.interactive_sphere import CursorBBox_OT_interactive_sphere
from ..operators.set_and_fit_box import CursorBBox_OT_set_and_fit_box
from ..operators.set_cursor import CursorBBox_OT_set_cursor

class CursorBBox_MT_pie_menu(bpy.types.Menu):
    bl_label = "Cursor BBox Pie"
    bl_idname = "CURSOR_BBOX_MT_pie_menu"

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()
        scene = context.scene

        # West: Interactive Box
        # We need to access operator properties, so we use the layout.operator method
        op = pie.operator("cursor_bbox.interactive_box", text="Interactive Box", icon='CUBE')
        op.push_value = scene.cursor_bbox_push
        op.align_to_face = scene.cursor_bbox_align_face

        # East: Interactive Hull
        op = pie.operator("cursor_bbox.interactive_hull", text="Interactive Hull", icon='MESH_ICOSPHERE')
        op.push_value = scene.cursor_bbox_push
        
        # South: Interactive Sphere
        op = pie.operator("cursor_bbox.interactive_sphere", text="Interactive Sphere", icon='MESH_UVSPHERE')
        
        # North: Auto Fit Box (Smart Action)
        op = pie.operator("cursor_bbox.set_and_fit_box", text="Auto Fit Box", icon='PIVOT_BOUNDBOX')
        op.push_value = scene.cursor_bbox_push
        op.align_to_face = scene.cursor_bbox_align_face

        # Northwest: Set Cursor Only
        op = pie.operator("cursor_bbox.set_cursor", text="Set Cursor Only", icon='CURSOR')
        op.align_to_face = scene.cursor_bbox_align_face
        
        # Northeast: Box From Selection
        op = pie.operator("cursor_bbox.create_box", text="From Selection", icon='SELECT_SET')
        op.push_value = scene.cursor_bbox_push

        # Southwest: V-HACD Decomposition
        pie.operator("cursor_bbox.collision_vhacd", text="V-HACD", icon='MOD_MESHDEFORM')

        # Southeast: CoACD Decomposition
        pie.operator("cursor_bbox.collision_coacd", text="CoACD", icon='MOD_MESHDEFORM')

        # Extra: CoACD-U Decomposition (overflow column)
        pie.operator("cursor_bbox.collision_coacd_u", text="CoACD-U (Fast)", icon='MOD_MESHDEFORM')
