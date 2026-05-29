"""HUD theme settings for Cursor_BBox — colors, sizes, placement,
and animation knobs read by `ui/hud/` and `ui/draw/`.

Mirrors the HUD-relevant subset of InteractionOps' `IOPS_Theme`. Property
attribute names are kept identical (e.g. `hud_mode`, `help_corner`,
`color_hud_header`) because `ui/draw/theme.py:get_theme()` reads them by
name. Class name and bl_idname switch to the Cursor_BBox prefix.
"""
import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, StringProperty,
                       PointerProperty)


def _color(default, name=""):
    return FloatVectorProperty(name=name, subtype="COLOR", size=4,
                               min=0.0, max=1.0, default=default)


class CursorBBox_HUD_Theme(bpy.types.PropertyGroup):
    # --- HUD text roles ---
    color_hud_header:        _color((0.302, 1.000, 0.620, 0.75), "HUD Header / Label Active")
    color_hud_key:           _color((1.000, 0.872, 0.174, 0.75), "HUD Glyph / Active Value")
    color_hud_label:         _color((0.844, 0.844, 0.844, 0.75), "HUD Label")
    color_hud_label_inactive:_color((0.466, 0.473, 0.487, 0.85), "HUD Label Inactive")
    color_hud_stats_error:   _color((1.000, 0.339, 0.382, 0.90), "HUD Stats Error/Warning")
    text_size_hud_header:    IntProperty(name="Header Size", default=14, min=8, max=64)
    text_size_hud_key:       IntProperty(name="Glyph Size",  default=12, min=8, max=64)
    text_size_hud_label:     IntProperty(name="Label Size",  default=11, min=8, max=64)

    # --- Shadow ---
    shadow_enabled:        BoolProperty(name="Shadow", default=True)
    shadow_color:          _color((0.0, 0.0, 0.0, 1.0), "Shadow color")
    shadow_blur:           IntProperty(name="Shadow blur", default=0, min=0, max=10)
    shadow_offset_x:       IntProperty(name="Shadow X", default=1, min=-8, max=8)
    shadow_offset_y:       IntProperty(name="Shadow Y", default=-1, min=-8, max=8)

    # --- Dynamic overlay (cursor-follow / anchored) placement ---
    hud_mode: EnumProperty(
        name="HUD Placement",
        items=[
            ("cursor",        "Mouse Cursor",  "Follow mouse cursor"),
            ("top_left",      "Top Left",      ""),
            ("top_center",    "Top Center",    ""),
            ("top_right",     "Top Right",     ""),
            ("left_center",   "Center Left",   ""),
            ("center",        "Center",        ""),
            ("right_center",  "Center Right",  ""),
            ("bottom_left",   "Bottom Left",   ""),
            ("bottom_center", "Bottom Center", ""),
            ("bottom_right",  "Bottom Right",  ""),
            ("free",          "Free",          "Fixed position (drag to move)"),
        ],
        default="cursor",
    )
    hud_offset_x: IntProperty(name="Mouse Cursor offset X", default=20)
    hud_offset_y: IntProperty(name="Mouse Cursor offset Y", default=-20)
    hud_anchor_offset_x: IntProperty(name="Offset X", default=0, min=-4000, max=4000)
    hud_anchor_offset_y: IntProperty(name="Offset Y", default=0, min=-4000, max=4000)
    hud_free_x: IntProperty(name="Position X", default=40, min=0)
    hud_free_y: IntProperty(name="Position Y", default=40, min=0)
    hud_padding: IntProperty(name="Padding", default=12, min=0, max=64)
    hud_key_label_spacing: IntProperty(
        name="Key→label spacing",
        description="Gap between the widest key glyph and the label column",
        default=16, min=0, max=240,
    )
    hud_anim_fps: IntProperty(
        name="Animation FPS",
        description="Internal redraw rate (Hz) for HUD animations and "
                    "cursor-follow smoothing",
        default=240, min=30, max=1000,
    )
    hud_smoothing: FloatProperty(
        name="Cursor smoothing",
        description="How smoothly the HUD glides toward its target "
                    "position after a viewport rotate/zoom. 0 = snap instantly",
        default=0.70, min=0.0, max=0.98, step=5, precision=2,
    )

    # --- Background panel ---
    panel_bg_enabled: BoolProperty(name="Background panel", default=True)
    panel_bg_color: FloatVectorProperty(
        name="Panel color", subtype="COLOR", size=4,
        default=(0.0, 0.0, 0.0, 0.25),
        soft_min=0.0, soft_max=1.0, min=0.0, max=1.0,
    )
    panel_bg_padding: IntProperty(
        name="Panel padding", default=10, min=0, max=64,
    )

    # --- Help overlay placement ---
    help_corner: EnumProperty(
        name="Help Placement",
        items=[
            ("top_left",      "Top Left",      ""),
            ("top_center",    "Top Center",    ""),
            ("top_right",     "Top Right",     ""),
            ("left_center",   "Center Left",   ""),
            ("right_center",  "Center Right",  ""),
            ("bottom_left",   "Bottom Left",   ""),
            ("bottom_center", "Bottom Center", ""),
            ("bottom_right",  "Bottom Right",  ""),
            ("free",          "Free",          "Fixed position"),
        ],
        default="left_center",
    )
    help_offset_x: IntProperty(name="Offset X", default=8, min=-4000, max=4000)
    help_offset_y: IntProperty(name="Offset Y", default=0, min=-4000, max=4000)
    help_free_x: IntProperty(name="Position X", default=40, min=0)
    help_free_y: IntProperty(name="Position Y", default=40, min=0)

    # --- Help overlay animation ---
    help_anim_preset: EnumProperty(
        name="Help animation",
        items=[
            ("none",       "None",         "Instant toggle"),
            ("fade",       "Fade",         "Smooth cross-fade between states"),
            ("slide-fade", "Slide + fade", "Slide in from the anchored edge"),
            ("wave",       "Wave",         "Per-letter staggered reveal from the anchored edge"),
            ("shockwave",  "Shockwave",    "Outgoing letters explode radially outward; new content fades in beneath"),
        ],
        default="fade",
    )
    help_anim_duration: FloatProperty(
        name="Help animation duration",
        default=0.5, min=0.0, max=2.0,
        description="Seconds for the help overlay transition",
    )
    help_anim_slide_amount: IntProperty(
        name="Slide distance", default=28, min=0, max=400,
    )
    help_anim_wave_duration: FloatProperty(
        name="Wave duration",
        default=2.0, min=0.05, max=5.0, step=10, precision=2,
    )
    help_anim_wave_spread: IntProperty(
        name="Wave spread", default=128, min=0, max=400,
    )
    help_anim_wave_stagger_scale: FloatProperty(
        name="Wave stagger",
        default=1.0, min=0.1, max=10.0, step=10, precision=2,
    )
    help_anim_wave_fade_window: FloatProperty(
        name="Wave letter fade",
        default=0.5, min=0.05, max=1.0, step=5, precision=2,
    )
    help_anim_shockwave_radius: IntProperty(
        name="Shockwave radius", default=160, min=20, max=800,
    )
    help_hint_text: StringProperty(
        name="Help hint text",
        description="Text shown when Help is collapsed. {key} is replaced "
                    "with the configured toggle key.",
        default="Press {key} for help",
    )

    # --- Misc ---
    depth_test_default: EnumProperty(
        name="Depth test",
        items=[("LESS", "Less", ""), ("ALWAYS", "Always", "")],
        default="ALWAYS",
    )
    font_path: StringProperty(
        name="Font file",
        description=("Path to a TTF/OTF font used by HUD and overlay text. "
                     "Empty = Blender's default font"),
        subtype="FILE_PATH",
        default="",
    )

    # --- Fold state (UI only) ---
    show_hud_text: BoolProperty(default=True)
    show_hud_panel: BoolProperty(default=False)
    show_hud_font: BoolProperty(default=False)
    show_hud_placement: BoolProperty(default=True)
    show_help: BoolProperty(default=False)


