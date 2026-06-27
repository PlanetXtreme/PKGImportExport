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
import struct
import os
import pkgimporter.common_helpers as helper

# --- CONSTANTS ---
ATB_ROAD = 0x0
ATB_SIDEWALK = 0x1
ATB_RECTANGLE = 0x2
ATB_SLIVER = 0x3
ATB_CROSSWALK = 0x4
ATB_ROADTRIANGLEFAN = 0x5
ATB_TRIANGLEFAN = 0x6
ATB_FACADEBOUND = 0x7
ATB_DIVIDEDROAD = 0x8
ATB_TUNNEL = 0x9
ATB_TEXTURE = 0xa
ATB_FACADE = 0xb
ATB_ROOFTRIANGLEFAN = 0xc

def runs(operator, context, filepath="", **kwargs):
    """Parses the binary PSDL file and generates Blender objects."""
    
    psdl = {
        'vertices': [],
        'heights': [],
        'textures': [],
        'blocks': []
    }
    
    with open(filepath, 'rb') as f:
        magic = f.read(4).decode('ascii', errors='ignore')
        if magic.startswith("PSD1"): version = 1
        elif magic.startswith("PSD0"): version = 0
        else:
            print(f"Error: Invalid PSDL magic identifier: {magic}")
            return
            
        f.seek(4, 1) # Skip 4 unknown bytes
        
        # 1. READ VERTICES
        n_verts = struct.unpack('<I', f.read(4))[0]
        for _ in range(n_verts):
            raw_vtx = struct.unpack('<fff', f.read(12))
            # Send the game's X, Y, Z directly through our universal helper
            psdl['vertices'].append(helper.convert_vecspace_to_blender(raw_vtx))
            
        # 2. READ HEIGHTS
        # (Heights don't need conversion, they are purely scalar game-Y (Up) values 
        # which will be directly mapped to Blender-Z (Up) during geometry generation!)
        n_heights = struct.unpack('<I', f.read(4))[0]
        for _ in range(n_heights):
            h = struct.unpack('<f', f.read(4))[0]
            psdl['heights'].append(h)
            
        # 3. READ TEXTURES
        n_textures = struct.unpack('<I', f.read(4))[0]
        for _ in range(n_textures - 1):
            n_len = struct.unpack('<B', f.read(1))[0]
            if n_len > 0:
                tex_name = f.read(n_len).decode('ascii', errors='ignore').strip('\x00')
            else:
                tex_name = ""
            psdl['textures'].append(tex_name)
            if version == 1: f.seek(1, 1)
                
        # 4. READ BLOCKS
        n_blocks = struct.unpack('<I', f.read(4))[0]
        _unknown0 = f.read(4)
        n_blocks -= 1 
        
        for i in range(n_blocks):
            block = {'id': i, 'attributes': []}
            
            n_perimeters = struct.unpack('<I', f.read(4))[0]
            n_attributesize = struct.unpack('<I', f.read(4))[0]
            
            f.seek(4 * n_perimeters, 1) 
            target_pos = f.tell() + (2 * n_attributesize)
            
            while f.tell() < target_pos:
                atb_id = struct.unpack('<H', f.read(2))[0]
                
                last = (atb_id >> 7) & 0x1
                b_type = (atb_id >> 3) & 0xF
                subtype = atb_id & 0x7
                
                if b_type > 0xC:
                    f.seek(target_pos)
                    break
                    
                atb = {'type': b_type, 'subtype': subtype, 'verts': []}
                
                if b_type == ATB_ROAD:
                    sections = subtype if subtype else struct.unpack('<H', f.read(2))[0]
                    for _ in range(4 * sections):
                        atb['verts'].append(struct.unpack('<H', f.read(2))[0])
                        
                elif b_type in (ATB_SIDEWALK, ATB_RECTANGLE):
                    sections = subtype if subtype else struct.unpack('<H', f.read(2))[0]
                    for _ in range(2 * sections):
                        atb['verts'].append(struct.unpack('<H', f.read(2))[0])
                        
                elif b_type == ATB_SLIVER:
                    atb['top'], atb['tex_scale'] = struct.unpack('<HH', f.read(4))
                    for _ in range(2):
                        atb['verts'].append(struct.unpack('<H', f.read(2))[0])
                        
                elif b_type == ATB_CROSSWALK:
                    for _ in range(4):
                        atb['verts'].append(struct.unpack('<H', f.read(2))[0])
                        
                elif b_type in (ATB_ROADTRIANGLEFAN, ATB_TRIANGLEFAN):
                    tris = subtype if subtype else struct.unpack('<H', f.read(2))[0]
                    for _ in range(tris + 2):
                        atb['verts'].append(struct.unpack('<H', f.read(2))[0])
                        
                elif b_type == ATB_FACADEBOUND:
                    atb['angle'], atb['top'] = struct.unpack('<HH', f.read(4))
                    for _ in range(2):
                        atb['verts'].append(struct.unpack('<H', f.read(2))[0])
                        
                elif b_type == ATB_DIVIDEDROAD:
                    sections = subtype if subtype else struct.unpack('<H', f.read(2))[0]
                    flags, i_tex, height, val = struct.unpack('<BBBB', f.read(4))
                    atb['i_texture'] = i_tex - 1  
                    for _ in range(6 * sections):
                        atb['verts'].append(struct.unpack('<H', f.read(2))[0])
                        
                elif b_type == ATB_TUNNEL:
                    if subtype: 
                        f.seek(4, 1) 
                        if subtype > 2: f.seek(2, 1) 
                    else:
                        length = struct.unpack('<H', f.read(2))[0]
                        f.seek(8, 1) 
                        n_len = 2 * (length - 4)
                        f.seek(n_len, 1)
                        
                elif b_type == ATB_TEXTURE:
                    tex_ref = struct.unpack('<H', f.read(2))[0]
                    atb['i_texture'] = tex_ref + (256 * subtype) - 1
                    
                elif b_type == ATB_FACADE:
                    atb['bottom'], atb['top'], u, v = struct.unpack('<HHHH', f.read(8))
                    for _ in range(2):
                        atb['verts'].append(struct.unpack('<H', f.read(2))[0])
                        
                elif b_type == ATB_ROOFTRIANGLEFAN:
                    verts = subtype if subtype else struct.unpack('<H', f.read(2))[0]
                    atb['i_height'] = struct.unpack('<H', f.read(2))[0]
                    for _ in range(verts + 1):
                        atb['verts'].append(struct.unpack('<H', f.read(2))[0])
                        
                block['attributes'].append(atb)
            psdl['blocks'].append(block)

    build_blender_geometry(psdl)


