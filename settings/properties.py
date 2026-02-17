import bpy
import math
from bpy.props import (
    BoolProperty, IntProperty, FloatProperty,
    EnumProperty, PointerProperty,
)

# Shared preset items for both V-HACD and CoACD detail dropdowns
_DETAIL_ITEMS = [
    ('D01', "1 - Minimal", "Barest outline"),
    ('D02', "2 - Coarse", "Rough silhouette"),
    ('D03', "3 - Rough", "Basic shape recognition"),
    ('D04', "4 - Low", "Simple features visible"),
    ('D05', "5 - Medium", "Balanced detail"),
    ('D06', "6 - Moderate", "Good overall coverage"),
    ('D07', "7 - High", "Most features preserved"),
    ('D08', "8 - Detailed", "Fine features captured"),
    ('D09', "9 - Very Detailed", "Near-complete detail"),
    ('D10', "10 - Full", "Maximum fidelity"),
]


# ------------------------------------------------------------------ #
#  Preset update callbacks (lazy-import avoids circular dependencies) #
# ------------------------------------------------------------------ #

def _vhacd_preset_update(self, context):
    from ..operators.collision_vhacd import VHACD_PRESETS
    vals = VHACD_PRESETS.get(self.preset)
    if vals:
        for k, v in vals.items():
            if getattr(self, k) != v:
                setattr(self, k, v)


def _coacd_preset_update(self, context):
    from ..operators.collision_coacd import COACD_PRESETS
    vals = COACD_PRESETS.get(self.preset)
    if vals:
        for k, v in vals.items():
            if getattr(self, k) != v:
                setattr(self, k, v)


def _coacd_u_preset_update(self, context):
    from ..operators.collision_coacd_u import COACD_U_PRESETS
    vals = COACD_U_PRESETS.get(self.preset)
    if vals:
        for k, v in vals.items():
            if getattr(self, k) != v:
                setattr(self, k, v)


# ------------------------------------------------------------------ #
#  V-HACD settings PropertyGroup                                      #
# ------------------------------------------------------------------ #

class CursorBBox_VHACDSettings(bpy.types.PropertyGroup):
    show_expanded: BoolProperty(name="Show V-HACD", default=False)

    preset: EnumProperty(
        name="Detail",
        description="Detail preservation preset (changes all values below)",
        items=_DETAIL_ITEMS,
        default='D05',
        update=_vhacd_preset_update,
    )

    max_convex_hulls: IntProperty(
        name="Max Hulls",
        description="Maximum number of output convex hulls",
        default=32, min=1, max=100000,
    )
    resolution: IntProperty(
        name="Voxel Resolution",
        description="Total number of voxels to use for voxelization",
        default=600000, min=10000, max=10000000,
    )
    min_volume_error: FloatProperty(
        name="Volume Error %",
        description="Minimum volume error allowed as percentage",
        default=1.0, min=0.001, max=10.0, precision=3,
    )
    max_recursion_depth: IntProperty(
        name="Max Recursion Depth",
        description="Maximum recursion depth for decomposition",
        default=10, min=2, max=64,
    )
    max_vertices_per_hull: IntProperty(
        name="Max Vertices / Hull",
        description="Maximum number of vertices per output convex hull",
        default=128, min=8, max=4096,
    )
    shrink_wrap: BoolProperty(
        name="Shrink Wrap",
        description="Shrinkwrap voxel positions to the source mesh",
        default=True,
    )
    fill_mode: EnumProperty(
        name="Fill Mode",
        description="How to fill the interior of the voxelized mesh",
        items=[
            ('flood', "Flood Fill", "Flood fill interior (best for watertight meshes)"),
            ('surface', "Surface Only", "Surface only — produces hollow decomposition"),
            ('raycast', "Raycast", "Raycast fill (better for non-watertight meshes)"),
        ],
        default='flood',
    )
    min_edge_length: IntProperty(
        name="Min Edge Length",
        description="Minimum voxel edge length; stops recursion below this",
        default=2, min=1, max=32,
    )
    find_best_plane: BoolProperty(
        name="Find Best Plane",
        description="Try to find optimal split plane location (slower)",
        default=False,
    )


# ------------------------------------------------------------------ #
#  CoACD settings PropertyGroup                                       #
# ------------------------------------------------------------------ #

