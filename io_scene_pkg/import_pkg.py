# ##### BEGIN LICENSE BLOCK #####
#
# This program is licensed under Creative Commons BY-NC-SA:
# https://creativecommons.org/licenses/by-nc-sa/3.0/
#
# Created by Dummiesman, 2016-2020
#
# ##### END LICENSE BLOCK #####

import bpy, bmesh, mathutils
import os, time, struct, math

import os.path as path
from mathutils import*
from mathutils import Vector, Matrix #redundant dummy

from pkgimporter.fvf import FVF
from pkgimporter.shader_set import (ShaderSet, Shader)

import pkgimporter.binary_helper as bin
import pkgimporter.import_helper as import_helper
import pkgimporter.common_helpers as helper
import pkgimporter.import_bbnd as extract_bbnd_file

pkg_path = None

#misc objects that are legacy MidtownMadness implementation
misc_mtx_objects = ["EXHAUST0", "EXHAUST1"]

XREF_CACHE = {} 
def fast_scan_for_skip(filepath, filter_mode):
    "Skips files based off position data in the pkg footer"
    if filter_mode == 'NONE':
        return False
        
    basename = path.basename(filepath).lower()
    
    # REQ #1: Check if filename has sp_ to skip
    if basename.startswith("sp_"):
        if filter_mode in ['SKIP_SP', 'SKIP_UNP']:
            return True # Skip it
            
    # REQ #2: Check coordinate data FIRST
    if filter_mode in ['SKIP_UNP', 'SKIP_POS']:
        try:
            with open(filepath, 'rb') as f:
                pkg_version = f.read(4).decode("utf-8", errors="ignore")
                if pkg_version not in ["PKG3", "PKG2"]:
                    # Not a valid PKG file, therefore has no position data
                    return True if filter_mode == 'SKIP_POS' else False
                
                pkg_version_id = int(pkg_version[-1:])
                pkg_size = path.getsize(filepath)
                
                # Fast forward through file blocks
                while f.tell() < pkg_size:
                    file_header = f.read(4).decode("utf-8", errors="ignore")
                    if file_header != "FILE": break
                    
                    file_name = bin.read_angel_string(f)
                    file_length = 0 if pkg_version_id == 2 else struct.unpack('L', f.read(4))[0]
                    
                    if file_name == "offset":
                        # We found the offset! Check if it's 0,0,0
                        offset_data = struct.unpack('<3f', f.read(12))
                        is_zero_pos = sum(abs(v) for v in offset_data) < 0.001
                        
                        if filter_mode == 'SKIP_UNP':
                            return True if is_zero_pos else False # Skip if it IS 0,0,0
                        elif filter_mode == 'SKIP_POS':
                            return True if not is_zero_pos else False # Skip if it is NOT 0,0,0
                            
                    else:
                        if pkg_version_id == 3 and file_length > 0:
                            f.seek(file_length, 1) # Skip block quickly
                        elif pkg_version_id == 2:
                            # PKG2 is hard to fast-forward without parsing
                            # For SKIP_POS we assume no readable pos data, so we skip
                            return True if filter_mode == 'SKIP_POS' else False
                
                # If we exit the loop without ever finding the "offset" file
                if filter_mode == 'SKIP_POS':
                    return True # Skip it, it contains no position data
                return False
                
        except Exception:
            # If fast scan fails, skip if we require position data, else import normally
            if filter_mode == 'SKIP_POS':
                return True
            pass 
            
    return False

