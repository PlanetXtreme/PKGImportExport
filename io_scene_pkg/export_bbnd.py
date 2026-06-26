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
import math
from mathutils import Matrix

def save(operator, context):
    filepath = operator.filepath
    FIX_COORDINATE_ROTATION = True

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    obj = bpy.context.active_object
    if not obj or obj.type != 'MESH':
        operator.report({'ERROR'}, "Please select a Mesh object in the 3D viewport!")
        return {'CANCELLED'}

    mesh = obj.data

    new_num_verts = len(mesh.vertices)
    new_num_faces = len(mesh.polygons)
    new_num_groups = max(1, len(mesh.materials))
    
    header = bytearray(b'\x01')             
    header += struct.pack('<I', new_num_verts)   
    header += struct.pack('<I', new_num_groups)                   
    header += struct.pack('<I', new_num_faces)   

    export_mat = obj.matrix_world
    if FIX_COORDINATE_ROTATION:
        rot_z_inv = Matrix.Rotation(math.radians(-180.0), 4, 'Z')
        rot_x_inv = Matrix.Rotation(math.radians(-90.0), 4, 'X')
        export_mat = rot_x_inv @ rot_z_inv @ export_mat

    verts_data = bytearray()
    for v in mesh.vertices:
        final_co = export_mat @ v.co
        verts_data += struct.pack('<fff', final_co.x, final_co.y, final_co.z)

    mat_data = bytearray()
    for i in range(new_num_groups):
        if len(mesh.materials) > 0:
            mat = mesh.materials[i]
            
            # Use custom property as the absolute source of truth
            fallback_name = mat.name.split('.')[0]
            mat_name = mat.get("bbnd_material_name", fallback_name)
            
            f1 = mat.get("bbnd_float1", 0.1)
            f2 = mat.get("bbnd_float2", 0.5)
            data_a_hex = mat.get("bbnd_data_A", "0f000000401db50200000000000000006cde1200288e4200") #This is a default "pointer" in MCSR
            data_b_hex = mat.get("bbnd_data_B", "0f000000401db50200000000000000006cde1200288e4200") #Very likely different and unworking in Midtown Madness
        else:
            mat_name = "default"
            f1, f2 = 0.1, 0.5
            data_a_hex = data_b_hex = "0f000000401db50200000000000000006cde1200288e4200"

        chunk = bytearray(104)
        
        # Material Engine Name (Dictates Physics/Sound in-game)
        chunk[0:32] = str(mat_name).encode('ascii', errors='ignore')[:31].ljust(32, b'\0')
        
        # Floats (Untested - But probably related to volume opposed to friction. Usually 0.1 & 0.5)
        chunk[32:36] = struct.pack('<f', float(f1))
        chunk[36:40] = struct.pack('<f', float(f2))
        
        # 3. SubStruct A (Hardcoded "none" + Hex Data)
        chunk[40:48] = b'none\x00\x00\x00\x00'
        try:
            chunk[48:72] = bytes.fromhex(str(data_a_hex))[:24].ljust(24, b'\0')
        except ValueError:
            chunk[48:72] = bytes(24)

        # 4. SubStruct B (Hardcoded "none" + Hex Data)
        chunk[72:80] = b'none\x00\x00\x00\x00'
        try:
            chunk[80:104] = bytes.fromhex(str(data_b_hex))[:24].ljust(24, b'\0')
        except ValueError:
            chunk[80:104] = bytes(24)

        mat_data += chunk

    faces_data = bytearray()
    for p in mesh.polygons:
        num_v = len(p.vertices)
        if num_v < 3 or num_v > 4:
            operator.report({'ERROR'}, f"Face {p.index} has {num_v} vertices! BBND only supports Triangles and Quads.")
            return {'CANCELLED'}

        mat_id = p.material_index if p.material_index < new_num_groups else 0

        if num_v == 3:
            v1, v2, v3 = p.vertices
            faces_data += struct.pack('<HHHHH', v1, v2, v3, 0, mat_id)
        elif num_v == 4:
            v_list = list(p.vertices)
            if v_list[3] == 0:
                v_list = [v_list[3], v_list[0], v_list[1], v_list[2]]
            faces_data += struct.pack('<HHHHH', v_list[0], v_list[1], v_list[2], v_list[3], mat_id)

    final_file = header + verts_data + mat_data + faces_data

    with open(filepath, 'wb') as f:
        f.write(final_file)

    operator.report({'INFO'}, f"SUCCESS! Exported to {os.path.basename(filepath)}")
    return {'FINISHED'}