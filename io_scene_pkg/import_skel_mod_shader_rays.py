# ##### BEGIN LICENSE BLOCK #####
#
# This program is licensed under Creative Commons BY-NC-SA:
# https://creativecommons.org/licenses/by-nc-sa/3.0/
#
# Created by PlanetXtreme, 2026
#
# ##### END LICENSE BLOCK #####


import bpy
import bmesh
import os
import struct
import math
from mathutils import Vector, Matrix

from . import common_helpers
from . import import_helper
from . import binary_helper
from .shader_set import ShaderSet, Shader

def convert_axis(x, y, z):
    return common_helpers.convert_vecspace_to_blender((x, y, z))

def standardize_face(v0, v1, v2):
    if v0 < v1 and v0 < v2: return (v0, v1, v2)
    if v1 < v0 and v1 < v2: return (v1, v2, v0)
    return (v2, v0, v1)

def safe_vector(v):
    if not (math.isfinite(v[0]) and math.isfinite(v[1]) and math.isfinite(v[2])):
        return (0.0, 0.0, 1.0)
    length = math.sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2])
    if length < 0.00001 or not math.isfinite(length):
        return (0.0, 0.0, 1.0)
    return (float(v[0]/length), float(v[1]/length), float(v[2]/length))

def get_or_create_circle_widget():
    widget_name = "WIDGET_ROOOOT_SHAPE"
    if widget_name in bpy.data.objects:
        return bpy.data.objects[widget_name]
    
    mesh = bpy.data.meshes.new(widget_name)
    obj = bpy.data.objects.new(widget_name, mesh)
    
    try:
        bpy.context.scene.collection.objects.link(obj)
    except Exception:
        pass 
        
    bm = bmesh.new()
    
    # Rotate on X axis to match ground plane-y-ness
    rot_matrix = Matrix.Rotation(math.radians(90.0), 4, 'X')
    
    bmesh.ops.create_circle(
        bm, 
        cap_ends=False, 
        radius=1.0, 
        segments=16, 
        matrix=rot_matrix
    )
    
    bm.to_mesh(mesh)
    bm.free()
    
    # Hide the widget itself from views
    obj.hide_viewport = True
    obj.hide_render = True
    obj.hide_set(True)
    return obj

def create_hitbox(arm_obj, bone_name, connected_name, size, hit_group, bones_dict):
    b1_pos = Vector(bones_dict[bone_name]['global_pos'])
    b2_pos = Vector(bones_dict[connected_name]['global_pos'])
    
    length = (b2_pos - b1_pos).length
    radius = max(size[0], size[1])
    if radius < 0.001: 
        radius = 0.05
        
    if length < 0.001 or hit_group == 0:
        return
        
    mesh = bpy.data.meshes.new(name=f"Hitbox_{bone_name}")
    obj = bpy.data.objects.new(f"Hitbox_{bone_name}_Gr{hit_group}", mesh)
    bpy.context.collection.objects.link(obj)
    
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=8, radius1=radius, radius2=radius, depth=length)
    
    direction = (b2_pos - b1_pos).normalized()
    rot_matrix = direction.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    loc_matrix = Matrix.Translation((b1_pos + b2_pos) / 2.0)
    
    bm.transform(loc_matrix @ rot_matrix)
    bm.to_mesh(mesh)
    bm.free()
    
    obj.parent = arm_obj
    mod = obj.modifiers.new(name="Armature", type='ARMATURE')
    mod.object = arm_obj
    
    vg = obj.vertex_groups.new(name=bone_name)
    vg.add(range(len(mesh.vertices)), 1.0, 'REPLACE')
    
    obj.display_type = 'WIRE'
    obj.color = (1.0, 0.0, 0.0, 1.0)


