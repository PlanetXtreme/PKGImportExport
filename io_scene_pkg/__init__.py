# This program is licensed under Creative Commons BY-NC-SA:
# https://creativecommons.org/licenses/by-nc-sa/3.0/
#
# Created by Dummiesman, 2016-2020, edited in 2026, {ADD YEARS HERE}

bl_info = {
    "name": "Angel Studios PKG Format",
    "author": "Dummiesman, other", #edited for Blender 5.0 + MCSR compatibility by Planet Xtreme but he doesn't deserve credit, does he
    "version": (1, 0, 3),
    "blender": (5, 1, 0),
    "location": "File > Import-Export",
    "description": "Import-Export PKG files",
    "warning": "",
    "doc_url": "https://github.com/Dummiesman/PKGImportExport/",
    "tracker_url": "https://github.com/Dummiesman/PKGImportExport/",
    "support": 'COMMUNITY',
    "category": "Import-Export"}

import bpy
import pkgimporter.variant_ui as variant_ui
import pkgimporter.angel_scenedata as angel_scenedata
import pkgimporter.bl_preferences as bl_preferences
import pkgimporter.import_tex as import_tex
import pkgimporter.material_helper_ui as material_helper_ui
import json #for saved export/import settings :)
import os
from bpy.props import StringProperty, BoolProperty, CollectionProperty

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

