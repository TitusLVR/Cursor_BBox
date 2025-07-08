import bpy
from bpy.types import AddonPreferences
from bpy.props import FloatProperty, BoolProperty, FloatVectorProperty, StringProperty

class CursorBBoxPreferences(AddonPreferences):
    """Addon preferences for Cursor Aligned Bounding Box"""
    bl_idname = __package__
    
    # Default values
    default_push_value: FloatProperty(
        name="Default Push Value",
        description="Default push value for new bounding boxes",
        default=0.01,
        min=-1.0,
        max=1.0,
        precision=3
    )
    
    default_align_to_face: BoolProperty(
        name="Default Align to Face",
        description="Default setting for face alignment",
        default=True
    )
    
    # Edge highlight settings
    edge_highlight_color: FloatVectorProperty(
        name="Edge Highlight Color",
        description="Color for highlighted edges",
        subtype='COLOR',
        default=(0.0, 1.0, 0.0),
        min=0.0,
        max=1.0
    )
    
    edge_highlight_width: FloatProperty(
        name="Edge Highlight Width",
        description="Width of highlighted edges",
        default=4.0,
        min=1.0,
        max=10.0
    )
    
    # Bounding box settings
    bbox_show_wire: BoolProperty(
        name="Show Wireframe",
        description="Show wireframe for created bounding boxes",
        default=True
    )
    
    bbox_show_all_edges: BoolProperty(
        name="Show All Edges",
        description="Show all edges for created bounding boxes",
        default=True
    )
    
    # BBox preview settings
    bbox_preview_enabled: BoolProperty(
        name="Show BBox Preview",
        description="Show bounding box preview while placing cursor",
        default=True
    )
    
    bbox_preview_color: FloatVectorProperty(
        name="BBox Preview Color",
        description="Color for bounding box preview",
        subtype='COLOR',
        default=(1.0, 1.0, 0.0),  # Yellow
        min=0.0,
        max=1.0
    )
    
    bbox_preview_alpha: FloatProperty(
        name="BBox Preview Alpha",
        description="Transparency for bounding box preview wireframe",
        default=0.8,
        min=0.0,
        max=1.0
    )
    
    bbox_preview_line_width: FloatProperty(
        name="BBox Preview Line Width",
        description="Line width for bounding box preview",
        default=2.0,
        min=1.0,
        max=10.0
    )
    
    bbox_preview_show_faces: BoolProperty(
        name="Show Preview Faces",
        description="Show semi-transparent faces in bounding box preview",
        default=True
    )
    
    # Keyboard shortcuts
    enable_shortcuts: BoolProperty(
        name="Enable Keyboard Shortcuts",
        description="Enable addon keyboard shortcuts",
        default=True
    )
    
    cursor_place_key: StringProperty(
        name="Place Cursor Key",
        description="Key for placing cursor (with Ctrl+Shift)",
        default="C",
        maxlen=1
    )
    
    cursor_place_bbox_key: StringProperty(
        name="Place Cursor & BBox Key", 
        description="Key for placing cursor and creating bbox (with Ctrl+Shift+Alt)",
        default="B",
        maxlen=1
    )
    
    use_ctrl: BoolProperty(
        name="Use Ctrl",
        description="Require Ctrl key for shortcuts",
        default=True
    )
    
    use_shift: BoolProperty(
        name="Use Shift", 
        description="Require Shift key for shortcuts",
        default=True
    )
    
    use_alt_for_bbox: BoolProperty(
        name="Use Alt for BBox",
        description="Require Alt key for place & create bbox shortcut",
        default=True
    )
    
    def draw(self, context):
        layout = self.layout
        
        box = layout.box()
        box.label(text="Default Settings:", icon='SETTINGS')
        
        row = box.row()
        row.prop(self, "default_push_value")
        
        row = box.row()
        row.prop(self, "default_align_to_face")
        
        layout.separator()
        
        # BBox preview settings
        box = layout.box()
        box.label(text="Bounding Box Preview:", icon='GHOST_ENABLED')
        
        row = box.row()
        row.prop(self, "bbox_preview_enabled")
        
        if self.bbox_preview_enabled:
            row = box.row()
            row.prop(self, "bbox_preview_color")
            
            row = box.row()
            row.prop(self, "bbox_preview_alpha")
            
            row = box.row()
            row.prop(self, "bbox_preview_line_width")
            
            row = box.row()
            row.prop(self, "bbox_preview_show_faces")
        
        layout.separator()
        
        box = layout.box()
        box.label(text="Visual Settings:", icon='COLOR')
        
        row = box.row()
        row.prop(self, "edge_highlight_color")
        
        row = box.row()
        row.prop(self, "edge_highlight_width")
        
        layout.separator()
        
        box = layout.box()
        box.label(text="Bounding Box Display:", icon='CUBE')
        
        row = box.row()
        row.prop(self, "bbox_show_wire")
        
        row = box.row()
        row.prop(self, "bbox_show_all_edges")
        
        layout.separator()
        
        # Keyboard shortcuts section
        box = layout.box()
        box.label(text="Keyboard Shortcuts:", icon='KEYINGSET')
        
        row = box.row()
        row.prop(self, "enable_shortcuts")
        
        if self.enable_shortcuts:
            # Modifier keys
            sub_box = box.box()
            sub_box.label(text="Modifier Keys:")
            row = sub_box.row()
            row.prop(self, "use_ctrl", text="Ctrl")
            row.prop(self, "use_shift", text="Shift")
            row.prop(self, "use_alt_for_bbox", text="Alt (for BBox)")
            
            # Key assignments
            sub_box = box.box()
            sub_box.label(text="Key Assignments:")
            
            row = sub_box.row()
            row.prop(self, "cursor_place_key")
            
            # Show the actual shortcut combination
            modifiers = []
            if self.use_ctrl:
                modifiers.append("Ctrl")
            if self.use_shift:
                modifiers.append("Shift")
            shortcut_text = "+".join(modifiers + [self.cursor_place_key.upper()])
            row.label(text=f"= {shortcut_text}", icon='BLANK1')
            
            row = sub_box.row()
            row.prop(self, "cursor_place_bbox_key")
            
            # Show the actual shortcut combination for bbox
            bbox_modifiers = modifiers.copy()
            if self.use_alt_for_bbox:
                bbox_modifiers.append("Alt")
            bbox_shortcut_text = "+".join(bbox_modifiers + [self.cursor_place_bbox_key.upper()])
            row.label(text=f"= {bbox_shortcut_text}", icon='BLANK1')
            
            # Instructions
            sub_box = box.box()
            sub_box.label(text="Current Shortcuts:", icon='INFO')
            col = sub_box.column(align=True)
            col.label(text=f"• {shortcut_text}: Place Cursor with Raycast")
            col.label(text=f"• {bbox_shortcut_text}: Place Cursor & Create BBox")
            
            # Warning about restart
            if context.preferences.view.show_developer_ui:
                sub_box.separator()
                col = sub_box.column()
                col.alert = True
                col.label(text="Note: Restart Blender or reload addon for shortcut changes", icon='ERROR')
        
        else:
            box.label(text="Keyboard shortcuts are disabled", icon='X')

def get_preferences():
    """Get addon preferences"""
    try:
        return bpy.context.preferences.addons[__package__].preferences
    except:
        return None

def register():
    bpy.utils.register_class(CursorBBoxPreferences)

def unregister():
    bpy.utils.unregister_class(CursorBBoxPreferences)