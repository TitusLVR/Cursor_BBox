import bpy
import math

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
    
    bpy.types.Scene.cursor_bbox_select_coplanar = bpy.props.BoolProperty(
        name="Select Coplanar",
        description="Automatically select connected coplanar faces",
        default=False
    )
    
    bpy.types.Scene.cursor_bbox_coplanar_angle = bpy.props.FloatProperty(
        name="Coplanar Angle",
        description="Angle threshold for coplanar selection",
        default=0.0872665,  # 5 degrees in radians
        min=0.0,
        max=math.pi,
        unit='ROTATION'
    )
    
    bpy.types.Scene.cursor_bbox_name_box = bpy.props.StringProperty(
        name="Box Name",
        description="Name pattern for Box objects",
        default="Cube"
    )
    
    bpy.types.Scene.cursor_bbox_name_hull = bpy.props.StringProperty(
        name="Hull Name",
        description="Name pattern for Hull objects",
        default="Convex"
    )
    
    bpy.types.Scene.cursor_bbox_name_sphere = bpy.props.StringProperty(
        name="Sphere Name",
        description="Name pattern for Sphere objects",
        default="Sphere"
    )
    
    bpy.types.Scene.cursor_bbox_collection_name = bpy.props.StringProperty(
        name="Collection Name",
        description="Name of the collection for collision objects",
        default="CBB_Collision"
    )

def unregister():
    """Unregister scene properties"""
    del bpy.types.Scene.cursor_bbox_push
    del bpy.types.Scene.cursor_bbox_align_face
    del bpy.types.Scene.cursor_bbox_select_coplanar
    del bpy.types.Scene.cursor_bbox_coplanar_angle
    del bpy.types.Scene.cursor_bbox_name_box
    del bpy.types.Scene.cursor_bbox_name_hull
    del bpy.types.Scene.cursor_bbox_name_sphere
    del bpy.types.Scene.cursor_bbox_collection_name