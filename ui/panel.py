import bpy

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

        # Subtle preferences button
        row = box.row()
        row.alignment = 'RIGHT'
        row.operator("preferences.addon_show", text="", icon='SETTINGS', emboss=False).module = __package__.split('.')[0]