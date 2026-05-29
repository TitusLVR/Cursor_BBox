"""Marker operators for HUD / Help overlay toggle keymaps.

These operators don't *do* anything when invoked through the global
keymap — they exist so the addon can register normal Blender keymap
items, displayed in the Keymaps tab and rebindable via the standard
keymap UI. Modal operators that drive a HUD/Help overlay read the
keymap item's current `type` to know which key the user assigned.
"""
import bpy


class CursorBBox_OT_HelpToggleMarker(bpy.types.Operator):
    bl_idname = "cursor_bbox.ui_help_toggle"
    bl_label = "Toggle Help Overlay"
    bl_description = ("Marker operator — its keymap binding controls "
                      "which key expands/collapses the corner Help overlay "
                      "while a modal operator is running")
    bl_options = {"INTERNAL"}

    def execute(self, context):
        return {"CANCELLED"}


class CursorBBox_OT_HudParamsToggleMarker(bpy.types.Operator):
    bl_idname = "cursor_bbox.ui_hud_params_toggle"
    bl_label = "Toggle HUD Params"
    bl_description = ("Marker operator — its keymap binding controls "
                      "which key hides/shows the HUD parameter rows "
                      "while a modal operator is running")
    bl_options = {"INTERNAL"}

    def execute(self, context):
        return {"CANCELLED"}


classes = (CursorBBox_OT_HelpToggleMarker, CursorBBox_OT_HudParamsToggleMarker)
