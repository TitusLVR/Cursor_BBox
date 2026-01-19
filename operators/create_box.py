import bpy
from ..functions.core import cursor_aligned_bounding_box
from ..functions.utils import (
    is_collection_instance,
    make_collection_instance_real,
    cleanup_collection_instance_temp
)

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
        # Check if we have selected objects with collection instances
        instance_data_list = []
        
        try:
            for obj in context.selected_objects:
                if is_collection_instance(obj):
                    self.report({'INFO'}, f"Processing collection instance: {obj.name}")
                    instance_info = make_collection_instance_real(context, obj)
                    if instance_info:
                        instance_data_list.append(instance_info)
                        # Use the first real object for the bbox
                        if instance_info['real_objects']:
                            cursor_aligned_bounding_box(self.push_value, instance_info['real_objects'][0])
                    else:
                        self.report({'WARNING'}, f"Failed to process instance: {obj.name}")
                else:
                    cursor_aligned_bounding_box(self.push_value, obj)
            
            # If no objects were selected, use default behavior
            if not context.selected_objects:
                cursor_aligned_bounding_box(self.push_value)
            
            self.report({'INFO'}, "Cursor-aligned bounding box created")
            return {'FINISHED'}
            
        finally:
            # Clean up all temporary instances
            for instance_info in instance_data_list:
                cleanup_collection_instance_temp(context, instance_info)
