import bpy
from ..functions.core import cursor_aligned_bounding_box

class CursorBBox_OT_create_box(bpy.types.Operator):
    """Create cursor-aligned bounding box"""
    bl_idname = "cursor_bbox.create_box"
    bl_label = "Create Box"
    bl_description = "Create a Bounding Box at current cursor"
    bl_options = {'REGISTER', 'UNDO'}
    
    push_value: bpy.props.FloatProperty(
        name="Push Value",
        description="How much to push bounding box faces outward",
        default=0.01,
        min=-1.0,
        max=1.0,
        precision=3
    )
    
    def execute(self, context):
        cursor_aligned_bounding_box(self.push_value)
        self.report({'INFO'}, "Cursor-aligned bounding box created")
        return {'FINISHED'}
