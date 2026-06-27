# ##### BEGIN LICENSE BLOCK #####
#
# This program is licensed under Creative Commons BY-NC-SA:
# https://creativecommons.org/licenses/by-nc-sa/3.0/
#
# Created by PlanetXtreme, 2026
#
# ##### END LICENSE BLOCK #####

import bpy
import struct
import os
from pathlib import Path
import pkgimporter.common_helpers as helper


def runs(operator, context, root_parent_obj=None, target_collection=None):
    filepath = operator.filepath if hasattr(operator, "filepath") else str(operator)
    if not filepath or not os.path.exists(filepath):
        print({'ERROR'}, f"Cannot find file at {filepath}")
        return {'CANCELLED'}

    with open(filepath, 'rb') as f:
        data = f.read()

    if len(data) < 13:
        print("Not a real bbnd file, what...")
        return {'CANCELLED'}

    num_verts = struct.unpack('<I', data[1:5])[0]
    num_groups = struct.unpack('<I', data[5:9])[0]
    num_faces = struct.unpack('<I', data[9:13])[0]
    
    offset = 13
    verts = []
    for _ in range(num_verts):
        raw_vtx = struct.unpack('<fff', data[offset:offset+12])
        # Convert coordinate space immediately as we read the vertices
        verts.append(helper.convert_vecspace_to_blender(raw_vtx))
        offset += 12

    mat_chunks = []
    for _ in range(num_groups):
        mat_chunks.append(data[offset : offset + 104])
        offset += 104
    
    faces = []
    mat_indices = []
    for _ in range(num_faces):
        v1, v2, v3, v4, mat_id = struct.unpack('<HHHHH', data[offset:offset+10])
        offset += 10
        if v4 == 0:
            faces.append((v1, v2, v3))
        else:
            faces.append((v1, v2, v3, v4))
        mat_indices.append(mat_id)

    mesh_name = "BOUND"
    mesh = bpy.data.meshes.new(mesh_name)
    obj = bpy.data.objects.new(mesh_name, mesh)
    
    if target_collection:
        target_collection.objects.link(obj)
    else:
        bpy.context.collection.objects.link(obj)
        
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    for i in range(num_groups):
        chunk = mat_chunks[i]
        
        # Extract name string
        engine_name = chunk[0:32].split(b'\0')[0].decode('ascii', errors='ignore').strip()
        blender_name = engine_name if engine_name else f"{mesh_name}_Mat_{i}"
        
        mat = bpy.data.materials.new(name=blender_name)
        
        # Assign custom properties
        mat["bbnd_material_name"] = engine_name if engine_name else "default"
        mat["bbnd_float1"] = struct.unpack('<f', chunk[32:36])[0]
        mat["bbnd_float2"] = struct.unpack('<f', chunk[36:40])[0]
        mat["bbnd_data_A"] = chunk[48:72].hex()
        mat["bbnd_data_B"] = chunk[80:104].hex()
        
        obj.data.materials.append(mat)
            
    for i, poly in enumerate(mesh.polygons):
        poly.material_index = mat_indices[i]

    #bpy.context.view_layer.objects.active = obj
    #obj.select_set(True)

    if root_parent_obj:
        obj.parent = root_parent_obj

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

        for ext in (".bbnd", ".bnd"):
            candidate = root / f"{target_base}{ext}"
            #print("CHECKING:", candidate)

            if candidate.exists():
                #print("FOUND MATCH:", candidate)
                return str(candidate)

    print(f"    NO BBND MATCH FOUND for {pkg_path}")
    return None