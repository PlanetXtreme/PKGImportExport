# ##### BEGIN LICENSE BLOCK #####
#
# This program is licensed under Creative Commons BY-NC-SA:
# https://creativecommons.org/licenses/by-nc-sa/3.0/
#
# Created by Dummiesman, 2016-2020
#
# ##### END LICENSE BLOCK #####

import bpy, mathutils
import os, struct
import os.path as path
import glob #for headlights
import re

import pkgimporter.common_helpers as helper
import pkgimporter.binary_helper as bin
from .material_helper_ui import build_angel_material_nodes

#######################
### Other Functions ###
#######################

def get_object_name_without_lod_suffix(meshname):
    """Strips off all suffixes for LOD"""
    return meshname.upper().replace("_VL", "").replace("_L", "").replace("_M", "").replace("_H", "")

def find_matrix3x4(meshname, pkg_path):
    """search for *.mtx and load if found"""
    pkg_name = os.path.basename(pkg_path)[:-4]
    search_path = os.path.dirname(pkg_path)
    mesh_name_parsed = get_object_name_without_lod_suffix(meshname)
    
    find_path = helper.find_file_with_game_fallback(pkg_name + "_" + mesh_name_parsed + ".mtx", search_path, "geometry", ignore_subdir_on_search_path=True)
    
    if find_path is not None:
        mtxfile = open(find_path, 'rb')
        return bin.read_matrix3x4(mtxfile)
    return None
    
def find_matrix(meshname, pkg_path):
    """search for *.mtx and load if found"""
    pkg_name = os.path.basename(pkg_path)[:-4]
    search_path = os.path.dirname(pkg_path)
    mesh_name_parsed = get_object_name_without_lod_suffix(meshname)
    
    find_path = helper.find_file_with_game_fallback(pkg_name + "_" + mesh_name_parsed + ".mtx", search_path, "geometry", ignore_subdir_on_search_path=True)
    
    if find_path is not None:
        mtxfile = open(find_path, 'rb')
        mtx_info = struct.unpack('ffffffffffff', mtxfile.read(48))
        
        mtx_min = helper.convert_vecspace_to_blender((mtx_info[0], mtx_info[1], mtx_info[2]))
        mtx_max = helper.convert_vecspace_to_blender((mtx_info[3], mtx_info[4], mtx_info[5]))
        pivot =   helper.convert_vecspace_to_blender((mtx_info[6], mtx_info[7], mtx_info[8]))
        origin =  helper.convert_vecspace_to_blender((mtx_info[9], mtx_info[10], mtx_info[11]))
        
        mtxfile.close()
        
        return (True, mtx_min, mtx_max, pivot, origin)
    return (False, None, None, None, None)
 
def check_degenerate(i1, i2, i3):
    if i1 == i2 or i1 == i3 or i2 == i3:
        return True
    return False
    
def triangle_strip_to_list(strip, clockwise):
    """convert a strip of triangles into a list of triangles"""
    triangle_list = []
    for v in range(len(strip) - 2):
        if clockwise:
            triangle_list.extend([strip[v+1], strip[v], strip[v+2]])
        else:
            triangle_list.extend([strip[v], strip[v+1], strip[v+2]])
            
        # make sure we aren't resetting the clockwise
        # flag if we have a degenerate triangle
        if not check_degenerate(strip[v], strip[v+1], strip[v+2]):
            clockwise = not clockwise

    return triangle_list
    
def convert_triangle_strips(tristrip_data):
    """convert Midnight Club triangle strips into triangle list data"""
    last_strip_cw = False
    last_strip_indices = []
    trilist_data = []
    for us in tristrip_data:
        # flags processing
        FLAG_CW = ((us & (1 << 14)) != 0)
        FLAG_END = ((us & (1 << 15)) != 0)
        INDEX = us
        if FLAG_CW:
            INDEX &= ~(1 << 14)
        if FLAG_END:
            INDEX &= ~(1 << 15)
            
        # cw flag is only set at the first index in the strip
        if len(last_strip_indices) == 0:
            last_strip_cw = FLAG_CW
        last_strip_indices.append(INDEX)
        
        # are we done with this strip?
        if FLAG_END:
            trilist_data.extend(triangle_strip_to_list(last_strip_indices, last_strip_cw))
            last_strip_cw = False
            last_strip_indices = []
    
    return trilist_data

