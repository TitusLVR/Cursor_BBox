# Cursor Aligned Bounding Box

A powerful Blender addon for precise 3D cursor placement and intelligent bounding shape creation. Create perfectly aligned bounding boxes, convex hulls, and bounding spheres with advanced marking, snapping, and visual feedback features.

## Overview

Cursor BBox revolutionizes how you work with bounding volumes in Blender. Instead of manually aligning objects or using basic bounding box tools, this addon provides an interactive, modal workflow that lets you:

- **Place the 3D cursor** with pixel-perfect precision using raycasting
- **Create aligned bounding shapes** that automatically orient to your geometry
- **Mark specific faces** for selective bounding calculations
- **Add custom points** to include arbitrary locations in your calculations
- **Snap precisely** to vertices, edges, and face centers
- **Visualize everything** in real-time with color-coded feedback

Perfect for game development, collision mesh creation, architectural visualization, and any workflow requiring precise bounding volumes.

## Key Features

### 🎯 Precision Cursor Placement
- **Raycast-based positioning**: Hover over any surface to place the cursor exactly where you need it
- **Face alignment**: Automatically align the cursor rotation to face normals
- **Edge-based orientation**: Use mouse wheel to cycle through edge alignments for perfect box orientation
- **Smart snapping**: Snap to vertices, edges, or face centers with a single keypress

### 📦 Multiple Bounding Shape Types
- **Interactive Box**: Create axis-aligned or face-aligned bounding boxes
- **Interactive Hull**: Generate convex hulls wrapping marked geometry
- **Interactive Sphere**: Create bounding spheres encompassing selected elements
- **Auto Fit Box**: One-click bounding box generation with current settings

### 🎨 Advanced Marking System
- **Face marking**: Selectively mark faces to include only specific regions in calculations
- **Point marking**: Add custom points in 3D space to influence bounding calculations
- **Coplanar selection**: Automatically select connected coplanar faces with adjustable angle threshold
- **Visual feedback**: See marked faces highlighted in red, selected edges in green

### ⚙️ Flexible Configuration
- **Push offset**: Inflate or deflate generated geometry by a specified amount
- **Material system**: Automatically apply materials and colors to created objects
- **Collection management**: Organize generated objects into dedicated collections
- **Custom naming**: Configure naming patterns for different shape types

### 🎮 Intuitive Controls
- **Modal workflow**: Stay in the tool for multiple operations without exiting
- **Keyboard shortcuts**: Efficient key-based controls for all operations
- **Pie menu support**: Quick access via Shift+Alt+C
- **Real-time preview**: See bounding shapes before finalizing

## Use Cases

- **Game Development**: Create collision meshes, trigger volumes, and bounding boxes for physics
- **Architectural Visualization**: Generate precise bounding volumes for room calculations
- **3D Modeling**: Quickly create reference boxes and alignment helpers
- **Animation**: Set up precise pivot points and alignment guides
- **Technical Art**: Generate custom collision shapes and bounding volumes
