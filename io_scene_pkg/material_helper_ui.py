 # ##### BEGIN LICENSE BLOCK #####
#
# This program is licensed under Creative Commons BY-NC-SA:
# https://creativecommons.org/licenses/by-nc-sa/3.0/
#
# Created by Dummiesman, 2016-2020
#
# ##### END LICENSE BLOCK #####

import bpy, mathutils

from bpy.types import (Panel,
                       Menu,
                       Operator,
                       PropertyGroup,
                       UIList
                       )
                       
from bpy.props import (IntProperty,
                       BoolProperty,
                       StringProperty,
                       CollectionProperty,
                       PointerProperty)

# -------------------------------------------------------------------
#   Operators
# -------------------------------------------------------------------

def build_angel_material_nodes(mtl, image=None, diffuse_color=(1.0, 1.0, 1.0, 1.0), emissive_color=(0.0, 0.0, 0.0, 1.0), shininess=0.0, use_roughness_instead=True, is_substituted_tex=False, use_alpha_hash=True, force_node_creation=False):
    """Centralized function to build the Angel material node setup."""
    mtl.use_nodes = True
    mtl.use_backface_culling = True
    
    nodes = mtl.node_tree.nodes
    links = mtl.node_tree.links
    
    bsdf = nodes.get("Principled BSDF")
    if not bsdf:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.name = "Principled BSDF"

    bsdf.location = mathutils.Vector((-100.0, 120.0))
    
    # Handle Blender 4.0+ Node Changes seamlessly
    emission_key = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
    specular_key = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"

    bsdf.inputs['Base Color'].default_value = diffuse_color
    bsdf.inputs[emission_key].default_value = emissive_color

    if use_roughness_instead:
        # Invert shininess back to roughness (Shininess 1.0 -> Roughness 0.0)
        roughness_val = min(max(1.0 - shininess, 0.0), 1.0)
        bsdf.inputs['Roughness'].default_value = roughness_val
        bsdf.inputs[specular_key].default_value = 0.5 
    else:
        bsdf.inputs[specular_key].default_value = shininess
        bsdf.inputs['Roughness'].default_value = 0.0

    # Viewport display fallback properties
    mtl.diffuse_color = diffuse_color
    mtl.specular_intensity = 0.1
    mtl.metallic = shininess

    mtl_alpha = diffuse_color[3]
    tex_depth = image.depth if image else 0
    is_emission_mask = image.get('is_emission_mask', False) if image else False
    
    # Determine if we should build the texture nodes
    create_tex_nodes = (image is not None) or force_node_creation

    if create_tex_nodes:
        # 1. Create Image Node
        tex_image_node = nodes.new('ShaderNodeTexImage')
        tex_image_node.location = mathutils.Vector((-740.0, 20.0))
        if image:
            tex_image_node.image = image
            if is_substituted_tex:
                tex_image_node.interpolation = "Closest"
                
        # 2. Setup Diffuse
        blend_node_diff = nodes.new('ShaderNodeMixRGB')
        blend_node_diff.inputs['Color2'].default_value = diffuse_color
        blend_node_diff.inputs['Fac'].default_value = 1.0
        blend_node_diff.blend_type = 'MULTIPLY'
        blend_node_diff.label = "Diffuse Color"
        blend_node_diff.location = mathutils.Vector((-460.0, 160.0))
        
        links.new(blend_node_diff.inputs['Color1'], tex_image_node.outputs['Color'])
        links.new(bsdf.inputs['Base Color'], blend_node_diff.outputs['Color'])

        # 3. Setup Emission
        blend_node_emis = nodes.new('ShaderNodeMixRGB')
        blend_node_emis.inputs['Color2'].default_value = emissive_color
        blend_node_emis.inputs['Fac'].default_value = 1.0
        blend_node_emis.blend_type = 'MULTIPLY'
        blend_node_emis.label = "Emission Color"
        blend_node_emis.location = mathutils.Vector((-460.0, -20.0))
        
        links.new(blend_node_emis.inputs['Color1'], tex_image_node.outputs['Color'])

        is_emissive_material = sum(emissive_color[:3]) > 0.001
        
        # Emission Mask Multiply
        if is_emission_mask:
            blend_node_emis.inputs['Color2'].default_value = diffuse_color # Force to diffuse
            mask_node = nodes.new('ShaderNodeMixRGB')
            mask_node.blend_type = 'MULTIPLY'
            mask_node.inputs['Fac'].default_value = 1.0
            mask_node.label = "Apply Emission Mask"
            mask_node.location = mathutils.Vector((-300.0, -20.0))
            
            links.new(mask_node.inputs['Color1'], blend_node_emis.outputs['Color'])
            links.new(mask_node.inputs['Color2'], tex_image_node.outputs['Alpha'])
            links.new(bsdf.inputs[emission_key], mask_node.outputs['Color'])
        else:
            if is_emissive_material:
                blend_node_emis.inputs['Color2'].default_value = diffuse_color
            links.new(bsdf.inputs[emission_key], blend_node_emis.outputs['Color'])

        if 'Emission Strength' in bsdf.inputs:
            bsdf.inputs['Emission Strength'].default_value = 1.0

        # 4. Setup Alpha Logic
        if not is_emission_mask:
            blend_node_alpha = nodes.new('ShaderNodeMath')
            blend_node_alpha.inputs[0].default_value = mtl_alpha
            blend_node_alpha.operation = 'MULTIPLY'
            blend_node_alpha.label = "Alpha"
            blend_node_alpha.location = mathutils.Vector((-460.0, -200.0))
            
            links.new(blend_node_alpha.inputs[1], tex_image_node.outputs['Alpha'])
            links.new(bsdf.inputs['Alpha'], blend_node_alpha.outputs[0])
        else:
            # If it's an emission mask, it does not dictate transparency
            bsdf.inputs['Alpha'].default_value = mtl_alpha
            
    else:
        # No texture nodes requested, just set standard Alpha
        bsdf.inputs['Alpha'].default_value = mtl_alpha

    # 5. Global Blend Mode Assignments
    if is_emission_mask:
        tex_depth = 24 
        
    if mtl_alpha < 1 or tex_depth == 32:
        mtl.blend_method = 'HASHED' if use_alpha_hash else 'BLEND'

