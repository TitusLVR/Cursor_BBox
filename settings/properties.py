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
        default="BBox"
    )
    
    bpy.types.Scene.cursor_bbox_name_hull = bpy.props.StringProperty(
        name="Hull Name",
        description="Name pattern for Hull objects",
        default="ConvexHull"
    )
    
    bpy.types.Scene.cursor_bbox_name_sphere = bpy.props.StringProperty(
        name="Sphere Name",
        description="Name pattern for Sphere objects",
        default="BSphere"
    )
    
    bpy.types.Scene.cursor_bbox_collection_name = bpy.props.StringProperty(
        name="Collection Name",
        description="Name of the collection for collision objects",
        default="CursorBBox"
    )
    
    bpy.types.Scene.cursor_bbox_hull_dissolve_angle = bpy.props.FloatProperty(
        name="Hull Dissolve Angle",
        description="Angle threshold for dissolving planar faces in convex hull (degrees)",
        default=5.0,
        min=0.0,
        max=180.0,
        precision=1
    )

    def update_material_color(self, context):
        """Update material color when property changes"""
        rgba = list(self.cursor_bbox_material_color) + [1.0]
        
        # Update Material
        mat = bpy.data.materials.get("Cursor BBox Material")
        if mat:
            mat.diffuse_color = rgba
            if mat.use_nodes:
                bsdf = mat.node_tree.nodes.get("Principled BSDF")
                if bsdf:
                    # Append alpha=1.0 (already done in rgba)
                    bsdf.inputs['Base Color'].default_value = rgba

        # Update Object Color for objects in the specific collection
        coll_name = context.scene.cursor_bbox_collection_name
        if coll_name in bpy.data.collections:
            for obj in bpy.data.collections[coll_name].objects:
                obj.color = rgba

    bpy.types.Scene.cursor_bbox_material_color = bpy.props.FloatVectorProperty(
        name="Material Color",
        description="Color for Cursor BBox Material",
        subtype='COLOR',
        default=(1.0, 0.58, 0.231), # #FF943B
        min=0.0,
        max=1.0,
        update=update_material_color
    )

    def update_use_material(self, context):
        """Update material usage"""
        if self.cursor_bbox_use_material:
            # If turning on, apply color immediately
            update_material_color(self, context)

    bpy.types.Scene.cursor_bbox_use_material = bpy.props.BoolProperty(
        name="Use Material",
        description="Apply material and color to created objects",
        default=False,
        update=update_use_material
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
    del bpy.types.Scene.cursor_bbox_material_color
    del bpy.types.Scene.cursor_bbox_use_material
    del bpy.types.Scene.cursor_bbox_hull_dissolve_angle