class CursorBBox_CoACDSettings(bpy.types.PropertyGroup):
    show_expanded: BoolProperty(name="Show CoACD", default=False)

    preset: EnumProperty(
        name="Detail",
        description="Detail preservation preset (changes core values below)",
        items=_DETAIL_ITEMS,
        default='D05',
        update=_coacd_preset_update,
    )

    # Core
    threshold: FloatProperty(
        name="Threshold",
        description="Concavity threshold for terminating decomposition",
        default=0.05, min=0.01, max=1.0, precision=3,
    )
    max_convex_hull: IntProperty(
        name="Max Hulls",
        description="Maximum convex hulls in result (-1 = no limit)",
        default=-1, min=-1, max=2048,
    )
    approximate_mode: EnumProperty(
        name="Approximation",
        description="Approximation shape type",
        items=[
            ('ch', "Convex Hulls", "Use convex hulls for approximation"),
            ('box', "Boxes", "Use cubes for approximation"),
        ],
        default='ch',
    )

    # Preprocessing
    preprocess_mode: EnumProperty(
        name="Preprocess",
        description="Manifold preprocessing mode",
        items=[
            ('auto', "Auto", "Automatically detect if preprocessing is needed"),
            ('on', "Force On", "Always apply manifold preprocessing"),
            ('off', "Force Off", "Skip preprocessing"),
        ],
        default='auto',
    )
    prep_resolution: IntProperty(
        name="Prep Resolution",
        description="Resolution for manifold preprocessing",
        default=50, min=20, max=100,
    )
    pca: BoolProperty(
        name="PCA",
        description="Enable PCA pre-processing for better axis alignment",
        default=False,
    )

    # MCTS Search
    mcts_iteration: IntProperty(
        name="MCTS Iterations",
        description="Number of search iterations in MCTS",
        default=150, min=60, max=2000,
    )
    mcts_depth: IntProperty(
        name="MCTS Depth",
        description="Maximum search depth in MCTS",
        default=3, min=2, max=7,
    )
    mcts_nodes: IntProperty(
        name="MCTS Nodes",
        description="Maximum number of child nodes in MCTS",
        default=20, min=10, max=40,
    )

    # Advanced
    hausdorff_resolution: IntProperty(
        name="Sampling Resolution",
        description="Sampling resolution for Hausdorff distance",
        default=2000, min=1000, max=10000,
    )
    rv_k: FloatProperty(
        name="Rv K",
        description="Value of k for R_v concavity metric",
        default=0.3, min=0.0, max=1.0, precision=2,
    )
    no_merge: BoolProperty(
        name="Disable Merge",
        description="Disable merge postprocessing step",
        default=False,
    )
    decimate: BoolProperty(
        name="Decimate",
        description="Enable max vertex constraint per convex hull",
        default=False,
    )
    max_ch_vertex: IntProperty(
        name="Max Vertices / Hull",
        description="Maximum vertices per convex hull (only when Decimate enabled)",
        default=256, min=8, max=2048,
    )
    extrude: BoolProperty(
        name="Extrude",
        description="Extrude neighboring hulls along overlapping faces",
        default=False,
    )
    extrude_margin: FloatProperty(
        name="Extrude Margin",
        description="Extrude margin distance",
        default=0.01, min=0.0, max=1.0, precision=4,
    )
    seed: IntProperty(
        name="Seed",
        description="Random seed for reproducibility (0 = random)",
        default=0, min=0,
    )


# ------------------------------------------------------------------ #
#  CoACD-U settings PropertyGroup                                     #
# ------------------------------------------------------------------ #

