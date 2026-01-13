# Usage

## Getting Started

The Cursor BBox addon provides both quick one-click operations and powerful interactive modal tools. This guide covers all features, controls, and workflows in detail.

## Core Workflow

The typical workflow for using the interactive tools:

1. **Select target objects** in the 3D Viewport (you can select multiple objects)
2. Open the **Cursor BBox** panel in the Sidebar (press `N` key)
3. Choose one of the interactive operators to start the tool
4. Use keyboard shortcuts and mouse interactions to manipulate the cursor or mark geometry
5. Press **Space** or **Enter** to finalize and create the geometry
6. Press **ESC** or **RMB** to cancel at any time

---

## Interactive Operators

These operators run in a modal state, allowing you to interact with the scene before creating geometry. They provide real-time visual feedback and support multiple operations before finalizing.

### 1. Interactive Box

**Purpose:** Place the 3D cursor precisely and create an aligned bounding box.

**How it works:**
- Fits a box around the *active object* (last selected) or *marked elements* (if faces/points are marked)
- The box orientation follows the cursor's rotation, which can be aligned to faces and edges
- Real-time preview shows the bounding box before finalization

**Key Features:**
- **Raycast alignment**: Hover over faces to align the cursor to surface normals
- **Edge-based rotation**: Use mouse wheel to cycle through edge alignments for perfect box orientation
- **Smart snapping**: Press `S` to snap cursor to the closest vertex, edge midpoint, or face center
- **Selective bounding**: Mark specific faces (`LMB` or `F`) to fit the box only to those areas
- **Point inclusion**: Add custom points (`A`) to influence the bounding calculation

**Best Use Cases:**
- Creating collision boxes aligned to angled surfaces
- Fitting bounding boxes around specific sub-regions of a mesh
- Setting up precise pivot points with aligned geometry
- Creating reference boxes for modeling or animation

**Workflow Example:**
1. Select your target object
2. Start Interactive Box
3. Hover over the face you want to align to
4. Scroll to rotate the box orientation if needed
5. Optionally mark specific faces with `F` or add points with `A`
6. Press `Space` to create the box

### 2. Interactive Hull

**Purpose:** Create a convex hull mesh wrapping specific parts of your geometry.

**How it works:**
- Generates a convex hull (the smallest convex shape) that encloses all marked faces and points
- The hull is calculated from the vertices of marked faces plus any custom points
- Creates a new mesh object with the hull geometry

**Key Features:**
- **Face marking**: Hover and click (`LMB`) to mark faces for inclusion
- **Coplanar selection**: Press `C` to toggle automatic selection of connected coplanar faces
- **Point addition**: Press `A` to add arbitrary points in 3D space to the hull calculation
- **Visual preview**: See marked faces highlighted in red
- **Angle threshold**: Adjust coplanar detection sensitivity with `Shift + Scroll`

**Best Use Cases:**
- Creating custom collision shapes for game engines
- Generating simplified geometry for LOD (Level of Detail) systems
- "Shrink-wrapping" complex geometry groups
- Creating simplified representations of organic shapes

**Workflow Example:**
1. Select objects containing the geometry you want to hull
2. Start Interactive Hull
3. Hover over faces and click `LMB` to mark them
4. Press `C` to enable coplanar selection for flat regions
5. Optionally press `A` to add custom points
6. Press `Space` to generate the hull mesh

### 3. Interactive Sphere

**Purpose:** Create a bounding sphere encompassing specific geometry.

**How it works:**
- Calculates the minimum-radius sphere that encloses all marked vertices and points
- The sphere center is the geometric center of all marked elements
- Radius is automatically calculated to encompass everything

**Key Features:**
- **Automatic calculation**: Center and radius computed from marked elements
- **Same marking tools**: Uses the same face marking and point addition as Hull
- **Coplanar support**: Works with coplanar face selection
- **Visual feedback**: Preview shows marked elements

**Best Use Cases:**
- Simple collision volumes for spherical objects
- Ensuring an area is fully covered by a radius
- Creating trigger zones and detection volumes
- Quick bounding volume generation

**Workflow Example:**
1. Select target objects
2. Start Interactive Sphere
3. Mark faces or add points to define the volume
4. Press `Space` to create the sphere

---

## Helper Operators

These are quick, one-click operations that don't enter a modal state. Perfect for fast workflows when you don't need interactive control.

### Auto Fit Box

**What it does:** Immediately creates a bounding box around the current selection.

**Features:**
- Uses current scene settings (Push Offset, Align to Face)
- Works with multiple selected objects
- No modal interaction required
- Fastest way to create a bounding box

**When to use:** Quick bounding box creation when you don't need precise cursor placement or face marking.

### From Selection

**What it does:** Creates a generic bounding box aligned to world or object axes.

**Features:**
- Axis-aligned bounding box (AABB)
- Works with current selection
- Applies Push Offset if configured
- Simple and straightforward

**When to use:** When you need a basic bounding box without alignment considerations.

### Set Cursor Only

**What it does:** Places the 3D cursor using raycasting, without creating any geometry.

**Features:**
- Same raycasting logic as Interactive Box
- Respects "Align to Face" setting
- Exits immediately after placement
- Perfect for cursor positioning workflows

**When to use:** When you only need to position the cursor precisely, without creating bounding shapes.

---

## Complete Controls Reference

### Mouse Controls

| Input | Context | Action |
| :--- | :--- | :--- |
| **LMB** | Box | Place cursor at raycast hit & mark face (if applicable) |
| **LMB** | Hull/Sphere | Mark/unmark face under cursor |
| **RMB** | All | Cancel operation |
| **Scroll** | Box | Cycle through edge alignments for cursor rotation |
| **Shift + Scroll** | All | Adjust coplanar angle threshold (when coplanar mode active) |

