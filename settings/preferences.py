import bpy
from bpy.types import AddonPreferences
from bpy.props import FloatProperty, BoolProperty, FloatVectorProperty, StringProperty, EnumProperty

class CursorBBoxPreferences(AddonPreferences):
    """Addon preferences for Cursor Aligned Bounding Box"""
    bl_idname = "Cursor_BBox"
    
    # Tab selection
    active_tab: EnumProperty(
        name="Active Tab",
        items=[
            ('KEYMAPS', "Keymaps", "Edit keyboard shortcuts"),
            ('UI', "UI", "Customize colors and appearance"),
        ],
        default='KEYMAPS'
    )
    
    # Edge highlight settings - Updated to #46FFB4
    edge_highlight_color: FloatVectorProperty(
        name="Edge Highlight Color",
        description="Color for highlighted edges",
        subtype='COLOR',
        default=(0.275, 1.0, 0.706),  # #46FFB4 converted to RGB
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
    
    # Face marking settings - Updated to #51AAFB
    face_marking_color: FloatVectorProperty(
        name="Face Marking Color",
        description="Color for marked faces",
        subtype='COLOR',
        default=(0.318, 0.667, 0.984),  # #51AAFB converted to RGB
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
    
    # Point marking settings - Using same color as edge highlight #46FFB4
    point_marking_color: FloatVectorProperty(
        name="Point Marking Color",
        description="Color for marked points",
        subtype='COLOR',
        default=(0.275, 1.0, 0.706),  # #46FFB4 converted to RGB
        min=0.0,
        max=1.0
    )
    
    point_marking_alpha: FloatProperty(
        name="Point Marking Alpha",
        description="Transparency for marked points",
        default=0.9,
        min=0.0,
        max=1.0
    )
    
    point_marking_size: FloatProperty(
        name="Point Marking Size",
        description="Size of point markers in Blender units",
        default=0.1,
        min=0.01,
        max=1.0,
        precision=3
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
    
    # BBox preview settings - Updated to #FFFFFF
    bbox_preview_enabled: BoolProperty(
        name="Show BBox Preview",
        description="Show bounding box preview while placing cursor",
        default=True
    )
    
    bbox_preview_color: FloatVectorProperty(
        name="BBox Preview Color",
        description="Color for bounding box preview",
        subtype='COLOR',
        default=(1.0, 1.0, 1.0),  # #FFFFFF converted to RGB
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
        
        # Tab selection
        row = layout.row()
        row.prop(self, "active_tab", expand=True)
        layout.separator()
        
        if self.active_tab == 'UI':
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
            
            # Point marking settings
            box = layout.box()
            box.label(text="Point Marking:", icon='EMPTY_AXIS')
            
            row = box.row()
            row.prop(self, "point_marking_color")
            
            row = box.row()
            row.prop(self, "point_marking_alpha")
            
            row = box.row()
            row.prop(self, "point_marking_size")
            
            layout.separator()
            
            # Bounding box display
            box = layout.box()
            box.label(text="Bounding Box Display:", icon='CUBE')
            
            row = box.row()
            row.prop(self, "bbox_show_wire")
            
            row = box.row()
            row.prop(self, "bbox_show_all_edges")
            
        elif self.active_tab == 'KEYMAPS':
            # Keymap shortcuts
            box = layout.box()
            box.label(text="Keyboard Shortcuts:", icon='KEY_HLT')
            kc = bpy.context.window_manager.keyconfigs.addon
            col = box.column()
            if kc:
                import sys
                import rna_keymap_ui
                addon_main = sys.modules[__package__.split('.')[0]]
                for km, kmi in getattr(addon_main, "addon_keymaps", []):
                    col.context_pointer_set("keymap", km)
                    rna_keymap_ui.draw_kmi([], kc, km, kmi, col, 0)
            else:
                col.label(text="Keyconfig not found", icon='ERROR')

def get_preferences():
    """Get addon preferences"""
    try:
        return bpy.context.preferences.addons["Cursor_BBox"].preferences
    except:
        return None

def register():
    bpy.utils.register_class(CursorBBoxPreferences)

def unregister():
    bpy.utils.unregister_class(CursorBBoxPreferences)