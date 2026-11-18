"""Blender glue for the Hull modal's split mode (manual convex decomposition).

A :class:`Piece` holds clipped copies of source polygons (world space, see
``hull_split``) plus its convex hull, ready for drawing and picking. The source
meshes are never modified.
"""
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils

from . import hull_split as hs
from .utils import get_evaluated_mesh


# Fill colours for the pieces, indexed by ``color_index % len(SPLIT_PALETTE)``.
SPLIT_PALETTE = (
    (1.00, 0.45, 0.20),  # orange
    (0.25, 0.65, 1.00),  # blue
    (0.40, 0.90, 0.30),  # green
    (0.95, 0.30, 0.65),  # pink
    (1.00, 0.85, 0.20),  # yellow
    (0.60, 0.40, 1.00),  # violet
    (0.20, 0.90, 0.85),  # cyan
    (0.85, 0.20, 0.25),  # red
)

_uid_counter = [0]


def _next_uid():
    _uid_counter[0] += 1
    return _uid_counter[0]


class Piece:
    """One convex piece of the decomposition."""

    __slots__ = ('polys', 'hull_verts', 'hull_tris', 'hull_edges', 'bvh',
                 'tri_normals', 'tri_centers',
                 'color_index', 'center', 'radius', 'extent', 'uid', 'volume')

    def __init__(self, polys, hull_verts, hull_tris, hull_edges, bvh, color_index,
                 tri_normals=(), tri_centers=(), volume=0.0):
        self.polys = polys
        self.hull_verts = hull_verts      # list of world-space Vectors
        self.hull_tris = hull_tris        # flat vertex list for 'TRIS', outward winding
        self.hull_edges = hull_edges      # flat vertex list for 'LINES'
        self.bvh = bvh
        # One outward unit normal (zero for a degenerate triangle) and one
        # centre per triangle of hull_tris, for the view-dependent fill fade.
        self.tri_normals = tri_normals
        self.tri_centers = tri_centers
        self.color_index = color_index
        center = Vector((0.0, 0.0, 0.0))
        for v in hull_verts:
            center += v
        center /= max(1, len(hull_verts))
        self.center = center
        self.radius = max(((v - center).length for v in hull_verts), default=0.0)
        self.extent = hs.extent(polys)
        self.volume = volume              # volume of the hull
        self.uid = _next_uid()


def _points_eps(points):
    """Plane tolerance for loose *points*: 1e-6 of their bbox diagonal, min 1e-9."""
    box = hs.bbox(points)
    if box is None:
        return 1e-9
    lo, hi = box
    diag = ((hi[0] - lo[0]) ** 2 + (hi[1] - lo[1]) ** 2 + (hi[2] - lo[2]) ** 2) ** 0.5
    return max(1e-6 * diag, 1e-9)


def _hull_data(points):
    """Convex hull of *points* (assumed solid) via bmesh.

    Returns ``(hull_verts, faces, tris, tri_normals, tri_centers, edges)`` or
    None when the hull has no faces. Raises on bmesh failure.
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
        hull_verts = [v.co.copy() for v in bm.verts]
        faces = [[v.index for v in f.verts] for f in bm.faces]
        hull_center = Vector((0.0, 0.0, 0.0))
        for v in hull_verts:
            hull_center += v
        hull_center /= max(1, len(hull_verts))
        tris = []
        tri_normals = []
        tri_centers = []
        for f, bm_face in zip(faces, bm.faces):
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
                else:
                    n = Vector((0.0, 0.0, 0.0))
                tris.extend((a, b, c))
                tri_normals.append(n)
                tri_centers.append(tc)
        edges = []
        for e in bm.edges:
            edges.append(hull_verts[e.verts[0].index])
            edges.append(hull_verts[e.verts[1].index])
    finally:
        bm.free()
    return hull_verts, faces, tris, tri_normals, tri_centers, edges


def make_piece(polys, color_index):
    """Build a Piece from *polys*, or None when they do not enclose a volume."""
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
        hull_verts, faces, tris, tri_normals, tri_centers, edges = data
        bvh = BVHTree.FromPolygons(hull_verts, faces)
    except Exception as e:
        print(f"Split: failed to build piece hull: {e}")
        return None
    return Piece(polys, hull_verts, tris, edges, bvh, color_index, tri_normals, tri_centers,
                 hs.tris_volume(tris))


def hull_volume(points):
    """Volume of the convex hull of *points* (same bmesh path as make_piece);
    0.0 when they are flat or the hull fails."""
    if not hs.is_solid(points, _points_eps(points)):
        return 0.0
    try:
        data = _hull_data(points)
    except Exception as e:
        print(f"Split: failed to build a union hull: {e}")
        return 0.0
    if data is None:
        return 0.0
    return hs.tris_volume(data[2])


def piece_thickness(piece):
    """Smallest extent of the piece's hull along its own face normals."""
    return hs.min_width(piece.hull_verts, piece.tri_normals)


