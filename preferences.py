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
    
    # Face marking settings
    face_marking_color: FloatVectorProperty(
        name="Face Marking Color",
        description="Color for marked faces",
        subtype='COLOR',
        default=(1.0, 0.0, 0.0),
        min=0.0,
        max=1.0
    )
    
    face_marking_alpha: FloatProperty(
        name="Face Marking Alpha",
        description="Transparency for marked faces",
        default=0.3,
        min=0.0,
        max=1.0
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
    
    def draw(self, context):
        layout = self.layout
        
        # Default settings
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
        
        # Visual settings
        box = layout.box()
        box.label(text="Visual Settings:", icon='COLOR')
        
        row = box.row()
        row.prop(self, "edge_highlight_color")
        
        row = box.row()
        row.prop(self, "edge_highlight_width")
        
        layout.separator()
        
        # Face marking settings
        box = layout.box()
        box.label(text="Face Marking:", icon='FACE_MAPS')
        
        row = box.row()
        row.prop(self, "face_marking_color")
        
        row = box.row()
        row.prop(self, "face_marking_alpha")
        
        layout.separator()
        
        # Bounding box display
        box = layout.box()
        box.label(text="Bounding Box Display:", icon='CUBE')
        
        row = box.row()
        row.prop(self, "bbox_show_wire")
        
        row = box.row()
        row.prop(self, "bbox_show_all_edges")
        
        layout.separator()
        
        # Keymap shortcuts
        box = layout.box()
        box.label(text="Keyboard Shortcuts:", icon='KEY_HLT')
        kc = bpy.context.window_manager.keyconfigs.addon
        col = box.column()
        if kc:
            import sys
            import rna_keymap_ui
            addon_main = sys.modules[__package__]
            for km, kmi in getattr(addon_main, "addon_keymaps", []):
                col.context_pointer_set("keymap", km)
                rna_keymap_ui.draw_kmi([], kc, km, kmi, col, 0)
        else:
            col.label(text="Keyconfig not found", icon='ERROR')

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