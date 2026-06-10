import bpy


class CursorBBox_OT_use_active_collection(bpy.types.Operator):
    """Set the collision Collection name to the active collection"""
    bl_idname = "cursor_bbox.use_active_collection"
    bl_label = "Use Active Collection"
    bl_description = (
        "Set the Collection field to the name of the active collection"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        alc = context.view_layer.active_layer_collection
        # Disabled when the active collection is the master Scene Collection:
        # its name isn't a usable target (it doesn't live in bpy.data.collections).
        return alc is not None and alc.collection is not context.scene.collection

    def execute(self, context):
        name = context.view_layer.active_layer_collection.collection.name
        context.scene.cursor_bbox_collection_name = name
        self.report({'INFO'}, f'Collection set to "{name}"')
        return {'FINISHED'}