def read_vertex_data(file, FVF_FLAGS, compressed):
    """read PKG vertex data into a tuple"""
    vnorm = mathutils.Vector((1, 1, 1))
    vuv = (0, 0)
    vcolor = mathutils.Color((1, 1, 1))
    if FVF_FLAGS.has_flag("D3DFVF_NORMAL"):
        vnorm = bin.read_cfloat3(file) if compressed else bin.read_float3(file)
    if FVF_FLAGS.has_flag("D3DFVF_DIFFUSE"):
        c4d = bin.read_color4d(file)
        vcolor = mathutils.Color((c4d[0], c4d[1], c4d[2]))
    if FVF_FLAGS.has_flag("D3DFVF_SPECULAR"):
        c4d = bin.read_color4d(file)
        vcolor = mathutils.Color((c4d[0], c4d[1], c4d[2]))
    if FVF_FLAGS.has_flag("D3DFVF_TEX1"):
        vuv = bin.read_cfloat2(file) if compressed else bin.read_float2(file)
          
    return (vnorm, vuv, vcolor)

def populate_material(mtl=None, shader=None, pkg_path="", use_roughness_instead=True):
    """ Initializes a material by locating textures and delegating to the UI builder """
    # get addon settings
    preferences = bpy.context.preferences 
    
    # get tex name
    texture_name = "age:notexture" if shader.name is None else shader.name
    
    # look for a texture
    tex_result = None
    is_substituted_tex = False
    
    if shader.name is not None:
        tex_result = helper.try_load_texture(texture_name, path.abspath(path.join(os.path.dirname(pkg_path), "..")))
            
        # texture substitution
        if tex_result is None:
            tex_result = helper.make_placeholder_texture(texture_name)
            is_substituted_tex = True

    build_angel_material_nodes(
        mtl=mtl,
        image=tex_result,
        diffuse_color=shader.diffuse_color,
        emissive_color=shader.emissive_color,
        shininess=shader.shininess,
        use_roughness_instead=use_roughness_instead,
        is_substituted_tex=is_substituted_tex,
        use_alpha_hash=True,
        force_node_creation=False # Let it skip generating blank nodes if no texture is found
    )
        
    mtl.name = texture_name

def import_headlight_objs(filepath, root_parent_obj=None, target_collection=None):

    """
    Finds and imports HEADLIGHT / HLIGHT (with optional GLOW) .mtx files that 
    strictly match the base name of the given filepath. 
    Reconstructs them as plane objects in Blender.
    """
    
    directory = os.path.dirname(filepath)
    if not directory:
        directory = "."
        
    filename = os.path.basename(filepath)
    base_name = os.path.splitext(filename)[0]
    
    pattern_str = r"^" + re.escape(base_name) + r"_?(HEADLIGHT|HLIGHT)(GLOW)?\d*\.mtx$"
    regex = re.compile(pattern_str, re.IGNORECASE)
    
    # 3. Search the directory for perfectly matching MTX files
    mtx_files =[]
    if os.path.exists(directory):
        for f in os.listdir(directory):
            if regex.match(f):
                mtx_files.append(os.path.join(directory, f))
    
    if not mtx_files:
        print(f"Notice: No matching HEADLIGHT/HLIGHT mtx files found for '{base_name}' in {directory}")
        return
        
    for mtx_path in mtx_files:
        file_base = os.path.basename(mtx_path)
        obj_name = os.path.splitext(file_base)[0]
        
        # Strip the base prefix to make the object name clean in Blender (e.g. "HLIGHTGLOW0")
        obj_upper = obj_name.upper()
        if "HEADLIGHT" in obj_upper:
            start_index = obj_upper.find("HEADLIGHT")
            obj_name = obj_name[start_index:]
        elif "HLIGHT" in obj_upper:
            start_index = obj_upper.find("HLIGHT")
            obj_name = obj_name[start_index:]

        with open(mtx_path, 'rb') as f:
            # The export script packs exactly 9 floats (36 bytes) followed by padding
            float_data = f.read(36)
            if len(float_data) < 36:
                print(f"Warning: Skipping {file_base}, file is too small.")
                continue
                
            # Unpack the Game Space floats (Little Endian '<9f')
            (g_minX, g_minY, g_minZ, 
             g_maxX, g_maxY, g_maxZ, 
             g_centerX, g_centerY, g_centerZ) = struct.unpack('<9f', float_data)
             
        b_minX, b_maxX = g_minX, g_maxX
        b_minY, b_maxY = g_minZ, g_maxZ
        b_minZ, b_maxZ = g_minY, g_maxY
        
        # Craft the Headlight Object (Quad / Plane)
        verts =[
            (b_minX, b_minY, b_minZ), # Bottom-Left
            (b_maxX, b_minY, b_minZ), # Bottom-Right
            (b_maxX, b_maxY, b_maxZ), # Top-Right
            (b_minX, b_maxY, b_maxZ), # Top-Left
        ]
        
        faces = [(0, 1, 2, 3)]
        
        # Create Blender mesh and object
        mesh = bpy.data.meshes.new(name=obj_name)
        mesh.from_pydata(verts,[], faces)
        mesh.update()
        
        obj = bpy.data.objects.new(obj_name, mesh)
        
        # FIX: Link to the specific PKG collection instead of default
        if target_collection:
            target_collection.objects.link(obj)
        else:
            bpy.context.collection.objects.link(obj)
            
        # FIX: Parent to the Master Root Object
        if root_parent_obj:
            obj.parent = root_parent_obj
        
        print(f"Imported custom HLIGHT file: {mtx_path} as '{obj_name}'")

