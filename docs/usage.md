# Usage

## Core Workflow

1. **Select target objects** in the 3D Viewport.
2. Open the **Cursor BBox** panel in the Sidebar (N-Panel).
3. Choose one of the interactive operators to start the tool.
4. Use keyboard shortcuts to manipulating the cursor or mark geometry.
5. Press **Space** or **Enter** to finalize and create the geometry.

---

## Interactive Operators

These operators run modally, allowing you to interact with the scene before creating geometry.

### 1. Interactive Box
**Goal:** Place the 3D cursor precisely and create an aligned bounding box.

- **Primary Action:** Fits a box around the *active object* or *marked elements*.
- **Features:** 
    - Raycasts against faces to align the cursor.
    - **Scroll** to cycle through edge alignments for the box orientation.
    - **Snap (S)** cursor to vertices, edges, or face centers without exiting the tool.
    - Mark specific faces (`LMB` or `F`) to fit the box *only* to those areas.
- **Best Use Case:** When you need a bounding box aligned to a specific angled surface, or when fitting a box around a specific sub-region of a mesh.

### 2. Interactive Hull
**Goal:** Create a convex hull wrapping specific parts of your geometry.

- **Primary Action:** Generates a convex hull mesh enclosing all marked elements.
- **Features:**
    - **Hover** over faces to preview the selection.
    - **Mark (LMB)** faces to include them in the hull calculation.
    - **Coplanar Selection (C)** allows you to quickly grab flat regions.
    - **Add Points (A)** to include arbitrary points in space (or surface hits) in the hull.
- **Best Use Case:** Creating custom collision shapes or "shrink-wrapping" complex geometry groups.

### 3. Interactive Sphere
**Goal:** Create a bounding sphere encompassing specific geometry.

- **Primary Action:** Generates a sphere enclosing all marked elements.
- **Features:** 
    - calculates the center and minimum radius required to envelope all marked vertices and points.
    - Supports the same powerful marking and coplanar selection tools as the Hull operator.
- **Best Use Case:** Simple collision volumes or ensuring an area is fully covered by a radius.

---

## Helper Operators

These are "one-click" actions available in the panel for quick tasks.

- **Auto Fit Box**: Immediately fits a bounding box to the current selection using the scene's *Push* and *Align* settings. Does not enter a modal state.
- **From Selection**: Creates a generic bounding box aligned to the world (or local object axis depending on internal logic) for the selected objects.
- **Set Cursor Only**: Uses the same raycasting logic as the Interactive Box to place the cursor, but exits immediately after placement without creating any geometry.

---

## Controls Reference

| Key | Context | Action |
| :--- | :--- | :--- |
| **LMB** | All | **Mark face** under cursor (Hull/Sphere) or **Place Cursor & Mark** (Box) |
| **Space / Enter** | All | **Finalize** and create the geometry |
| **Scroll** | Box | **Rotate** cursor alignment based on face edges |
| **Shift + Scroll** | All | Adjust **Coplanar Angle** threshold |
| **C** | All | Toggle **Coplanar Face Selection** mode |
| **A** | All | **Add Point** at mouse position (surface hit or cursor loc) |
| **S** | Box | **Snap Cursor** to closest vertex/edge/center |
| **F** | Box | **Mark Face** (alternative to LMB) |
| **Z** | All | **Clear** all marked faces and points |
| **ESC / RMB** | All | **Cancel** operation |

## Parameters

- **Push Offset**: Inflates the generated geometry (Box/Hull) by this amount globally.
- **Align to Face**: (Box/Cursor) If checked, the cursor/box aligns to the normal of the face under the mouse.
- **Auto-Select Coplanar**: Default state for the coplanar toggle.
- **Angle Threshold**: The angle tolerance for detecting coplanar faces.
