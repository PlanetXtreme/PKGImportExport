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

import pkgimporter.common_helpers as helper
import pkgimporter.binary_helper as bin
                       
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
    """ Initializes a material """
    print(f"use_roughness_instead_of_specular is {use_roughness_instead}")
    # get addon settings
    preferences = bpy.context.preferences
    addon_prefs = preferences.addons[__package__].preferences    
    
    # get tex name
    texture_name = "age:notexture" if shader.name is None else shader.name
    
    # basics
    mtl.use_nodes = True
    mtl.use_backface_culling = True
    
    # setup colors
    bsdf = mtl.node_tree.nodes["Principled BSDF"]
    bsdf.inputs['Base Color'].default_value = shader.diffuse_color
    bsdf.inputs['Emission Color'].default_value = shader.emissive_color

    if use_roughness_instead:
        # Invert shininess back to roughness (Shininess 1.0 -> Roughness 0.0)
        roughness_val = min(max(1.0 - shader.shininess, 0.0), 1.0)
        
        bsdf.inputs['Roughness'].default_value = roughness_val
        bsdf.inputs['Specular IOR Level'].default_value = 0.5 
    else:
        # Original functionality
        bsdf.inputs['Specular IOR Level'].default_value = shader.shininess
        bsdf.inputs['Roughness'].default_value = 0.0

    mtl.diffuse_color = shader.diffuse_color
    mtl.specular_intensity = 0.1
    mtl.metallic = shader.shininess

    # alpha vars
    mtl_alpha = shader.diffuse_color[3]
    tex_depth = 0
        
    # look for a texture
    tex_result = None
    tex_image_node = None
    is_substituted_tex = False
    if shader.name is not None:
        tex_result = helper.try_load_texture(texture_name, path.abspath(path.join(os.path.dirname(pkg_path), "..")))
        
        # debug
        #if tex_result is not None:
        #    print("Texture:" + texture_name + ", Path:" + tex_result.filepath_raw)
            
        # texture substitution
        if tex_result is None and addon_prefs.substitute_textures:
            tex_result = helper.make_placeholder_texture(texture_name)
            is_substituted_tex = True

    # set up diffuse
    if tex_result is not None:
        tex_depth = tex_result.depth
        tex_image_node = mtl.node_tree.nodes.new('ShaderNodeTexImage')
        tex_image_node.image = tex_result
        tex_image_node.location = mathutils.Vector((-740.0, 20.0))
        
        # the substitution texture is very low res. Don't filter it.
        if is_substituted_tex:
            tex_image_node.interpolation = "Closest"
            
        blend_node = mtl.node_tree.nodes.new('ShaderNodeMixRGB')
        blend_node.inputs['Color2'].default_value = shader.diffuse_color
        blend_node.inputs['Fac'].default_value = 1.0
        blend_node.blend_type = 'MULTIPLY'
        blend_node.label = "Diffuse Color"
        blend_node.location = mathutils.Vector((-460.0, 160.0))
        
        mtl.node_tree.links.new(blend_node.inputs['Color1'], tex_image_node.outputs['Color'])
        mtl.node_tree.links.new(bsdf.inputs['Base Color'], blend_node.outputs['Color'])

    # setup emission
    if tex_image_node is not None:
        blend_node = mtl.node_tree.nodes.new('ShaderNodeMixRGB')
        blend_node.inputs['Color2'].default_value = shader.emissive_color
        blend_node.inputs['Fac'].default_value = 1.0
        blend_node.blend_type = 'MULTIPLY'
        blend_node.label = "Emission Color"
        blend_node.location = mathutils.Vector((-460.0, -20.0))
        
        mtl.node_tree.links.new(blend_node.inputs['Color1'], tex_image_node.outputs['Color'])
        mtl.node_tree.links.new(bsdf.inputs['Emission Color'], blend_node.outputs['Color'])
     
    # have alpha?
    if mtl_alpha < 1 or tex_depth == 32:
        mtl.blend_method = 'HASHED' if addon_prefs.use_alpha_hash else 'BLEND'
        
    # assign transparent channel on BSDF
    if tex_image_node is not None:
        blend_node = mtl.node_tree.nodes.new('ShaderNodeMath')
        blend_node.inputs[0].default_value = mtl_alpha
        blend_node.operation = 'MULTIPLY'
        blend_node.label = "Alpha"
        blend_node.location = mathutils.Vector((-460.0, -200.0))
        
        mtl.node_tree.links.new(blend_node.inputs[1], tex_image_node.outputs['Alpha'])
        mtl.node_tree.links.new(bsdf.inputs['Alpha'], blend_node.outputs[0])
    else:
        bsdf.inputs['Alpha'].default_value = mtl_alpha
        
    mtl.name = texture_name

def import_headlight_objs(filepath):
    """
    Finds and imports all *_HLIGHTGLOW*.mtx files in the same directory as the given filepath.
    Reconstructs them as plane objects in Blender.
    """
    # 1. Get the directory from the provided .pkg filepath
    directory = os.path.dirname(filepath)
    
    # 2. Search for any MTX file matching the headlight naming convention
    search_pattern = os.path.join(directory, "*_HLIGHTGLOW*.mtx")
    mtx_files = glob.glob(search_pattern)
    
    if not mtx_files:
        print(f"Notice: No HLIGHTGLOW mtx files found in {directory}")
        return
        
    for mtx_path in mtx_files:
        # Get the filename to name our Blender object (e.g., "example_HLIGHTGLOW0")
        filename = os.path.basename(mtx_path)
        obj_name = os.path.splitext(filename)[0]
        if "HLIGHTGLOW" in obj_name: #changes exported name
            start_index = obj_name.find("HLIGHTGLOW")
            obj_name = obj_name[start_index:]

        with open(mtx_path, 'rb') as f:
            # The export script packs exactly 9 floats (36 bytes) followed by padding
            float_data = f.read(36)
            if len(float_data) < 36:
                print(f"Warning: Skipping {filename}, file is too small.")
                continue
                
            # Unpack the Game Space floats (Little Endian '<9f')
            (g_minX, g_minY, g_minZ, 
             g_maxX, g_maxY, g_maxZ, 
             g_centerX, g_centerY, g_centerZ) = struct.unpack('<9f', float_data)
             
        # Convert Game Space back to Blender Space
        # Export did: Game_X = Blen_X | Game_Y = Blen_Z | Game_Z = Blen_Y
        # So Import:  Blen_X = Game_X | Blen_Y = Game_Z | Blen_Z = Game_Y
        b_minX, b_maxX = g_minX, g_maxX
        b_minY, b_maxY = g_minZ, g_maxZ
        b_minZ, b_maxZ = g_minY, g_maxY
        
        # Craft the Headlight Object (Quad / Plane)
        verts = [
            (b_minX, b_minY, b_minZ), # Bottom-Left
            (b_maxX, b_minY, b_minZ), # Bottom-Right
            (b_maxX, b_maxY, b_maxZ), # Top-Right
            (b_minX, b_maxY, b_maxZ), # Top-Left
        ]
        
        faces = [(0, 1, 2, 3)]
        
        # Create Blender mesh and object
        mesh = bpy.data.meshes.new(name=obj_name)
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        
        obj = bpy.data.objects.new(obj_name, mesh)
        bpy.context.collection.objects.link(obj)
        
        print(f"Imported custom HLIGHT file: {mtx_path} as '{obj_name}'")