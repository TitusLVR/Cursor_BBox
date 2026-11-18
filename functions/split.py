"""Blender glue for the Hull modal's split mode (manual convex decomposition).

A :class:`Piece` holds clipped copies of source polygons (world space, see
``hull_split``) plus its convex hull, ready for drawing and picking. The source
meshes are never modified.
"""
import math

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils

from . import hull_split as hs
from .utils import get_evaluated_mesh


# Fill colours for the pieces, indexed by ``color_index % len(SPLIT_PALETTE)``.
# Muted at the user's request: each hue mixed 40% toward a grey of its own
# luminance (pastel tones, not pure primaries).
SPLIT_PALETTE = (
    (0.82, 0.49, 0.34),  # orange
    (0.39, 0.63, 0.84),  # blue
    (0.54, 0.84, 0.48),  # green
    (0.76, 0.37, 0.58),  # pink
    (0.93, 0.84, 0.45),  # yellow
    (0.55, 0.43, 0.79),  # violet
    (0.42, 0.84, 0.81),  # cyan
    (0.65, 0.26, 0.29),  # red
)

_uid_counter = [0]


def _next_uid():
    _uid_counter[0] += 1
    return _uid_counter[0]


class Piece:
    """One convex piece of the decomposition."""

    __slots__ = ('polys', 'hull_verts', 'hull_tris', 'hull_edges', 'bvh',
                 'tri_normals', 'tri_centers', 'edge_normals',
                 'color_index', 'center', 'radius', 'extent', 'uid', 'volume')

    def __init__(self, polys, hull_verts, hull_tris, hull_edges, bvh, color_index,
                 tri_normals=(), tri_centers=(), volume=0.0, edge_normals=(), uid=None):
        self.polys = polys
        self.hull_verts = hull_verts      # list of world-space Vectors
        self.hull_tris = hull_tris        # flat vertex list for 'TRIS', outward winding
        self.hull_edges = hull_edges      # flat vertex list for 'LINES'
        self.bvh = bvh
        # One outward unit normal (zero for a degenerate triangle) and one
        # centre per triangle of hull_tris, for the view-dependent fill fade.
        self.tri_normals = tri_normals
        self.tri_centers = tri_centers
        # One ``(n1, n2)`` per edge of hull_edges: the outward unit normals of
        # the two hull faces sharing it (repeated when it has only one), for
        # the back-face edge fade.
        self.edge_normals = edge_normals
        self.color_index = color_index
        center = Vector((0.0, 0.0, 0.0))
        for v in hull_verts:
            center += v
        center /= max(1, len(hull_verts))
        self.center = center
        self.radius = max(((v - center).length for v in hull_verts), default=0.0)
        self.extent = hs.extent(polys)
        self.volume = volume              # volume of the hull
        # A given uid means "the same piece rebuilt" (undo / redo): identical
        # geometry, so caches keyed by uid stay valid.
        self.uid = _next_uid() if uid is None else uid


def _points_eps(points):
    """Plane tolerance for loose *points*: 1e-6 of their bbox diagonal, min 1e-9."""
    box = hs.bbox(points)
    if box is None:
        return 1e-9
    lo, hi = box
    diag = ((hi[0] - lo[0]) ** 2 + (hi[1] - lo[1]) ** 2 + (hi[2] - lo[2]) ** 2) ** 0.5
    return max(1e-6 * diag, 1e-9)