class CursorBBox_CoACDUSettings(bpy.types.PropertyGroup):
    show_expanded: BoolProperty(name="Show CoACD-U", default=False)

    preset: EnumProperty(
        name="Detail",
        description="Detail preservation preset (changes core values below)",
        items=_DETAIL_ITEMS,
        default='D05',
        update=_coacd_u_preset_update,
    )

    # Core
    threshold: FloatProperty(
        name="Threshold",
        description="Concavity threshold for terminating decomposition",
        default=0.05, min=0.01, max=1.0, precision=3,
    )
    max_convex_hull: IntProperty(
        name="Max Hulls",
        description="Maximum convex hulls in result (-1 = no limit, requires merge)",
        default=-1, min=-1, max=2048,
    )

    # Preprocessing
    preprocess_mode: EnumProperty(
        name="Preprocess",
        description="Manifold preprocessing mode",
        items=[
            ('auto', "Auto", "Automatically detect if preprocessing is needed"),
            ('on', "Force On", "Always apply manifold preprocessing"),
            ('off', "Force Off", "Skip preprocessing (input must be 2-manifold)"),
        ],
        default='auto',
    )
    prep_resolution: IntProperty(
        name="Prep Resolution",
        description="Resolution for manifold preprocessing",
        default=50, min=20, max=100,
    )
    pca: BoolProperty(
        name="PCA",
        description="Enable PCA pre-processing for better axis alignment (bug-fixed in U variant)",
        default=False,
    )

    # MCTS Search
    mcts_iterations: IntProperty(
        name="MCTS Iterations",
        description="Number of search iterations in MCTS",
        default=150, min=60, max=2000,
    )
    mcts_max_depth: IntProperty(
        name="MCTS Depth",
        description="Maximum search depth in MCTS",
        default=3, min=2, max=7,
    )
    mcts_nodes: IntProperty(
        name="MCTS Nodes",
        description="Maximum number of child nodes in MCTS",
        default=20, min=10, max=40,
    )

    # Sampling / Advanced
    resolution: IntProperty(
        name="Sampling Resolution",
        description="Sampling resolution for Hausdorff distance calculation",
        default=2000, min=1000, max=10000,
    )
    merge: BoolProperty(
        name="Merge",
        description="Enable merge post-processing to reduce hull count",
        default=True,
    )
    seed: IntProperty(
        name="Seed",
        description="Random seed for reproducibility (0 = random)",
        default=0, min=0,
    )


# ------------------------------------------------------------------ #
#  Registration                                                       #
# ------------------------------------------------------------------ #

