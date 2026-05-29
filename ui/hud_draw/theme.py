from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import bpy
from mathutils import Color


def _srgb_encode(rgba):
    """Convert a scene-linear RGBA tuple to sRGB for screen-space drawing.

    `FloatVectorProperty(subtype='COLOR')` stores its value scene-linear, so
    the picker shows #2C3037 while memory holds ~(0.025, 0.030, 0.038).
    POST_PIXEL draw handlers write straight into the already color-managed
    display buffer with no sRGB encode, so a linear 0.025 renders near-black.
    Encode here for screen-space (POST_PIXEL) colors only — POST_VIEW (3D
    world-space) draws go through the color-managed pipeline and are correct
    as-is, so they must NOT be passed through this helper.
    """
    r, g, b = rgba[0], rgba[1], rgba[2]
    a = rgba[3] if len(rgba) > 3 else 1.0
    c = Color((r, g, b)).from_scene_linear_to_srgb()
    return (c.r, c.g, c.b, a)


class Role(Enum):
    # Point variants
    POINT = "point"
    CLOSEST_POINT = "closest_point"
    ACTIVE_POINT = "active_point"
    LOCKED_POINT = "locked_point"
    PREVIEW_POINT = "preview_point"
    ERROR_POINT = "error_point"

    LINE = "line"
    CLOSEST_LINE = "closest_line"
    ACTIVE_LINE = "active_line"
    LOCKED_LINE = "locked_line"
    PREVIEW_LINE = "preview_line"
    ERROR_LINE = "error_line"

    POINT_OUTLINE = "point_outline"

    HANDLE = "handle"
    HANDLE_HOVER = "handle_hover"
    PIVOT = "pivot"
    BBOX = "bbox"
    CURSOR = "cursor"

    GHOST_EDGE = "ghost_edge"
    GHOST_DEFAULT = "ghost_default"
    GHOST_ACTIVE = "ghost_active"
    GHOST_CLOSEST = "ghost_closest"
    GHOST_LOCKED = "ghost_locked"
    GHOST_PREVIEW = "ghost_preview"
    GHOST_TARGET_SEL = "ghost_target_sel"
    GHOST_MATCH_HINT = "ghost_match_hint"

    # HUD text — the only roles that the ported HUD/Help actually read.
    HUD_HEADER = "hud_header"
    HUD_KEY = "hud_key"
    HUD_LABEL = "hud_label"
    HUD_LABEL_ACTIVE = "hud_label_active"
    HUD_LABEL_INACTIVE = "hud_label_inactive"
    HUD_ACTIVE_VALUE = "hud_active_value"
    HUD_STATS_ERROR = "hud_stats_error"


STATES = ("default", "closest", "active", "locked", "preview", "error")


def state_from_role(role: Role) -> str:
    name = role.value
    for s in ("closest", "active", "locked", "preview", "error"):
        if name.startswith(s + "_") or name == s:
            return s
    return "default"


_C_CYAN  = (0.302, 0.816, 1.000)
_C_GREEN = (0.302, 1.000, 0.620)
_C_AMBER = (1.000, 0.722, 0.302)
_C_RED   = (1.000, 0.353, 0.353)
_C_WHITE = (1.000, 1.000, 1.000)