def _hull_data(points, wire=True):
    """Convex hull of *points* (assumed solid) via bmesh.

    Returns ``(hull_verts, faces, tris, tri_normals, tri_centers, edges,
    edge_normals)`` or None when the hull has no faces. Raises on bmesh
    failure. Everything comes from the raw hull except, with *wire*, the
    edges / edge_normals (the drawn wireframe), which come from a planar
    dissolve of it (see ``_clean_hull_edges``).
    """
    bm = bmesh.new()
    try:
        for p in points:
            bm.verts.new(p)
        bm.verts.ensure_lookup_table()
        ret = bmesh.ops.convex_hull(bm, input=bm.verts)
        geom_to_remove = list(set(ret.get('geom_interior', []) + ret.get('geom_unused', [])))
        if geom_to_remove:
            bmesh.ops.delete(bm, geom=geom_to_remove, context='VERTS')
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        if not bm.faces:
            return None
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.verts.index_update()
        bm.faces.index_update()
        hull_verts = [v.co.copy() for v in bm.verts]
        faces = [[v.index for v in f.verts] for f in bm.faces]
        hull_center = Vector((0.0, 0.0, 0.0))
        for v in hull_verts:
            hull_center += v
        hull_center /= max(1, len(hull_verts))
        tris = []
        tri_normals = []
        tri_centers = []
        # Outward unit normal per bmesh face (that of its first non-degenerate
        # triangle), for the edges' adjacent-face normals.
        face_normals = []
        for f, bm_face in zip(faces, bm.faces):
            face_n = None
            for i in range(1, len(f) - 1):
                a, b, c = hull_verts[f[0]], hull_verts[f[i]], hull_verts[f[i + 1]]
                tc = (a + b + c) / 3.0
                n = (b - a).cross(c - a)
                if n.length_squared < 1e-30:
                    n = bm_face.normal.copy()
                # The hull centre is inside a convex hull: an outward normal
                # points away from it. Flip the winding of any triangle that
                # recalc_face_normals left facing inwards.
                if n.dot(tc - hull_center) < 0.0:
                    b, c = c, b
                    n = -n
                if n.length_squared > 1e-30:
                    n.normalize()
                    if face_n is None:
                        face_n = n
                else:
                    n = Vector((0.0, 0.0, 0.0))
                tris.extend((a, b, c))
                tri_normals.append(n)
                tri_centers.append(tc)
            if face_n is None:
                face_n = Vector((0.0, 0.0, 0.0))
            face_normals.append(face_n)
        edges = []
        edge_normals = []
        zero = Vector((0.0, 0.0, 0.0))
        for e in bm.edges:
            edges.append(hull_verts[e.verts[0].index])
            edges.append(hull_verts[e.verts[1].index])
            linked = [face_normals[f.index] for f in e.link_faces
                      if 0 <= f.index < len(face_normals)]
            if not linked:
                edge_normals.append((zero, zero))
            elif len(linked) == 1:
                edge_normals.append((linked[0], linked[0]))
            else:
                edge_normals.append((linked[0], linked[1]))
        # Wireframe only: real hull edges, without the diagonals between
        # coplanar triangles and the vertices sitting on straight edges.
        clean = _clean_hull_edges(bm, hull_center) if wire else None
        if clean is not None:
            edges, edge_normals = clean
    finally:
        bm.free()
    return hull_verts, faces, tris, tri_normals, tri_centers, edges, edge_normals


_MIN_WIRE_DISSOLVE = math.radians(0.5)


def _wire_dissolve_angle():
    """Dissolve angle for the wireframe: the creation path's
    ``cursor_bbox_hull_dissolve_angle`` when larger than 0.5 degrees."""
    try:
        deg = float(bpy.context.scene.cursor_bbox_hull_dissolve_angle)
    except Exception:
        return _MIN_WIRE_DISSOLVE
    if deg != deg:  # NaN
        return _MIN_WIRE_DISSOLVE
    return max(_MIN_WIRE_DISSOLVE, math.radians(deg))


def _clean_hull_edges(bm, hull_center):
    """``(edges, edge_normals)`` of a copy of the hull bmesh *bm* after a
    planar ``dissolve_limit``: flat LINES vertex pairs and one ``(n1, n2)``
    of outward unit face normals per edge (parallel lists, same layout as
    ``_hull_data``'s raw ones). None when the dissolve fails or leaves no
    edges (the caller keeps the raw edges). *bm* is not modified."""
    tmp = None
    try:
        tmp = bm.copy()
        bmesh.ops.dissolve_limit(
            tmp, angle_limit=_wire_dissolve_angle(), use_dissolve_boundaries=True,
            verts=list(tmp.verts), edges=list(tmp.edges), delimit={'NORMAL'})
        tmp.verts.ensure_lookup_table()
        tmp.edges.ensure_lookup_table()
        tmp.faces.ensure_lookup_table()
        if not tmp.edges or not tmp.faces:
            return None
        bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces)
        tmp.faces.index_update()
        zero = Vector((0.0, 0.0, 0.0))
        face_normals = []
        for f in tmp.faces:
            n = f.normal.copy()
            if n.length_squared < 1e-30:
                face_normals.append(zero)
                continue
            n.normalize()
            # Outward = away from the hull centre (convex hull).
            if n.dot(f.calc_center_median() - hull_center) < 0.0:
                n = -n
            face_normals.append(n)
        edges = []
        edge_normals = []
        for e in tmp.edges:
            edges.append(e.verts[0].co.copy())
            edges.append(e.verts[1].co.copy())
            linked = [face_normals[f.index] for f in e.link_faces
                      if 0 <= f.index < len(face_normals)]
            if not linked:
                edge_normals.append((zero, zero))
            elif len(linked) == 1:
                edge_normals.append((linked[0], linked[0]))
            else:
                edge_normals.append((linked[0], linked[1]))
        if not edges:
            return None
        return edges, edge_normals
    except Exception as e:
        print(f"Split: wireframe dissolve failed, keeping the raw edges: {e}")
        return None
    finally:
        if tmp is not None:
            tmp.free()