def register():
    """Register scene properties and PropertyGroups."""

    # PropertyGroups for collision decomposition settings
    bpy.utils.register_class(CursorBBox_VHACDSettings)
    bpy.utils.register_class(CursorBBox_CoACDSettings)
    bpy.utils.register_class(CursorBBox_CoACDUSettings)

    bpy.types.Scene.cursor_bbox_vhacd = PointerProperty(type=CursorBBox_VHACDSettings)
    bpy.types.Scene.cursor_bbox_coacd = PointerProperty(type=CursorBBox_CoACDSettings)
    bpy.types.Scene.cursor_bbox_coacd_u = PointerProperty(type=CursorBBox_CoACDUSettings)

    # General addon properties
    bpy.types.Scene.cursor_bbox_push = bpy.props.FloatProperty(
        name="Push Value",
        description="How much to push bounding box faces outward",
        default=0.01,
        min=-1.0,
        max=1.0,
        precision=3
    )

    bpy.types.Scene.cursor_bbox_align_face = bpy.props.BoolProperty(
        name="Align to Face",
        description="Align cursor rotation to face normal",
        default=True
    )

    bpy.types.Scene.cursor_bbox_select_coplanar = bpy.props.BoolProperty(
        name="Select Coplanar",
        description="Automatically select connected coplanar faces",
        default=False
    )

    bpy.types.Scene.cursor_bbox_coplanar_angle = bpy.props.FloatProperty(
        name="Coplanar Angle",
        description="Angle threshold for coplanar selection",
        default=0.0872665,  # 5 degrees in radians
        min=0.0,
        max=math.pi,
        unit='ROTATION'
    )

    bpy.types.Scene.cursor_bbox_name_box = bpy.props.StringProperty(
        name="Box Name",
        description="Name pattern for Box objects",
        default="BBox"
    )

    bpy.types.Scene.cursor_bbox_name_hull = bpy.props.StringProperty(
        name="Hull Name",
        description="Name pattern for Hull objects",
        default="ConvexHull"
    )

    bpy.types.Scene.cursor_bbox_name_sphere = bpy.props.StringProperty(
        name="Sphere Name",
        description="Name pattern for Sphere objects",
        default="BSphere"
    )

    bpy.types.Scene.cursor_bbox_collection_name = bpy.props.StringProperty(
        name="Collection Name",
        description="Name of the collection for collision objects",
        default="CursorBBox"
    )

    bpy.types.Scene.cursor_bbox_hull_dissolve_angle = bpy.props.FloatProperty(
        name="Hull Dissolve Angle",
        description="Angle threshold for dissolving planar faces in convex hull (degrees)",
        default=3.0,
        min=0.0,
        max=180.0,
        precision=1
    )

    bpy.types.Scene.cursor_bbox_hull_use_triangulate = bpy.props.BoolProperty(
        name="Triangulate Hull",
        description="Triangulate the final convex hull mesh",
        default=True
    )

    bpy.types.Scene.cursor_bbox_hull_triangulate_quads = bpy.props.EnumProperty(
        name="Quad Method",
        description="Method for triangulating quads in convex hull",
        items=[
            ('BEAUTY', "Beauty", "Use beauty method for quads"),
            ('FIXED', "Fixed", "Use fixed method for quads"),
            ('ALTERNATE', "Alternate", "Use alternate method for quads"),
            ('SHORT_EDGE', "Short Edge", "Use shortest edge method for quads"),
            ('LONG_EDGE', "Long Edge", "Use longest edge method for quads"),
        ],
        default='SHORT_EDGE'
    )

    bpy.types.Scene.cursor_bbox_hull_triangulate_ngons = bpy.props.EnumProperty(
        name="N-gon Method",
        description="Method for triangulating n-gons in convex hull",
        items=[
            ('BEAUTY', "Beauty", "Use beauty method for n-gons"),
            ('EAR_CLIP', "Ear Clip", "Use ear clip method for n-gons"),
        ],
        default='BEAUTY'
    )

    def update_material_color(self, context):
        """Update material color when property changes"""
        rgba = list(self.cursor_bbox_material_color) + [1.0]

        mat = bpy.data.materials.get("Cursor BBox Material")
        if mat:
            mat.diffuse_color = rgba
            if mat.use_nodes:
                bsdf = mat.node_tree.nodes.get("Principled BSDF")
                if bsdf:
                    bsdf.inputs['Base Color'].default_value = rgba

        coll_name = context.scene.cursor_bbox_collection_name
        if coll_name in bpy.data.collections:
            for obj in bpy.data.collections[coll_name].objects:
                obj.color = rgba

    bpy.types.Scene.cursor_bbox_material_color = bpy.props.FloatVectorProperty(
        name="Material Color",
        description="Color for Cursor BBox Material",
        subtype='COLOR',
        default=(1.0, 0.58, 0.231),  # #FF943B
        min=0.0,
        max=1.0,
        update=update_material_color
    )

    def update_use_material(self, context):
        """Update material usage"""
        if self.cursor_bbox_use_material:
            update_material_color(self, context)

    bpy.types.Scene.cursor_bbox_use_material = bpy.props.BoolProperty(
        name="Use Material",
        description="Apply material and color to created objects",
        default=False,
        update=update_use_material
    )


def unregister():
    """Unregister scene properties and PropertyGroups."""
    del bpy.types.Scene.cursor_bbox_push
    del bpy.types.Scene.cursor_bbox_align_face
    del bpy.types.Scene.cursor_bbox_select_coplanar
    del bpy.types.Scene.cursor_bbox_coplanar_angle
    del bpy.types.Scene.cursor_bbox_name_box
    del bpy.types.Scene.cursor_bbox_name_hull
    del bpy.types.Scene.cursor_bbox_name_sphere
    del bpy.types.Scene.cursor_bbox_collection_name
    del bpy.types.Scene.cursor_bbox_material_color
    del bpy.types.Scene.cursor_bbox_use_material
    del bpy.types.Scene.cursor_bbox_hull_dissolve_angle
    del bpy.types.Scene.cursor_bbox_hull_use_triangulate
    del bpy.types.Scene.cursor_bbox_hull_triangulate_quads
    del bpy.types.Scene.cursor_bbox_hull_triangulate_ngons

    del bpy.types.Scene.cursor_bbox_vhacd
    del bpy.types.Scene.cursor_bbox_coacd
    del bpy.types.Scene.cursor_bbox_coacd_u

    bpy.utils.unregister_class(CursorBBox_CoACDUSettings)
    bpy.utils.unregister_class(CursorBBox_CoACDSettings)
    bpy.utils.unregister_class(CursorBBox_VHACDSettings)