class ImportPKG(bpy.types.Operator, ImportHelper):
    """Import from PKG file format (.pkg)"""
    bl_idname = "import_scene.pkg"
    bl_label = 'Import PKG'
    bl_options = {'UNDO'}

    filename_ext = ".pkg"
    filter_glob: StringProperty(default="*.pkg", options={'HIDDEN'})
    files: CollectionProperty(
        name="File Path",
        type=bpy.types.OperatorFileListElement,
    )
    directory: StringProperty(
        subtype='DIR_PATH',
    )

    import_variants: BoolProperty(
        name="Import LOD Variants",
        description="PKG files can contain High, Medium, Low, VeryLow variants. If unselected, only imports High variant.",
        default=user_settings.get("import_variants", True),
        )

    import_bbnd: BoolProperty(
        name="Import bbnd/bnd",
        description="Import boundary box object in ../bound as mesh",
        default=user_settings.get("import_bbnd", True),
        )

    use_roughness_instead_of_specular_two: BoolProperty(
        name="Import Materials using roughness for shininess",
        description="Reccomended to select this; If unselected, 'Specular ⌄ IOR Level' (original, outdated functionality) will determine shininess.",
        default=user_settings.get("use_roughness_instead_of_specular_two", True),
        )

    import_headlights: BoolProperty(
        name="Import headlights",
        description="If headlight MTX file(s) are found (...HLIGHTGLOW0, ...HLIGHTGLOW1.mtx), import it as geometry",
        default=user_settings.get("import_headlights", True),
        )    

    import_coordinate_offset: BoolProperty(
        name="Apply Files' Coordinate offset",
        description="All MCSR pkg files have a file footer that describes the coordinates of the pkg in MCSR world space; Place object at those coordinates in Blender space?",
        default=user_settings.get("import_coordinate_offset", True),
        )    

    xref_handling_mode: EnumProperty(
        name="Child xrefs",
        description="How are xrefs handled during import    ",
        items=[
            ('EMPTYS', "Import as Emptys (Export-Safest)", "Creates Blender Emptys to maintain the link to the external file. Recommended if planning to export."),
            ('GEOMETRY', "Import as Geometry", "Attempts to replace each xref object with the reference .pkg file."),
            ('SKIP', "Skip xrefs Entirely", "Ignores all xref importing.")
        ],
        default='EMPTYS' #name the "geometry" objects that are imported as the same name as the reference xref object so exporting can still preserve data
    )

    batch_import_filter: EnumProperty(
        name="Batch Filter",
        description="Choose rules to filter batch contents    ", #NONE is chosen when non-batch importing
        items=[
            ('NONE', 
             "Import Everything", 
             "As Described. Warning: vehicles, UI, and xref files will pile up at 0,0,0."),
            
            ('SKIP_SP', 
             "Skip xrefs (sp_*)", 
             "Skips filenames starting with 'sp_'. These are xref (references) in MCSR."),
            
            ('SKIP_UNP', 
             "Skip Unpositioned Files (0,0,0)", 
             "Strictest filter. Skips all files with 0,0,0 coordinate data (cehicles, UI, props) in pkg file footer. Recommended for entire-map imports.")
        ],
        default='NONE'
    )

    #what I gotta change
    #1: check if filename has sp_ to skip if SKIP_SP is chosen
    #2: Check coordinate data of pkg FIRST (0,0,0) [file footer] to check if skip is necessary
    #   Only do this IF SKIP_UNP is selected
    #3: make "Batch filer" NONE if only one file is selected
    #4: force all objects to load geometry first, at 0,0,0 position regardless.
    #   Place the emptys as normal, except after placing, parent them to loaded geometry.
    #   Then place relative bbnd + headlights geometry. Then parent to original imported geo file (from pkg)
    #   Finally, if there is position data on that geometry file, move that parent geo to its position.

    #5: Secondary step for emptys:
            #realize references (GEOMETRY-choice)
            #delete emptys (SKIP-choice)
            #import each reference only once, and re-use its blender data [efficient for batching]
    
    #6: place imported objects into collection, if collection is selected


    def execute(self, context):
        save_settings({
            "import_variants": self.import_variants,
            "import_bbnd": self.import_bbnd,
            "use_roughness_instead_of_specular_two": self.use_roughness_instead_of_specular_two,
            "import_headlights": self.import_headlights,
            "import_coordinate_offset": self.import_coordinate_offset,
            "batch_import_filter": self.batch_import_filter,
            "xref_handling_mode": self.xref_handling_mode,
        })

        from . import import_pkg
        keywords = self.as_keywords(ignore=("axis_forward",
                                            "axis_up",
                                            "filter_glob",
                                            "check_existing",
                                            "filepath",
                                            "files",
                                            "directory"
                                            ))
        if self.files:
            is_batch = ( #this checks if the selected files are >1File, UNLESS all the filenames start with vp_ or sp_
                         #this is a file filtering check for unpositioned or xref files (sp). vp application convenient
                         #when just importing cars
                len(self.files) > 1
                and not all(
                    file.name.lower().startswith(("vp_", "sp_"))
                    for file in self.files
                )
            )
            for file_elem in self.files:
                full_filepath = os.path.join(self.directory, file_elem.name)
                
                # Run the import load function for this specific file
                import_pkg.load(self, context, filepath=full_filepath, is_batch_mode=is_batch, **keywords)

        else: #shouldn't reach here??
            import_pkg.load(self, context, filepath=self.filepath, is_batch_mode=False, **keywords)

        return {'FINISHED'}

class ImportBBND(bpy.types.Operator, ImportHelper):
    """Import the bbnd file format (.bbnd)"""
    bl_idname = "import_scene.bbnd"
    bl_label = 'Import BBND'
    bl_options = {'UNDO'}

    filename_ext = ".bbnd"
    filter_glob: StringProperty(default="*.bbnd;*.bnd", options={'HIDDEN'},)
        
    def execute(self, context):
        from . import import_bbnd

        return import_bbnd.runs(self, context)

