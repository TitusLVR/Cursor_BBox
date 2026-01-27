# Usage Reference

## Controls

### Mouse Interaction

| Action | Context | Description |
| :--- | :--- | :--- |
| **LMB** | Box | Place cursor / Mark face |
| **LMB** | Hull/Sphere | Toggle face marking |
| **RMB** | All | Cancel operation |
| **Mouse Wheel** | Box | Cycle cursor rotation (cycle closest edge alignment) |
| **Shift + Wheel** | All | Adjust coplanar angle threshold |

### Keyboard Shortcuts

| Key | Action | Details |
| :--- | :--- | :--- |
| **Space** / **Enter** | Confirm | Create the bounding shape and exit |
| **ESC** | Cancel | Exit without creating geometry |
| **S** | Snap | Snap cursor to nearest vertex, edge center, or face center |
| **F** | Mark Face | Toggle face marking (Box mode) |
| **A** | Add Point | Add a custom point at cursor location (Hull/Sphere) |
| **C** | Coplanar / Plane | Toggle coplanar selection (Normal) or Construction Plane (Point Mode) |
| **Z** | Clear | Clear all marked faces and points |
| **Shift+Alt+C** | Pie Menu | Open addon pie menu (Global) |

## Parameters (N-Panel)

Located in the **Cursor BBox** tab.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| **Push Offset** | Float | `0.01` | Inflation margin for generated geometry. Negative values shrink. |
| **Align to Face** | Bool | `True` | Automatically align cursor rotation to face normals. |
| **Auto-Select Coplanar** | Bool | `False` | Enable coplanar selection by default on startup. |
| **Angle Threshold** | Float | `5°` | Angular tolerance for coplanar face detection. |
| **Use Material** | Bool | `False` | Assign a debug material to created meshes. |
| **Color** | Color | `Orange` | Color for debug material and UI highlights. |
| **Collection** | String | `CursorBBox` | Name of the collection where shapes are created. |

## Quick Notes

- **Modes**: Works in **Object Mode** (uses active object/marked faces) and **Edit Mode** (uses selected faces).
- **Extension**: Shape dimensions can be manually extended by adding points (`A` key) at the cursor location.
- **Selection**: Select objects *before* starting an operator.
- **Marking**: In Hull/Sphere modes, if no faces are marked, the operation may fail or do nothing.
- **Performance**: High-poly meshes may lag with `Auto-Select Coplanar` enabled. Use `C` to toggle it only when needed.
