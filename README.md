# Cursor Aligned Bounding Box

Blender addon for precise cursor placement and cursor-aligned bounding box creation with advanced marking and snapping features.

## Features

- **Raycast cursor placement** with face/edge alignment
- **Interactive edge selection** via mouse wheel
- **Real-time bounding box preview** with visual feedback
- **Face marking system** with 'F' key for selective bounding
- **Point marking system** with 'A' key for custom points
- **Smart snapping** with 'S' key to face elements (vertices/edges/center)
- **Persistent modal operation** for multiple actions
- **Works only with selected objects** for focused workflow
- **Visual highlighting** of edges and marked faces

## Installation

1. Place files in: `[Blender]/scripts/addons/Cursor_BBox/`
2. Enable in Preferences > Add-ons > "Cursor Aligned Bounding Box"

## Controls

**Modal Operation:**
- `LMB` - Place cursor / Create bbox
- `Scroll` - Select edge alignment  
- `F` - Mark/unmark face under cursor
- `A` - Add point marker at cursor location
- `S` - Snap cursor to closest face element (vertex/edge/center)
- `Z` - Clear all markings (faces and points)
- `C` - Create bbox only (without moving cursor)
- `ESC/RMB` - Cancel operation

**Panel:** View3D > Sidebar (N) > Cursor BBox

## Workflow

1. **Select target objects** in your scene
2. **Start modal tool** from panel or shortcut
3. **Position cursor** by hovering over surfaces
4. **Select edge orientation** with mouse wheel
5. **Mark faces** with 'F' key (optional)
6. **Add custom points** with 'A' key (optional)  
7. **Snap precisely** with 'S' key to face elements
8. **Create bounding box** with LMB or 'C' key

## Advanced Features

- **Face-specific snapping**: 'S' key only snaps to elements of the face under cursor
- **Combined bounding**: Create boxes from both marked faces and custom points
- **Visual feedback**: Real-time preview of final bounding box
- **Edge highlighting**: See selected edge alignment in green
- **Face marking**: Red highlighting shows marked faces

## Requirements

- Blender 3.0+
- GPU with OpenGL support