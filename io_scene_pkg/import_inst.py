import bpy
import struct
import math
import os
import mathutils
import json

from . import import_pkg
from .import_pkg import load_pkg, XREF_CACHE
import pkgimporter.common_helpers as helper

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "pkg_addon_settings.json")

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "pkg_addon_settings.json")

def load_settings():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f: return json.load(f)
        except Exception: pass
    return {}

def get_cached_collection(obj_name):
    if obj_name in XREF_CACHE:
        col = XREF_CACHE[obj_name]
        try:
            _ = col.name
            return col
        except ReferenceError:
            del XREF_CACHE[obj_name]
    return None

# The magic coordinate conversion matrix: Maps Game (X,Y,Z) -> Blender (-X,Z,Y)
CONV_MAT = mathutils.Matrix((
    (-1.0,  0.0,  0.0,  0.0),
    ( 0.0,  0.0,  1.0,  0.0),
    ( 0.0,  1.0,  0.0,  0.0),
    ( 0.0,  0.0,  0.0,  1.0)
))

def runs(operator, context, filepath="", is_batch_mode=False, **kwargs):
    xref_handling = kwargs.get('xref_handling', 'EMPTYS')
    origin_placement = kwargs.get('origin_placement', 'SKIP_UNRELATED')
    
    settings = load_settings()
    path_i_pkg = settings.get("path_i_pkg", "")
    path_i_xref = settings.get("path_i_xref", "")
    
    if not os.path.exists(filepath):
        print(f"Error: Could not find INST file {filepath}")
        return

    with open(filepath, 'rb') as f:
        data = f.read()
        
    file_length = len(data)
    offset = 0
    
    inst_name = os.path.splitext(os.path.basename(filepath))[0]
    inst_col = bpy.data.collections.new(inst_name)
    context.scene.collection.children.link(inst_col)
    
    failed_xref_count = 0
    loaded_count = 0

    print(f"--- IMPORTING INST: {inst_name} ---")

    while offset < file_length:
        if offset + 5 > file_length: break
            
        flags = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        
        len_type = data[offset]
        offset += 1
        
        is_short_format = (len_type & 0x80) != 0
        str_len = len_type & 0x7F
        
        if offset + str_len > file_length: break
            
        raw_str = data[offset : offset+str_len]
        obj_name = raw_str.decode('ascii', errors='ignore').replace('\0', '').strip()
        offset += str_len
        
        ob = bpy.data.objects.new(obj_name, None)
        ob.empty_display_type = 'ARROWS'
        ob.empty_display_size = 2.0
        ob["inst_original_name"] = obj_name 
        #flag for group has moved to collection name
        
        flag_col_name = f"lot_{flags}"
        if flag_col_name in inst_col.children:
            flag_col = inst_col.children[flag_col_name]
        else:
            flag_col = bpy.data.collections.new(flag_col_name)
            inst_col.children.link(flag_col)
            
        flag_col.objects.link(ob)
        
        if is_short_format:
            f1, f2, px, py, pz = struct.unpack_from('<5f', data, offset)
            offset += 20
            
            scale = math.sqrt((f1*f1) + (f2*f2))
            
            # Negating both flips it 180 degrees (which is apparantly correct)
            yaw = math.atan2(-f2, f1)
            
            # Use CONV_MAT to perfectly convert location
            vec_game = mathutils.Vector((px, py, pz, 1.0))
            loc = CONV_MAT @ vec_game
            
            ob.location = loc.xyz
            ob.rotation_euler = (0, 0, yaw)
            ob.scale = (scale, scale, scale)
            ob["inst_is_short"] = True
            
        else:
            floats = struct.unpack_from('<12f', data, offset)
            offset += 48
            
            mat_game = mathutils.Matrix((
                (floats[0], floats[3], floats[6], floats[9]),
                (floats[1], floats[4], floats[7], floats[10]),
                (floats[2], floats[5], floats[8], floats[11]),
                (0.0,       0.0,       0.0,       1.0)
            ))
            
            ob.matrix_basis = CONV_MAT @ mat_game @ CONV_MAT
            ob["inst_is_short"] = False
            
        # XREF LOADING LOGIC
        if xref_handling in {'INSTANCED', 'GEOMETRY'} and failed_xref_count < 3:
            cached_col = get_cached_collection(obj_name)
            if not cached_col:
                search_dirs = [
                    os.path.normpath(os.path.join(filepath, "..", "..", "geometry")),
                    path_i_pkg, path_i_xref
                ]
                
                found_pkg_path = None
                for s_dir in search_dirs:
                    if not s_dir or not os.path.exists(s_dir): continue
                    
                    for test_name in (f"{obj_name}.pkg", f"sp_{obj_name}.pkg"):
                        test_path = os.path.join(s_dir, test_name)
                        if os.path.exists(test_path):
                            found_pkg_path = test_path
                            break
                    if found_pkg_path: break
                
                if found_pkg_path:
                    try:
                        imported_collection = load_pkg(
                            filepath=found_pkg_path, context=context, import_lods=False,
                            import_bbnd=False, use_roughness_instead_of_specular_two=True,
                            import_headlights=False, import_coordinate_offset=False, 
                            batch_import_filter='NONE', xref_handling='EMPTYS',  
                            origin_placement=origin_placement, is_batch_mode=False, is_xref_import=True 
                        )
                        XREF_CACHE[obj_name] = imported_collection
                        cached_col = imported_collection
                    except NameError: pass
                else:
                    failed_xref_count += 1
                    print(f"Warning: Could not find pkg for {obj_name}")
                    if failed_xref_count >= 3:
                        print("Too many missing XREFs. Falling back to EMPTYS mode.")
                        xref_handling = 'EMPTYS'
            
            if cached_col is not None:
                if xref_handling == 'INSTANCED':
                    ob.instance_type = 'COLLECTION'
                    ob.instance_collection = cached_col
                elif xref_handling == 'GEOMETRY':
                    old_to_new = {}
                    for src_obj in cached_col.objects:
                        new_obj = src_obj.copy()
                        old_to_new[src_obj] = new_obj
                        flag_col.objects.link(new_obj)
                        
                    for src_obj, new_obj in old_to_new.items():
                        if src_obj.parent in old_to_new:
                            new_obj.parent = old_to_new[src_obj.parent]
                            new_obj.matrix_parent_inverse = src_obj.matrix_parent_inverse
                        else:
                            new_obj.parent = ob

        loaded_count += 1 
    print(f"Successfully loaded {loaded_count} instances.")