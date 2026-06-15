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

    import_lods: BoolProperty(
        name="Import LOD Variants",
        description="PKG files can contain High, Medium, Low, and VeryLow mesh variants. If unselected, only imports High variant.",
        default=user_settings.get("import_lods", True),
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
             "Skips filenames starting with 'sp_'. These are most xrefs (references) in MCSR."),
            
            ('SKIP_UNP', 
             "Skip Unpositioned Files (0,0,0)", 
             "Skips all files with 0,0,0 coordinate data (cehicles, UI, props) in pkg file footer. Recommended for entire-map imports."),

            ('SKIP_POS', 
             "Skip Positioned Files (Anything NOT 0,0,0)", 
             "Use case? Finding that aircraft carrier ship file. WHAT IS IT NAMED??"),
        ],
        default='NONE'
    )

    import_variants: BoolProperty(
        name="Import MM Variants",
        description="Variants are only applicable to Midtown Madness materials (multi-color options). Import?",
        default=user_settings.get("import_variants", True),
        )

    def execute(self, context):
        save_settings({
            "import_lods": self.import_lods,
            "import_bbnd": self.import_bbnd,
            "use_roughness_instead_of_specular_two": self.use_roughness_instead_of_specular_two,
            "import_headlights": self.import_headlights,
            "import_coordinate_offset": self.import_coordinate_offset,
            "batch_import_filter": self.batch_import_filter,
            "xref_handling_mode": self.xref_handling_mode,
            "import_variants": self.import_variants,
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

    files: CollectionProperty(
        name="File Path",
        type=bpy.types.OperatorFileListElement,
    )
    directory: StringProperty(
        subtype='DIR_PATH',
    )

    def execute(self, context):
        from . import import_bbnd

        keywords = self.as_keywords(ignore=("axis_forward",
                                            "axis_up",
                                            "filter_glob",
                                            "check_existing",
                                            "filepath",
                                            "files",
                                            "directory"
                                            ))
        if self.files:
            for file_elem in self.files:
                full_filepath = os.path.join(self.directory, file_elem.name)
            
                import_bbnd.runs(self, context, filepath=full_filepath, **keywords)

        return {'FINISHED'}

class ImportINST(bpy.types.Operator, ImportHelper):
    """Import the inst file format (.inst) [BUGGY]"""
    bl_idname = "import_scene.inst"
    bl_label = 'Import .Inst'
    bl_options = {'UNDO'}

    filename_ext = ".inst"
    filter_glob: StringProperty(default="*.inst", options={'HIDDEN'},)
        
    def execute(self, context):
        from . import import_inst

        return import_inst.runs(self.filepath, context)

class ImportPSDL(bpy.types.Operator, ImportHelper):
    """Import the psd1 file format (.psdl) [BUGGY]"""
    bl_idname = "import_scene.psdl"
    bl_label = 'Import .psdl'
    bl_options = {'UNDO'}
    filename_ext = ".inst"
    filter_glob: StringProperty(default="*.psdl", options={'HIDDEN'},)
        
    files: CollectionProperty(
        name="File Path",
        type=bpy.types.OperatorFileListElement,
    )
    directory: StringProperty(
        subtype='DIR_PATH',
    )

    setting_one: BoolProperty(
        name="SETTINGS ONE",
        description="",
        default=user_settings.get("setting_one", True),
        )    

    setting_two: EnumProperty(
        name="SETTINGS TWO",
        description="",
        items=[
            ('OPTIONONE', "Name", "Desc"),
            ('OPTIONTWO', "Name", "Desc"),
        ],
        default='OPTIONONE' 
    )

    def execute(self, context):
        save_settings({
            "setting_one": self.setting_one,
            "setting_two": self.setting_two,
        })

        from . import import_psdl
        keywords = self.as_keywords(ignore=("axis_forward",
                                            "axis_up",
                                            "filter_glob",
                                            "check_existing",
                                            "filepath",
                                            "files",
                                            "directory"
                                            ))
        if self.files:
            for file_elem in self.files:
                full_filepath = os.path.join(self.directory, file_elem.name)
            
                import_psdl.runs(self, context, filepath=full_filepath, **keywords)

        return {'FINISHED'}




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

class ExportINST(bpy.types.Operator, ImportHelper):
    """Export selected objects into .inst"""
    bl_idname = "export_scene.inst"
    bl_label = 'Export .inst'
    bl_options = {'UNDO'}

    filename_ext = ".inst"
    filter_glob: StringProperty(default="*.inst", options={'HIDDEN'},)
        
    def execute(self, context):
        from . import export_inst

        return export_inst.runs(self.filepath, context)

# Adds to menu
def menu_func_import(self, context):
    self.layout.operator(ImportPKG.bl_idname,  text="Angel Studios ModPackage  (.pkg)")
    self.layout.operator(ImportBBND.bl_idname, text="Angel Studios BoxBoundary (.bbnd)")
    self.layout.operator(ImportPSDL.bl_idname, text="Angel Studios psdl        (.psdl)")
    #self.layout.operator(ImportINST.bl_idname, text="Angel Studios sp_stop_f   (.inst)")

def menu_func_export(self, context):
    self.layout.operator(ExportPKG.bl_idname,  text="Angel Studios ModPackage  (.pkg)")
    self.layout.operator(ExportBBND.bl_idname, text="Angel Studios BoxBoundary (.bbnd)")
    #self.layout.operator(ExportINST.bl_idname, text="Angel Studios sp_stop_f   (.inst)")


# Register factories
classes = (
    ImportPKG,
    ImportBBND,
    ImportPSDL,
    #ImportINST,
    ExportPKG,
    ExportBBND,
    #ExportINST,
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



#file formats to understand/know

#          PLAINTEXT
#          PLAINTEXT
#/anim
#    .mod  (model data for pedestrians)
#    .rays (likely look-at info)
#    .skel (rig)
#/city
#    .aimap   (related to vehicle/ped spawning for specific map config)
#    .reset   (player respawn point)
#    .sky     (global lighting rule)
#    .water   (global water height?)
#    _lighting.csv
#/city/m01 /city/l01
#    facades.csv
#    lighting.csv
#    propdefs.csv
#    proprules.csv
#/citylights
#    .lmp      (lamp)
#/frontend
#    .htm      (a version of old html)
#    .txt      (vehicles, waypoint races)
#/frontend
#    all       (no extension, just all - a list of all items, not called)
#/race/l01 /race/m01
#    .aimap    (describes spawned va vehicles, pedestrians)
#    .aimap_p  (describes spawned va vehicles, pedestrians for 2P mode)
#    .ctf      (ctf settings)
#    .opp      (opponent coordinates to drive to)
#tune
#    .cltLightData       (light data)
#    .cltLightManager    (light data)
#    .movie              (gif rate)
#    .ptxGlassBirthRules (emitter rules)
#    .FXWATERSPOUT       (emitter rules)
#    .asBirthRule        (emitted particle rules)
#    .cinfo              (outdated, unused info file)
#tune/camera
#    .camTrackCS    (player vehicle camera rules)
#    .camPovCS      (player vehicle camera rule, POV)
#tune/hud
#    .hud           (hud positioning data)
#tune/banger
#    .dgBangerData  (sim data related to rigid body objects)
#tune/vehicle
#    .asNode        (unknown, probably outdated)
#    .aiVehicleData (simulation params; weight, friction etc)
#    .vehCarDamage  (visual + gameplay params for vehicle damage)
#    .vehCarSim     (simulation params for vehicle engine; horsepower, center of gravity, etc)
#    .vehGyro       (camera-related info for orbital camera)
#    .vehStuck      (how long to wait until vehicle flips upright, and related params)


#          CAN READ (JAILBROKEN)
#          CAN READ (JAILBROKEN)
#/city
#    .inst (low-end)
#    .
#/audvag
#    .VAG (audio, looped)
#/bound
#    .bbnd  (boundary file)
#/geometry
#    .csv (random non-read data)
#    .pkg (fully jailbroken thanks to racingfreak + others)
#    .mtx (material that is tied to pkg)
#/texture
#    .tex (xnconvert readable texture)


#          NEEDS JAILBREAK
#          NEEDS JAILBREAK
#/anim
#    .anim
#    .shaders
#/bound
#    .ter     (related to .bbnd)
#/city   
#    .bai     (boundary AI)
#    .inst    (sp references)
#    .cpvs    (?)
#    .psdl    (map file - semi-solved, but not really)
#/city/m01 /city/l01
#    .pathset (props, decals)
#/fonts
#    .strtbl  (in-sim textual content [AKA 'non-htm' text: Cutscenes, "next race", etc])
#/race/l01 /race/m01
#    .short   (shortcut routes? Unsure)