def make_piece(polys, color_index, uid=None):
    """Build a Piece from *polys*, or None when they do not enclose a volume.

    *uid* (optional) reuses the uid of the piece these polygons came from
    unchanged (undo / redo); otherwise the piece gets a new one."""
    polys = tuple(polys)
    if not polys:
        return None
    points = hs.unique_points(polys)
    if not hs.is_solid(points, hs.plane_eps(polys)):
        return None
    try:
        data = _hull_data(points)
        if data is None:
            return None
        hull_verts, faces, tris, tri_normals, tri_centers, edges, edge_normals = data
        bvh = BVHTree.FromPolygons(hull_verts, faces)
    except Exception as e:
        print(f"Split: failed to build piece hull: {e}")
        return None
    return Piece(polys, hull_verts, tris, edges, bvh, color_index, tri_normals, tri_centers,
                 hs.tris_volume(tris), edge_normals, uid)


def hull_volume(points):
    """Volume of the convex hull of *points* (same bmesh path as make_piece);
    0.0 when they are flat or the hull fails."""
    if not hs.is_solid(points, _points_eps(points)):
        return 0.0
    try:
        data = _hull_data(points, wire=False)
    except Exception as e:
        print(f"Split: failed to build a union hull: {e}")
        return 0.0
    if data is None:
        return 0.0
    return hs.tris_volume(data[2])


def hull_planes(points, tol):
    """Bounding planes ``(point, outward unit normal)`` of the convex hull of
    *points* (same bmesh path as make_piece), each pushed OUTWARD by *tol*.

    Duplicate planes (normal within 1e-4 and distance within *tol*) are
    dropped. Empty when the points are flat or the hull fails.
    """
    if not hs.is_solid(points, _points_eps(points)):
        return []
    try:
        data = _hull_data(points, wire=False)
    except Exception as e:
        print(f"Split: failed to build a region hull: {e}")
        return []
    if data is None:
        return []
    _verts, _faces, _tris, tri_normals, tri_centers, _edges, _edge_normals = data
    planes = []
    seen = []   # (normal tuple, distance) of the planes kept
    for n, c in zip(tri_normals, tri_centers):
        if n.length_squared < 0.5:
            continue    # degenerate triangle (zero normal)
        no = (n.x, n.y, n.z)
        d = n.dot(c)
        duplicate = False
        for sno, sd in seen:
            if (abs(no[0] - sno[0]) <= 1e-4 and abs(no[1] - sno[1]) <= 1e-4
                    and abs(no[2] - sno[2]) <= 1e-4 and abs(d - sd) <= tol):
                duplicate = True
                break
        if duplicate:
            continue
        seen.append((no, d))
        co = c + n * tol
        planes.append(((co.x, co.y, co.z), no))
    return planes


def hull_volume_thickness(points):
    """``(volume, thickness)`` of the convex hull of *points* from one hull
    build (thickness = ``min_width`` over the hull's triangle normals);
    ``(0.0, 0.0)`` when they are flat or the hull fails."""
    if not hs.is_solid(points, _points_eps(points)):
        return 0.0, 0.0
    try:
        data = _hull_data(points, wire=False)
    except Exception as e:
        print(f"Split: failed to build a union hull: {e}")
        return 0.0, 0.0
    if data is None:
        return 0.0, 0.0
    hull_verts, _faces, tris, tri_normals = data[0], data[1], data[2], data[3]
    return hs.tris_volume(tris), hs.min_width(hull_verts, tri_normals)


