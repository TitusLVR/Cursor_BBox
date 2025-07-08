# Cursor Aligned Bounding Box

A powerful Blender addon for placing the 3D cursor with raycast and creating precisely aligned bounding boxes with interactive edge selection and real-time preview.

## Features

### 🎯 **Precise Cursor Placement**
- **Raycast-based positioning** - Click on any surface to place cursor
- **Face normal alignment** - Z-axis automatically aligns to face normal
- **Edge direction control** - X-axis aligns to selected edge
- **Interactive edge selection** - Scroll mouse wheel to cycle through face edges
- **Real-time preview** - See cursor orientation before placing

### 📦 **Smart Bounding Box Creation**
- **Cursor-aligned boxes** - Perfect alignment to cursor orientation
- **Push/pull adjustment** - Expand or contract box dimensions
- **Multiple creation modes** - Edit mode (selected faces) or Object mode (whole objects)
- **Raycast object targeting** - Works on any object under mouse cursor
- **Persistent modal** - Create multiple boxes without restarting tool

### 🎨 **Visual Feedback**
- **Green edge highlighting** - Shows selected edge that will become X-axis
- **Yellow bounding box preview** - Real-time preview of final box size and position
- **Customizable colors** - Adjust highlight and preview colors in preferences
- **Transparency control** - Set alpha values for optimal visibility

### 🎮 **Navigation Friendly**
- **Non-blocking navigation** - Pan, orbit, and zoom while tool is active
- **Smart input handling** - Plain scroll selects edges, modified scroll navigates
- **Intuitive controls** - Familiar Blender-style interaction

### ⌨️ **Customizable Shortcuts**
- **Default shortcuts**: 
  - `Ctrl+Shift+C` - Place Cursor
  - `Ctrl+Shift+Alt+B` - Place Cursor & Create BBox
- **Fully customizable** - Change keys and modifiers in preferences
- **Enable/disable** - Turn shortcuts on/off as needed

## Installation

