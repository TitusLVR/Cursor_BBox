![Cursor BBox Addon](docs/img/cursor_bbox_addon.png)

# Cursor Aligned Bounding Box

Blender addon for cursor-aligned bounding shape creation with face marking and coplanar selection.

**[Documentation](https://tituslvr.github.io/Cursor_BBox/)** | **[Releases](https://github.com/TitusLVR/Cursor_BBox/releases)** | **[Source](https://github.com/TitusLVR/Cursor_BBox)**

## Features

**Operators**
- Interactive Box — Fit bounding box around marked faces or active object
- Interactive Hull — Fit convex hull around marked faces
- Interactive Sphere — Fit bounding sphere around marked faces
- Set & Fit Box — Set cursor and immediately fit bounding box
- Set Cursor — Set cursor location and rotation aligned to surface

**Marking & Selection**
- Face marking with LMB or F key
- Coplanar face selection with adjustable angle threshold
- Custom point addition for precise bounds
- Visual feedback (red faces, green edges)

**Configuration**
- Push offset for geometry inflation/deflation
- Material and color assignment
- Collection organization
- Custom object naming

## Installation

1. Copy `Cursor_BBox` folder to Blender addons directory
2. Enable in Edit > Preferences > Add-ons
3. Access panel via N key in 3D Viewport

**Addon Paths**
- Windows: `%APPDATA%\Blender Foundation\Blender\[Version]\scripts\addons\`
- macOS: `~/Library/Application Support/Blender/[Version]/scripts/addons/`
- Linux: `~/.config/blender/[Version]/scripts/addons/`

## Requirements

- Blender 4.0 or higher
- GPU with OpenGL support

## Documentation

- [Installation Guide](https://tituslvr.github.io/Cursor_BBox/installation/) — Setup and troubleshooting
- [Usage Guide](https://tituslvr.github.io/Cursor_BBox/usage/) — Controls and workflows
- [GitHub Issues](https://github.com/TitusLVR/Cursor_BBox/issues) — Bug reports and feature requests