def read_shaders_file(file, length, offset, import_variants, use_roughness_instead_of_specular_two):
    # get custom stuff

    scene = bpy.context.scene
    angel = scene.angel
    
    # read shader set
    shader_set = ShaderSet(file)
    
    num_variants = len(shader_set.variants)
    if num_variants <= 0:
        return
        
    num_shaders_per_variant = len(shader_set.variants[0])
    
    # setup base material set
    base_material_set = []
    base_variant = shader_set.variants[0]
    for shader_num in range(num_shaders_per_variant):
        shader = base_variant[shader_num]
        
        mtl = bpy.data.materials.get(str(shader_num))
        if mtl is not None:
            import_helper.populate_material(mtl, shader, pkg_path, use_roughness_instead_of_specular_two)
            base_material_set.append(mtl)
        else:
            base_material_set.append(None) # SHOULD NOT HAPPEN!
    
    # don't set up variants if the import flag isn't set 
    if not import_variants:
        return
        
    # clear existing variant stuff
    angel.clear()
    
    # find what materials are equal across the board
    # this will give us the ability of quickly checking if variants are unique
    # but also a reference point for variant 0
    variant_similarities = [0] * num_shaders_per_variant
    for i in range(num_variants - 1, 0, -1):
        variant_ref = shader_set.variants[i]
        variant_prev = shader_set.variants[i-1]
        for j in range(num_shaders_per_variant):
            if variant_ref[j] == variant_prev[j]:
                variant_similarities[j] += 1
   
    # setup variants
    for variant_num  in range(num_variants):
        tool_variant = angel.variants.add() # add to our tool
        variant = shader_set.variants[variant_num]
        for shader_num in range(num_shaders_per_variant):
            shader = variant[shader_num]
            
            # check if this shader is unique to this variant
            if variant_similarities[shader_num] == num_variants - 1:
                continue
            elif variant_num > 0 and shader == base_variant[shader_num]:
                continue

            # get shader base material
            base_mtl = base_material_set[shader_num]
            
            # add the base material to the variant, returning the cloned, variant version
            variant_material = tool_variant.add_material(base_mtl)
            
            # adjust the cloned version
            import_helper.populate_material(variant_material.material, shader, pkg_path, use_roughness_instead_of_specular_two)
            variant_material.material.name = helper.get_undupe_name(variant_material.material.name) + "_VARIANT" + str(variant_num)
            
    # apply it 
    angel.apply_to_scene()
    angel.selected_variant = 0
    
    # skip to the end of this FILE
    file.seek(length - (file.tell() - offset), 1)
    return

def read_xrefs(file, root_parent_obj, collection, xref_handling, parent_filepath, context):
    if xref_handling == 'SKIP':
        num_xrefs = struct.unpack('L', file.read(4))[0]
        # Skip logic here (approximate byte skipping if you have it)
        return

    num_xrefs = struct.unpack('L', file.read(4))[0]
    for num in range(num_xrefs):
        mtx = bin.read_matrix3x4(file)

        raw_bytes = file.read(32)
        # C-style strings terminate at the first null byte. 
        # Everything after it is uninitialized garbage memory, so we cut it off.
        null_index = raw_bytes.find(b'\x00')
        if null_index != -1:
            raw_bytes = raw_bytes[:null_index]
            
        # Decode and strip any leftover whitespace
        xref_name = raw_bytes.decode("utf-8", errors="ignore").strip()
        
        # Setup Empty
        ob = bpy.data.objects.new("xref:" + xref_name, None)
        ob.matrix_basis = mtx
        ob.show_name = True
        ob.show_axis = True
        ob.parent = root_parent_obj 
        collection.objects.link(ob) 
        
        if xref_handling in {'INSTANCED', 'GEOMETRY'}:
                    
            # SAFE CACHE CHECK: Ensure the cache exists AND the Blender data hasn't been deleted
            is_cached_and_alive = False
            if xref_name in XREF_CACHE:
                cached_col = XREF_CACHE[xref_name]
                if cached_col is None:
                    is_cached_and_alive = True # Valid 'None' (file wasn't found previously)
                else:
                    try:
                        _ = cached_col.name # Tests if the C-struct is still alive
                        is_cached_and_alive = True
                    except ReferenceError:
                        pass # It was deleted by the user! We must re-import.

            if not is_cached_and_alive:
                
                # 1. Look for the target pkg file in the same directory
                parent_dir = os.path.dirname(parent_filepath)
                
                # Check for direct name, or sp_ prefix
                search_path = os.path.join(parent_dir, f"{xref_name}.pkg")
                if not os.path.exists(search_path):
                    search_path = os.path.join(parent_dir, f"sp_{xref_name}.pkg")
                    
                if os.path.exists(search_path):
                    # 2. Call load_pkg to import the xref, getting the resulting Collection back
                    imported_collection = load_pkg(
                        filepath=search_path,
                        context=context,
                        import_lods=False,
                        import_bbnd=False,
                        use_roughness_instead_of_specular_two=True,
                        import_headlights=False, 
                        import_coordinate_offset=True,
                        batch_import_filter='NONE', 
                        xref_handling='EMPTYS',  
                        origin_placement='SKIP_UNRELATED',  
                        import_variants=False,
                        is_batch_mode=False,
                        is_xref_import=True 
                    )
                    
                    # 3. Add to Cache
                    XREF_CACHE[xref_name] = imported_collection
                else:
                    XREF_CACHE[xref_name] = None
                    print(f"Warning: Could not find xref file for {xref_name}")
            
            # 4. Apply to Empty
            cached_col = XREF_CACHE.get(xref_name)
            if cached_col is not None:
                if xref_handling == 'INSTANCED':
                    # Create a Collection Instance
                    ob.instance_type = 'COLLECTION'
                    ob.instance_collection = cached_col
                    
                elif xref_handling == 'GEOMETRY':
                    old_to_new = {}
                    
                    for src_obj in cached_col.objects:
                        new_obj = src_obj.copy()
                        
                        # By default, .copy() shares Mesh Data (like pressing Alt+D) to save memory.
                        # If you want 100% unique, unlinked mesh data: Uncomment the next 2 lines
                        # if new_obj.data is not None:
                        #     new_obj.data = new_obj.data.copy()
                        
                        old_to_new[src_obj] = new_obj
                        
                        if ob.users_collection:
                            for col in ob.users_collection:
                                col.objects.link(new_obj)
                        else:
                            context.collection.objects.link(new_obj)
                            
                    # Rebuild the object hierarchy 
                    for src_obj, new_obj in old_to_new.items():
                        if src_obj.parent in old_to_new:
                            # Inner xref hierarchy: parent to the duplicated parent
                            new_obj.parent = old_to_new[src_obj.parent]
                            new_obj.matrix_parent_inverse = src_obj.matrix_parent_inverse
                        else:
                            # Root objects of the XREF: Parent them to the main Empty locator
                            new_obj.parent = ob