class CreateMaterialSetupOperator(Operator):
    """Creates a full node setup that lets you set up all aspects of a PKG shader."""
    bl_idname = "angel.create_material_setup"
    bl_label = "Create Material Setup"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
    
    def execute(self, context):
        ob = context.active_object
        if ob is None or ob.active_material is None:
            self.report({'ERROR'}, "No active material found.")
            return {'CANCELLED'}
            
        material = ob.active_material
        is_mat_modified = False
        
        # check if it's made by Blender, or touched by the user
        if len(material.node_tree.nodes) != 2:
            is_mat_modified = True
        for node in material.node_tree.nodes:
            if node.type != "BSDF_PRINCIPLED" and node.type != "OUTPUT_MATERIAL":
                is_mat_modified = True
        
        if is_mat_modified:
            self.report({'ERROR'}, "This material has been modified. This operation only works on brand new materials.")
            return {'CANCELLED'}
            
        # Delegate building to the shared function!
        # force_node_creation=True ensures the blank Image Texture and Mix nodes spawn
        build_angel_material_nodes(material, force_node_creation=True)
        
        return {'FINISHED'}
        
# -------------------------------------------------------------------	
#   Drawing	
# -------------------------------------------------------------------   

class ANGEL_PT_MaterialHelperPanel(bpy.types.Panel):
    bl_label = "Angel Tools: Quick Setup"	
    bl_idname = "OBJECT_PT_material_helper_panel"	
    bl_space_type = "PROPERTIES"   	
    bl_region_type = "WINDOW"	
    bl_context = "material"	
    bl_category = "Angel Tools" 

    @classmethod	
    def poll(self,context):
        ob = context.active_object
        mat = ob.active_material
        return mat is not None
        
    def draw(self, context):
        layout = self.layout
        layout.operator("angel.create_material_setup")
        
# -------------------------------------------------------------------	
#   Register & Unregister	
# -------------------------------------------------------------------

classes = (	
    CreateMaterialSetupOperator,
    ANGEL_PT_MaterialHelperPanel
)	

def register():        	
    from bpy.utils import register_class	
    for cls in classes:	
        register_class(cls)	


def unregister():	
    from bpy.utils import unregister_class	
    for cls in reversed(classes):	
        unregister_class(cls)	