def build_blender_geometry(psdl):
    master_coll = bpy.data.collections.new("PSDL_Map")
    bpy.context.scene.collection.children.link(master_coll)
    
    mat_cache = {}
    def get_material(tex_idx):
        if tex_idx < 0 or tex_idx >= len(psdl['textures']): return None
        tex_name = psdl['textures'][tex_idx]
        if tex_name not in mat_cache:
            mat = bpy.data.materials.new(name=f"MAT_{tex_name}")
            mat_cache[tex_name] = mat
        return mat_cache[tex_name]

    for block in psdl['blocks']:
        block_coll = bpy.data.collections.new(f"Block_{block['id']}")
        master_coll.children.link(block_coll)
        current_material = None
        
        for atb in block['attributes']:
            b_type = atb['type']
            
            # 1. TEXTURE CHANGE
            if b_type == ATB_TEXTURE:
                current_material = get_material(atb.get('i_texture', -1))
                continue
                
            verts_raw = atb.get('verts', [])
            if not verts_raw: continue
            
            temp_material = current_material
            if b_type == ATB_DIVIDEDROAD and 'i_texture' in atb:
                temp_material = get_material(atb['i_texture'])
            
            # THE FIX: Sidewalk/Road Endpieces point to Map Origins (0 or 1). 
            # We must skip them so they don't stretch geometry across the map!
            if b_type in (ATB_ROAD, ATB_SIDEWALK):
                if len(verts_raw) == 4 and verts_raw[0] == verts_raw[1] and verts_raw[0] <= 1:
                    continue # Skip Endpiece!
            
            verts = [psdl['vertices'][v_idx] for v_idx in verts_raw]
            faces = []
            name = "Mesh"
            
            # 2. FACADES & WALLS 
            if b_type in (ATB_FACADE, ATB_SLIVER, ATB_FACADEBOUND):
                name = "Facade"
                v1, v2 = verts[0], verts[1]
                
                if b_type == ATB_FACADE:
                    z_bot = psdl['heights'][atb['bottom']]
                    z_top = psdl['heights'][atb['top']]
                else: 
                    z_bot = v1[2] 
                    z_top = psdl['heights'][atb['top']]
                    
                verts = [
                    (v1[0], v1[1], z_bot), (v2[0], v2[1], z_bot),
                    (v2[0], v2[1], z_top), (v1[0], v1[1], z_top)
                ]
                faces = [(0, 1, 2, 3)]
                
            # 3. TRIANGLE FANS
            elif b_type in (ATB_ROADTRIANGLEFAN, ATB_TRIANGLEFAN, ATB_ROOFTRIANGLEFAN):
                name = "TriFan"
                if b_type == ATB_ROOFTRIANGLEFAN:
                    z_roof = psdl['heights'][atb['i_height']]
                    verts = [(v[0], v[1], z_roof) for v in verts]
                    
                for i in range(1, len(verts) - 1):
                    faces.append((0, i, i + 1))
                    
            # 4. MULTI-LANE GRIDS 
            elif b_type in (ATB_ROAD, ATB_SIDEWALK, ATB_RECTANGLE, ATB_DIVIDEDROAD, ATB_CROSSWALK):
                if b_type == ATB_ROAD: 
                    width = 4
                    name = "Road"
                elif b_type == ATB_DIVIDEDROAD: 
                    width = 6
                    name = "DivRoad"
                else: 
                    width = 2
                    name = "Sidewalk"
                    if b_type == ATB_RECTANGLE: name = "Rectangle"
                    if b_type == ATB_CROSSWALK: name = "Crosswalk"

                num_rows = len(verts) // width
                
                for row in range(num_rows - 1):
                    for col in range(width - 1):
                        v0 = (row * width) + col
                        v1 = v0 + 1
                        v2 = v0 + width
                        v3 = v1 + width
                        
                        # Note: If the sidewalk segments look like "bowties" / hourglasses, 
                        # change this to: faces.append((v0, v2, v3, v1))
                        faces.append((v0, v1, v3, v2))
                    
            # 5. MESH CREATION
            if faces:
                mesh = bpy.data.meshes.new(f"{name}_{block['id']}")
                obj = bpy.data.objects.new(f"{name}_{block['id']}", mesh)
                block_coll.objects.link(obj)
                mesh.from_pydata(verts, [], faces)
                mesh.update()
                if temp_material:
                    obj.data.materials.append(temp_material)