def piece_thickness(piece):
    """Smallest extent of the piece's hull along its own face normals."""
    return hs.min_width(piece.hull_verts, piece.tri_normals)


def clone_piece(piece, color_index):
    """A new Piece (new uid) sharing *piece*'s geometry, with another colour."""
    return Piece(piece.polys, piece.hull_verts, piece.hull_tris, piece.hull_edges, piece.bvh,
                 color_index, piece.tri_normals, piece.tri_centers, piece.volume,
                 piece.edge_normals)


# More islands than this are not auto-merged: every island becomes a piece.
MAX_AUTO_MERGE_ISLANDS = 400


class IslandSet:
    """The islands of one explode, for live re-grouping.

    Holds the island polygon tuples, a Piece per island (None for a flat
    island) built once, and a cache ``{frozenset(island indices): (volume,
    thickness)}`` of union hulls shared by every re-grouping.
    """

    def __init__(self, islands):
        self.islands = tuple(tuple(polys) for polys in islands)
        self.pieces = [make_piece(polys, 0) for polys in self.islands]
        # Points whose convex hull is the island's hull: the hull vertices of a
        # solid island (same hull, far fewer points), else its unique points.
        self.points = []
        self.boxes = []
        self.thickness = []
        for polys, piece in zip(self.islands, self.pieces):
            if piece is not None:
                pts = [tuple(v) for v in piece.hull_verts]
                self.thickness.append(piece_thickness(piece))
            else:
                pts = hs.unique_points(polys)
                self.thickness.append(0.0)
            self.points.append(pts)
            box = hs.bbox(pts)
            self.boxes.append(box if box is not None else ((0.0,) * 3, (0.0,) * 3))
        self._cache = {}

    @property
    def too_many(self):
        return len(self.islands) > MAX_AUTO_MERGE_ISLANDS

    def _union(self, indices):
        """``(volume, thickness)`` of the convex hull of the islands
        *indices*, from one hull build (cached per frozenset)."""
        key = frozenset(indices)
        hit = self._cache.get(key)
        if hit is None:
            pts = []
            for i in sorted(key):
                pts.extend(self.points[i])
            hit = hull_volume_thickness(pts)
            self._cache[key] = hit
        return hit

    def union_volume(self, indices):
        """Volume of the convex hull of the islands *indices* (cached)."""
        return self._union(indices)[0]

    def union_thickness(self, indices):
        """Thickness (``min_width``) of the convex hull of the islands
        *indices* (cached; 0.0 for a flat union)."""
        return self._union(indices)[1]

    def groups(self, max_gap, max_cost, min_thickness, flat=False):
        """``(groups, ignored_count)``: lists of island indices, one per hull.

        Islands thinner than *min_thickness* (when > 0) are ignored; flat
        islands take part with volume 0 (thickness 0) and are ignored if
        left alone. *flat* enables the flat-merge rule of ``plan_merges``
        (coplanar parts merge whatever the void). Over
        MAX_AUTO_MERGE_ISLANDS islands nothing is merged: every solid island
        is its own group.
        """
        n = len(self.islands)
        if self.too_many:
            groups = [[i] for i in range(n) if self.pieces[i] is not None]
            return groups, n - len(groups)
        kept = [i for i in range(n)
                if not (min_thickness > 0.0 and self.thickness[i] < min_thickness)]
        ignored = n - len(kept)
        volumes = [self.pieces[i].volume if self.pieces[i] is not None else 0.0 for i in kept]
        boxes = [self.boxes[i] for i in kept]

        def union_volume(local):
            return self.union_volume(kept[j] for j in local)

        def union_thickness(local):
            return self.union_thickness(kept[j] for j in local)

        thicknesses = [self.thickness[i] for i in kept]
        plan = hs.plan_merges(volumes, boxes, max_gap, max_cost, union_volume,
                              union_thickness=union_thickness, thicknesses=thicknesses,
                              flat=flat)
        out = []
        for local in plan:
            group = [kept[j] for j in local]
            if len(group) == 1 and self.pieces[group[0]] is None:
                ignored += 1
                continue
            out.append(group)
        return out, ignored

    def build_pieces(self, groups, next_color):
        """One Piece per group (its islands' polygons concatenated), coloured
        by successive ``next_color()`` calls; groups that fail are skipped."""
        pieces = []
        for group in groups:
            if not group:
                continue
            if len(group) == 1 and self.pieces[group[0]] is not None:
                piece = clone_piece(self.pieces[group[0]], next_color())
            else:
                polys = tuple(p for i in group for p in self.islands[i])
                piece = make_piece(polys, next_color())
            if piece is not None:
                pieces.append(piece)
        return pieces


