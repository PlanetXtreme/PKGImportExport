import bpy
import struct
import os
import math
from mathutils import Matrix

def save(operator, context):
    filepath = operator.filepath
    FIX_COORDINATE_ROTATION = True

    # 1. Force Object Mode
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    obj = bpy.context.active_object
    if not obj or obj.type != 'MESH':
        operator.report({'ERROR'}, "Please select a Mesh object in the 3D viewport!")
        return {'CANCELLED'}

    mesh = obj.data

    # We MUST read the original file to salvage the physics block
    if not os.path.exists(filepath):
        operator.report({'ERROR'}, "Exporting requires selecting an existing .bbnd file to overwrite (to preserve physics).")
        return {'CANCELLED'}

    # 2. Extract Data from Original File
    with open(filepath, 'rb') as f:
        data = f.read()

    orig_version = data[0:1] 
    old_num_verts = struct.unpack('<I', data[1:5])[0]
    orig_group_bytes = data[5:9]
    old_num_faces = struct.unpack('<I', data[9:13])[0]
    num_orig_groups = struct.unpack('<I', orig_group_bytes)[0]

    mat_start = 13 + (old_num_verts * 12)
    mat_end = len(data) - (old_num_faces * 10)
    material_block = data[mat_start:mat_end]

    # 3. Build Header
    new_num_verts = len(mesh.vertices)
    new_num_faces = len(mesh.polygons)
    
    header = bytearray(orig_version)             
    header += struct.pack('<I', new_num_verts)   
    header += orig_group_bytes                   
    header += struct.pack('<I', new_num_faces)   

    # 4. Calculate Final Transform Matrix
    # Undo the +180 Z and +90 X rotations that were applied during import
    export_mat = obj.matrix_world
    
    if FIX_COORDINATE_ROTATION:
        rot_z_inv = Matrix.Rotation(math.radians(-180.0), 4, 'Z')
        rot_x_inv = Matrix.Rotation(math.radians(-90.0), 4, 'X')
        # The inverse order mathematically cancels out the import rotations!
        export_mat = rot_x_inv @ rot_z_inv @ export_mat

    # 5. Build New Vertices
    verts_data = bytearray()
    for v in mesh.vertices:
        final_co = export_mat @ v.co
        verts_data += struct.pack('<fff', final_co.x, final_co.y, final_co.z)

    # 6. Build New Faces
    faces_data = bytearray()
    for p in mesh.polygons:
        num_v = len(p.vertices)
        if num_v < 3 or num_v > 4:
            operator.report({'ERROR'}, f"Face {p.index} has {num_v} vertices! BBND only supports Triangles and Quads.")
            return {'CANCELLED'}

        mat_id = p.material_index 
        
        if mat_id >= num_orig_groups:
            operator.report({'WARNING'}, f"Face {p.index} uses Material {mat_id}, but original file only has {num_orig_groups} groups!")

        if num_v == 3:
            v1, v2, v3 = p.vertices
            faces_data += struct.pack('<HHHHH', v1, v2, v3, 0, mat_id)
            
        elif num_v == 4:
            v_list = list(p.vertices)
            if v_list[3] == 0:
                v_list = [v_list[3], v_list[0], v_list[1], v_list[2]]
                
            faces_data += struct.pack('<HHHHH', v_list[0], v_list[1], v_list[2], v_list[3], mat_id)

    # 7. Assemble and Overwrite Save
    final_file = header + verts_data + material_block + faces_data

    with open(filepath, 'wb') as f:
        f.write(final_file)

    operator.report({'INFO'}, f"SUCCESS! Exported to {os.path.basename(filepath)}")
    return {'FINISHED'}