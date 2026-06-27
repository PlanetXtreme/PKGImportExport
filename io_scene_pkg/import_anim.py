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
from mathutils import Vector, Euler

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def is_ignored_bone(name):
    """Ignore bones with specific keywords"""
    return bool(re.search(r'PLACEMENT|IGNORE', name.upper()))

def get_valid_bone_order(arm_obj):
    order = []
    roots = [b for b in arm_obj.pose.bones if not b.parent]
    
    def traverse(bone):
        if not is_ignored_bone(bone.name):
            order.append(bone.name)
        for child in bone.children: 
            traverse(child)
            
    for r in roots: 
        traverse(r)
    return order

def read_age_engine_animation(filepath):
    if not os.path.exists(filepath):
        return None

    with open(filepath, 'rb') as f:
        data = f.read()
        
    if len(data) < 12:
        return None

    header_int1, header_int2, header_int3 = struct.unpack_from('<III', data, 0)
    anim_data = {'frames': []}

    if header_int1 == 0:
        num_frames = header_int2
        num_bones = 19
        offset = 17 
        frame_stride = 240
    else:
        num_frames = header_int1
        num_bones = header_int2 
        offset = 69 
        frame_stride = 144

    for frame in range(num_frames):
        if offset + frame_stride > len(data):
            break
            
        # First 12 bytes of the frame block = Root Translation
        root_loc = struct.unpack_from('<3f', data, offset)
        read_offset = offset + 12 
            
        bones = []
        for _ in range(num_bones):
            euler = struct.unpack_from('<3f', data, read_offset)
            read_offset += 12
            bones.append(euler)
            
        anim_data['frames'].append({
            'root_loc': root_loc,
            'bones': bones
        })
        
        offset += frame_stride

    return anim_data

def apply_animations_to_rig(filepaths, arm_obj):
    """Applies a list of animations sequentially to the same rig"""
    BONE_ORDER = get_valid_bone_order(arm_obj)
    
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode='POSE')

    if arm_obj.animation_data is None: 
        arm_obj.animation_data_create()
        
    action_name = os.path.basename(filepaths[0]) if len(filepaths) == 1 else f"BatchAnim_{arm_obj.name}"
    action = bpy.data.actions.new(name=action_name)
    arm_obj.animation_data.action = action

    pose_bones = []
    for b_name in BONE_ORDER:
        pb = arm_obj.pose.bones.get(b_name)
        if pb: pb.rotation_mode = 'XYZ'
        pose_bones.append(pb)

    current_frame = 1 # Start at frame 1

    for filepath in filepaths:
        anim_data = read_age_engine_animation(filepath)
        if not anim_data or len(anim_data['frames']) == 0:
            continue
            
        safe_count = min(len(anim_data['frames'][0]['bones']), len(pose_bones))
        
        for f_idx, frame_data in enumerate(anim_data['frames']):
            blender_frame = current_frame + f_idx
            
            tx, ty, tz = frame_data['root_loc']
            
            # Apply Root Translation to the first valid bone (Pelvis)
            if pose_bones[0]:
                pose_bones[0].location = Vector((-tx, -ty, tz))
                pose_bones[0].keyframe_insert(data_path="location", frame=blender_frame)
            
            for b_idx in range(safe_count):
                if not pose_bones[b_idx]: continue
                rx, ry, rz = frame_data['bones'][b_idx]
                
                # Apply rotation map
                pose_bones[b_idx].rotation_euler = Euler((-rx, -ry, rz), 'XYZ')
                pose_bones[b_idx].keyframe_insert(data_path="rotation_euler", frame=blender_frame)
        
        # 2 blocks of empty, unanimated space in between sequential animations is nice
        current_frame += len(anim_data['frames']) + 2

    bpy.ops.object.mode_set(mode='OBJECT')

def runs(operator, context, filepaths):
    filepaths.sort(key=natural_sort_key)
    
    selected_rigs = [obj for obj in context.selected_objects if obj.type == 'ARMATURE']
    selected_rigs.sort(key=lambda r: natural_sort_key(r.name))

    if not selected_rigs:
        operator.report({'ERROR'}, "Please select at least one armature first!")
        return
        
    num_rigs = len(selected_rigs)
    num_anims = len(filepaths)

    # Framerate @ 30 matches the playback speed in-game, regardless of what the file header says the framerate of the imported/exported animation is
    bpy.context.scene.render.fps = 30

    if num_rigs == 1:
        operator.report({'INFO'}, f"Applying {num_anims} animations sequentially to rig.")
        apply_animations_to_rig(filepaths, selected_rigs[0])
        
    elif num_rigs == num_anims:
        for idx in range(num_rigs):
            apply_animations_to_rig([filepaths[idx]], selected_rigs[idx])
            
    else:
        if num_rigs > num_anims:
            operator.report({'WARNING'}, f"More rigs ({num_rigs}) than animations ({num_anims}). Ignoring later rigs.")
            for idx in range(num_anims):
                apply_animations_to_rig([filepaths[idx]], selected_rigs[idx])
                
        elif num_anims > num_rigs and num_rigs >= 2:
            operator.report({'WARNING'}, f"More anims ({num_anims}) than rigs ({num_rigs}). Applying all animations to first rig only.")
            apply_animations_to_rig(filepaths, selected_rigs[0])

    operator.report({'INFO'}, "Animation(s) successfully applied!")