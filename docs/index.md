![Cursor BBox Addon](img/cursor_bbox_addon.png)

# Cursor Aligned Bounding Box

Blender addon for cursor-aligned bounding shape creation with face marking and coplanar selection.

## Quick Links

- [GitHub Repository](https://github.com/TitusLVR/Cursor_BBox)
- [Latest Release](https://github.com/TitusLVR/Cursor_BBox/releases)
- [Installation Guide](installation.md)
- [Usage Guide](usage.md)

## Overview

Creates bounding volumes (boxes, convex hulls, spheres) aligned to 3D cursor with face marking and point addition support.

**Core Features**
- Raycast-based cursor placement with face/edge alignment
- Multiple bounding shape types (box, hull, sphere)
- Face marking for selective bounding
- Coplanar face selection with angle threshold
- Custom point addition
- Real-time visual feedback

**Use Cases**
- Collision mesh creation for game engines
- LOD generation and simplified geometry
- Architectural space bounding
- Alignment helpers and reference objects

## Operators

### Interactive Box
**Description:** Fit bounding box around marked faces or active object  
Creates cursor-aligned bounding box. Box orientation follows cursor rotation. Supports face marking for partial bounds.

### Interactive Hull
**Description:** Fit convex hull around marked faces  
Generates convex hull from marked face vertices and custom points. Hull encloses all marked elements.

### Interactive Sphere
**Description:** Fit bounding sphere around marked faces  
Creates minimum-radius sphere encompassing marked vertices. Center calculated from marked elements.

### Set & Fit Box
**Description:** Set cursor and immediately fit bounding box  
One-click operation. Places cursor and creates bounding box without modal interaction.

### Set Cursor
**Description:** Set cursor location and rotation aligned to surface  
Raycast-based cursor placement. Aligns to face normals when enabled.

## Key Features

### Face Marking
- Mark faces with LMB or F key
- Visual feedback (red highlight)
- Clear markings with Z key
- Toggle individual faces

### Coplanar Selection
- Automatic connected face selection
- Adjustable angle threshold (default 5°)
- Toggle with C key
- Adjust threshold with Shift + Mouse Wheel

### Cursor Alignment
- Raycast to surface
- Face normal alignment
- Edge-based rotation (mouse wheel)
- Snap to vertices/edges/face centers (S key)

### Visual Feedback
- Red: Marked faces
- Green: Selected edge alignment
- Wireframe: Bounding shape preview
- Point markers: Custom points

## Settings

| Parameter | Default | Description |
|:----------|:--------|:------------|
| Push Offset | 0.01 | Inflate/deflate geometry |
| Align to Face | Enabled | Auto-align cursor to normals |
| Auto-Select Coplanar | Disabled | Default coplanar mode state |
| Angle Threshold | 5° | Coplanar detection tolerance |
| Use Material | Disabled | Apply material to objects |
| Color | #FF943B | Material and display color |
| Collection | CursorBBox | Target collection name |

## System Requirements

| Component | Requirement |
|:----------|:------------|
| Blender | 4.0+ (tested to 5.0+) |
| GPU | OpenGL support |
| Python | Included with Blender |
| OS | Windows, macOS, Linux |

**Version:** 1.0.9
