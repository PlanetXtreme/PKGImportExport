# This program is licensed under Creative Commons BY-NC-SA:
# https://creativecommons.org/licenses/by-nc-sa/3.0/
#
# Created by Dummiesman, 2016-2020, edited in 2026 (PX), {ADD YEARS HERE}

bl_info = {
    "name": "Angel Studios File Formats",
    "author": "Dummiesman, PlanetXtreme",
    "version": (1, 0, 4),
    "blender": (5, 1, 0),
    "location": "File > Import-Export",
    "description": "Import-Export PKG files",
    "warning": "",
    "doc_url": "https://github.com/Dummiesman/PKGImportExport/",
    "tracker_url": "https://github.com/Dummiesman/PKGImportExport/",
    "support": 'COMMUNITY',
    "category": "Import-Export"}

import bpy
import pkgimporter.quick_export_tool as export_tool
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

class ImportPSDL(bpy.types.Operator, ImportHelper):
    """ Import PSD1 file format (Midnight Club Street Racing) """
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
        default=user_settings.get("import_psdl_setting_one", True),
        )

    setting_two: EnumProperty(
        name="SETTINGS TWO",
        description="",
        items=[
            ('import_psdl_opt_one', "Name", "Desc"),
            ('import_psdl_opt_two', "Name", "Desc"),
        ],
        default=user_settings.get("import_psdl_setting_two", "import_psdl_opt_one"),
    )

    def invoke(self, context, event): #memorization call
        settings = load_settings()
        psdl_path = settings.get("path_i_psdl", "")

        if psdl_path and os.path.exists(psdl_path):
            if not psdl_path.endswith(os.sep) and not psdl_path.endswith(("/", "\\")):
                psdl_path += os.sep
            
            self.filepath = psdl_path

        return super().invoke(context, event)


    def execute(self, context):
        save_settings({
            "import_psdl_setting_one": self.setting_one,
            "import_psdl_setting_two": self.setting_two,
            "path_i_psdl": self.directory,
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

class ImportINST(bpy.types.Operator, ImportHelper):
    """ Import Inst File Format (xrefs) """
    bl_idname = "import_scene.inst"
    bl_label = 'Import INST'
    bl_options = {'UNDO'}
    filename_ext = ".inst"
    filter_glob: StringProperty(default="*.inst", options={'HIDDEN'})

    files: CollectionProperty(
        name="File Path",
        type=bpy.types.OperatorFileListElement,
    )
    directory: StringProperty(
        subtype='DIR_PATH',
    )

    import_coordinate_offset: BoolProperty(
        name="Apply Files' Coordinate offset",
        description="All MCSR pkg files have a file footer that describes the coordinates of the pkg in MCSR world space; Place object at those coordinates in Blender space?",
        default=user_settings.get("import_inst_coordinate_offset", True),
        )    

    xref_handling: EnumProperty(
        name="Child xrefs",
        description="How are xrefs handled during import    ",
        items=[
            ('EMPTYS', "Emptys", "Creates Blender Emptys @ listed rot + pos, best for fast-viewport performance."),
            ('INSTANCED', "Instanced Geometry", "Attempts to replace each xref object with an instance for performance + visibility."),
            ('GEOMETRY', "Raw Geometry", "Attempts to replace each xref object with raw geometry - Expect poorest viewport performance."),
        ],
        default=user_settings.get("import_inst_xref_handling", 'INSTANCED'),
    )

    origin_placement: EnumProperty(
        name="Origin Placement",
        description="Apply dgBangerData Center of Gravity    ",
        items=[
            ('NONE', 
             "Ignore dgBangerData", 
             "Don't attempt to find dgBangerData origin for positioning elements"),
            
            ('SKIP_UNRELATED', 
             "Skip vp_ + mtx", 
             "Skips applying pre-calculated origin to objects which probably shouldn't use it (vp_vehicles, files with mtx pair)."),
            
            ('APPLY', 
             "Apply to all", 
             "Applies dgBangerData origin calculation to all objects which have dgBangerData filename pair."),
        ],
        default=user_settings.get("import_inst_origin_placement", 'SKIP_UNRELATED'),
    )


    def invoke(self, context, event): #memorization call
        settings = load_settings()
        inst_path = settings.get("path_i_inst", "")

        if inst_path and os.path.exists(inst_path):
            # Blender requires directories to end with a slash. WHY
            if not inst_path.endswith(os.sep) and not inst_path.endswith(("/", "\\")):
                inst_path += os.sep
            
            self.filepath = inst_path

        return super().invoke(context, event)

    def execute(self, context):
        save_settings({
            "import_inst_coordinate_offset": self.import_coordinate_offset,
            "import_inst_xref_handling": self.xref_handling,
            "import_inst_origin_placement": self.origin_placement,
            "path_i_inst": self.directory,
        })

        from . import import_inst
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

                import_inst.runs(self, context, filepath=full_filepath, **keywords)

        else: #shouldn't reach here??
            import_inst.runs(self, context, filepath=self.filepath, is_batch_mode=False, **keywords)

        return {'FINISHED'}

#class ImportBAI

#class ImportCVPS

class ImportPKG(bpy.types.Operator, ImportHelper):
    """ Import PKG File Format (MCSR and Midtown Madness) """
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
        default=user_settings.get("import_pkg_lods", True),
        )
    import_bbnd: BoolProperty(
        name="Import bbnd/bnd",
        description="Import boundary box object in ../bound as mesh",
        default=user_settings.get("import_pkg_bbnd", True),
        )

    use_roughness_instead_of_specular_two: BoolProperty(
        name="Import Materials using roughness for shininess",
        description="Reccomended to select this; If unselected, 'Specular ⌄ IOR Level' (original, outdated functionality) will determine shininess.",
        default=user_settings.get("import_pkg_use_roughness_instead", True),
        )

    import_headlights: BoolProperty(
        name="Import headlights",
        description="If headlight MTX file(s) are found (...HLIGHTGLOW0, ...HLIGHTGLOW1.mtx), import it as geometry",
        default=user_settings.get("import_pkg_headlights", True),
        )    

    import_coordinate_offset: BoolProperty(
        name="Apply Files' Coordinate offset",
        description="All MCSR pkg files have a file footer that describes the coordinates of the pkg in MCSR world space; Place object at those coordinates in Blender space?",
        default=user_settings.get("import_pkg_coordinate_offset", True),
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
             "Skips selected filenames starting with 'sp_'. These are most xrefs (references) in MCSR."),
            
            ('SKIP_UNP', 
             "Skip Unpositioned Files (0,0,0)", 
             "Skips all files with 0,0,0 coordinate data (cehicles, UI, props) in pkg file footer. Recommended for entire-map imports."),

            ('SKIP_POS', 
             "Skip Positioned Files (Anything NOT 0,0,0)", 
             "Use case? Finding that aircraft carrier ship file. WHAT IS IT NAMED??"),
        ],
        default=user_settings.get("import_pkg_batch_filter", 'NONE'),
    )

    xref_handling: EnumProperty(
        name="Child xrefs",
        description="How are xrefs handled during import    ",
        items=[
            ('SKIP', "Skip", "Ignores all xref importing."),
            ('EMPTYS', "Emptys", "Creates Blender Emptys @ listed rot + pos, best for fast-viewport performance."),
            ('INSTANCED', "Instanced Geometry", "Attempts to replace each xref object with an instance for performance + visibility."),
            ('GEOMETRY', "Raw Geometry", "Attempts to replace each xref object with raw geometry - Expect poorest viewport performance."),
        ],
        default=user_settings.get("import_pkg_xref_handling", 'INSTANCED'),
    )

    origin_placement: EnumProperty(
        name="Origin Placement",
        description="Apply dgBangerData Center of Gravity    ",
        items=[
            ('NONE', 
             "Ignore dgBangerData", 
             "Don't attempt to find dgBangerData origin for positioning elements"),
            
            ('SKIP_UNRELATED', 
             "Skip vp_ + mtx", 
             "Skips applying pre-calculated origin to objects which probably shouldn't use it (vp_vehicles, files with mtx pair)."),
            
            ('APPLY', 
             "Apply to all", 
             "Applies dgBangerData origin calculation to all objects which have dgBangerData filename pair."),
        ],
        default=user_settings.get("import_pkg_origin_placement", 'SKIP_UNRELATED'),
    )

    #import_variants: BoolProperty(
    #    name="Import MM Variants",
    #    description="Variants are only applicable to Midtown Madness materials (multi-color options). Import?",
    #    default=user_settings.get("import_pkg_variants", True),
    #    )

    def invoke(self, context, event): #memorization call
        settings = load_settings()
        pkg_path = settings.get("path_i_pkg", "")

        if pkg_path and os.path.exists(pkg_path):
            # Blender requires directories to end with a slash. WHY
            if not pkg_path.endswith(os.sep) and not pkg_path.endswith(("/", "\\")):
                pkg_path += os.sep
            
            self.filepath = pkg_path

        return super().invoke(context, event)

    def execute(self, context):
        save_settings({
            "import_pkg_lods": self.import_lods,
            "import_pkg_bbnd": self.import_bbnd,
            "import_pkg_use_roughness_instead": self.use_roughness_instead_of_specular_two,
            "import_pkg_headlights": self.import_headlights,
            "import_pkg_coordinate_offset": self.import_coordinate_offset,
            "import_pkg_batch_filter": self.batch_import_filter,
            "import_pkg_xref_handling": self.xref_handling,
            "import_pkg_origin_placement": self.origin_placement,
            #"import_pkg_variants": self.import_variants,
            "path_i_pkg": self.directory, #path import
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
    """ Import AngelStudios BoxBoundary (Hitbox) """
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

    def invoke(self, context, event): #memorization call
        settings = load_settings()
        bbnd_path = settings.get("path_i_bbnd", "")

        if bbnd_path and os.path.exists(bbnd_path):
            if not bbnd_path.endswith(os.sep) and not bbnd_path.endswith(("/", "\\")):
                bbnd_path += os.sep
            
            self.filepath = bbnd_path

        return super().invoke(context, event)


    def execute(self, context):

        save_settings({
            "path_i_bbnd": self.directory,
        })
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
            
                import_bbnd.runs(self, context, **keywords) #filepath=full_filepath,

        return {'FINISHED'}

class ImportMODSKEL(bpy.types.Operator, ImportHelper):
    """ Import AngelStudios Model/Skeleton files """
    bl_idname = "import_scene.modskel"
    bl_label = 'Import mod/skel files'
    bl_options = {'UNDO'} 
    filename_ext = ".mod"
    filter_glob: StringProperty(default="*.mod;*.skel", options={'HIDDEN'})

    files: CollectionProperty(name="File Path", type=bpy.types.OperatorFileListElement)
    directory: StringProperty(subtype='DIR_PATH')

    force_shader_override: BoolProperty(
        name="Force .shaders Override",
        description="Attempt to read external binary .shaders file for materials",
        default=user_settings.get("import_modskel_force_shader", False),
    )
    import_hitboxes: BoolProperty(
        name="Import Hitboxes",
        description="Generate collision capsules from .rays file if found",
        default=user_settings.get("import_modskel_hitboxes", True),
    )
    default_hitboxes: BoolProperty(
        name="Fallback Default Hitboxes",
        description="Generate basic hitboxes even if .rays is missing",
        default=user_settings.get("import_modskel_default_hitboxes", False),
    )
    import_rotate_filter: EnumProperty(
        name="Axis of Animation",
        description="Default rotation into Blender",
        items=[
            ('NONE', 
             "Don't Rotate Z", 
             "Default Blender Importing"),
            
            ('PLUS_NINTY', 
             "+90 Degrees Z", 
             "Imports animation so character is facing a different way."),
            
            ('PLUS_ONE_EIGHTY', 
             "+180 Degrees Z", 
             "Imports animation so character is facing a different way."),

            ('MINUS_NINTY', 
             "+270 Degrees Z", 
             "Imports animation so character is facing a different way."),
        ],
        default=user_settings.get("import_modskel_rotate_filter", "PLUS_ONE_EIGHTY"),
    )
    def invoke(self, context, event):
        settings = load_settings()
        
        modskel_path = settings.get("path_i_modskel", "")
        if modskel_path and os.path.exists(modskel_path):
            if not modskel_path.endswith(os.sep) and not modskel_path.endswith(("/", "\\")):
                modskel_path += os.sep
            self.filepath = modskel_path

        self.force_shader_override = settings.get("import_modskel_force_shader", False)
        self.import_hitboxes = settings.get("import_modskel_hitboxes", True)
        self.default_hitboxes = settings.get("import_modskel_default_hitboxes", False)
        self.import_rotate_filter = settings.get("import_modskel_rotate_filter", "PLUS_ONE_EIGHTY")

        return super().invoke(context, event)

    def execute(self, context):
        from . import import_skel_mod_shader_rays
        save_settings({
            "import_modskel_force_shader": self.force_shader_override,
            "import_modskel_hitboxes": self.import_hitboxes,
            "import_modskel_default_hitboxes": self.default_hitboxes,
            "import_modskel_rotate_filter": self.import_rotate_filter,
            "path_i_modskel": self.directory,
        })
        
        selected_files = [os.path.join(self.directory, f.name) for f in self.files]
        
        # Scenario 1: Exact 2 files chosen (Manual Override)
        if len(selected_files) == 2:
            mod_path = next((f for f in selected_files if f.lower().endswith('.mod')), None)
            skel_path = next((f for f in selected_files if f.lower().endswith('.skel')), None)
            if mod_path and skel_path:
                import_skel_mod_shader_rays.runs(context, mod_path=mod_path, skel_path=skel_path, operator=self)
                return {'FINISHED'}

        processed_bases = set()
        for filepath in selected_files:
            base_name, ext = os.path.splitext(filepath)
            if base_name in processed_bases: continue
            processed_bases.add(base_name)
            
            mod_path = base_name + ".mod"
            skel_path = base_name + ".skel"
            
            has_mod = os.path.exists(mod_path)
            has_skel = os.path.exists(skel_path)
            
            # Scenario 2: Both files exist automatically with the same name
            if has_mod and has_skel:
                print(f"[Import] Auto-paired {base_name}.mod and .skel!")
                import_skel_mod_shader_rays.runs(context, mod_path=mod_path, skel_path=skel_path, operator=self)
                
            # Scenario 3: Only 1 file picked, and no auto-pair was found!
            elif len(selected_files) == 1:
                print(f"[Import] Missing pair for {base_name}. Launching search dialog...")
                bpy.ops.import_scene.angel_find_pair('INVOKE_DEFAULT', 
                                                     original_filepath=filepath,
                                                     force_shader_override=self.force_shader_override,
                                                     import_hitboxes=self.import_hitboxes,
                                                     default_hitboxes=self.default_hitboxes,
                                                     import_rotate_filter=self.import_rotate_filter,
                                                     )
                return {'FINISHED'}
                
            # Scenario 4: Batch Import (Just grab whatever exists)
            else:
                import_skel_mod_shader_rays.runs(context, 
                                                 mod_path=mod_path if has_mod else None, 
                                                 skel_path=skel_path if has_skel else None, 
                                                 operator=self)

        return {'FINISHED'}

class ImportAngelEnginePair(bpy.types.Operator, ImportHelper):
    """Find the missing .mod or .skel pair"""
    bl_idname = "import_scene.angel_find_pair"
    bl_label = 'Select Missing Pair File'
    bl_options = {'UNDO'} 
    
    filter_glob: StringProperty(default="*.mod;*.skel", options={'HIDDEN'})
    
    original_filepath: StringProperty(options={'HIDDEN'})
    force_shader_override: BoolProperty(options={'HIDDEN'})
    import_hitboxes: BoolProperty(options={'HIDDEN'})
    default_hitboxes: BoolProperty(options={'HIDDEN'})
    import_rotate_filter: StringProperty(options={'HIDDEN'})

    def draw(self, context): 
        layout = self.layout
        box = layout.box()
        box.label(text="Reminder:", icon='INFO')
        
        # Determine what we actually have and what is missing
        is_mod = self.original_filepath.lower().endswith('.mod')
        current_ext = ".mod" if is_mod else ".skel"
        missing_ext = ".skel" if is_mod else ".mod"
        if is_mod:
            finalText = "otherwise your geometry will be bad."
        else:
            finalText = "otherwise your rig will be useless."
        
        box.label(text=f"You just imported a {current_ext} file, but")
        box.label(text=f"it had no detectable pair.")
        box.label(text=f"Please locate the matching {missing_ext} file,")
        box.label(text=f"{finalText}")

    def invoke(self, context, event):
        # 1. Dynamically change the file filter BEFORE the window opens
        is_mod = self.original_filepath.lower().endswith('.mod')
        self.filter_glob = "*.skel" if is_mod else "*.mod"

        # 2. Load settings for the starting directory
        settings = load_settings()
        modskel_path = settings.get("path_i_modskel", "") 
        if modskel_path and os.path.exists(modskel_path):
            if not modskel_path.endswith(os.sep) and not modskel_path.endswith(("/", "\\")):
                modskel_path += os.sep
            self.filepath = modskel_path

        return super().invoke(context, event)

    def execute(self, context):
        from . import import_skel_mod_shader_rays
        
        file1 = self.original_filepath
        file2 = self.filepath
        
        is_mod = file1.lower().endswith('.mod')
        expected_ext = ".skel" if is_mod else ".mod"
        
        # Safety Check: If the user manually types an invalid extension and hits import anyway
        if not file2.lower().endswith(expected_ext):
            self.report({'WARNING'}, f"Invalid pair! Expected a {expected_ext} file. Importing single file instead.")
            return self.cancel(context)
        
        mod_path = file1 if is_mod else file2
        skel_path = file2 if is_mod else file1
        
        print(f"[Import] Found pair! Mod: {mod_path} | Skel: {skel_path}")
        import_skel_mod_shader_rays.runs(context, mod_path=mod_path, skel_path=skel_path, operator=self)
        return {'FINISHED'}
        
    def cancel(self, context):
        from . import import_skel_mod_shader_rays
        print("[Import] User cancelled pair search. Importing single file.")
        
        mod_path = self.original_filepath if self.original_filepath.lower().endswith('.mod') else None
        skel_path = self.original_filepath if self.original_filepath.lower().endswith('.skel') else None
        
        import_skel_mod_shader_rays.runs(context, mod_path=mod_path, skel_path=skel_path, operator=self)
        return {'CANCELLED'}

class ImportANIM(bpy.types.Operator, ImportHelper):
    """ Import MCSR Animation for .mod&.skel Files """
    bl_idname = "import_scene.anim"
    bl_label = 'Import ANIM'
    bl_options = {'UNDO'} 
    filename_ext = ".anim"
    filter_glob: StringProperty(default="*.anim", options={'HIDDEN'},)

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
        box.label(text="Animations require a rig import.")
        box.label(text="You must select the rig when Importing.")
        box.label(text="(Import rig via mod/skel Importing!)")

    def invoke(self, context, event):
        settings = load_settings()
        anim_path = settings.get("path_i_anim", "")

        if anim_path and os.path.exists(anim_path):
            if not anim_path.endswith(os.sep) and not anim_path.endswith(("/", "\\")):
                anim_path += os.sep
            self.filepath = anim_path

        return super().invoke(context, event)

    def execute(self, context):
        save_settings({"path_i_anim": self.directory})
        from . import import_anim

        if self.files:
            # Batch all files together to send to the import module
            filepaths = [os.path.join(self.directory, f.name) for f in self.files]
            import_anim.runs(self, context, filepaths)

        return {'FINISHED'}


#class ExportPSDL

class ExportINST(bpy.types.Operator, ExportHelper):
    """ Export Inst File (xrefs) """
    bl_idname = "export_scene.inst"
    bl_label = 'Export INST'
    bl_options = {'UNDO'}
    filename_ext = ".inst"
    filter_glob: StringProperty(default="*.inst", options={'HIDDEN'})

    force_long_format: BoolProperty(
        name="Force Long Format",
        description="Forces all objects to export as a 12-float Matrix. Disable for optimization.",
        default=False,
    )

    custom_prop_name: BoolProperty(
        name="Use Custom Property Name",
        description="Use custom property name for xref pkg name? Else uses empty/instance/geo name [truncating .001, .002...] for reference in exported .inst",
        default=False,
    )
    def invoke(self, context, event):
        # Load the saved export directory
        settings = load_settings()
        inst_export_path = settings.get("path_e_inst", "")

        if inst_export_path and os.path.exists(inst_export_path):
            if not inst_export_path.endswith(os.sep) and not inst_export_path.endswith(("/", "\\")):
                inst_export_path += os.sep
            
            # ExportHelper uses filepath for both directory and the file name
            self.filepath = inst_export_path

        return super().invoke(context, event)

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Reminder:", icon='INFO')
        box.label(text="Only ACTIVELY SELECTED")
        box.label(text="objects will be exported!")

        layout.separator()
        
        layout.prop(self, "force_long_format")
        layout.prop(self, "custom_prop_name")

    def execute(self, context):
        save_settings({
            "export_inst_long_format": self.force_long_format,
            "export_inst_name": self.custom_prop_name,
            "path_e_inst": os.path.dirname(self.filepath),
        })

        from . import export_inst
        keywords = self.as_keywords(ignore=("filter_glob", "check_existing", "filepath"))
        
        return export_inst.runs(self, context, filepath=self.filepath, **keywords)


#class ExportBAI

#class ExportCVPS

#class ExportINST 

class ExportPKG(bpy.types.Operator, ExportHelper):
    """ Export AngelStudios PKG """
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
        default=user_settings.get("export_pkg_bbnd_file", True),
        )    
    
    export_headlights: BoolProperty(
        name="Export headlights",
        description="If geometry is named HLIGHT/HEADLIGHT, and geometry is apropriate (2 tris/headlight or 1 plane per headlight), export applicable MTX file",
        default=user_settings.get("export_pkg_headlights", True),
        )    
    
    use_roughness_instead_of_specular_one: BoolProperty(
        name="Export Materials using roughness for shininess",
        description="Reccomended to select this; If unselected, 'Specular ⌄ IOR Level' (original, outdated functionality) will determine shininess.",
        default=user_settings.get("export_pkg_use_roughness_instead", True),
        )

    e_vertexcolors: BoolProperty(
        name="Vertex Colors (Diffuse)",
        description="Export vertex colors that might affect diffuse",
        default=user_settings.get("export_pkg_e_vertexcolors", False),
        )
        
    e_vertexcolors_s: BoolProperty(
        name="Vertex Colors (Specular)",
        description="Export vertex colors that might affect specular",
        default=user_settings.get("export_pkg_e_vertexcolors_s", False),
        )
        
    apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        description="(Temporarily) apply Blender modifiers to objects before exporting to the pkg?",
        default=user_settings.get("export_pkg_apply_modifiers", True),
        )

    origin_placement: EnumProperty(
        name="Origin Placement",
        description="Apply dgBangerData Center of Gravity    ",
        items=[
            ('NONE', 
             "Ignore dgBangerData", 
             "Don't attempt to find dgBangerData origin for positioning elements. Select this if selected on import."),
            
            ('APPLY', 
             "Apply to all", 
             "Undo-s dgBangerData origin calculation to all objects which have dgBangerData custom property. Choose this if selected on import."),
        ],
        default=user_settings.get("export_origin_placement", 'APPLY'),
    )

    #selection_only: BoolProperty(
    #    name="Selection Only",
    #    description="This is enabled whether you select it or not",
    #    default=True,
    #    )
        
    def invoke(self, context, event): #memorization call
        settings = load_settings()
        pkg_path = settings.get("path_e_pkg", "")

        if pkg_path and os.path.exists(pkg_path):
            # We want to provide a default name so the export window doesn't have a blank textbox
            if context.active_object:
                default_name = context.active_object.name + self.filename_ext
            elif bpy.data.filepath:
                default_name = bpy.path.display_name_from_filepath(bpy.data.filepath) + self.filename_ext
            else:
                default_name = "untitled" + self.filename_ext
            
            # Combine the saved folder path with the default file name
            self.filepath = os.path.join(pkg_path, default_name)

        return super().invoke(context, event)


    def execute(self, context):
        export_directory = os.path.dirname(self.filepath)

        save_settings({
            "export_pkg_bbnd_file": self.export_bbnd_file,
            "export_pkg_headlights": self.export_headlights,
            "export_pkg_use_roughness_instead": self.use_roughness_instead_of_specular_one,
            "export_pkg_e_vertexcolors": self.e_vertexcolors,
            "export_pkg_e_vertexcolors_s": self.e_vertexcolors_s,
            "export_pkg_apply_modifiers": self.apply_modifiers,
            "export_origin_placement": self.origin_placement,
            "path_e_pkg": export_directory,
        })

        from . import export_pkg
        
        keywords = self.as_keywords(ignore=("axis_forward",
                                            "axis_up",
                                            "filter_glob",
                                            "check_existing",
                                            ))
                                    
        return export_pkg.save(self, context, **keywords)

