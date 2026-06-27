import bpy
import struct
import math
import mathutils

CONV_MAT = mathutils.Matrix((
    (-1.0,  0.0,  0.0,  0.0),
    ( 0.0,  0.0,  1.0,  0.0),
    ( 0.0,  1.0,  0.0,  0.0),
    ( 0.0,  0.0,  0.0,  1.0)
))

def runs(operator, context, filepath="", force_long_format=False, custom_prop_name=False, **kwargs):
    objects = context.selected_objects
        
    # Only export Root Objects to avoid exporting child geometry twice
    export_objects = [ob for ob in objects if ob.parent is None]
    
    if not export_objects:
        print("No objects to export!")
        return {'CANCELLED'}

    print(f"--- EXPORTING INST: {len(export_objects)} items ---")

    with open(filepath, 'wb') as f:
        for ob in export_objects:
            
            if custom_prop_name and "inst_original_name" in ob:
                base_name = ob["inst_original_name"]
            else:
                base_name = ob.name.split('.')[0] # Strips .001, .002 etc.
                
            name_bytes = base_name.encode('ascii', errors='ignore') + b'\x00'
            str_len = len(name_bytes)
            
            if str_len > 127:
                print(f"Warning: Name {base_name} is too long! Truncating.")
                name_bytes = name_bytes[:126] + b'\x00'
                str_len = 127
                
            flags = 1  # Default fallback if not in a lot_ collection
            for col in ob.users_collection:
                if col.name.startswith("lot_"):
                    # Strip .001, .002 (lot_69.001 -> lot_69)
                    base_col_name = col.name.split('.')[0]
                    # Strip "lot_" 
                    flag_str = base_col_name.replace("lot_", "")
                    
                    try:
                        flags = int(flag_str)
                    except ValueError:
                        print(f"Warning: Could not parse number from collection {col.name}. Using 1.")
                    break
            
            euler = ob.rotation_euler
            scale = ob.scale
            
            is_uniform_scale = abs(scale.x - scale.y) < 0.001 and abs(scale.y - scale.z) < 0.001
            is_z_rot_only = abs(euler.x) < 0.001 and abs(euler.y) < 0.001
            was_short = ob.get("inst_is_short", False)
            
            use_short = not force_long_format and is_uniform_scale and is_z_rot_only and (was_short or True)
            
            len_type = str_len
            if use_short:
                len_type |= 0x80 # Set highest bit for Short format
                
            f.write(struct.pack('<I B', flags, len_type))
            f.write(name_bytes)
            
            
            # Game_Matrix = CONV_MAT @ Blender_Matrix @ CONV_MAT
            mat_game = CONV_MAT @ ob.matrix_basis @ CONV_MAT
            
            if use_short:
                yaw = euler.z
                s = scale.x
                
                # Inverse of math.atan2(-f2, -f1):
                f1 = -math.cos(yaw) * s
                f2 = -math.sin(yaw) * s
                
                # Extract positional XYZ from Game Matrix Translation
                px, py, pz = mat_game.col[3][:3]

                f.write(struct.pack(
                    '<5f',
                    f1, f2,
                    px, py, pz
                ))

            else:
                m11, m21, m31 = mat_game.col[0][:3]  # Game X axis
                m12, m22, m32 = mat_game.col[1][:3]  # Game Y axis
                m13, m23, m33 = mat_game.col[2][:3]  # Game Z axis
                px,  py,  pz  = mat_game.col[3][:3]  # Game Translation

                f.write(struct.pack(
                    '<12f',
                    m11, m12, m13,
                    m21, m22, m23,
                    m31, m32, m33,
                    px, py, pz
                ))

    print(f"Successfully exported to {filepath}")
    return {'FINISHED'}