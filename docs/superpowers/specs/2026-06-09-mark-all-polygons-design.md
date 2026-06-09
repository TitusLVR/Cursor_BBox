# Mark All Polygons in Interactive Modals — Design

**Date:** 2026-06-09
**Status:** Approved (pending spec review)

## Problem

In the interactive modal operators (Interactive Box, Interactive Sphere,
Interactive Hull) the user marks faces one at a time with LMB, then builds a
single combined primitive from the marked faces. When the user wants the
primitive to enclose *everything* across all selected objects, they must click
every face by hand. There is no way to say "use all polygons of all selected
objects."

The user wants a hotkey, available inside each interactive modal, that marks
**every polygon of every selected mesh object at once** — as if all polygons
had been selected manually — so a single combined box / sphere / convex hull
can be built immediately.

## Scope

- Applies to the three interactive modal operators only:
  `cursor_bbox.interactive_box`, `cursor_bbox.interactive_sphere`,
  `cursor_bbox.interactive_hull`.
- Not a panel/HUD button; it is an in-modal hotkey.
- Out of scope: the non-interactive `From Selection` box button and the
  collision-decomposition tools. Their behavior is unchanged.

## Design

### Shared helper (`functions/utils.py`)

```python
def build_all_faces_dict(objects, use_depsgraph=False):
    """Return {obj: set(all polygon indices)} for every mesh object in `objects`.

    Mirrors the structure of the operators' `self.marked_faces` so the result
    plugs directly into the existing fit/build pipeline. Objects with no
    polygons are skipped.
    """
```

Implementation walks each object, gets its (optionally evaluated) mesh via the
existing `get_evaluated_mesh`, and returns `set(range(len(mesh.polygons)))`.
Polygon indices line up with the indices already stored in `marked_faces`
(which come from raycast `face_index` / `get_faces_to_process`).

### Per-operator modal hotkey (Ctrl+A)

In each operator's `modal()`, add an early handler placed **immediately after
the existing Ctrl+Z undo/redo block** (so it is evaluated before the plain `A`
point-mode toggle):

```python
# Mark all polygons of all selected objects (Ctrl+A)
if (event.type == 'A' and event.value == 'PRESS'
        and event.ctrl and not self.point_mode):
    self._push_undo()
    self.marked_faces = build_all_faces_dict(
        self.original_selected_objects, use_depsgraph=self.use_depsgraph)
    clear_all_markings()
    for obj, faces in self.marked_faces.items():
        if faces:
            mark_faces_batch(obj, faces, use_depsgraph=self.use_depsgraph)
    # operator-specific preview refresh:
    #   box    -> update_marked_faces_bbox(...)
    #   sphere -> update_marked_faces_sphere(...)
    #   hull   -> update_marked_faces_convex_hull(...)
    self.report({'INFO'}, "Marked all polygons of selected objects")
    context.area.tag_redraw()
    return {'RUNNING_MODAL'}
```

Each operator already calls its own preview-update function elsewhere; the same
call (with the same arguments those call sites use) is reused here.

### Collision guard

The existing plain-`A` point-mode handler (`elif event.type == 'A' and
event.value == 'PRESS':`) gets `and not event.ctrl` added so a stray Ctrl+A can
never toggle point mode even if control flow changes later. The early Ctrl+A
`if` returns first in practice; the guard is defensive.

### HUD

Add one line to each modal's Object-Mode help section in `_setup_hud`:

```python
HUDItem("Mark all polygons", "Ctrl+A"),
```

## Behavior details

- **Mark-all only.** Ctrl+A always marks everything; it does not toggle off.
  The existing `Z` clears markings and `Ctrl+Z` undoes the mark-all.
- **Respects selection restriction.** Only objects in
  `self.original_selected_objects` are marked — the same set LMB marking is
  limited to (collection instances already resolved to real objects in
  `invoke`).
- **Cursor-aligned.** No orientation change; the combined primitive uses the
  same cursor-aligned fit the modals already use.
- **Depsgraph aware.** Uses the operator's current `use_depsgraph` toggle so
  polygon indices match the marked-face visuals.
- **Not in point mode.** Ctrl+A is ignored while point mode is active (marking
  faces is meaningless there).

## Files touched

- `functions/utils.py` — add `build_all_faces_dict`.
- `operators/interactive_box.py` — Ctrl+A handler, `A` guard, HUD line.
- `operators/interactive_sphere.py` — Ctrl+A handler, `A` guard, HUD line.
- `operators/interactive_hull.py` — Ctrl+A handler, `A` guard, HUD line.

## Testing

Verified live in Blender via the blender-mcp bridge:
1. Select 2+ mesh objects, launch each interactive modal.
2. Press Ctrl+A → all polygons of all selected objects show as marked and the
   combined preview updates.
3. Press SPACE/Enter → one combined box / sphere / hull is created enclosing
   all selected geometry.
4. Z clears; Ctrl+Z undoes the mark-all. Ctrl+A in point mode is a no-op.
```

