Thanks for trying 3dmake!

3dmake is a tool for designing, inspecting, and printing 3D models. Unlike most other such tools, it is designed for Blind and visually impaired people who need non-visual workflows for model design and 3D slicing.

3dmake provides the following functionality through a single command line tool:

- Compiling OpenSCAD code to produce STL files
- Describing the shape of 3D models using AI
- Slicing STL files for your printer
- Configuring printing options
- Auto-orienting prints before slicing
- Preparing 2-dimensional "previews" of a model's shape that are very fast to print
- Sending sliced models directly to OctoPrint

## Setting up 3Dmake

To set up 3dmake, extract the release for your operating system (Windows or 64 bit Linux) and navigate to the 3dmake folder
in your terminal. Run `./3dm setup` and answer a few questions to complete the setup process.

Once this is done, `3dm` should be installed so that you can run it by simply typing 3dm in your terminal from any folder. Do not delete the original directory where you extracted 3dmake.

## Starting a new project

Although 3dmake can work with any OpenSCAD or STL files you've downloaded, it's most convenient to structure your own work in 3dmake projects. These "projects" are simply directories that are laid out in a certain way, with a src folder containing OpenSCAD code, a build folder containing outputs that 3dmake produced, and a 3dmake.toml file where you can set up different settings.

To start a new project in the current directory, run `3dm new`.

## Editing models

3DMake is based on OpenSCAD, and OpenSCAD's .scad files can be edited in any text editor. There is *no need to install OpenSCAD* or to use the OpenSCAD editor. Something like Notepad++, Visual Studio Code, or even Notepad will work just fine.

As a shortcut, you can use the `3dm edit-model` in your project folder to open the SCAD file in a text editor. By default, this will use your system's text editor. To configure a specific one, you can set its path in `3dmake.toml` or in your system 3dmake config directory's `defaults.toml` file. For example, to configure Notepad++ on Windows, you might add this line to your config:

```
# The triple quotes below allow your program's path to contain backslashes
editor = '''C:\Program Files (x86)\Notepad++\notepad++.exe'''
```

## Describing models

The `3dm info` command will describe a model for you. If you have not configured Gemini during the setup process, it only describes the dimensions of the model's bounding box.  If you have configured Gemini, it will render the model from multiple angles, send all the images to Gemini along with a prompt, and return a description of the model. Gemini has been asked to call out any obvious flaws in the model if they exist.

Large language models and AI image processing have unpredictable shortcomings. Do not rely too strongly on these descriptions alone, although they can be a good way to pre-qualify models before printing them. 

## Building, slicing and printing

If you have an OpenSCAD project and you want a 3d model, you can run `3dm build`. By default, 3dm will build your main model and produce an STL file in your project's build directory (e.g. build/main.stl). This is useful if you want to send the STL file to someone, or use your own slicer (like Simplify3D) to slice it.

To build *and* slice the model, run `3dm build slice`. This will both build the model and slice it, producing an STL file and a .gcode file. The .gcode file's name will also have the project name, which makes it easier to differentiate different projects if you upload your files to OctoPrint or save them in an SD card.

As you can see, you can string together multiple actions when running 3dmake. For example, if you have set up OctoPrint, you can run `3dm build slice print` and have the model built from OpenSCAD source, sliced to GCODE, and sent to your printer! In fact, you can leave out "slice" here because `print` implies that 3dmake must slice, so it will do it even if you don't tell it to. To get a full list of the actions, you can always run `3dm help`.

## Configuring slicer settings

3dmake is based around PrusaSlicer, but it takes care of talking to the slicer for you because PrusaSlicer has accessibility issues. All of PrusaSlicer's settings are editable in 3dmake's text-based configruation files, which you can open in your favorite text editor. These files are in your 3dmake configuration folder, which you can find by running `3dm version`

There are two kinds of files in this directory. The ones in the profiles folder are complete sets of default settings for each printer. The files in the overlays folder are smaller collectiosns of settings. If you have one printer, you'll typically stick with the same profile, but choose different overlays using the -o option of 3dmake. One overlay that comes built in is the "supports" overlay, which (as you might guess) enables automatic supports.

You can create your own overlays by making new .ini files in the overlays/default folder. If your overlay only works on a specific printer, you can put an overlay in the overlays/PRINTER_NAME folder. For example, if you choose the printer profile prusa_i3_MK3S, you can make a special overlays/prusa_i3_MK3S/supports.ini. When you are using that printer's profile, 3dmake will use your printer-specific overlay. When you ask for supports on another printer, it will use the default overlay.