def runs(context, mod_path, skel_path, operator):
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bones = []
    bone_dict = {}
    arm_obj = None
    
    # --- 1. SKELETON PARSING ---
    if skel_path and os.path.exists(skel_path):
        with open(skel_path, 'r') as f:
            tokens = f.read().replace('{', ' { ').replace('}', ' } ').split()
            
        stack = []
        i = 0
        while i < len(tokens):
            if tokens[i] == 'bone':
                bone_name = tokens[i+1]
                parent_idx = stack[-1] if stack else -1
                bone_idx = len(bones)
                bone_data = {'name': bone_name, 'parent': parent_idx, 'children': [], 'global_pos': (0,0,0)}
                bones.append(bone_data)
                bone_dict[bone_name] = bone_data
                if parent_idx != -1: bones[parent_idx]['children'].append(bone_idx)
                i += 2
            elif tokens[i] == '{':
                stack.append(bone_idx)
                i += 1
            elif tokens[i] == '}':
                stack.pop()
                i += 1
            elif tokens[i] == 'offset':
                ox, oy, oz = convert_axis(float(tokens[i+1]), float(tokens[i+2]), float(tokens[i+3]))
                if bones[-1]['parent'] != -1:
                    px, py, pz = bones[bones[-1]['parent']]['global_pos']
                    bones[-1]['global_pos'] = (px + ox, py + oy, pz + oz)
                else:
                    bones[-1]['global_pos'] = (ox, oy, oz)
                i += 4
            else:
                i += 1

    # --- 2. GENERATE ARMATURE ---
    if bones:
        arm_data = bpy.data.armatures.new(name=os.path.basename(skel_path))
        arm_obj = bpy.data.objects.new(os.path.basename(skel_path), arm_data)
        bpy.context.collection.objects.link(arm_obj)
        arm_obj.show_in_front = True
        
        bpy.context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode='EDIT')
        
        # ---> CREATE NEW ROOT BONE <---
        root_bone_name = "ROOOOT_PLACEMENT_IGNORED_FOR_EXPORT"
        root_eb = arm_data.edit_bones.new(root_bone_name)
        
        root_eb.head = (0.0, 0.0, 0.0)
        root_eb.tail = (0.0, 0.0, 0.5)
        root_eb.roll = 0.0 
        
        edit_bones = []
        for i, b in enumerate(bones):
            eb = arm_data.edit_bones.new(b['name'])
            eb.head = b['global_pos']
            edit_bones.append(eb)
            
        def rotate_bone_tail(eb_target, angle_degrees, axis_str):
            vec = eb_target.tail - eb_target.head
            rot_mat = Matrix.Rotation(math.radians(angle_degrees), 3, axis_str)
            eb_target.tail = eb_target.head + (rot_mat @ vec)

        for i, b in enumerate(bones):
            eb = edit_bones[i]
            bone_name = b['name'].lower()
            
            if b['parent'] != -1: 
                eb.parent = edit_bones[b['parent']]
            else:
                eb.parent = root_eb
            
            eb.use_connect = False 
            
            if len(b['children']) > 0:
                child_center = Vector((0.0, 0.0, 0.0))
                for child_idx in b['children']:
                    child_center += Vector(bones[child_idx]['global_pos'])
                child_center /= len(b['children'])
                eb.tail = child_center
            else:
                if b['parent'] != -1:
                    p_pos = Vector(bones[b['parent']]['global_pos'])
                    c_pos = Vector(b['global_pos'])
                    direction = (c_pos - p_pos).normalized()
                    if direction.length < 0.001:
                        direction = Vector((0, 0, 1))
                    eb.tail = c_pos + (direction * 0.1)
                else:
                    eb.tail = Vector(b['global_pos']) + Vector((0, 0, 0.1))
                    
            eb.roll = 0.0 #default

            if 'clavicle_r' in bone_name:
                eb.roll = math.radians(180)
            elif 'clavicle_l' in bone_name :
                eb.roll = math.radians(-180)
            elif 'wrist_r' in bone_name:
                rotate_bone_tail(eb, 90, 'Y')
                eb.roll = math.radians(90)
            elif 'wrist_l' in bone_name:
                rotate_bone_tail(eb, -90, 'Y')
                eb.roll = math.radians(-90)
            elif 'ankle_r' in bone_name:
                rotate_bone_tail(eb, -90, 'X')
                eb.roll = math.radians(180)
            elif 'ankle_l' in bone_name:
                rotate_bone_tail(eb, -90, 'X')
                eb.roll = math.radians(-180)

        bpy.ops.object.mode_set(mode='OBJECT')
        arm_data.display_type = 'OCTAHEDRAL'
        
        rot_val = getattr(operator, "import_rotate_filter", 'NONE')
        angle_rad = 0.0
        if rot_val == 'PLUS_NINTY': angle_rad = math.radians(90)
        elif rot_val == 'PLUS_ONE_EIGHTY': angle_rad = math.radians(180)
        elif rot_val == 'MINUS_NINTY': angle_rad = math.radians(-90)

        if root_bone_name in arm_obj.pose.bones:
            pose_root = arm_obj.pose.bones[root_bone_name]
            pose_root.custom_shape = get_or_create_circle_widget()
            pose_root.rotation_mode = 'XYZ'
            pose_root.rotation_euler[1] = angle_rad

        # --- 3. HITBOXES (.rays OR Default) ---
        if getattr(operator, "import_hitboxes", False):
            rays_path = os.path.splitext(skel_path if skel_path else mod_path)[0] + ".rays"
            if os.path.exists(rays_path):
                print(f"[Import] Found .rays file! Importing Hitboxes...")
                with open(rays_path, 'r') as f:
                    lines = [l.strip() for l in f.readlines() if l.strip()]
                    num_rays = int(lines[0])
                    for i in range(1, num_rays + 1):
                        parts = lines[i].split()
                        size = (float(parts[0]), float(parts[1]), float(parts[2]))
                        conn_idx = int(parts[3])
                        hit_group = int(parts[4])
                        
                        if i-1 < len(bones) and conn_idx < len(bones):
                            create_hitbox(arm_obj, bones[i-1]['name'], bones[conn_idx]['name'], size, hit_group, bone_dict)
                            
            elif getattr(operator, "default_hitboxes", False):
                print(f"[Import] No .rays file. Generating Default Hitboxes...")
                for i, b in enumerate(bones):
                    if b['parent'] != -1:
                        create_hitbox(arm_obj, bones[b['parent']]['name'], b['name'], (0.05, 0.05, 0), 1, bone_dict)

    # --- 4. MESH PARSING (.mod) ---
    if not mod_path or not os.path.exists(mod_path): return 
    
    with open(mod_path, 'r') as f: lines = f.readlines()
    verts, normals, uvs = [], [], []
    materials, packets = [], []
    current_mtl, current_packet = None, None

    for line in lines:
        line = line.strip()
        if not line: continue
        parts = line.split()
        cmd = parts[0]

        if cmd == 'v': 
            verts.append(convert_axis(float(parts[1]), float(parts[2]), float(parts[3])))
        elif cmd == 'n': 
            raw_n = convert_axis(float(parts[1]), float(parts[2]), float(parts[3]))
            normals.append(safe_vector(raw_n))
        elif cmd == 't1': 
            uvs.append((float(parts[1]), 1.0 - float(parts[2])))
        elif cmd == 'mtl':
            current_mtl = {'name': parts[1].replace('{', ''), 'packets': 1, 'diffuse': (0.8, 0.8, 0.8, 1.0), 'texture': 'white'}
            materials.append(current_mtl)
        elif cmd == 'packets:' and current_mtl: current_mtl['packets'] = int(parts[1])
        elif cmd == 'diffuse:' and current_mtl: current_mtl['diffuse'] = (float(parts[1]), float(parts[2]), float(parts[3]), 1.0)
        elif cmd == 'texture:' and current_mtl: current_mtl['texture'] = parts[2]
        elif cmd == 'packet':
            current_packet = {'adjs': [], 'faces': [], 'mtx': []}
            packets.append(current_packet)
        elif cmd == 'adj' and current_packet:
            current_packet['adjs'].append({'v': int(parts[1]), 'n': int(parts[2]), 't1': int(parts[4]), 'mtx_idx': int(parts[6])})
        elif cmd == 'mtx' and current_packet:
            current_packet['mtx'] = [int(x) for x in parts[1:]]
        elif cmd in ('str', 'stp') and current_packet:
            indices = [int(x) for x in parts[2:2+int(parts[1])]]
            clockwise = (cmd == 'stp')
            for v_idx in range(len(indices) - 2):
                i1, i2, i3 = indices[v_idx], indices[v_idx+1], indices[v_idx+2]
                if not (i1 == i2 or i1 == i3 or i2 == i3): 
                    current_packet['faces'].append((i2, i1, i3) if clockwise else (i1, i2, i3))
                    clockwise = not clockwise

    # --- 5. BONE MAPPING & MESH CREATION ---
    vertex_bone_map = {}
    for packet in packets:
        for adj in packet['adjs']:
            if 'mtx' in packet and adj['mtx_idx'] < len(packet['mtx']):
                vertex_bone_map[adj['v']] = packet['mtx'][adj['mtx_idx']]

    if 'bones' in locals() and bones:
        for i in range(len(verts)):
            bone_idx = vertex_bone_map.get(i, 0)
            if bone_idx < len(bones):
                bx, by, bz = bones[bone_idx]['global_pos']
                vx, vy, vz = verts[i]
                verts[i] = (vx + bx, vy + by, vz + bz)

    blender_faces = []
    face_map = {} 
    
    mtl_idx, packets_consumed = 0, 0
    num_verts = len(verts)
    
    for packet in packets:
        if mtl_idx < len(materials) and packets_consumed >= materials[mtl_idx]['packets']:
            mtl_idx += 1; packets_consumed = 0
            
        for f in packet['faces']:
            adj0, adj1, adj2 = packet['adjs'][f[0]], packet['adjs'][f[1]], packet['adjs'][f[2]]
            v0, v1, v2 = adj0['v'], adj1['v'], adj2['v']
            
            if v0 >= num_verts or v1 >= num_verts or v2 >= num_verts: continue
                
            std_face = standardize_face(v0, v1, v2)
            
            if std_face not in face_map:
                blender_faces.append((v0, v1, v2))
                face_map[std_face] = ((adj0, adj1, adj2), mtl_idx)
                
        packets_consumed += 1

    mesh = bpy.data.meshes.new(name=os.path.basename(mod_path))
    mod_obj = bpy.data.objects.new(os.path.basename(mod_path), mesh)
    bpy.context.collection.objects.link(mod_obj)
    
    mesh.from_pydata(verts, [], blender_faces)
    mesh.validate(clean_customdata=False) 
    mesh.update()

    # --- 6. ADVANCED MATERIALS & TEXTURES ---
    
    # Check for a binary .shaders file to override the text colors
    external_shaders = {}
    if getattr(operator, "force_shader_override", False):
        shaders_path = os.path.splitext(mod_path)[0] + ".shaders"
        if os.path.exists(shaders_path):
            try:
                with open(shaders_path, 'rb') as f:
                    shader_set = ShaderSet(f) # Uses your modular shader_set.py parser!
                    if shader_set.variants:
                        for sh in shader_set.variants[0]:
                            if sh.name:
                                external_shaders[sh.name.lower()] = sh
                print(f"[Import] Loaded external .shaders overrides!")
            except Exception as e:
                print(f"[Import] Failed to parse .shaders: {e}")

    for i, m in enumerate(materials):
        mat = bpy.data.materials.new(name=m['name'])
        
        # Build an abstract Shader object
        shader = Shader()
        shader.name = m['texture'] if m.get('texture') and m['texture'] != 'white' else None
        
        tex_key = shader.name.lower() if shader.name else ""
        
        if tex_key in external_shaders:
            # Override with parsed binary variables
            ext_sh = external_shaders[tex_key]
            shader.diffuse_color = ext_sh.diffuse_color
            shader.ambient_color = ext_sh.ambient_color
            shader.specular_color = ext_sh.specular_color
            shader.emissive_color = ext_sh.emissive_color
            shader.shininess = ext_sh.shininess
        else:
            # Use data parsed directly from the text .mod file
            # Automatically push it through your binary_helper Linear curve fix
            r = binary_helper.srgb_to_linear(m['diffuse'][0])
            g = binary_helper.srgb_to_linear(m['diffuse'][1])
            b = binary_helper.srgb_to_linear(m['diffuse'][2])
            a = m['diffuse'][3]
            
            shader.diffuse_color = [r, g, b, a]
            
            # Text values don't provide these, provide fallbacks
            shader.ambient_color = [1, 1, 1, 1]
            shader.emissive_color = [0, 0, 0, 0]
            shader.specular_color = [0, 0, 0, 0]
            shader.shininess = 0.5 
            
        # Push the Shader object to your universal material builder!
        import_helper.populate_material(mtl=mat, shader=shader, pkg_path=mod_path, use_roughness_instead=True)
        mod_obj.data.materials.append(mat)


    # --- 7. UVS & NORMALS ---
    if len(mesh.loops) > 0:
        uv_layer = mesh.uv_layers.new(name="UVMap")
        mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
        loop_normals = [(0.0, 0.0, 1.0)] * len(mesh.loops)

        for poly in mesh.polygons:
            std_face = standardize_face(poly.vertices[0], poly.vertices[1], poly.vertices[2])
            lookup_data = face_map.get(std_face)
            
            if not lookup_data: continue
            adjs, mat_idx = lookup_data
            
            poly.material_index = mat_idx
                
            for loop_idx, loop_v_idx in zip(poly.loop_indices, poly.vertices):
                adj = next((a for a in adjs if a['v'] == loop_v_idx), None)
                if not adj: continue
                
                if adj['t1'] < len(uvs): uv_layer.data[loop_idx].uv = uvs[adj['t1']]
                if adj['n'] < len(normals): loop_normals[loop_idx] = normals[adj['n']]

        final_safe_normals = []
        for n in loop_normals:
            if not (math.isfinite(n[0]) and math.isfinite(n[1]) and math.isfinite(n[2])):
                final_safe_normals.append((0.0, 0.0, 1.0))
            else:
                final_safe_normals.append((float(n[0]), float(n[1]), float(n[2])))

        try: mesh.use_auto_smooth = True
        except AttributeError: pass
        mesh.normals_split_custom_set(final_safe_normals)
        mesh.update()
    
    # --- 8. RIG BINDING ---
    if 'arm_obj' in locals() and arm_obj and len(mesh.vertices) > 0:
        for b in bones: 
            mod_obj.vertex_groups.new(name=b['name'])
            
        for v_idx, b_idx in vertex_bone_map.items():
            if b_idx < len(bones) and v_idx < len(mesh.vertices):
                mod_obj.vertex_groups[bones[b_idx]['name']].add([v_idx], 1.0, 'REPLACE')

        arm_mod = mod_obj.modifiers.new(name="Armature", type='ARMATURE')
        arm_mod.object = arm_obj
        mod_obj.parent = arm_obj