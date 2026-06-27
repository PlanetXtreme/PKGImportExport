 # ##### BEGIN LICENSE BLOCK #####
#
# This program is licensed under Creative Commons BY-NC-SA:
# https://creativecommons.org/licenses/by-nc-sa/3.0/
#
# Created by Dummiesman, 2016-2020
#
# ##### END LICENSE BLOCK #####

import bpy
import os
import json

from bpy.props import (
        BoolProperty,
        EnumProperty,
        FloatProperty,
        StringProperty,
        CollectionProperty,
        IntProperty,
        PointerProperty
        )
from bpy_extras.io_utils import (
        ImportHelper,
        ExportHelper,
        )

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "pkg_addon_settings.json")

def load_settings():
    """Load settings from JSON file, return empty dict if it fails/doesn't exist."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Failed to load PKG settings: {e}")
    return {}

def save_settings(new_settings):
    """Update and save settings to the JSON file."""
    settings = load_settings()
    settings.update(new_settings)
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        print(f"Failed to save PKG settings: {e}")

user_settings = load_settings()

class ImportTEXMenu(bpy.types.Menu):
    bl_idname = "ANGEL_MT_import_tex_menu"
    bl_label = "Angel QUICK Tools"

    def draw(self, context):
        layout = self.layout
        #layout.operator("realize_ref_choose.xref")
        #layout.operator("realize_ref_quick.xref")
        #layout.operator("export_psdl.psdl")
        #layout.operator("export_inst.inst")
        #layout.operator("export_bai.bai")
        #layout.operator("export_pkg.pkg")
        #layout.operator("export_bbnd.bbnd")
        #layout.operator("export_anim.anim")
        layout.operator("import_texture.tex")
        layout.operator("export_texture.tex")
        
    def menu_draw(self, context):
        self.layout.menu("ANGEL_MT_import_tex_menu")


class ImportTEX(bpy.types.Operator, ImportHelper):
    """ Convert .tex image to Blender Shader """
    bl_idname = "import_texture.tex"
    bl_label = 'Import TEX Image'
    bl_options = {'UNDO'}

    filename_ext = ".tex"
    filter_glob: StringProperty(default="*.tex", options={'HIDDEN'},)

    files: CollectionProperty(
        name="File Path",
        type=bpy.types.OperatorFileListElement,
    )
    directory: StringProperty(
        subtype='DIR_PATH',
    )
    
    def draw(self, context):
        layout = self.layout
        box = layout.box()
        #box.label(text="Reminder:", icon='INFO')
        #box.label(text="Exporting to TGA also works.")
        #box.label(text="But TGA doesn't support certain")
        #box.label(text="transparency/emission customizations.")
        #box.label(text="I reccomend using XNConvert for TGA.")

    def invoke(self, context, event):
        settings = load_settings()
        tex_path = settings.get("path_i_tex", "")

        if tex_path and os.path.exists(tex_path):
            if not tex_path.endswith(os.sep) and not tex_path.endswith(("/", "\\")):
                tex_path += os.sep
            self.filepath = tex_path

        return super().invoke(context, event)

    def execute(self, context):
        from pkgimporter.tex_file import TEXFile
        
        # IMPORT YOUR SHARED FUNCTION HERE
        # Adjust the dot import depending on your addon's folder structure
        from .material_helper_ui import build_angel_material_nodes

        save_settings({"path_i_tex": self.directory})

        # Loop through all selected files
        for file_elem in self.files:
            filepath = os.path.join(self.directory, file_elem.name)
            imagename = bpy.path.display_name_from_filepath(filepath)
            
            # Import Texture File
            tex = TEXFile(filepath)
            blender_image = tex.to_blender_image(imagename)

            # Create the Material
            material = bpy.data.materials.new(name=imagename)
            material.use_nodes = True
            
            # Pass the material & the image so it auto-links
            build_angel_material_nodes(material, image=blender_image)
            
            return {'FINISHED'}

class RealizeXREF_Choose(bpy.types.Operator, ImportHelper):
    """ Convert Reference into editable model """
    bl_idname = "realize_xref"
    bl_label = 'Realize XREF - Choose'
    bl_options = {'UNDO'}

    filename_ext = ".pkg"
    filter_glob: StringProperty(default="*.pkg", options={'HIDDEN'},)

    files: CollectionProperty(
        name="File Path",
        type=bpy.types.OperatorFileListElement,
    )
    directory: StringProperty(
        subtype='DIR_PATH',
    )
    
    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Reminder:", icon='INFO')
        box.label(text="Choose the directory the target pkg")
        box.label(text="resides in. The Importer will do the rest.")

    def invoke(self, context, event):
        settings = load_settings()
        xref_path = settings.get("path_r_xref", "")

        if xref_path and os.path.exists(xref_path):
            if not xref_path.endswith(os.sep) and not xref_path.endswith(("/", "\\")):
                xref_path += os.sep
            self.filepath = xref_path

        return super().invoke(context, event)

    def execute(self, context):
        import import_inst as realize_xrefs
        save_settings({"path_r_xref": self.directory})
            
        return {'FINISHED'}


class ExportTEX(bpy.types.Operator, ExportHelper):
    """ Convert Blender Material to .tex Image """
    bl_idname = "export_texture.tex"
    bl_label = 'Export TEX Image'
    bl_options = {'UNDO'}

    filename_ext = ".tex"
    filter_glob: StringProperty(default="*.tex", options={'HIDDEN'},)
    
    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Reminder:", icon='INFO')
        box.label(text="Exporting to TGA also works.")
        box.label(text="But TGA doesn't support certain")
        box.label(text="transparency/emission customizations.")
        box.label(text="I recommend using XNConvert for TGA.")

    def invoke(self, context, event):
        obj = context.active_object
        
        if not obj or not obj.active_material:
            self.report({'ERROR'}, "Must select an object with an active material.")
            return {'CANCELLED'}
            
        mat = obj.active_material
        
        if not mat.use_nodes or not mat.node_tree.nodes.get("Principled BSDF"):
            self.report({'ERROR'}, "Material must use nodes and contain a Principled BSDF.")
            return {'CANCELLED'}
            
        # SET UP PATH
        settings = load_settings() 
        tex_path = settings.get("path_e_tex", "")
        base_name = mat.name

        if tex_path and os.path.exists(tex_path):
            if not tex_path.endswith(os.sep) and not tex_path.endswith(("/", "\\")):
                tex_path += os.sep
            self.filepath = os.path.join(tex_path, base_name + ".tex")
        else:
            self.filepath = base_name + ".tex"

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        from .shader_set import Shader 
        from pkgimporter.tex_file import TEXFile
        
        export_dir = os.path.dirname(self.filepath)
        save_settings({"path_e_tex": export_dir})

        # Grab the CURRENTLY SELECTED material
        mat = context.active_object.active_material
        nodes = mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")
        
        # EXTRACT DATA INTO A SHADER OBJECT
        shader = Shader(type="float")
        shader.name = mat.name

        diff_node = next((n for n in nodes if n.label == "Diffuse Color"), None)
        if diff_node:
            shader.diffuse_color = list(diff_node.inputs['Color2'].default_value)
        else:
            shader.diffuse_color = list(bsdf.inputs['Base Color'].default_value)

        alpha_node = next((n for n in nodes if n.label == "Alpha"), None)
        if alpha_node:
            shader.diffuse_color[3] = alpha_node.inputs[0].default_value
        else:
            shader.diffuse_color[3] = bsdf.inputs['Alpha'].default_value

        emission_key = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
        emis_node = next((n for n in nodes if n.label == "Emission Color"), None)
        if emis_node:
            shader.emissive_color = list(emis_node.inputs['Color2'].default_value)
        else:
            shader.emissive_color = list(bsdf.inputs[emission_key].default_value)

        roughness = bsdf.inputs['Roughness'].default_value
        shader.shininess = max(0.0, min(1.0 - roughness, 1.0))

        image_node = next((n for n in nodes if n.type == 'TEX_IMAGE' and n.image), None)
        if not image_node:
            self.report({'ERROR'}, "No Image Texture node found in the active material!")
            return {'CANCELLED'}

        tex = TEXFile()
        
        # PASS SHADER
        tex.from_blender_image(image_node.image, shader)
        tex.write(self.filepath)

        self.report({'INFO'}, f"Successfully exported {shader.name}.tex!")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(ImportTEXMenu)
    bpy.utils.register_class(ImportTEX)
    bpy.utils.register_class(ExportTEX)
    bpy.types.TOPBAR_MT_editor_menus.append(ImportTEXMenu.menu_draw)


def unregister():
    bpy.types.TOPBAR_MT_editor_menus.remove(ImportTEXMenu.menu_draw)
    bpy.utils.unregister_class(ImportTEX)
    bpy.utils.unregister_class(ExportTEX)
    bpy.utils.unregister_class(ImportTEXMenu)