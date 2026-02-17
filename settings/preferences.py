import os
import bpy
from bpy.types import AddonPreferences
from bpy.props import FloatProperty, BoolProperty, FloatVectorProperty, EnumProperty, StringProperty

class CursorBBoxPreferences(AddonPreferences):
    """Addon preferences for Cursor Aligned Bounding Box"""
    bl_idname = "Cursor_BBox"
    
    # Tab selection
    active_tab: EnumProperty(
        name="Active Tab",
        items=[
            ('SETTINGS', "Settings", "General addon settings"),
            ('TOOLS', "Tools", "External tool paths"),
            ('KEYMAPS', "Keymaps", "Edit keyboard shortcuts"),
            ('UI', "UI", "Customize colors and appearance"),
        ],
        default='SETTINGS'
    )
    
    # External tool paths
    vhacd_executable: StringProperty(
        name="V-HACD Executable",
        description="Path to V-HACD executable (VHACD.exe / TestVHACD)",
        subtype='FILE_PATH',
        default=""
    )
    
    coacd_executable: StringProperty(
        name="CoACD Executable",
        description="Path to CoACD executable (CoACD.exe / main)",
        subtype='FILE_PATH',
        default=""
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
        default=(0.984, 0.122, 0.483),  # #51AAFB converted to RGB
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
        default=(0.750, 0.750, 0.750),  # #FFFFFF converted to RGB
        min=0.0,
        max=1.0
    )
    
    bbox_preview_alpha: FloatProperty(
        name="BBox Preview Alpha",
        description="Transparency for bounding box preview wireframe",
        default=0.75,
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
    
    bbox_preview_face_alpha_multiplier: FloatProperty(
        name="Preview Face Alpha Multiplier",
        description="Multiplier for bbox preview face transparency (relative to wireframe alpha)",
        default=0.3,
        min=0.0,
        max=1.0
    )
    
    # Preview faces (hover) settings
    preview_faces_color: FloatVectorProperty(
        name="Preview Faces Color",
        description="Color for face hover preview (when hovering over faces)",
        subtype='COLOR',
        default=(0.275, 1.0, 0.706),  # Cyan
        min=0.0,
        max=1.0
    )
    
    preview_faces_alpha: FloatProperty(
        name="Preview Faces Alpha",
        description="Transparency for face hover preview",
        default=0.35,
        min=0.0,
        max=1.0
    )
    
    # Preview point settings
    preview_point_color: FloatVectorProperty(
        name="Preview Point Color",
        description="Color for point preview (when hovering in add point mode)",
        subtype='COLOR',
        default=(1.0, 0.48, 0.0),  # Green
        min=0.0,
        max=1.0
    )
    
    preview_point_alpha: FloatProperty(
        name="Preview Point Alpha",
        description="Transparency for point preview",
        default=1.0,
        min=0.0,
        max=1.0
    )

    # General Settings
    use_depsgraph: BoolProperty(
        name="Use Depsgraph",
        description="Use evaluated dependency graph for raycasting and operations (slower but supports modifiers)",
        default=True
    )
    
    def draw(self, context):
        layout = self.layout
        
        # Tab selection
        row = layout.row()
        row.prop(self, "active_tab", expand=True)
        layout.separator()
        
        if self.active_tab == 'SETTINGS':
             # General Settings
            box = layout.box()
            box.label(text="General Settings:", icon='PREFERENCES')
            
            row = box.row()
            row.prop(self, "use_depsgraph")
        
        elif self.active_tab == 'TOOLS':
            # V-HACD
            box = layout.box()
            row = box.row()
            row.label(text="V-HACD (Convex Decomposition):", icon='MOD_MESHDEFORM')
            col = box.column(align=True)
            col.prop(self, "vhacd_executable")
            vhacd_path = bpy.path.abspath(self.vhacd_executable)
            if vhacd_path and os.path.isfile(vhacd_path):
                row = box.row()
                row.label(text="Found", icon='CHECKMARK')
            elif self.vhacd_executable:
                row = box.row()
                row.label(text="File not found!", icon='ERROR')
            
            layout.separator()
            
            # CoACD
            box = layout.box()
            row = box.row()
            row.label(text="CoACD (Collision-Aware Decomposition):", icon='MOD_MESHDEFORM')
            col = box.column(align=True)
            col.prop(self, "coacd_executable")
            coacd_path = bpy.path.abspath(self.coacd_executable)
            if coacd_path and os.path.isfile(coacd_path):
                row = box.row()
                row.label(text="Found", icon='CHECKMARK')
            elif self.coacd_executable:
                row = box.row()
                row.label(text="File not found!", icon='ERROR')

            layout.separator()

            # CoACD-U (Python library)
            box = layout.box()
            row = box.row()
            row.label(text="CoACD-U (Ultikynnys Variant, 3-10x Faster):", icon='MOD_MESHDEFORM')
            col = box.column(align=True)
            try:
                import coacd_u
                has_coacd_u = True
            except ImportError:
                has_coacd_u = False
            if has_coacd_u:
                row = box.row()
                row.label(text="coacd_u installed", icon='CHECKMARK')
            else:
                row = box.row()
                row.label(text="coacd_u not installed", icon='ERROR')
                row = box.row()
                row.scale_y = 1.3
                row.operator(
                    "cursor_bbox.install_coacd_u",
                    text="Install coacd_u from GitHub",
                    icon='IMPORT',
                )
                row = box.row()
                row.label(text="Or download manually: github.com/Ultikynnys/CoACD/releases")
            
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

        elif self.active_tab == 'UI':
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
                
                if self.bbox_preview_show_faces:
                    row = box.row()
                    row.prop(self, "bbox_preview_face_alpha_multiplier")
            
            layout.separator()
            
            # Preview faces (hover) settings
            box = layout.box()
            box.label(text="Face Hover Preview:", icon='GHOST_ENABLED')
            
            row = box.row()
            row.prop(self, "preview_faces_color")
            
            row = box.row()
            row.prop(self, "preview_faces_alpha")
            
            layout.separator()
            
            # Preview point settings
            box = layout.box()
            box.label(text="Point Preview:", icon='EMPTY_AXIS')
            
            row = box.row()
            row.prop(self, "preview_point_color")
            
            row = box.row()
            row.prop(self, "preview_point_alpha")
            
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