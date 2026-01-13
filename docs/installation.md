# Installation

## Quick Start

1. **Download the addon**: Clone or download this repository
2. **Locate Blender's addons directory**: 
   - **Windows**: `C:\Users\[YourUsername]\AppData\Roaming\Blender Foundation\Blender\[Version]\scripts\addons\`
   - **macOS**: `~/Library/Application Support/Blender/[Version]/scripts/addons/`
   - **Linux**: `~/.config/blender/[Version]/scripts/addons/`
3. **Copy the addon folder**: Place the entire `Cursor_BBox` folder into the addons directory
4. **Enable the addon**: 
   - Open Blender
   - Go to `Edit > Preferences > Add-ons`
   - Search for "Cursor Aligned Bounding Box"
   - Check the checkbox to enable it
5. **Access the panel**: Press `N` in the 3D Viewport to open the sidebar, then navigate to the "Cursor BBox" tab

## Installation Methods

### Method 1: Manual Installation (Recommended)
This is the standard method for installing Blender addons:

1. Download or clone the repository
2. Copy the `Cursor_BBox` folder to your Blender addons directory
3. Enable through Blender's preferences

### Method 2: Install from File
If you have a `.zip` file of the addon:

1. Open Blender
2. Go to `Edit > Preferences > Add-ons`
3. Click `Install...` button
4. Select the `.zip` file
5. Enable the addon from the list

## Post-Installation Setup

After installation, you may want to:

1. **Set up keyboard shortcuts**: The addon includes a pie menu accessible via `Shift+Alt+C`. You can customize this in `Edit > Preferences > Keymap`
2. **Configure default settings**: Open the Cursor BBox panel (`N` key in 3D Viewport) and adjust:
   - Push Offset (default: 0.01)
   - Align to Face (default: enabled)
   - Material settings
   - Collection naming
3. **Test the installation**: 
   - Select an object in your scene
   - Open the Cursor BBox panel
   - Try the "Auto Fit Box" button to verify everything works

## Requirements

### Minimum Requirements
- **Blender Version**: 3.0 or higher (tested up to 4.0+)
- **GPU**: Any GPU with OpenGL support (required for viewport drawing)
- **Python**: Included with Blender (no separate installation needed)

### Recommended
- **Blender 4.0+**: For best compatibility and performance
- **Dedicated GPU**: For smooth viewport performance with complex scenes
- **8GB+ RAM**: For working with large meshes and multiple objects

## Troubleshooting

### Addon Not Appearing
- Ensure the folder structure is correct: `[addons]/Cursor_BBox/__init__.py` must exist
- Check that you're looking in the correct Blender version's addons folder
- Try restarting Blender completely

### Panel Not Showing
- Press `N` in the 3D Viewport to toggle the sidebar
- Ensure you're in Object Mode (not Edit Mode)
- Check that the addon is enabled in Preferences

### Operators Not Working
- Make sure you have at least one object selected
- Verify you're in the 3D Viewport (not other editors)
- Check the Blender console (`Window > Toggle System Console` on Windows) for error messages

### Performance Issues
- Reduce the number of selected objects
- Disable "Auto-Select Coplanar" if working with very dense meshes
- Lower the viewport quality settings in Blender preferences

## Updating the Addon

To update to a newer version:

1. **Disable the addon** in Preferences
2. **Remove the old folder** from the addons directory
3. **Copy the new version** following the installation steps above
4. **Re-enable the addon**

Your settings and preferences will be preserved between updates.
