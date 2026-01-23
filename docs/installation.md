![Cursor BBox Addon](img/cursor_bbox_addon.png)

# Installation

## Quick Install

1. Download [latest release](https://github.com/TitusLVR/Cursor_BBox/releases) or clone repository
2. Copy `Cursor_BBox` folder to Blender addons directory
3. Enable in Edit > Preferences > Add-ons (search "Cursor Aligned Bounding Box")
4. Access via N key in 3D Viewport > Cursor BBox tab

### Addon Directory Paths

| OS | Path |
|:---|:-----|
| Windows | `%APPDATA%\Blender Foundation\Blender\[Version]\scripts\addons\` |
| macOS | `~/Library/Application Support/Blender/[Version]/scripts/addons/` |
| Linux | `~/.config/blender/[Version]/scripts/addons/` |

**Folder Structure**
```
addons/
  └── Cursor_BBox/
      ├── __init__.py
      ├── operators/
      ├── functions/
      ├── settings/
      └── ui/
```

!!! warning
    `__init__.py` must be directly inside `Cursor_BBox/` folder.

## Alternative: Install from ZIP

1. Edit > Preferences > Add-ons
2. Click Install button
3. Select `.zip` file
4. Enable addon in list

## Configuration

### Keyboard Shortcuts

Default pie menu: `Shift+Alt+C`

To customize:
1. Edit > Preferences > Keymap
2. Search "Cursor BBox" or "call_menu_pie"
3. Expand 3D View > 3D View (Global)
4. Modify key combination

### Default Settings

| Setting | Default | Range |
|:--------|:--------|:------|
| Push Offset | 0.01 | Any float |
| Align to Face | Enabled | Boolean |
| Auto-Select Coplanar | Disabled | Boolean |
| Angle Threshold | 5° | 0.01-180° |
| Use Material | Disabled | Boolean |
| Color | #FF943B | RGB |

### Test Installation

1. Select mesh object
2. Open Cursor BBox panel (N key)
3. Click Auto Fit Box
4. Verify bounding box created

## Requirements

### Minimum

| Component | Requirement |
|:----------|:------------|
| Blender | 4.0+ |
| GPU | OpenGL support |
| RAM | 4GB |
| Python | Included with Blender |

### Recommended

| Component | Specification |
|:----------|:--------------|
| Blender | 4.2+ or 5.0+ |
| GPU | Dedicated GPU |
| RAM | 8GB+ |
| Display | 1920×1080+ |

### Tested Versions
- Blender 4.0.x, 4.1.x, 4.2.x, 5.0.x

!!! info
    Version 3.6+ may work but not officially supported.

## Troubleshooting

### Addon Not Appearing

**Cause:** Incorrect folder structure or location

**Solutions:**
- Verify `__init__.py` inside `Cursor_BBox/`
- Check correct addons directory
- Restart Blender
- Check System Console (Window > Toggle System Console) for errors

### Panel Not Visible

**Cause:** Sidebar hidden or wrong mode

**Solutions:**
- Press N to toggle sidebar
- Switch to Object Mode
- Scroll through sidebar tabs
- Verify addon enabled (green checkbox)

### Operators Not Working

**Cause:** No objects selected or wrong context

**Solutions:**
- Select at least one mesh object
- Verify 3D Viewport active
- Check System Console for errors
- Disable and re-enable addon
- Verify Blender version 4.0+

### Performance Issues

**Cause:** High polygon count or many objects

**Solutions:**
- Reduce selected object count
- Disable Auto-Select Coplanar for dense meshes
- Lower viewport quality (Edit > Preferences > Viewport)
- Update GPU drivers

### Python Errors

**Cause:** Missing or corrupted files

**Solutions:**
- Download fresh copy from releases
- Verify all files present
- Check file permissions
- Try different install location

## Updating

1. Disable addon (Edit > Preferences > Add-ons)
2. Close Blender
3. Delete old `Cursor_BBox` folder
4. Install new version
5. Restart Blender
6. Re-enable addon

!!! tip
    Settings preserved in Blender user config.

## Uninstalling

1. Disable addon in Preferences
2. Close Blender
3. Delete `Cursor_BBox` folder from addons directory
4. Restart Blender

## Support

- [Usage Guide](usage.md) — Workflow documentation
- [GitHub Issues](https://github.com/TitusLVR/Cursor_BBox/issues) — Bug reports

**Issue Template:**
- Blender version
- Operating system
- Steps to reproduce
- Console error messages