_DEFAULT_COLORS: dict[Role, tuple[float, float, float, float]] = {
    Role.POINT:          (*_C_WHITE, 0.70),
    Role.CLOSEST_POINT:  (*_C_GREEN, 1.00),
    Role.ACTIVE_POINT:   (*_C_CYAN,  1.00),
    Role.LOCKED_POINT:   (*_C_AMBER, 1.00),
    Role.PREVIEW_POINT:  (*_C_CYAN,  0.50),
    Role.ERROR_POINT:    (*_C_RED,   1.00),

    Role.LINE:           (0.650, 0.650, 0.650, 0.30),
    Role.CLOSEST_LINE:   (*_C_GREEN, 0.85),
    Role.ACTIVE_LINE:    (*_C_CYAN,  0.90),
    Role.LOCKED_LINE:    (*_C_AMBER, 0.95),
    Role.PREVIEW_LINE:   (*_C_CYAN,  0.50),
    Role.ERROR_LINE:     (*_C_RED,   1.00),

    Role.POINT_OUTLINE:  (0.000, 0.000, 0.000, 1.00),

    Role.HANDLE:        (1.000, 1.000, 1.000, 0.85),
    Role.HANDLE_HOVER:  (0.302, 0.816, 1.000, 0.90),
    Role.PIVOT:         (1.000, 0.872, 0.174, 0.90),
    Role.BBOX:          (0.650, 0.650, 0.650, 0.30),
    Role.CURSOR:        (1.000, 0.200, 0.600, 1.00),

    Role.GHOST_EDGE:    (0.000, 0.000, 0.000, 0.349),
    Role.GHOST_DEFAULT: (0.851, 0.851, 0.851, 0.149),
    Role.GHOST_ACTIVE:  (*_C_CYAN,  0.90),
    Role.GHOST_CLOSEST: (*_C_GREEN, 0.85),
    Role.GHOST_LOCKED:  (*_C_AMBER, 0.95),
    Role.GHOST_PREVIEW: (*_C_CYAN,  0.50),
    Role.GHOST_TARGET_SEL: (*_C_AMBER, 0.70),
    Role.GHOST_MATCH_HINT: (*_C_GREEN, 0.35),

    Role.HUD_HEADER:         (0.302, 1.000, 0.620, 0.75),
    Role.HUD_LABEL_ACTIVE:   (0.302, 1.000, 0.620, 0.75),
    Role.HUD_KEY:            (1.000, 0.872, 0.174, 0.75),
    Role.HUD_ACTIVE_VALUE:   (1.000, 0.872, 0.174, 0.75),
    Role.HUD_LABEL:          (0.844, 0.844, 0.844, 0.75),
    Role.HUD_LABEL_INACTIVE: (0.466, 0.473, 0.487, 0.85),
    Role.HUD_STATS_ERROR:    (1.000, 0.339, 0.382, 0.90),
}

_DEFAULT_POINT_SIZES = {
    "default": 8.0, "closest": 11.0, "active": 12.0,
    "locked": 13.0, "preview": 10.0, "error": 13.0,
}
_DEFAULT_LINE_WIDTHS = {
    "default": 1.5, "closest": 2.5, "active": 2.5,
    "locked": 3.0, "preview": 2.0, "error": 2.5,
}
_DEFAULT_TEXT_SIZES = {
    "hud_header": 13,
    "hud_key":    11,
    "hud_label":  11,
    "stats":      11,
}


@dataclass(frozen=True)
class HUDSettings:
    mode: str = "cursor"
    offset_x: int = 20
    offset_y: int = -20
    anchor_offset_x: int = 0
    anchor_offset_y: int = 0
    free_x: int = 40
    free_y: int = 40
    padding: int = 12
    section_spacing: int = 8
    row_spacing: int = 2
    key_label_spacing: int = 16
    smoothing: float = 0.70
    bg_enabled: bool = True
    bg_color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.25)
    bg_padding: int = 10


@dataclass(frozen=True)
class ShadowSettings:
    enabled: bool = True
    color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.7)
    blur: int = 3
    offset_x: int = 1
    offset_y: int = -1


@dataclass(frozen=True)
class Theme:
    colors: dict[Role, tuple[float, float, float, float]] = field(
        default_factory=lambda: dict(_DEFAULT_COLORS))
    point_sizes: dict[str, float] = field(
        default_factory=lambda: dict(_DEFAULT_POINT_SIZES))
    line_widths: dict[str, float] = field(
        default_factory=lambda: dict(_DEFAULT_LINE_WIDTHS))
    text_sizes: dict[str, int] = field(
        default_factory=lambda: dict(_DEFAULT_TEXT_SIZES))
    shadow: ShadowSettings = field(default_factory=ShadowSettings)
    hud: HUDSettings = field(default_factory=HUDSettings)
    depth_test_default: str = "LESS"
    font_path: str = ""
    point_size_handle: float = 8.0
    point_size_handle_hover: float = 10.0
    point_size_pivot: float = 12.0
    point_size_cursor: float = 8.0
    line_width_bbox: float = 1.5

    def color_for(self, role: Role) -> tuple[float, float, float, float]:
        return self.colors[role]

    def point_size_for(self, role: Role) -> float:
        if role is Role.HANDLE:
            return self.point_size_handle
        if role is Role.HANDLE_HOVER:
            return self.point_size_handle_hover
        if role is Role.PIVOT:
            return self.point_size_pivot
        if role is Role.CURSOR:
            return self.point_size_cursor
        return self.point_sizes[state_from_role(role)]

    def line_width_for(self, role: Role) -> float:
        if role is Role.BBOX:
            return self.line_width_bbox
        return self.line_widths[state_from_role(role)]

    def text_size_for(self, role: Role) -> int:
        if role is Role.HUD_HEADER:
            return self.text_sizes["hud_header"]
        if role is Role.HUD_KEY:
            return self.text_sizes["hud_key"]
        return self.text_sizes["hud_label"]

    def point_size(self, token: str) -> float:
        return self.point_sizes[token]

    def width(self, token: str) -> float:
        return self.line_widths[token]

    def text_size(self, token: str) -> int:
        if token == "hud_header" or token == "title":
            return self.text_sizes["hud_header"]
        if token == "hud_key":
            return self.text_sizes["hud_key"]
        if token == "stats":
            return self.text_sizes["stats"]
        return self.text_sizes["hud_label"]


