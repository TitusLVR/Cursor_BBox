import bpy

def register():
    """Register scene properties"""
    bpy.types.Scene.cursor_bbox_push = bpy.props.FloatProperty(
        name="Push Value",
        description="How much to push bounding box faces outward",
        default=0.01,
        min=-1.0,
        max=1.0,
        precision=3
    )
    
    bpy.types.Scene.cursor_bbox_align_face = bpy.props.BoolProperty(
        name="Align to Face",
        description="Align cursor rotation to face normal",
        default=True
    )

def unregister():
    """Unregister scene properties"""
    del bpy.types.Scene.cursor_bbox_push
    del bpy.types.Scene.cursor_bbox_align_face