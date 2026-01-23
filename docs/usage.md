![Cursor BBox Addon](img/cursor_bbox_addon.png)

# Usage

## Workflow

1. Select objects
2. Open Cursor BBox panel (N key > Cursor BBox tab)
3. Run operator
4. Mark faces/add points (interactive operators)
5. Space/Enter to confirm, ESC to cancel

## Operators

### Interactive Box

**Description:** Fit bounding box around marked faces or active object

**Behavior:**
- Fits box to active object or marked faces
- Box orientation follows cursor rotation
- Real-time preview

**Usage:**
1. Start operator
2. Hover over face to align cursor
3. Mouse Wheel to cycle edge alignments
4. F or LMB to mark faces (optional)
5. A to add points (optional)
6. S to snap cursor to vertex/edge/face
7. Space to create

---

### Interactive Hull

**Description:** Fit convex hull around marked faces

**Behavior:**
- Generates convex hull from marked face vertices
- Includes custom points
- Creates new mesh object

**Usage:**
1. Start operator
2. LMB to mark/unmark faces
3. C to toggle coplanar selection
4. Shift + Mouse Wheel to adjust angle threshold
5. A to add points
6. Z to clear markings
7. Space to create

---

### Interactive Sphere

**Description:** Fit bounding sphere around marked faces

**Behavior:**
- Calculates minimum-radius sphere
- Center from geometric center of marked elements
- Radius encompasses all marked vertices

**Usage:**
1. Start operator
2. LMB to mark faces
3. C for coplanar selection
4. A to add points
5. Space to create

---

### Set & Fit Box

**Description:** Set cursor and immediately fit bounding box

**Behavior:**
- Non-modal, instant operation
- Uses current settings
- No face marking

**Usage:**
1. Select objects
2. Click operator
3. Box created immediately

---

### Set Cursor

**Description:** Set cursor location and rotation aligned to surface

**Behavior:**
- Raycast-based placement
- Respects Align to Face setting
- Exits after placement

**Usage:**
1. Start operator
2. Hover over surface
3. LMB to place
4. Tool exits

---

## Controls

### Mouse

| Input | Context | Action |
|:------|:--------|:-------|
| LMB | Box | Place cursor, mark face |
| LMB | Hull/Sphere | Toggle face marking |
| RMB | All | Cancel |
| Mouse Wheel | Box | Cycle edge alignments |
| Shift + Mouse Wheel | All | Adjust angle threshold |

### Keyboard

| Key | Context | Action |
|:----|:--------|:-------|
| Space / Enter | All | Confirm |
| ESC | All | Cancel |
| S | Box | Snap to vertex/edge/face |
| F | Box | Mark face |
| A | All | Add point |
| C | All | Toggle coplanar mode |
| Z | All | Clear markings |
| Shift+Alt+C | Global | Pie menu |

### Visual Feedback

| Element | Color | Meaning |
|:--------|:------|:--------|
| Marked Faces | Red | Included in calculation |
| Selected Edge | Green | Current alignment |
| Point Markers | Yellow/White | Custom points |
| Preview | Wireframe | Bounding shape |

## Parameters

### Geometry

**Push Offset** (Float, default 0.01)
- Inflates/deflates geometry
- Positive: expand, Negative: shrink
- Applies to box and hull

**Align to Face** (Boolean, default True)
- Auto-align cursor to face normal
- Affects Box, Set & Fit Box, Set Cursor

### Coplanar Selection

**Auto-Select Coplanar** (Boolean, default False)
- Default coplanar mode state
- Toggle with C key during operation

**Angle Threshold** (Float, default 5°)
- Angular tolerance for coplanar detection
- Lower: stricter, Higher: more lenient
- Adjust with Shift + Mouse Wheel

### Material

**Use Material** (Boolean, default False)
- Apply material to created objects

**Color** (RGB, default #FF943B)
- Material and object color

### Organization

**Collection** (String, default "CursorBBox")
- Target collection for created objects

**Naming Prefixes**
- Bounding Box: "BBox"
- Bounding Sphere: "BSphere"
- Convex Hull: "ConvexHull"

## Workflows

### Collision Box (Aligned)

1. Select game object
2. Interactive Box
3. Hover main surface
4. Mouse Wheel for edge alignment
5. S to snap if needed
6. Set Push Offset to 0.05
7. Space to create

### Convex Hull (Simplified)

1. Select high-poly object
2. Interactive Hull
3. C to enable coplanar
4. Shift + Mouse Wheel to adjust threshold
5. LMB to mark key areas
6. A to add critical points
7. Space to generate

### Batch Bounding Boxes

1. Configure settings once
2. Select multiple objects
3. Set & Fit Box
4. Boxes created instantly

### Cursor Positioning

1. Set Cursor
2. Hover target surface
3. Mouse Wheel for rotation
4. S to snap
5. LMB to place

## Tips

**Selection**
- Always select objects before running operators
- Active object (last selected) used for some operations

**Marking**
- Coplanar mode faster for flat surfaces
- Combine face marking with point addition
- Z key clears all markings

**Visual Feedback**
- Green = selected edge alignment
- Red = marked faces
- Preview shows final shape

**Push Offset**
- 0.01-0.1 for collision clearance
- Negative values shrink bounds
- 0 for exact fit

**Angle Threshold**
- Hard-surface: 1-5°
- Architectural: 3-7°
- Organic: 10-20°

**Collection Organization**
- All bounds in CursorBBox collection
- Toggle visibility in Outliner
- Easy selection and export

## Troubleshooting

### No Geometry Created

**Cause:** No faces marked in Hull/Sphere mode

**Solution:** Mark at least one face or add points

### Cursor Not Snapping

**Cause:** No face under cursor

**Solution:** Hover over face before pressing S

### Coplanar Not Working

**Cause:** Threshold too low or faces not connected

**Solution:** Increase angle threshold with Shift + Mouse Wheel

### Box Misaligned

**Cause:** Wrong edge alignment selected

**Solution:** Use Mouse Wheel to cycle alignments

### Performance Lag

**Cause:** Too many polygons or objects

**Solution:** 
- Reduce selection count
- Disable Auto-Select Coplanar
- Lower viewport quality

## Quick Reference

### Essential Shortcuts

```
Space/Enter  Confirm
ESC          Cancel
LMB          Mark face
S            Snap cursor
F            Mark face (Box)
A            Add point
C            Toggle coplanar
Z            Clear markings
Mouse Wheel  Cycle edges (Box)
Shift+Wheel  Angle threshold
```

### Operator Summary

```
Interactive Box     Marked faces or active object
Interactive Hull    Convex hull from marked faces
Interactive Sphere  Bounding sphere from marked faces
Set & Fit Box       Instant bounding box
Set Cursor          Cursor placement only
```

## Support

- [Installation Guide](installation.md) — Setup and troubleshooting
- [GitHub Issues](https://github.com/TitusLVR/Cursor_BBox/issues) — Bug reports
- [Releases](https://github.com/TitusLVR/Cursor_BBox/releases) — Latest version