1. Download the addon files
2. Create a folder named `Cursor_BBox` in your Blender addons directory:
   - **Windows**: `%APPDATA%\Blender Foundation\Blender\[VERSION]\scripts\addons\`
   - **macOS**: `~/Library/Application Support/Blender/[VERSION]/scripts/addons/`
   - **Linux**: `~/.config/blender/[VERSION]/scripts/addons/`
3. Place all addon files in the `Cursor_BBox` folder
4. Enable the addon in Blender Preferences > Add-ons > Object > "Cursor Aligned Bounding Box"

### File Structure
```
Cursor_BBox/
├── __init__.py           # Main addon registration
├── functions.py          # Core functionality and GPU drawing
├── operators.py          # Blender operators (modal tools)
├── preferences.py        # Addon preferences and settings
├── properties.py         # Scene properties
├── ui.py                # User interface panel
├── utils.py             # Utility functions
└── README.md            # This file
```

## Usage

### Basic Workflow

1. **Open the panel**: View3D > Sidebar (N) > Cursor BBox tab
2. **Select geometry**: 
   - Edit mode: Select faces you want to bound
   - Object mode: Select objects you want to bound
3. **Start the tool**: Click "Place Cursor" or "Place & Create BBox"
4. **Position cursor**: Hover over target surface
5. **Select edge orientation**: Scroll mouse wheel to choose edge direction
6. **Confirm**: Left-click to place cursor and/or create bounding box

### Controls (During Modal Operation)

| Input | Action |
|-------|--------|
| **Mouse Move** | Preview cursor position and bounding box |
| **Mouse Wheel** | Select edge for X-axis alignment |
| **Left Click** | Place cursor (and create box if using combined tool) |
| **C Key** | Create bounding box without moving cursor |
| **Middle Mouse** | Navigate (pan/orbit) |
| **Shift + Wheel** | Pan left/right |
| **Ctrl + Wheel** | Zoom in/out |
| **ESC / Right Click** | Cancel operation |

### Panel Controls

- **Align to Face**: Toggle face normal alignment
- **Push Value**: Expand/contract bounding box dimensions
- **Place Cursor**: Interactive cursor placement tool
- **Create BBox**: Create box at current cursor position
- **Place & Create BBox**: Combined tool for cursor placement and box creation

## Preferences

Access preferences via: Edit > Preferences > Add-ons > Cursor Aligned Bounding Box

### Default Settings
- **Default Push Value**: Starting push value for new operations
- **Default Align to Face**: Starting face alignment setting

### Visual Settings
- **Edge Highlight Color**: Color for selected edge highlight (default: green)
- **Edge Highlight Width**: Line thickness for edge highlight
- **BBox Preview Color**: Color for bounding box preview (default: yellow)
- **BBox Preview Alpha**: Transparency for preview wireframe
- **Preview Line Width**: Thickness of preview lines
- **Show Preview Faces**: Toggle semi-transparent face display

### Bounding Box Display
- **Show Wireframe**: Display wireframe on created boxes
- **Show All Edges**: Display all edges on created boxes

### Keyboard Shortcuts
- **Enable Shortcuts**: Master toggle for all shortcuts
- **Customizable keys**: Change shortcut keys and modifier combinations
- **Modifier options**: Configure Ctrl, Shift, and Alt usage

## Technical Details

### Requirements
- **Blender 3.0+** (tested with 4.4)
- **GPU with OpenGL support** for visual previews

### Performance
- **Efficient GPU rendering** using Blender's gpu module
- **Real-time updates** with minimal performance impact
- **Optimized raycast operations** for smooth interaction

### Compatibility
- **Works in Edit and Object modes**
- **Supports modified meshes** (with modifiers applied)
- **Handles complex geometry** and multiple selected objects
- **Graceful error handling** with informative user feedback

## Tips and Tricks

### 🎯 **Precision Placement**
- Use edge selection to precisely control bounding box orientation
- Preview shows exact final result - no surprises
- Push value can be negative to create smaller boxes

### 🔄 **Workflow Optimization**
- Use "Place & Create BBox" for quick single-box creation
- Use "Place Cursor" + "C key" for multiple boxes with same orientation
- Adjust push value in real-time to see preview changes

### 🎨 **Visual Customization**
- Adjust preview colors for better visibility against your scene
- Lower alpha values for less intrusive previews
- Disable face preview if you prefer wireframe-only

### ⌨️ **Shortcut Efficiency**
- Customize shortcuts to match your workflow
- Use modifier combinations that don't conflict with other tools
- Disable shortcuts if you prefer panel-only access

## Troubleshooting

### Common Issues

**Preview not showing:**
- Check that "Show BBox Preview" is enabled in preferences
- Ensure you're hovering over a mesh object
- Try adjusting preview alpha if it's too transparent

**Shortcuts not working:**
- Verify shortcuts are enabled in preferences
- Check for conflicts with other addons
- Restart Blender after changing shortcut settings

**Edge selection not responding:**
- Use plain mouse wheel (no Ctrl/Shift modifiers)
- Make sure you're hovering over a face with edges
- Check that the object has proper face geometry

**Bounding box in wrong location:**
- Verify cursor position is correct before creating box
- Check that target object is the intended one
- Ensure mesh has valid geometry (no isolated vertices)

### Performance Tips

- Close unnecessary 3D viewports when using intensive previews
- Adjust preview line width if experiencing lag
- Disable face preview for better performance on complex scenes

## Version History

### v1.1.0
- Added real-time bounding box preview
- Implemented customizable keyboard shortcuts
- Enhanced preferences with visual settings
- Improved GPU-based rendering system
- Added comprehensive user interface

### v1.0.0
- Initial release
- Basic cursor placement with raycast
- Edge selection and highlighting
- Bounding box creation
- Modal operator system

## Contributing

This addon is designed to be modular and extensible. Key areas for potential enhancement:

- Additional alignment modes (vertex, edge midpoint, etc.)
- Custom bounding box shapes (spheres, cylinders, etc.)
- Batch processing capabilities
- Integration with other Blender tools

## License

This addon is provided as-is for educational and productivity purposes. Feel free to modify and distribute according to your needs.

## Support

For issues, suggestions, or contributions:
1. Check the troubleshooting section above
2. Verify you're using a compatible Blender version
3. Check addon preferences for relevant settings
4. Test with simple geometry to isolate issues

---

**Happy bounding box creation!** 📦✨