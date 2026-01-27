![Cursor BBox Addon](docs/img/cursor_bbox_addon.png)

# Cursor Aligned Bounding Box

Blender addon for creating bounding volumes (boxes, hulls, spheres) aligned to the 3D cursor with face marking and coplanar selection.

**[Documentation](https://tituslvr.github.io/Cursor_BBox/)** | **[Installation](https://tituslvr.github.io/Cursor_BBox/installation/)** | **[Controls](https://tituslvr.github.io/Cursor_BBox/#controls)** | **[Releases](https://github.com/TitusLVR/Cursor_BBox/releases)**

## Key Features

- **Interactive Placement**: Raycast-based cursor alignment to faces and edges.
- **Bounding Shapes**: Box, Convex Hull, and Sphere generation.
- **Smart Selection**: Face marking, coplanar face detection, and custom point addition.
- **Visual Feedback**: Real-time wireframe previews and snapping indicators.

## Operators

| Operator | Description |
| :--- | :--- |
| **Interactive Box** | Create a cursor-aligned bounding box. Supports face marking and edge rotation. |
| **Interactive Hull** | Generate a convex hull from marked faces and points. |
| **Interactive Sphere** | Create a minimum bounding sphere for marked geometry. |
| **Set & Fit Box** | Keep it simple. Instantly sets cursor and fits a box to selection. |
| **Set Cursor** | Raycast-based cursor placement without geometry creation. |

## Quick Start

1. **Install**: Copy the `Cursor_BBox` folder to your Blender addons directory or install the `.zip`.
2. **Access**: Open the **N-Panel** in the 3D Viewport and look for the `Cursor BBox` tab.
3. **Usage**: Select an object, choose an operator (e.g., **Interactive Box**), and use `Space` to confirm.

**Requirements**: Blender 4.0+