class ExportBBND(bpy.types.Operator, ExportHelper):
    """ Export AngelStudios BoxBoundary (Hitbox) """
    bl_idname = "export_scene.bbnd"
    bl_label = 'Export BBND'

    filename_ext = ".bbnd"
    filter_glob: StringProperty(default="*.bbnd;*.bnd", options={'HIDDEN'},)

    def invoke(self, context, event): #memorization call
        settings = load_settings()
        bbnd_path = settings.get("path_e_bbnd", "")

        if bbnd_path and os.path.exists(bbnd_path):
            if context.active_object:
                default_name = context.active_object.name + self.filename_ext
            elif bpy.data.filepath:
                default_name = bpy.path.display_name_from_filepath(bpy.data.filepath) + self.filename_ext
            else:
                default_name = "untitled" + self.filename_ext
            
            self.filepath = os.path.join(bbnd_path, default_name)

        return super().invoke(context, event)

    def execute(self, context):
        export_directory = os.path.dirname(self.filepath)

        save_settings({
            "path_e_bbnd": export_directory,
        })
        from . import export_bbnd
                                    
        return export_bbnd.save(self, context)

#class ExportMODSKEL #exports based on selection, and ignores "ROOT" or "IGNORE" bonennames in hierarchy

class ExportANIM(bpy.types.Operator, ExportHelper):
    """ Export AngelStudios .mod&.skel Animation """
    bl_idname = "export_scene.anim"
    bl_label = 'Export ANIM'
    bl_options = {'UNDO'}
    filename_ext = ".anim"
    filter_glob: StringProperty(default="*.anim", options={'HIDDEN'})
    
    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Export Rules:", icon='INFO')
        box.label(text="Only Pedestrian formatting exported.")
        box.label(text="Ensures ROOT bone is ignored.")

    def invoke(self, context, event):
        settings = load_settings()
        anim_path = settings.get("path_e_anim", "")

        if anim_path and os.path.exists(anim_path):
            if not anim_path.endswith(os.sep) and not anim_path.endswith(("/", "\\")):
                anim_path += os.sep
            self.filepath = anim_path

        return super().invoke(context, event)

    def execute(self, context):
        save_settings({"path_e_anim": os.path.dirname(self.filepath)})
        from . import export_anim

        export_anim.runs(self, context, self.filepath)
        return {'FINISHED'}


