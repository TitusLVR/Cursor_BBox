"""Resolve a keymap item's current key by its idname.

Used by the HUD/Help overlays to find which key the user has bound to the
marker toggle operators (`cursor_bbox.ui_help_toggle`,
`cursor_bbox.ui_hud_params_toggle`). Reads the *user* keyconfig so
rebindings in Blender's Preferences UI are honored.
"""
import bpy


def get_ui_toggle_key(idname: str, default: str) -> str:
    """Return the event-type currently bound to a UI-toggle marker
    operator, or `default` if the kmi can't be found."""
    try:
        kc = bpy.context.window_manager.keyconfigs.user
    except AttributeError:
        return default
    if kc is None:
        return default
    for km in kc.keymaps:
        for kmi in km.keymap_items:
            if kmi.idname == idname:
                return kmi.type
    return default