def collect_source_polys(context, faces_dict, use_depsgraph):
    """World-space polygons (tuples of xyz tuples) of ``{obj: face indices}``."""
    polys = []
    for obj, face_indices in faces_dict.items():
        if not face_indices or obj is None or obj.type != 'MESH':
            continue
        mesh, matrix_world = get_evaluated_mesh(obj, use_depsgraph=use_depsgraph, context=context)
        world = [tuple(matrix_world @ v.co) for v in mesh.vertices]
        mesh_polys = mesh.polygons
        count = len(mesh_polys)
        for idx in face_indices:
            if idx >= count:
                continue
            verts = mesh_polys[idx].vertices
            if len(verts) < 3:
                continue
            polys.append(tuple(world[i] for i in verts))
    return tuple(polys)


def cut_piece(piece, plane_co, plane_no, next_color):
    """Cut *piece* by a plane. Returns ``(front, back)`` Pieces (or None each).

    The front piece keeps the piece's colour; the back piece gets *next_color*.
    """
    no = Vector(plane_no)
    if no.length_squared < 1e-20:
        return None, None
    no.normalize()
    eps = hs.plane_eps(piece.polys)
    front_polys, back_polys = hs.split_polygons(piece.polys, tuple(plane_co), tuple(no), eps)
    front = make_piece(front_polys, piece.color_index) if front_polys else None
    back = make_piece(back_polys, next_color) if back_polys else None
    return front, back


def pick_piece(context, pieces, mouse):
    """Index of the piece whose hull is hit first by the view ray, or None."""
    region = context.region
    rv3d = context.region_data
    if region is None or rv3d is None or not pieces:
        return None
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse)
    if origin is None or direction is None:
        return None
    best, best_dist = None, float('inf')
    for i, piece in enumerate(pieces):
        if piece.bvh is None:
            continue
        loc, _normal, _index, dist = piece.bvh.ray_cast(origin, direction)
        if loc is not None and dist < best_dist:
            best, best_dist = i, dist
    return best


# Overlay roles, in draw order (later ones blend on top):
# (fill base alpha, edge alpha, edge is white, edge width, edge drawn on top).
# PICK / FRESH / PICK_HOVER are the Split mode's piece-selection state: an
# even, stronger fill for every piece so the decomposition reads as blocks,
# white outlines for the pieces of the last cut and the piece under the mouse.
# Toned down at the user's request; keep these values: fills x0.85,
# coloured edges x0.70, outlines 0.50 (active / preview / fresh) and 0.65
# (hovered), no line wider than 1.5.
_ROLE_STYLE = {
    'INACTIVE': (0.085, 0.21, False, 1.0, False),
    'HOVER': (0.136, 0.65, False, 1.5, True),
    'ACTIVE': (0.17, 0.50, True, 1.5, True),
    'PREVIEW': (0.187, 0.50, True, 1.5, True),
    'PICK': (0.187, 0.315, False, 1.0, False),
    'FRESH': (0.187, 0.50, True, 1.5, True),
    'PICK_HOVER': (0.323, 0.65, True, 1.5, True),
    # Merge state's base piece (the other merge roles reuse PICK /
    # PICK_HOVER / PREVIEW).
    'MERGE_BASE': (0.187, 0.50, True, 1.5, True),
}
_ROLE_ORDER = {'INACTIVE': 0, 'HOVER': 1, 'ACTIVE': 2, 'PREVIEW': 2,
               'PICK': 0, 'FRESH': 1, 'PICK_HOVER': 2, 'MERGE_BASE': 1}