class CursorBBox_OT_HudThemeResetDefaults(bpy.types.Operator):
    bl_idname = "cursor_bbox.hud_theme_reset_defaults"
    bl_label = "Reset HUD Theme to Defaults"
    bl_description = "Restore all HUD theme values to defaults"
    bl_options = {"REGISTER"}

    def execute(self, context):
        prefs = context.preferences.addons["Cursor_BBox"].preferences
        t = prefs.hud_theme
        for prop_name in t.bl_rna.properties.keys():
            if prop_name in {"name", "rna_type"}:
                continue
            t.property_unset(prop_name)
        return {"FINISHED"}


def _hud_section(layout, theme, prop_name, title, *, icon="NONE"):
    box = layout.box()
    row = box.row(align=True)
    is_open = getattr(theme, prop_name)
    row.prop(theme, prop_name, text="",
             icon="TRIA_DOWN" if is_open else "TRIA_RIGHT",
             emboss=False)
    row.label(text=title, icon=icon)
    if not is_open:
        return None
    return box.column(align=True)


def draw_hud_theme_tab(layout, theme):
    """Draw the HUD-theme UI inside the addon's UI tab."""
    # --- Text Styles ---
    body = _hud_section(layout, theme, "show_hud_text",
                        "Text Styles", icon="FONT_DATA")
    if body is not None:
        for attr, size_attr, label in (
                ("color_hud_header",         "text_size_hud_header",
                 "HUD Header / Label Active"),
                ("color_hud_key",            "text_size_hud_key",
                 "HUD Glyph / Active Value"),
                ("color_hud_label",          "text_size_hud_label",
                 "HUD Label"),
                ("color_hud_label_inactive", None,
                 "HUD Label Inactive"),
                ("color_hud_stats_error",    None,
                 "HUD Stats Error/Warning"),
        ):
            row = body.row(align=True)
            row.label(text=label)
            if size_attr is not None:
                row.prop(theme, size_attr, text="")
            else:
                row.label(text="")
            row.prop(theme, attr, text="")

    # --- Panel & Shadow ---
    body = _hud_section(layout, theme, "show_hud_panel",
                        "Panel & Shadow", icon="MESH_PLANE")
    if body is not None:
        body.prop(theme, "panel_bg_enabled")
        bg = body.column(align=True)
        bg.active = theme.panel_bg_enabled
        bg.prop(theme, "panel_bg_color")
        bg.prop(theme, "panel_bg_padding")
        body.separator()
        body.prop(theme, "shadow_enabled")
        sh = body.column(align=True)
        sh.active = theme.shadow_enabled
        sh.prop(theme, "shadow_color")
        sh.prop(theme, "shadow_blur")
        sh.prop(theme, "shadow_offset_x")
        sh.prop(theme, "shadow_offset_y")

    # --- Font ---
    body = _hud_section(layout, theme, "show_hud_font",
                        "Font", icon="FILE_FONT")
    if body is not None:
        body.prop(theme, "font_path", text="")
        body.label(
            text="Empty = Blender default. Used by every HUD overlay.",
            icon="INFO",
        )

    layout.separator()

    # --- Dynamic Overlay ---
    body = _hud_section(layout, theme, "show_hud_placement",
                        "Dynamic Overlay", icon="WINDOW")
    if body is not None:
        body.prop(theme, "hud_mode")
        mode = theme.hud_mode
        row = body.row(align=True)
        if mode == "cursor":
            row.prop(theme, "hud_offset_x")
            row.prop(theme, "hud_offset_y")
        elif mode == "free":
            row.prop(theme, "hud_free_x")
            row.prop(theme, "hud_free_y")
        else:
            row.prop(theme, "hud_anchor_offset_x")
            row.prop(theme, "hud_anchor_offset_y")
        body.prop(theme, "hud_padding")
        body.prop(theme, "hud_key_label_spacing")
        body.prop(theme, "hud_smoothing", slider=True)
        body.prop(theme, "hud_anim_fps")
        body.label(text="Toggle: Keymaps → cursor_bbox.ui_hud_params_toggle",
                   icon="INFO")

    # --- Help Overlay ---
    body = _hud_section(layout, theme, "show_help",
                        "Help Overlay", icon="QUESTION")
    if body is not None:
        body.label(text="Toggle: Keymaps → cursor_bbox.ui_help_toggle",
                   icon="INFO")
        body.prop(theme, "help_corner")
        row = body.row(align=True)
        if theme.help_corner == "free":
            row.prop(theme, "help_free_x")
            row.prop(theme, "help_free_y")
        else:
            row.prop(theme, "help_offset_x")
            row.prop(theme, "help_offset_y")
        body.prop(theme, "help_hint_text")
        body.separator()
        body.prop(theme, "help_anim_preset")
        preset = theme.help_anim_preset
        if preset == "wave":
            body.prop(theme, "help_anim_wave_duration")
        else:
            body.prop(theme, "help_anim_duration")
        if preset == "slide-fade":
            body.prop(theme, "help_anim_slide_amount")
        elif preset == "wave":
            body.prop(theme, "help_anim_wave_spread")
            body.prop(theme, "help_anim_wave_stagger_scale")
            body.prop(theme, "help_anim_wave_fade_window")
        elif preset == "shockwave":
            body.prop(theme, "help_anim_shockwave_radius")

    layout.separator()
    row = layout.row()
    row.operator("cursor_bbox.hud_theme_reset_defaults", icon="LOOP_BACK")


classes = (CursorBBox_HUD_Theme, CursorBBox_OT_HudThemeResetDefaults)