class ExportPKG(bpy.types.Operator, ExportHelper):
    """Export to PKG file format (.PKG)"""
    bl_idname = "export_scene.pkg"
    bl_label = 'Export PKG'

    filename_ext = ".pkg"
    filter_glob: StringProperty(
            default="*.pkg",
            options={'HIDDEN'},
            )

    export_bbnd_file: BoolProperty(
        name="Export bbnd (BOUND) file too",
        description="If 'BOUND'-named object is selected, export it too (to ../bound folder)",
        default=user_settings.get("export_bbnd_file", True),
        )    
    
    export_headlights: BoolProperty(
        name="Export headlights",
        description="If geometry is named HLIGHT/HEADLIGHT, and geometry is apropriate (2 tris/headlight or 1 plane per headlight), export applicable MTX file",
        default=user_settings.get("export_headlights", True),
        )    
    
    use_roughness_instead_of_specular_one: BoolProperty(
        name="Export Materials using roughness for shininess",
        description="Reccomended to select this; If unselected, 'Specular ⌄ IOR Level' (original, outdated functionality) will determine shininess.",
        default=user_settings.get("use_roughness_instead_of_specular_one", True),
        )

    e_vertexcolors: BoolProperty(
        name="Vertex Colors (Diffuse)",
        description="Export vertex colors that might affect diffuse",
        default=user_settings.get("e_vertexcolors", False),
        )
        
    e_vertexcolors_s: BoolProperty(
        name="Vertex Colors (Specular)",
        description="Export vertex colors that might affect specular",
        default=user_settings.get("e_vertexcolors_s", False),
        )
        
    apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        description="(Temporarily) apply Blender modifiers to objects before exporting to the pkg?",
        default=user_settings.get("apply_modifiers", True),
        )
        
    #selection_only: BoolProperty(
    #    name="Selection Only",
    #    description="This is enabled whether you select it or not",
    #    default=True,
    #    )
        
    def execute(self, context):

        save_settings({
            "export_bbnd_file": self.export_bbnd_file,
            "use_roughness_instead_of_specular_one": self.use_roughness_instead_of_specular_one,
            "e_vertexcolors": self.e_vertexcolors,
            "e_vertexcolors_s": self.e_vertexcolors_s,
            "apply_modifiers": self.apply_modifiers,
            "apply_modifiers": self.apply_modifiers,
            "export_headlights": self.export_headlights,
        })

        from . import export_pkg
        
        keywords = self.as_keywords(ignore=("axis_forward",
                                            "axis_up",
                                            "filter_glob",
                                            "check_existing",
                                            ))
                                    
        return export_pkg.save(self, context, **keywords)

class ExportBBND(bpy.types.Operator, ExportHelper):
    """Export to bbnd file format (.bbnd)"""
    bl_idname = "export_scene.bbnd"
    bl_label = 'Export BBND'

    filename_ext = ".bbnd"
    filter_glob: StringProperty(default="*.bbnd;*.bnd", options={'HIDDEN'},)
        
    def execute(self, context):
        from . import export_bbnd
                                    
        return export_bbnd.save(self, context)


# Adds to menu
def menu_func_export(self, context):
    self.layout.operator(ExportPKG.bl_idname,  text="Angel Studios ModPackage  (.pkg)")
    self.layout.operator(ExportBBND.bl_idname, text="Angel Studios BoxBoundary (.bbnd)")

def menu_func_import(self, context):
    self.layout.operator(ImportPKG.bl_idname,  text="Angel Studios ModPackage  (.pkg)")
    self.layout.operator(ImportBBND.bl_idname, text="Angel Studios BoxBoundary (.bbnd)")

# Register factories
classes = (
    ImportPKG,
    ImportBBND,
    ExportPKG,
    ExportBBND,
)

def register():
    bl_preferences.register()
    for cls in classes:
        bpy.utils.register_class(cls)
    angel_scenedata.register()
    variant_ui.register()
    import_tex.register()
    material_helper_ui.register()
    
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    
    bpy.types.Material.variant = bpy.props.IntProperty(name="Variant")
    bpy.types.Material.cloned_from = bpy.props.PointerProperty(name="Cloned From", type=bpy.types.Material)
    
    bpy.types.Scene.angel = PointerProperty(type=angel_scenedata.AngelSceneData)


def unregister():
    del bpy.types.Scene.angel
    del bpy.types.Material.cloned_from
    del bpy.types.Material.variant 
    
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

    material_helper_ui.unregister()
    import_tex.unregister()
    variant_ui.unregister()
    angel_scenedata.unregister()
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    bl_preferences.unregister()
    

if __name__ == "__main__":
    register()