# Merge state draws the pieces solid (see ui.draw._draw_split_solid):
# role -> (edge is white, edge width). Non-white edges are the piece colour
# darkened by _SOLID_EDGE_DARKEN; the merge-preview hull is tinted towards
# white by _SOLID_PREVIEW_TINT.
_SOLID_EDGE = {
    'MERGE_BASE': (True, 1.5),
    'PREVIEW': (True, 1.5),
    'PICK_HOVER': (True, 1.25),
    'PICK': (False, 1.0),
}
_SOLID_EDGE_DARKEN = 0.5
_SOLID_PREVIEW_TINT = 0.55

# Back-face dimming defaults (addon preferences split_backface_edges /
# split_backface_faces).
BACKFACE_EDGES_DEFAULT = 0.25
BACKFACE_FACES_DEFAULT = 0.12


def _pref_factor(prefs, name, default):
    """Preference *name* as a float in [0, 1], *default* when missing / bad."""
    try:
        value = float(getattr(prefs, name))
    except Exception:
        return default
    if value != value:  # NaN
        return default
    return min(1.0, max(0.0, value))


def backface_factors():
    """``(edges, faces)`` back-face dimming factors from the addon preferences,
    the defaults when they cannot be read."""
    try:
        from ..settings.preferences import get_preferences
        prefs = get_preferences()
    except Exception:
        prefs = None
    if prefs is None:
        return BACKFACE_EDGES_DEFAULT, BACKFACE_FACES_DEFAULT
    return (_pref_factor(prefs, 'split_backface_edges', BACKFACE_EDGES_DEFAULT),
            _pref_factor(prefs, 'split_backface_faces', BACKFACE_FACES_DEFAULT))


def _overlay_item(piece, role):
    fill_alpha, edge_alpha, white, width, on_top = _ROLE_STYLE[role]
    rgb = tuple(SPLIT_PALETTE[piece.color_index % len(SPLIT_PALETTE)])
    edge_rgb = (1.0, 1.0, 1.0) if white else rgb
    return {
        'key': piece.uid,
        'role': role,
        'tris': piece.hull_tris,
        'normals': piece.tri_normals,
        'centers': piece.tri_centers,
        'edges': piece.hull_edges,
        'edge_normals': piece.edge_normals,
        'rgb': rgb,
        'fill_alpha': fill_alpha,
        'edge': (*edge_rgb, edge_alpha),
        'edge_width': width,
        'edge_on_top': on_top,
    }


def _solid_item(piece, role):
    """Overlay item for the Merge state's opaque drawing: fill alpha 1.0,
    the merge preview tinted towards white, edges white (base / preview /
    hovered) or the darkened piece colour, all opaque."""
    item = _overlay_item(piece, role)
    r, g, b = item['rgb']
    if role == 'PREVIEW':
        t = _SOLID_PREVIEW_TINT
        r, g, b = r + (1.0 - r) * t, g + (1.0 - g) * t, b + (1.0 - b) * t
    white, width = _SOLID_EDGE.get(role, (False, 1.0))
    if white:
        edge = (1.0, 1.0, 1.0, 1.0)
    else:
        k = _SOLID_EDGE_DARKEN
        edge = (r * k, g * k, b * k, 1.0)
    item.update(rgb=(r, g, b), fill_alpha=1.0, edge=edge, edge_width=width,
                edge_on_top=False)
    return item


# The cutting-plane preview is the active piece's section grown by this.
_PLANE_SECTION_SCALE = 1.12
# Fallback square (plane misses the active piece): half-size / piece radius.
_PLANE_FALLBACK_HALF = 0.25


