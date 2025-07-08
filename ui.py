import bpy

class VIEW3D_PT_cursor_bbox_panel(bpy.types.Panel):
    """Creates a Panel in the 3D Viewport N-Panel"""
    bl_label = "Cursor BBox"
    bl_idname = "VIEW3D_PT_cursor_bbox"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Cursor BBox"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        box = layout.box()
        box.label(text="Cursor Placement:", icon='CURSOR')
        
        row = box.row()
        row.prop(scene, 'cursor_bbox_align_face', text="Align to Face")
        
        row = box.row()
        op = row.operator("view3d.cursor_place_raycast", text="Place Cursor", icon='PIVOT_CURSOR')
        op.align_to_face = scene.cursor_bbox_align_face
        
        box = layout.box()
        box.label(text="Bounding Box:", icon='CUBE')
        
        row = box.row()
        row.prop(scene, 'cursor_bbox_push', text="Push Value")
        
        row = box.row()
        op = row.operator("view3d.create_cursor_bbox", text="Create BBox", icon='CUBE')
        op.push_value = scene.cursor_bbox_push
        
        layout.separator()
        
        box = layout.box()
        box.label(text="Combined Action:", icon='TOOL_SETTINGS')
        
        row = box.row()
        op = row.operator("view3d.cursor_place_and_bbox", text="Place & Create BBox", icon='CURSOR')
        op.push_value = scene.cursor_bbox_push
        op.align_to_face = scene.cursor_bbox_align_face
        
        layout.separator()
        
        # Instructions
        box = layout.box()
        box.label(text="Instructions:", icon='INFO')
        col = box.column(align=True)
        col.label(text="• Select faces (Edit) or objects")
        col.label(text="• Click 'Place Cursor' then hover over face")
        col.label(text="• Yellow preview shows bounding box")
        col.label(text="• Mouse wheel: select edge (no modifiers)")
        col.label(text="• Green highlight shows selected edge")
        col.label(text="• Middle mouse: orbit/pan")
        col.label(text="• Shift+Wheel or Ctrl+Wheel: zoom/pan")
        col.label(text="• C to create BBox without placing cursor")
        col.label(text="• RMB or ESC to cancel")
        
        layout.separator()
        
        # Preferences shortcut
        box = layout.box()
        box.label(text="Settings:", icon='PREFERENCES')
        row = box.row()
        row.operator("preferences.addon_show", text="Open Addon Preferences", icon='SETTINGS').module = __package__