def read_geometry_file(file, meshname, root_parent_obj, collection):
    scn = bpy.context.scene

    me = bpy.data.meshes.new(meshname+'Mesh')
    ob = bpy.data.objects.new(meshname, me)

    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    
    # create layers for this object
    uv_layer = bm.loops.layers.uv.new()
    vc_layer = bm.loops.layers.color.new()
    
    collection.objects.link(ob)
    
    # read geometry FILE data
    num_sections, num_vertices_tot, num_indices_tot, num_sections_dupe, fvf = struct.unpack('5L', file.read(20))
    FVF_FLAGS = FVF(fvf)

    ob_current_material = -1
    vertex_remap_table = {}
    vertex_index_remap = {}
    mesh_vertices = []
    mesh_uvs = []
    mesh_colors = []
    index_offset = 0

    ob.parent = root_parent_obj
    
    for num in range(num_sections):
        num_strips, strip_flags = struct.unpack('<HH', file.read(4))
        
        # check section strip flag
        FLAG_compact_strips = ((strip_flags & (1 << 8)) != 0)

        # get material, and add it to the objects material list
        shader_offset = struct.unpack('H', file.read(2))[0] if FLAG_compact_strips else struct.unpack('L', file.read(4))[0]
        
        # do we have this material?
        if bpy.data.materials.get(str(shader_offset)) is None:
            # we must make it!
            bpy.data.materials.new(name=str(shader_offset))
        
        ob.data.materials.append(bpy.data.materials.get(str(shader_offset)))
        ob_current_material += 1
        
        # read strips
        for strip in range(num_strips):
            # read
            prim_type = struct.unpack('H', file.read(2))[0] if FLAG_compact_strips else struct.unpack('L', file.read(4))[0] # seek past primtype
            num_vertices =  struct.unpack('H', file.read(2))[0] if FLAG_compact_strips else struct.unpack('L', file.read(4))[0]

            # read vertices
            for i in range(num_vertices):
                # read in raw data
                vpos = bin.read_float3(file)
                vnorm, vuv, vcolor = import_helper.read_vertex_data(file, FVF_FLAGS, FLAG_compact_strips)
               
                # convert coordinate spaces
                age_norm = helper.convert_vecspace_to_blender(vnorm)
                age_vert = helper.convert_vecspace_to_blender(vpos)
                age_uv = (vuv[0], (vuv[1] * -1) + 1)
                
                # add to uvs and colors list
                mesh_uvs.append(age_uv)
                mesh_colors.append(vcolor)
                
                # add vertex to mesh or remap
                pos_hash = str(age_vert)
                nrm_hash = str(age_norm)
                vertex_hash = pos_hash + "|" + nrm_hash
                
                if vertex_hash in vertex_remap_table:
                    vertex_index_remap[i+index_offset] = vertex_remap_table[vertex_hash]
                else:
                    # add vertex to mesh
                    bmvert = bm.verts.new(age_vert)
                    bmvert.normal = age_norm
               
                    vertex_remap_table[vertex_hash] = len(mesh_vertices)
                    vertex_index_remap[i+index_offset] = len(mesh_vertices)
                    
                    mesh_vertices.append(bmvert)
                    
            # read indices and build mesh
            num_indices = struct.unpack('H', file.read(2))[0] if FLAG_compact_strips else struct.unpack('L', file.read(4))[0]

            triangle_data = None
            if FLAG_compact_strips and prim_type == 4:
                tristrip_data = struct.unpack(str(num_indices) + 'H', file.read(2 * num_indices))
                triangle_data = import_helper.convert_triangle_strips(tristrip_data)
            else:
                triangle_data = struct.unpack(str(num_indices) + 'H', file.read(2 * num_indices))

            for i in range(0, len(triangle_data), 3):
                tri_indices = triangle_data[i:i+3]
                try:
                    # get verts
                    v0 = mesh_vertices[vertex_index_remap[tri_indices[0]+index_offset]]
                    v1 = mesh_vertices[vertex_index_remap[tri_indices[1]+index_offset]]
                    v2 = mesh_vertices[vertex_index_remap[tri_indices[2]+index_offset]]
                    
                    # setup face
                    face = bm.faces.new((v0, v1, v2))
                    face.smooth = True
                    face.material_index = ob_current_material
                    
                    # set uvs
                    for uv_set_loop in range(3):
                      face.loops[uv_set_loop][uv_layer].uv = mesh_uvs[tri_indices[uv_set_loop] + index_offset]
                      
                    # set colors
                    if FVF_FLAGS.has_flag("D3DFVF_DIFFUSE") or FVF_FLAGS.has_flag("D3DFVF_SPECULAR"):
                        for color_set_loop in range(3):
                            color = mesh_colors[tri_indices[color_set_loop] + index_offset]
                            # Blender requires RGBA (4 floats). If we only have RGB, add Alpha 1.0
                            if len(color) == 3:
                                color = (color[0], color[1], color[2], 1.0)
                            
                            face.loops[color_set_loop][vc_layer] = color
                except Exception as e:
                    print(str(e))
            
            index_offset += num_vertices

    # apply bmesh data to object
    bm.to_mesh(me)
    bm.free()
    
    # calculate normals
    #if FVF_FLAGS.has_flag("D3DFVF_NORMAL"):
      #me.calc_normals()

    # lastly, look for a MTX file. Don't grab an MTX for FNDR_M/L/VL though
    # as the FNDR lods are static and don't use the mtx
    if not ("fndr" in meshname.lower() and not "_h" in meshname.lower()):
        if helper.is_matrix_object(ob):
            # some objects actually use MTX as a matrix.
            mtx = import_helper.find_matrix3x4(meshname, pkg_path)
            if mtx is not None:
                ob.matrix_world = mtx
        else:
            # others use it as min,max,pivot,origin
            found, min, max, pivot, origin = import_helper.find_matrix(meshname, pkg_path)
            if found:
                ob.location = origin
    else:
        print(f"no location data found")
          
    # Return the object so load_pkg can apply the offset to it later
    return ob