def get_theme(context) -> "Theme":
    try:
        prefs = context.preferences.addons["Cursor_BBox"].preferences
        t = prefs.hud_theme
    except (KeyError, AttributeError):
        return DEFAULT_THEME

    def c(name, fallback):
        return tuple(getattr(t, name, fallback))

    def cs(name, fallback):
        # Screen-space (POST_PIXEL) color: encode scene-linear -> sRGB.
        return _srgb_encode(getattr(t, name, fallback))

    def fl(name, fallback):
        return float(getattr(t, name, fallback))

    def i(name, fallback):
        return int(getattr(t, name, fallback))

    return Theme(
        colors={
            # Non-HUD roles use code defaults (Cursor_BBox HUD doesn't
            # expose Point/Line/Ghost/Widget theming in prefs).
            Role.POINT:              _DEFAULT_COLORS[Role.POINT],
            Role.CLOSEST_POINT:      _DEFAULT_COLORS[Role.CLOSEST_POINT],
            Role.ACTIVE_POINT:       _DEFAULT_COLORS[Role.ACTIVE_POINT],
            Role.LOCKED_POINT:       _DEFAULT_COLORS[Role.LOCKED_POINT],
            Role.PREVIEW_POINT:      _DEFAULT_COLORS[Role.PREVIEW_POINT],
            Role.ERROR_POINT:        _DEFAULT_COLORS[Role.ERROR_POINT],

            Role.LINE:               _DEFAULT_COLORS[Role.LINE],
            Role.CLOSEST_LINE:       _DEFAULT_COLORS[Role.CLOSEST_LINE],
            Role.ACTIVE_LINE:        _DEFAULT_COLORS[Role.ACTIVE_LINE],
            Role.LOCKED_LINE:        _DEFAULT_COLORS[Role.LOCKED_LINE],
            Role.PREVIEW_LINE:       _DEFAULT_COLORS[Role.PREVIEW_LINE],
            Role.ERROR_LINE:         _DEFAULT_COLORS[Role.ERROR_LINE],

            Role.POINT_OUTLINE:      _DEFAULT_COLORS[Role.POINT_OUTLINE],

            Role.HANDLE:             _DEFAULT_COLORS[Role.HANDLE],
            Role.HANDLE_HOVER:       _DEFAULT_COLORS[Role.HANDLE_HOVER],
            Role.PIVOT:              _DEFAULT_COLORS[Role.PIVOT],
            Role.BBOX:               _DEFAULT_COLORS[Role.BBOX],
            Role.CURSOR:             _DEFAULT_COLORS[Role.CURSOR],

            Role.GHOST_EDGE:         _DEFAULT_COLORS[Role.GHOST_EDGE],
            Role.GHOST_DEFAULT:      _DEFAULT_COLORS[Role.GHOST_DEFAULT],
            Role.GHOST_ACTIVE:       _DEFAULT_COLORS[Role.GHOST_ACTIVE],
            Role.GHOST_CLOSEST:      _DEFAULT_COLORS[Role.GHOST_CLOSEST],
            Role.GHOST_LOCKED:       _DEFAULT_COLORS[Role.GHOST_LOCKED],
            Role.GHOST_PREVIEW:      _DEFAULT_COLORS[Role.GHOST_PREVIEW],
            Role.GHOST_TARGET_SEL:   _DEFAULT_COLORS[Role.GHOST_TARGET_SEL],
            Role.GHOST_MATCH_HINT:   _DEFAULT_COLORS[Role.GHOST_MATCH_HINT],

            # HUD_ACTIVE_VALUE + HUD_LABEL_ACTIVE share `color_hud_active_value`
            # (both convey the "active item" highlight); HUD_HEADER and
            # HUD_KEY each have their own standalone color.
            # Screen-space (POST_PIXEL) — encode scene-linear -> sRGB.
            Role.HUD_HEADER:         cs("color_hud_header",         _DEFAULT_COLORS[Role.HUD_HEADER]),
            Role.HUD_KEY:            cs("color_hud_key",            _DEFAULT_COLORS[Role.HUD_KEY]),
            Role.HUD_ACTIVE_VALUE:   cs("color_hud_active_value",   _DEFAULT_COLORS[Role.HUD_ACTIVE_VALUE]),
            Role.HUD_LABEL_ACTIVE:   cs("color_hud_active_value",   _DEFAULT_COLORS[Role.HUD_ACTIVE_VALUE]),
            Role.HUD_LABEL:          cs("color_hud_label",          _DEFAULT_COLORS[Role.HUD_LABEL]),
            Role.HUD_LABEL_INACTIVE: cs("color_hud_label_inactive", _DEFAULT_COLORS[Role.HUD_LABEL_INACTIVE]),
            Role.HUD_STATS_ERROR:    cs("color_hud_stats_error",    _DEFAULT_COLORS[Role.HUD_STATS_ERROR]),
        },
        point_sizes=dict(_DEFAULT_POINT_SIZES),
        line_widths=dict(_DEFAULT_LINE_WIDTHS),
        text_sizes={
            "hud_header": i("text_size_hud_header", _DEFAULT_TEXT_SIZES["hud_header"]),
            "hud_key":    i("text_size_hud_key",    _DEFAULT_TEXT_SIZES["hud_key"]),
            "hud_label":  i("text_size_hud_label",  _DEFAULT_TEXT_SIZES["hud_label"]),
            "stats":      _DEFAULT_TEXT_SIZES["stats"],
        },
        shadow=ShadowSettings(
            enabled=bool(getattr(t, "shadow_enabled", True)),
            color=_srgb_encode(getattr(t, "shadow_color", (0.0, 0.0, 0.0, 1.0))),
            blur=int(getattr(t, "shadow_blur", 0)),
            offset_x=int(getattr(t, "shadow_offset_x", 1)),
            offset_y=int(getattr(t, "shadow_offset_y", -1)),
        ),
        hud=HUDSettings(
            mode=str(getattr(t, "hud_mode", "cursor")),
            offset_x=int(getattr(t, "hud_offset_x", 20)),
            offset_y=int(getattr(t, "hud_offset_y", -20)),
            anchor_offset_x=int(getattr(t, "hud_anchor_offset_x", 0)),
            anchor_offset_y=int(getattr(t, "hud_anchor_offset_y", 0)),
            free_x=int(getattr(t, "hud_free_x", 40)),
            free_y=int(getattr(t, "hud_free_y", 40)),
            padding=int(getattr(t, "hud_padding", 12)),
            section_spacing=max(4, int(max(i("text_size_hud_key", 11),
                                           i("text_size_hud_label", 11)) * 0.6)),
            row_spacing=max(2, int(max(i("text_size_hud_key", 11),
                                       i("text_size_hud_label", 11)) * 0.25)),
            key_label_spacing=int(getattr(t, "hud_key_label_spacing", 16)),
            smoothing=float(getattr(t, "hud_smoothing", 0.70)),
            bg_enabled=bool(getattr(t, "panel_bg_enabled", True)),
            bg_color=_srgb_encode(getattr(t, "panel_bg_color",
                                          (0.0, 0.0, 0.0, 0.25))),
            bg_padding=int(getattr(t, "panel_bg_padding", 10)),
        ),
        depth_test_default=str(getattr(t, "depth_test_default", "LESS")),
        font_path=str(getattr(t, "font_path", "")),
    )


DEFAULT_THEME = Theme()


_AXIS_FALLBACK = {
    "X": (1.0, 0.27, 0.27, 1.0),
    "Y": (0.27, 0.75, 0.27, 1.0),
    "Z": (0.27, 0.27, 1.00, 1.0),
}


def axis_color(axis: str) -> tuple[float, float, float, float]:
    """Return Blender's built-in axis_x/y/z color with alpha=1.0."""
    try:
        ui = bpy.context.preferences.themes[0].user_interface
        src = {"X": ui.axis_x, "Y": ui.axis_y, "Z": ui.axis_z}[axis]
        return (src[0], src[1], src[2], 1.0)
    except (KeyError, AttributeError, IndexError):
        return _AXIS_FALLBACK[axis]
