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
import re

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def is_ignored_bone(name):
    """Rule 0: Ignore bones with specific keywords"""
    return bool(re.search(r'PLACEMENT|IGNORE', name.upper()))

def get_valid_bone_order(arm_obj):
    order = []
    roots = [b for b in arm_obj.pose.bones if not b.parent]
    
    def traverse(bone):
        if not is_ignored_bone(bone.name):
            order.append(arm_obj.pose.bones[bone.name])
        for child in bone.children: 
            traverse(child)
            
    for r in roots: 
        traverse(r)
    return order

def runs(operator, context, filepath):
    selected_rigs = [obj for obj in context.selected_objects if obj.type == 'ARMATURE']
    selected_rigs.sort(key=lambda r: natural_sort_key(r.name))

    if not selected_rigs:
        operator.report({'ERROR'}, "Please select at least one armature to export!")
        return

    scene = context.scene

    for r_idx, arm_obj in enumerate(selected_rigs):
        # Iterating filename for multiple rig selection
        out_filepath = filepath
        if len(selected_rigs) > 1:
            base, ext = os.path.splitext(filepath)
            out_filepath = f"{base}_{r_idx + 1:04d}{ext}"

        valid_bones = get_valid_bone_order(arm_obj)
        
        # Calculate bounds (Disallow negative frames per requirements)
        action = arm_obj.animation_data.action if arm_obj.animation_data else None
        
        start_f = 0
        end_f = 0
        
        if action:
            a_start, a_end = action.frame_range
            start_f = max(0, int(a_start)) # Force to 0 if negative
            end_f = int(a_end)
            
            # Constrain to the scene constraints if needed
            if scene.use_preview_range:
                start_f = max(start_f, scene.frame_preview_start)
                end_f = min(end_f, scene.frame_preview_end)
            else:
                start_f = max(start_f, scene.frame_start)
                end_f = min(end_f, scene.frame_end)
        else:
            start_f = max(0, scene.frame_start)
            end_f = scene.frame_end
            
        num_frames = max(0, end_f - start_f + 1)
        
        if num_frames == 0:
            operator.report({'WARNING'}, f"No valid frames found for {arm_obj.name}, skipping.")
            continue
            
        # Exporting logic
        with open(out_filepath, 'wb') as f_out:
            # Header: Int1(0=Ped), Int2(NumFrames), Int3(60 FPS/Tick)
            f_out.write(struct.pack('<III', 0, num_frames, 60))
            
            # Padding/Speed details (float 0.0, byte 0x01)
            f_out.write(struct.pack('<fB', 0.0, 1))
            
            # Bake timeline frames
            for f in range(start_f, end_f + 1):
                scene.frame_set(f)
                context.view_layer.update()
                
                # Fetch Root Translation from first valid bone (Invert Map: -X, -Y, +Z)
                if len(valid_bones) > 0:
                    loc = valid_bones[0].location
                    tx, ty, tz = -loc.x, -loc.y, loc.z
                else:
                    tx, ty, tz = 0.0, 0.0, 0.0
                    
                f_out.write(struct.pack('<3f', tx, ty, tz))
                
                #untested, but rigs might work with more bones than 19 (like 99) - requires more testing.
                for b_idx in range(19):
                    if b_idx < len(valid_bones):
                        pb = valid_bones[b_idx]
                        
                        # Invert parsing map: -x, -y, z
                        # Using rotation_euler allows exactly capturing what the user animated
                        euler = pb.rotation_euler
                        rx, ry, rz = -euler.x, -euler.y, euler.z
                    else:
                        rx, ry, rz = 0.0, 0.0, 0.0
                        
                    f_out.write(struct.pack('<3f', rx, ry, rz))

        operator.report({'INFO'}, f"Successfully exported: {os.path.basename(out_filepath)}")