### Keyboard Controls

| Key | Context | Action | Details |
| :--- | :--- | :--- | :--- |
| **Space / Enter** | All | **Finalize** | Create the geometry and exit modal |
| **ESC** | All | **Cancel** | Exit without creating anything |
| **S** | Box | **Snap Cursor** | Snap to closest vertex/edge/face center on current face |
| **F** | Box | **Mark Face** | Alternative to LMB for marking faces |
| **A** | All | **Add Point** | Add point marker at cursor/raycast location |
| **C** | All | **Toggle Coplanar** | Enable/disable automatic coplanar face selection |
| **Z** | All | **Clear All** | Remove all marked faces and points |
| **Shift+Alt+C** | All | **Pie Menu** | Open quick access pie menu (if configured) |

### Visual Feedback

The addon provides real-time visual feedback:

- **Green edges**: Currently selected edge alignment (Interactive Box)
- **Red faces**: Marked faces that will be included in calculations
- **Point markers**: Small indicators showing custom point locations
- **Bounding preview**: Wireframe preview of the final bounding shape
- **Cursor preview**: Visual indication of cursor position and rotation

---

## Parameters & Settings

All settings are accessible in the Cursor BBox panel (`N` key in 3D Viewport).

### Geometry Parameters

**Push Offset** (Float, default: 0.01)
- Inflates or deflates the generated geometry by this amount
- Positive values expand outward, negative values shrink inward
- Applied globally to Box and Hull operations
- Useful for creating collision meshes with padding

**Align to Face** (Boolean, default: True)
- When enabled, cursor/box aligns to the normal of the face under the mouse
- When disabled, maintains current cursor rotation
- Affects Interactive Box, Auto Fit Box, and Set Cursor Only

### Coplanar Selection

**Auto-Select Coplanar** (Boolean, default: False)
- Default state for coplanar face selection mode
- When enabled, automatically selects connected faces within angle threshold
- Can be toggled during modal operations with `C` key

**Angle Threshold** (Float, default: 5°)
- The angular tolerance for detecting coplanar faces
- Lower values = stricter (only very flat surfaces)
- Higher values = more lenient (includes slightly curved surfaces)
- Adjustable during operation with `Shift + Scroll`

### Material & Appearance

**Use Material** (Boolean, default: False)
- When enabled, applies a material to created objects
- Material is automatically created and managed by the addon

**Color** (RGB, default: Orange #FF943B)
- Color applied to the material and object color
- Can be customized per-project
- Updates existing objects in the collection when changed

### Naming & Organization

**Collection** (String, default: "CursorBBox")
- Name of the collection where created objects are placed
- Collection is created automatically if it doesn't exist
- Helps organize bounding volumes separately from main geometry

**Bounding Box** (String, default: "BBox")
- Naming pattern for box objects
- Objects are named with this prefix and a number

**Bounding Sphere** (String, default: "BSphere")
- Naming pattern for sphere objects

**Convex Hull** (String, default: "ConvexHull")
- Naming pattern for hull objects

---

## Advanced Workflows

### Workflow 1: Precise Collision Box

1. Select your game object
2. Start **Interactive Box**
3. Hover over the main surface you want the box aligned to
4. Scroll to fine-tune edge alignment
5. Press `S` to snap to a precise vertex if needed
6. Mark specific faces with `F` if you only want certain parts
7. Adjust Push Offset in panel for padding
8. Press `Space` to create

### Workflow 2: Complex Collision Hull

1. Select objects with complex geometry
2. Start **Interactive Hull**
3. Enable coplanar selection (`C`)
4. Adjust angle threshold with `Shift + Scroll` to match your needs
5. Click on key areas to mark faces
6. Use coplanar selection to grab entire flat regions
7. Add custom points (`A`) for specific collision points
8. Press `Space` to generate hull

### Workflow 3: Multiple Bounding Volumes

1. Create your first bounding shape
2. The object is automatically added to the CursorBBox collection
3. Repeat for additional volumes
4. All volumes are organized in the same collection
5. Use collection visibility to toggle them on/off

### Workflow 4: Cursor Placement Workflow

1. Use **Set Cursor Only** for precise cursor placement
2. Place cursor on surfaces using raycasting
3. Use `S` key to snap to precise locations
4. Cursor rotation follows face normals (if Align to Face enabled)
5. Perfect for setting up pivot points or reference locations

---

## Tips & Best Practices

1. **Selection Matters**: Always select objects before starting operations. The addon works with selected objects only.

2. **Active Object**: The last selected object (active object) is used as the primary target for some operations.

3. **Combining Marking Methods**: You can combine face marking and point addition for complex bounding calculations.

4. **Coplanar Selection**: Use coplanar selection for flat surfaces - it's much faster than marking faces individually.

5. **Visual Feedback**: Pay attention to the color-coded feedback - green for edges, red for marked faces.

6. **Push Offset**: Use small positive values (0.01-0.1) for collision meshes to prevent intersection issues.

7. **Collection Organization**: Keep bounding volumes in a separate collection for easy management and toggling.

8. **Material System**: Enable materials if you want visual distinction, or disable for cleaner viewport.

9. **Angle Threshold**: Start with default (5°) and adjust based on your geometry's flatness.

10. **Cancel Anytime**: Don't hesitate to cancel (`ESC`) and restart if something doesn't look right - the workflow is designed to be iterative.
