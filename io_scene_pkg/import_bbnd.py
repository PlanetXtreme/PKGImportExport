import bpy
import struct
import os
import math
from mathutils import Matrix
from pathlib import Path

def runs(operator, context):
    FIX_COORDINATE_ROTATION = True

    filepath = None

    # Primary: operator.filepath
    if hasattr(operator, "filepath"):
        filepath = operator.filepath

    # Fallback: operator itself might be a string path
    elif isinstance(operator, str):
        filepath = operator

    # If still nothing usable
    if not filepath or not os.path.exists(filepath):
        print({'ERROR'}, f"Cannot find file at {filepath}")
        return {'CANCELLED'}

    with open(filepath, 'rb') as f:
        data = f.read()

    if len(data) < 13:
        print({'ERROR'}, "File is too small to be a valid BBND.")
        return {'CANCELLED'}

    # 1. Parse Header
    num_verts = struct.unpack('<I', data[1:5])[0]
    num_faces = struct.unpack('<I', data[9:13])[0]
    
    # 2. Parse Vertices
    offset = 13
    verts = []
    for _ in range(num_verts):
        verts.append(struct.unpack('<fff', data[offset:offset+12]))
        offset += 12

    # 3. Parse Faces and Material Indices
    face_block_size = num_faces * 10
    face_offset = len(data) - face_block_size
    
    faces = []
    mat_indices = []
    
    for _ in range(num_faces):
        v1, v2, v3, v4, mat_id = struct.unpack('<HHHHH', data[face_offset:face_offset+10])
        face_offset += 10
        
        if v4 == 0:
            faces.append((v1, v2, v3))
        else:
            faces.append((v1, v2, v3, v4))
            
        mat_indices.append(mat_id)

    # 4. Build the Blender Mesh
    mesh_name = "BOUND" #os.path.basename(filepath)
    mesh = bpy.data.meshes.new(mesh_name)
    obj = bpy.data.objects.new(mesh_name, mesh)
    
    bpy.context.collection.objects.link(obj)
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    # 5. Setup Material Indices
    if mat_indices:
        max_mat = max(mat_indices)
        for i in range(max_mat + 1):
            mat = bpy.data.materials.new(name=f"{mesh_name}_Mat_{i}")
            obj.data.materials.append(mat)
            
        for i, poly in enumerate(mesh.polygons):
            poly.material_index = mat_indices[i]

    # 6. Apply Coordinate Rotation Fix
    if FIX_COORDINATE_ROTATION:
        rot_mat = Matrix.Rotation(math.radians(90.0), 4, 'X')
        obj.matrix_world = rot_mat @ obj.matrix_world
        
        rot_mat = Matrix.Rotation(math.radians(180.0), 4, 'Z')
        obj.matrix_world = rot_mat @ obj.matrix_world

    # Make the newly imported object the active selection
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    
    # Apply Transforms (Location, Rotation, Scale)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    print({'INFO'}, f"Successfully imported BBND: {mesh_name}")
    return {'FINISHED'}

def find_bbnd(pkg_path):
    pkg_path = Path(bpy.path.abspath(str(pkg_path)))

    if not pkg_path.exists():
        print("PKG PATH DOES NOT EXIST:", pkg_path)
        return None

    parent = pkg_path.parent
    grandparent = parent.parent

    base_name = pkg_path.stem
    target_base = f"{base_name}_bound"

    # Search locations in priority order
    search_roots = [
        grandparent / "bound",  # FIRST: two levels up
        parent / "bound",       # SECOND: one level up
    ]

    for root in search_roots:
        if not root.exists() or not root.is_dir():
            continue

        print("CHECKING:", root)

        for f in root.iterdir():
            name = f.name.lower()
            if name == f"{target_base}.bbnd" or name == f"{target_base}.bnd":
                print("FOUND MATCH:", f)
                return str(f)

    print("NO MATCH FOUND")
    return None