#Not implemented, may not have read-data
class ImportINST_STOP(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.inst"
    bl_label = 'Import .Inst'
    bl_options = {'UNDO'}

    filename_ext = ".inst"
    filter_glob: StringProperty(default="*.inst", options={'HIDDEN'},)
        
    def execute(self, context):
        from . import import_inst

        return import_inst.runs(self.filepath, context)

class ExportINST_STOP(bpy.types.Operator, ImportHelper):
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
    self.layout.operator(ImportPSDL.bl_idname,      text="AngelStudios psdl                 (.psdl)")
    self.layout.operator(ImportINST.bl_idname,      text="AngelStudios Instances       (.inst)")
    #self.layout.operator(ExportBAI.bl_idname,       text="AngelStudios BoundaryAI  (.bai)")
    #self.layout.operator(ExportCVPS.bl_idname,      text="AngelStudios cvps          (.cvps)")
    self.layout.operator(ImportPKG.bl_idname,       text="AngelStudios ModPackage  (.pkg)")
    self.layout.operator(ImportBBND.bl_idname,      text="AngelStudios BoxBoundary (.bbnd)")
    self.layout.operator(ImportMODSKEL.bl_idname,   text="AngelStudios Model              (.mod, .skel, .rays)")
    self.layout.operator(ImportANIM.bl_idname,      text="AngelStudios Animation        (.anim)")
    #self.layout.operator(ImportINST_SLOW.bl_idname, text="AngelStudios sp_stop_f   (.inst)")

def menu_func_export(self, context):
    #self.layout.operator(ExportPSDL.bl_idname,      text="AngelStudios psdl                 (.psdl)")
    self.layout.operator(ExportINST.bl_idname,      text="AngelStudios Instances       (.inst)")
    #self.layout.operator(ExportBAI.bl_idname,       text="AngelStudios BoundaryAI  (.bai)")
    #self.layout.operator(ExportCVPS.bl_idname,      text="AngelStudios cvps          (.cvps)")
    self.layout.operator(ExportPKG.bl_idname,       text="AngelStudios ModPackage  (.pkg)")
    self.layout.operator(ExportBBND.bl_idname,      text="AngelStudios BoxBoundary (.bbnd)")
    #self.layout.operator(ExportMODSKEL.bl_idname,   text="AngelStudios Model              (.mod, .skel, .rays)")
    self.layout.operator(ExportANIM.bl_idname,      text="AngelStudios Animation        (.anim)")
    #self.layout.operator(ExportINST_SLOW.bl_idname, text="AngelStudios sp_stop_f   (.inst)")


# Register factories
classes = ( #this is the best hierarchy: PSDL, PKG, BBND, ModSkel, Anim, ... 
            #Should look into exporting the selected material as a .Tex or .TGA file
            #.Tex has best functionality (ability for emission masks, alpha masks, + color masks)
    ImportPSDL,
    ImportINST, #<-- big inst file, not small one. 
    #ImportBAI,
    #ImportCVPS,
    ImportPKG,
    ImportBBND,
    ImportMODSKEL,
    ImportAngelEnginePair, #not visible in File -> Import, but required in order to be called by other function!
    ImportANIM,
    
    #ExportPSDL,
    ExportINST, 
    #ExportBAI,
    #ExportCVPS,
    ExportPKG,
    ExportBBND,
    #ExportMODSKEL, #exports 2 files with same name as each other (.skel + .mod)
    ExportANIM,

    #ImportINST_SLOW, #<-- small inst file (may be related to AI stopping at corners, but may also be useless)
    #ExportINST_SLOW, #<-- small inst file (may be related to AI stopping at corners, but may also be useless)
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    export_tool.register()
    material_helper_ui.register()
    
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    
    bpy.types.Material.variant = bpy.props.IntProperty(name="Variant")
    bpy.types.Material.cloned_from = bpy.props.PointerProperty(name="Cloned From", type=bpy.types.Material)

def unregister():
    del bpy.types.Scene.angel
    del bpy.types.Material.cloned_from
    del bpy.types.Material.variant 
    
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

    material_helper_ui.unregister()
    export_tool.unregister()
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    

if __name__ == "__main__":
    register()



#file formats to understand/know

#          PLAINTEXT
#          PLAINTEXT
#/anim
#    .anim (animation file, requires .mod and .skel to work)
#    .mod  (model data for pedestrians)
#    .rays (collision geometry / possibly raycaster info for peds)
#    .skel (rig)
#/city
#    .aimap   (related to vehicle/ped spawning for specific map config)
#    .reset   (player respawn point - pos then z rotation)
#    .sky     (global lighting rule)
#    .water   (global water height?)
#    .mtl     (Describes friction/collision values for all bbnd collision materials)
#    _lighting.csv
#/city/m01 /city/l01 #PROBABLY ALL LEFTOVER DEV FILES, seemingly not used
#    facades.csv
#    lighting.csv
#    propdefs.csv
#    proprules.csv
#/citylights
#    .lmp      (lamp)
#/frontend
#    .htm      (a version of very old html with extremely basic functionality)
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
#/anim
#    .mod      (ped model file, complete with materials)
#    .skel     (describes character rig)
#    .shaders  (Leftover dev data, unnecessary)
#    .anim     (animation file, requires .mod/.skel to work)
#/city
#    .inst (low-end) [might be rules for braking in corners for AI]
#    .inst    (Loads references to pkg files in the city, populates the city buildings + boundaries. Not required to load city)
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
#    .bai     (boundary AI - Tells AI where it can drive. Required for CTF to load, tells AI where to drive in races too)
#              This file also describes all 'street furniture' + traffic/pedestrian paths.
#              It probably draws splines related to where stuff needs to spawn.
#    .psdl    (map file - Required to load city. Contains all roads + road decals, some land pieces,
#              and describes textures, sidewalks, tunnels, various boundaries.
#/fonts
#    .strtbl  (in-sim textual content [AKA 'non-htm' text: Cutscenes, "next race", etc])
#    .fonttex (probably describes how the image file = characters, grid-based)

#           WORTHLESS
#           WORTHLESS
#/bound
#    .ter     (originally used to build bbnd files - but it's leftover dev data that is worthless!)
#/city   
#    .cpvs    (When removed, lost functionality was not clear. Unsure what this file does)
#/city/m01 /city/l01
#    .pathset (props, decals) [are likely leftover dev data blocks]
#/race/l01 /race/m01
#    .short   (Leftover dev data, unnecessary)