def clone_piece(piece, color_index):
    """A new Piece (new uid) sharing *piece*'s geometry, with another colour."""
    return Piece(piece.polys, piece.hull_verts, piece.hull_tris, piece.hull_edges, piece.bvh,
                 color_index, piece.tri_normals, piece.tri_centers, piece.volume)


# More islands than this are not auto-merged: every island becomes a piece.
MAX_AUTO_MERGE_ISLANDS = 400


class IslandSet:
    """The islands of one explode, for live re-grouping.

    Holds the island polygon tuples, a Piece per island (None for a flat
    island) built once, and a cache ``{frozenset(island indices): volume}``
    of union-hull volumes shared by every re-grouping.
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

    def union_volume(self, indices):
        """Volume of the convex hull of the islands *indices* (cached)."""
        key = frozenset(indices)
        vol = self._cache.get(key)
        if vol is None:
            pts = []
            for i in sorted(key):
                pts.extend(self.points[i])
            vol = hull_volume(pts)
            self._cache[key] = vol
        return vol

    def groups(self, max_gap, max_cost, min_thickness):
        """``(groups, ignored_count)``: lists of island indices, one per hull.

        Islands thinner than *min_thickness* (when > 0) are ignored; flat
        islands take part with volume 0 and are ignored if left alone. Over
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

        out = []
        for local in hs.plan_merges(volumes, boxes, max_gap, max_cost, union_volume):
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
_ROLE_STYLE = {
    'INACTIVE': (0.10, 0.30, False, 1.0, False),
    'HOVER': (0.16, 0.55, False, 1.0, True),
    'ACTIVE': (0.20, 0.75, True, 1.75, True),
    'PREVIEW': (0.22, 0.75, True, 1.75, True),
}
_ROLE_ORDER = {'INACTIVE': 0, 'HOVER': 1, 'ACTIVE': 2, 'PREVIEW': 2}


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
        'rgb': rgb,
        'fill_alpha': fill_alpha,
        'edge': (*edge_rgb, edge_alpha),
        'edge_width': width,
        'edge_on_top': on_top,
    }


def overlay_geometry(pieces, active, hover, plane, preview=None):
    """Data for ``draw_split_overlay``.

    *plane* is ``(origin, normal)`` or None. *preview* is ``(front, back)``,
    the pieces a cut of the active piece would produce, or None; when given
    they are drawn instead of the active piece. The hovered piece (when not
    the active one) is highlighted. The plane is a quad centred on the
    projection of the active piece's centre onto the plane.
    """
    items = []
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
    plane_data = None
    if plane is not None and pieces and active is not None and 0 <= active < len(pieces):
        co = Vector(plane[0])
        no = Vector(plane[1])
        if no.length_squared > 1e-20:
            no.normalize()
            piece = pieces[active]
            c = piece.center - no * (piece.center - co).dot(no)
            half = max(piece.radius, 1e-4) * 1.2
            u = no.orthogonal().normalized() * half
            v = no.cross(u).normalized() * half
            a, b, cc, d = c - u - v, c + u - v, c + u + v, c - u + v
            plane_data = {
                'tris': [a, b, cc, a, cc, d],
                'border': [a, b, b, cc, cc, d, d, a],
            }
    return {'pieces': items, 'plane': plane_data}
