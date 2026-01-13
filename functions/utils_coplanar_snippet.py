
def get_connected_coplanar_faces(obj, start_face_index, angle_tolerance_radians):
    """Find connected faces that are coplanar within tolerance"""
    if obj.type != 'MESH':
        return set()
    
    mesh = obj.data
    if start_face_index >= len(mesh.polygons):
        return set()

    # Create BVH/BMesh for adjacency
    # Since we need connectivity, BMesh is best.
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    
    if start_face_index >= len(bm.faces):
        bm.free()
        return set()
        
    start_face = bm.faces[start_face_index]
    start_normal = start_face.normal.copy()
    
    visited = set()
    coplanar_indices = set()
    queue = [start_face]
    
    visited.add(start_face)
    coplanar_indices.add(start_face.index)
    
    while queue:
        current_face = queue.pop(0)
        
        for edge in current_face.edges:
            for neighbor in edge.link_faces:
                if neighbor not in visited:
                    visited.add(neighbor)
                    
                    # Check angle
                    # We compare against the START face normal to prevent drift, 
                    # or current face? Usually start face for "planar region".
                    angle = start_normal.angle(neighbor.normal, 100.0) # 100.0 as safe default if error
                    
                    if angle < angle_tolerance_radians:
                        coplanar_indices.add(neighbor.index)
                        queue.append(neighbor)
    
    bm.free()
    return coplanar_indices
