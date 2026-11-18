import bpy

from ..settings.properties import reset_split_params


class CursorBBox_OT_split_reset_params(bpy.types.Operator):
    """Reset the remembered Split / Islands parameters to their defaults"""
    bl_idname = "cursor_bbox.split_reset_params"
    bl_label = "Reset Split / Islands Parameters"
    bl_description = (
        "Reset the remembered Split / Islands parameters (cut fit, snap, plane "
        "axis, merge gap / void / ignore thinner / flat merge) to their defaults. "
        "A running Split / Islands session keeps its own values: the reset takes "
        "effect the next time the mode is entered (Backspace resets it in the mode)"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        reset_split_params(context.scene)
        self.report({'INFO'}, "Split / Islands parameters reset to defaults")
        return {'FINISHED'}