def get_lod_info(name):
    """
    Returns 1=VL, 2=L, 3=M, 4=H, 5=None (No LOD suffix)
    """
    lower_name = name.lower()
    
    # 1. Handle exact matches for standalone LODs (H, M, L, VL)
    if lower_name == 'vl':
        return "__MAIN__", 1
    elif lower_name == 'l':
        return "__MAIN__", 2
    elif lower_name == 'm':
        return "__MAIN__", 3
    elif lower_name == 'h':
        return "__MAIN__", 4
        
    # 2. Handle standard suffix matches (e.g., BREAK01_H)
    if lower_name.endswith('_vl'):
        return name[:-3], 1
    elif lower_name.endswith('_l'):
        return name[:-2], 2
    elif lower_name.endswith('_m'):
        return name[:-2], 3
    elif lower_name.endswith('_h'):
        return name[:-2], 4
    
    return name, 5 #for misc geometry like BOUND (bbnd)


def pre_scan_highest_lods(filepath, pkg_size):
    """
    Prescans PKG3 files using block lengths
    Returns a set of allowed file_names, or None if the file is PKG2
    """
    allowed_meshes = set()
    lod_tracker = {} # base_name_lower -> (highest_lod_val, exact_file_name)
    
    with open(filepath, 'rb') as f:
        version = f.read(4).decode("utf-8", errors="ignore")
        if version != "PKG3":
            return None # Cannot fast-forward PKG2 easily, fallback to post-deletion
        
        while f.tell() < pkg_size:
            header = f.read(4).decode("utf-8", errors="ignore")
            if header != "FILE": break
            
            file_name = bin.read_angel_string(f)
            file_length = struct.unpack('L', f.read(4))[0]
            
            if file_name not in ["shaders", "offset", "xrefs"]:
                base_name, lod_val = get_lod_info(file_name)
                
                if lod_val < 5:
                    base_lower = base_name.lower()
                    # If we haven't seen this base name, or this LOD is higher than the previous best:
                    if base_lower not in lod_tracker or lod_val > lod_tracker[base_lower][0]:
                        lod_tracker[base_lower] = (lod_val, file_name)
                else:
                    allowed_meshes.add(file_name)# Not an LOD 
                    
            # Instantly leap over the file block's data payload
            if file_length > 0:
                f.seek(file_length, 1)
                
    for base, (val, best_file_name) in lod_tracker.items():
        allowed_meshes.add(best_file_name)
        
    return allowed_meshes