These config files have one setting per line, with the setting name, an equals sign, and the setting value. Here are a few example lines:

```
top_solid_infill_speed = 50
top_solid_layers = 5
top_solid_min_thickness = 0.7
```

For options that are either on or off, the value is either 1 or 0. For other options, the value is usually a number as well. If you want to edit a particular option that you have heard of, I recommend opening your printer profile and searching for words from that option name. The most commonly changed options are listed in the overlay template at the end of this README, and this is a good start when creating your own overlays.

The `3dm edit-overlay` command will open an existing overlay for you in your text editor, and will create a new overlay for you if you give it an overlay name that doesn't exist. `3dm edit-profile` will similarly open a printer profile in your editor, although it isn't capable of creating new profiles for an entirely new printer.

## Orienting models

Sometimes the orientation of your model on the build plate can make a big difference in printing time and amount of support needed. 3dmake has an auto-orient function that you can add to your print. It will produce an oriented STL that can then be sliced and printed.

For example, `3dm build orient print` will build your OpenSCAD code as is, then produce an oriented STL file (e.g. build/main-oriented.stl), and then slice and print it.

## Previews

3dmake's preview functionality lets you print flat tactile "previews" of 3D models. These previews usually print in a few minutes, while printing a full model may take several hours. These previews can then be felt directly on the bed of your printer, allowing you to tweak the model or select something different to print.

Of course, they contain significantly less detail than the full model. Specifically, the previews are "silhouettes" which represent the outermost outlines of an object if it were squashed against a particular plane. For example, the silhouette of a pyramid would be a triangle (when viewed from the side), or a square (when viewed from the top or bottom). This is because the silhouette is the combination of all the widest outlines of a shape when viewed from a particular direction. A sphere's silhouette would be a circle when viewed from any angle.

To slice a preview, use `3dm preview slice`, or to print do `3dm preview print`. The default preview is called `3sil`, and it includes 3 separate silhouettes of the object. In the front right you can feel the silhouette of the object when viewed from the front. To the left, is the silhouette viewed from the left. And above is the silhouette of the object when viewed from the bottom. You will find that the bottom, right, and back views are simply mirror images of the top, left, and front views, so we save filament by not printing them.

It's a good idea to get familiar with how the previews correspond to the shapes of 3d prints, and their limitations. By printing previews of objects you've already printed, you can develop a feel for how the preview functionality can help you save time when checking your models.

The orientation affects the preview as well. If you run `3dm orient preview print`, you'll often get a different result since the model is oriented *before* the preview is made.

The preview's "view" can be changed using the -v option. Here are the possible preview values:

- -v 3sil - The standard 3-silhouette composite preview
- -v frontsil - Silhouette from the front
- -v backsil - Silhouette from the back
- -v leftsil - Silhouette from the left
- -v rightsil - Silhouette from the right
- -v topsil - Silhouette from the top

# Working with files that aren't part of a project

3dmake can accept individual files to slice, orient, and preview even if they aren't part of a project. For example, you can do `3dm slice turtle.stl` or `3dm build orient print pyramid.stl`.

## Overlay template

You can use this template to help bootstrap a new overlay. It contains the most common options with example values. Delete any lines you don't want the overlay to modify. If you need additional control over any aspect of your print, there are additional settings to be found in the profile files.

Lines beginning with a semicolon are comments that are ignored by the slicer.

```
layer_height = 0.2
nozzle_diameter = 0.4

; Temperature
temperature = 205
bed_temperature = 60

; Speed
max_print_speed = 200
infill_speed = 180
perimeter_speed = 120
retract_speed = 30

; Infill
fill_density = 15%
; pattern can be grid, gyroid, stars, rectilinear, triangles, etc...
fill_pattern = grid

; Support
; support_material can be 1 (on) or 0 (off)
support_material = 1
; support_material_style can be grid, snug, or organic
support_material_style = grid
support_material_pattern = rectilinear
support_material_interface_layers = 2
support_material_interface_pattern = rectilinear
support_material_interface_spacing = 0.2

; Model strength
; perimeters is the wall thickness, in lines
perimeters = 2
bottom_solid_layers = 2
top_solid_layers = 2

; Build plate adhesion
; Skirts is the number of loops
skirts = 1
min_skirt_length = 100
; brim_width is in mm
brim_width = 3
raft_layers = 3
```