def plane_polygon(piece, plane_co, plane_no, plane_axis=None):
    """World-space polygon (list of Vectors) showing the cutting plane: the
    section of *piece*'s hull scaled by ``_PLANE_SECTION_SCALE``, or, when
    the plane misses the hull or only grazes it (section area below 1e-6 x
    extent squared), a small square on the plane origin. The square's first
    side runs along *plane_axis* (a world vector, e.g. the hovered edge)
    projected onto the plane; without a usable hint along the world axis
    least parallel to the normal. [] for a zero normal."""
    co = Vector(plane_co)
    no = Vector(plane_no)
    if no.length_squared < 1e-20:
        return []
    no.normalize()
    eps = max(1e-6 * piece.extent, 1e-9)
    section = hs.section_polygon(piece.hull_tris, tuple(co), tuple(no), eps)
    if section and hs.polygon_area(section) >= 1e-6 * piece.extent * piece.extent:
        return [Vector(p) for p in hs.scale_polygon(section, _PLANE_SECTION_SCALE)]
    u = None
    if plane_axis is not None:
        try:
            hint = Vector(plane_axis)
            hint = hint - no * hint.dot(no)
            if hint.length_squared > 1e-12 * max(1.0, Vector(plane_axis).length_squared):
                u = hint
        except Exception:
            u = None
    if u is None:
        axes = (Vector((1.0, 0.0, 0.0)), Vector((0.0, 1.0, 0.0)), Vector((0.0, 0.0, 1.0)))
        axis = min(axes, key=lambda a: abs(a.dot(no)))
        u = axis - no * axis.dot(no)
    if u.length_squared < 1e-20:
        return []
    half = max(piece.radius, 1e-4) * _PLANE_FALLBACK_HALF
    u = u.normalized() * half
    v = no.cross(u).normalized() * half
    return [co - u - v, co + u - v, co + u + v, co - u + v]


def overlay_geometry(pieces, active, hover, plane, preview=None, pick=False, fresh=(),
                     pick_base=None, merge=False, base=None, merge_preview=None, plane_axis=None):
    """Data for ``draw_split_overlay``.

    *plane* is ``(origin, normal)`` or None. *preview* is ``(front, back)``,
    the pieces a cut of the active piece would produce, or None; when given
    they are drawn instead of the active piece. The hovered piece (when not
    the active one) is highlighted. The plane is drawn as ``plane_polygon``
    of the ACTIVE piece (the section is the same during a cut preview):
    ``{'polygon': [points]}``; *plane_axis* orients its fallback square.

    *pick* (Split mode's piece-selection state) draws every piece evenly,
    the hovered one strongest, the pieces whose uid is in *fresh* outlined,
    and no active emphasis, plane or preview; the piece at index
    *pick_base* (the Shift+click merge target) gets the MERGE_BASE outline.

    *merge* (the Merge state) draws the pieces SOLID (``'solid': True`` in
    the result): the piece at index *base* as MERGE_BASE, the hovered one
    as PICK_HOVER, the others as PICK; when *merge_preview* (the hull the
    merge of the hovered piece into the base would give) is set, it is drawn
    as PREVIEW instead of those two pieces. No plane, no cut preview.

    The back-face dimming factors from the addon preferences ride along as
    ``'backface_edges'`` / ``'backface_faces'``.
    """
    items = []
    if merge:
        for i, piece in enumerate(pieces):
            if merge_preview is not None and (i == base or i == hover):
                continue
            if i == base:
                role = 'MERGE_BASE'
            elif i == hover:
                role = 'PICK_HOVER'
            else:
                role = 'PICK'
            items.append(_solid_item(piece, role))
        if merge_preview is not None:
            items.append(_solid_item(merge_preview, 'PREVIEW'))
        plane, preview = None, None
    elif pick:
        fresh = set(fresh or ())
        for i, piece in enumerate(pieces):
            if i == hover:
                role = 'PICK_HOVER'
            elif i == pick_base:
                role = 'MERGE_BASE'
            elif piece.uid in fresh:
                role = 'FRESH'
            else:
                role = 'PICK'
            items.append(_overlay_item(piece, role))
        plane, preview = None, None
    else:
        for i, piece in enumerate(pieces):
            if i == active:
                if preview:
                    continue
                role = 'ACTIVE'
            elif i == hover:
                role = 'HOVER'
            else:
                role = 'INACTIVE'
            items.append(_overlay_item(piece, role))
        if preview:
            for piece in preview:
                if piece is not None:
                    items.append(_overlay_item(piece, 'PREVIEW'))
    items.sort(key=lambda it: _ROLE_ORDER[it['role']])
    back_edges, back_faces = backface_factors()
    plane_data = None
    if plane is not None and pieces and active is not None and 0 <= active < len(pieces):
        polygon = plane_polygon(pieces[active], plane[0], plane[1], plane_axis)
        if polygon:
            plane_data = {'polygon': polygon}
    return {'pieces': items, 'plane': plane_data,
            'backface_edges': back_edges, 'backface_faces': back_faces,
            'solid': bool(merge)}