def import_misc_mtx(root_parent_obj, collection):
    for mtx in misc_mtx_objects:
        found, min, max, pivot, origin = import_helper.find_matrix(mtx, pkg_path)
        if found:
            ob = bpy.data.objects.new(mtx, None)
            ob.location = origin
            ob.empty_display_size = 0.5
            ob.show_name = True
            ob.parent = root_parent_obj
            collection.objects.link(ob)

def apply_dgbanger_data(obj_name, obj, pkg_path, origin_placement):
    """
    Finds the associated dgBangerData file relative to the PKG path and applies
    its calculated Center of Gravity offset to positioning the object.
    """
    #print(f"trying to apply dgbangerdata. {obj_name}, {obj}, {pkg_path}, {origin_placement}")
    if origin_placement == 'NONE':
        return

    pkg_basename = os.path.splitext(os.path.basename(pkg_path))[0]
    # Process skipping logic
    if origin_placement == 'SKIP_UNRELATED':
        if pkg_basename.lower().startswith('vp_'):
            return
            
        # Ignore if it has an existing MTX pair offset already applied in `read_geometry_file`
        if not ("fndr" in obj_name.lower() and not "_h" in obj_name.lower()):
            if helper.is_matrix_object(obj):
                if import_helper.find_matrix3x4(obj_name, pkg_path) is not None:
                    return
            #else:
            #    found, _, _, _, _ = import_helper.find_matrix(obj_name, pkg_path)
            #    if found:
            #        return

    pkg_dir = os.path.dirname(pkg_path)
    
    # Paths to search based on given criteria
    paths_to_check = [
        os.path.join(pkg_dir, "..", "..", "M01", "tune", "banger", f"{pkg_basename}.dgBangerData"),
        os.path.join(pkg_dir, "..", "..", "L01", "tune", "banger", f"{pkg_basename}.dgBangerData"),
        os.path.join(pkg_dir, "..", "tune", "banger", f"{pkg_basename}.dgBangerData"),
    ]
    
    found_path = None
    for p in paths_to_check:
        p_norm = os.path.normpath(p)
        if os.path.exists(p_norm):
            found_path = p_norm
            break
            
    if found_path is not None:
        try:
            with open(found_path, 'r', encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line_stripped = line.strip()
                    if line_stripped.startswith("CG "):
                        parts = line_stripped.split()
                        if len(parts) >= 4:
                            x = float(parts[1])
                            y = float(parts[2])
                            z = float(parts[3])
                            
                            #obj.location = (x, -z, -y)
                            obj.data.transform(Matrix.Translation((-x, z, y)))

                            obj["dgbanger_cg"] = [x, y, z] #custom property used for export
                            break
        except Exception as e:
            print(f"Failed to read dgBangerData for {pkg_basename}: {e}")
    else:
        print(f"couldn't find path in \n{paths_to_check}")

def load_pkg(
                filepath,
                context,
                import_lods=True, 
                import_bbnd=True, 
                use_roughness_instead_of_specular_two=True,
                import_headlights=True,
                import_coordinate_offset=True,
                batch_import_filter='NONE', 
                xref_handling='EMPTYS',
                origin_placement='SKIP_UNRELATED',
                is_batch_mode=False,
                import_variants=True, 
                is_xref_import=False,
            ):

    global pkg_path
    previous_pkg_path = pkg_path 
    pkg_path = filepath
    
    if not is_batch_mode:
        batch_import_filter = 'NONE'

    if fast_scan_for_skip(filepath, batch_import_filter):
        print(f"Skipping PKG (Filtered out): {path.basename(filepath)}")
        return

    print("importing PKG: %r..." % (filepath))

    if bpy.ops.object.select_all.poll():
        bpy.ops.object.select_all(action='DESELECT')

    time1 = time.perf_counter()
    
    base_name = path.splitext(path.basename(filepath))[0]
    pkg_collection = bpy.data.collections.new(base_name)
    
    if is_xref_import:
        lib_col = bpy.data.collections.get("XREF_LIBRARY")
        if not lib_col:
            lib_col = bpy.data.collections.new("XREF_LIBRARY")
            context.scene.collection.children.link(lib_col)
            lib_col.hide_viewport = True
            lib_col.hide_render = True
            
        lib_col.children.link(pkg_collection)
    else:
        active_col = context.collection if context.collection else context.scene.collection
        active_col.children.link(pkg_collection)

    root_ob = bpy.data.objects.new(f"ROOOOT_{base_name}", None)
    pkg_collection.objects.link(root_ob)

    file = open(filepath, 'rb')
    pkg_version = file.read(4).decode("utf-8")
    if pkg_version != "PKG3" and pkg_version != "PKG2":
        print('\tFatal Error: PKG file is wrong format : ' + pkg_version)
        file.close()
        return
        
    pkg_version_id = int(pkg_version[-1:])
    pkg_offset = None
    imported_objects = []

    pkg_size = path.getsize(filepath)

    # PRE-SCAN LODS FOR SPEED (PKG3 ONLY)
    allowed_meshes = None
    if not import_lods:
        allowed_meshes = import_helper.pre_scan_highest_lods(filepath, pkg_size)

    # READ PKG DATA
    while file.tell() != pkg_size:
        file_header = file.read(4).decode("utf-8")
        if file_header != "FILE": break

        file_name = bin.read_angel_string(file)
        file_length = 0 if pkg_version_id == 2 else struct.unpack('L', file.read(4))[0]
        
        # FAST SKIP
        # If this is a mesh, and we have an allowed list, and it's not on it: Skip the bytes entirely
        if allowed_meshes is not None and file_name not in ["shaders", "offset", "xrefs"]:
            if file_name not in allowed_meshes:
                print('\t[' + str(round(time.perf_counter() - time1, 3)) + '] skipping lower LOD : ' + file_name)
                if file_length > 0:
                    file.seek(file_length, 1)
                continue
        
        print('\t[' + str(round(time.perf_counter() - time1, 3)) + '] processing : ' + file_name)
        if file_name == "shaders":
            read_shaders_file(file, file_length, file.tell(), import_variants, use_roughness_instead_of_specular_two)
        elif file_name == "offset":
            offset_data = struct.unpack('<3f', file.read(12))
            pkg_offset = helper.convert_vecspace_to_blender(offset_data)
            if pkg_version_id == 3 and file_length > 12: file.seek(file_length - 12, 1)
        elif file_name == "xrefs":
            read_xrefs(file, root_ob, pkg_collection, xref_handling, filepath, context)
        else:
            new_obj = read_geometry_file(file, file_name, root_ob, pkg_collection)
            if new_obj is not None: imported_objects.append((file_name, new_obj))

    file.close()

    # --- LOD FILTERING FALLBACK (PKG2 ONLY) ---
    if not import_lods and allowed_meshes is None:
        print(f"is PKG2 file")
        lod_groups = {}
        
        for original_name, obj in imported_objects:
            base, lod_val = import_helper.get_lod_info(original_name)
            if lod_val < 5: 
                base_lower = base.lower()
                if base_lower not in lod_groups: lod_groups[base_lower] = []
                lod_groups[base_lower].append((lod_val, obj))
        
        for base_lower, group in lod_groups.items():
            if len(group) > 1: 
                max_lod = max([item[0] for item in group])
                for lod_val, obj in group:
                    if lod_val < max_lod:
                        mesh_data = obj.data
                        bpy.data.objects.remove(obj, do_unlink=True)
                        if mesh_data and isinstance(mesh_data, bpy.types.Mesh):
                            bpy.data.meshes.remove(mesh_data, do_unlink=True)

    if origin_placement != 'NONE':
        for original_name, obj in imported_objects:
            # Check if the object was deleted by the LOD fallback step
            try:
                _ = obj.name
                apply_dgbanger_data(original_name, obj, filepath, origin_placement)
            except ReferenceError:
                pass

    if import_bbnd:
        bbnd_path = extract_bbnd_file.find_bbnd(pkg_path)
        if bbnd_path:
            extract_bbnd_file.runs(bbnd_path, None, root_ob, pkg_collection) 
            
    import_misc_mtx(root_ob, pkg_collection)

    if import_headlights:
        import_helper.import_headlight_objs(filepath, root_ob, pkg_collection)

    if import_coordinate_offset and pkg_offset is not None:
        root_ob.location = pkg_offset

    pkg_path = previous_pkg_path 
    print(" done in %.4f sec." % (time.perf_counter() - time1))
    return pkg_collection


def load(operator, context, filepath="", **kwargs):
    is_batch = kwargs.get('is_batch_mode', False)
    
    load_pkg(filepath,
            context,
            import_lods=kwargs.get('import_lods', True),
            import_bbnd=kwargs.get('import_bbnd', True),
            use_roughness_instead_of_specular_two=kwargs.get('use_roughness_instead_of_specular_two', True),
            import_headlights=kwargs.get('import_headlights', True),
            import_coordinate_offset=kwargs.get('import_coordinate_offset', True),
            batch_import_filter=kwargs.get('batch_import_filter', 'NONE'),
            xref_handling=kwargs.get('xref_handling', 'EMPTYS'),
            origin_placement=kwargs.get('origin_placement', 'SKIP_UNRELATED'),
            import_variants=kwargs.get('import_variants', True),
            is_batch_mode=is_batch
            )

    return {'FINISHED'}