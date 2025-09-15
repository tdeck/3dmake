# 3DMake README
Thanks for trying 3DMake!

3DMake is a tool for designing, inspecting, and printing 3D models. Unlike most other such tools, it is designed for Blind and visually impaired people who need non-visual workflows for model design and 3D slicing.

[Here's a video (with screen reader audio) that shows what it can do.](https://www.youtube.com/watch?v=OCyDKVi6wAc)

3DMake provides the following functionality through a single command line tool:

- Designing 3D models using the OpenSCAD language
- Describing the shape of 3D models using AI
- Slicing STL files for your printer
- Automatically orienting models for optimal printing
- Downloading OpenSCAD libraries with 3DMake's library manager
- Preparing 2-dimensional "previews" of a model's shape that are very fast to print
- Sending sliced models directly to OctoPrint

## Setting up 3DMake
Download the latest version of 3DMake for your operating system by following these links:
- [Windows](https://github.com/tdeck/3dmake/releases/latest/download/3dmake_windows.zip)
- [Linux (x86-64)](https://github.com/tdeck/3dmake/releases/latest/download/3dmake_linux.tar.gz)

3DMake is a command line program, which means you need to run it from the terminal (or command prompt). If you've never used the terminal before, read the [terminal quick start guide](docs/terminal_quick_start.md).

To set up 3DMake, extract the release for your operating system and navigate to the 3DMake folder
in your terminal. Run `./3dm setup` and answer a few questions to complete the setup process.

Once this is done, `3dm` should be installed so that you can run it by simply typing 3dm in your terminal from any folder. Do not delete the original directory where you extracted 3DMake.

## Starting a new project

Although 3DMake can work with any OpenSCAD or STL files you've downloaded, it's most convenient to structure your own work in 3DMake projects. These projects are simply directories that are laid out in a certain way, with a src folder containing OpenSCAD code, a build folder containing outputs that 3DMake produced, and a 3dmake.toml file where you can set up different settings.

To start a new project in the current directory, run `3dm new`.

## Editing models

Model design in 3DMake is based on [OpenSCAD](https://openscad.org/), a text-based language for describing 3D models. OpenSCAD models are written in .scad files, which you can edit with any text editor. Something like Notepad++, Visual Studio Code, or even Notepad will work just fine.

You can open your project's main model in a text editor with `3dm edit-model` - this will simply open the file `src/main.scad`. You can select a different model name with the `-m` option when running 3DMake; if you want to edit the "lid.scad" model, you'd run `3dm edit-model -m lid`.

By default, 3DMake's edit commands use Notepad in Windows. To configure a different editor, you can set its path in the [3DMake configuration](#global-config) For example, to configure Notepad++ on Windows, you might add this line to your config:

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

As you can see, you can string together multiple actions when running 3DMake. For example, if you have set up OctoPrint, you can run `3dm build slice print` and have the model built from OpenSCAD source, sliced to GCODE, and sent to your printer! In fact, you can leave out "slice" here because `print` implies that 3DMake must slice, so it will do it even if you don't tell it to. To get a full list of the actions, you can always run `3dm help`.

## Configuring slicer settings

3DMake is based around PrusaSlicer, but it takes care of talking to the slicer for you because PrusaSlicer has accessibility issues. All of PrusaSlicer's settings are editable in 3DMake's text-based configuration files, which you can open in your favorite text editor. These files are in your 3DMake configuration folder, which you can find by running `3dm version`.

There are two kinds of slicer configuration. The first kind are printer profiles, which have a complete sets of default settings for each printer. The second kind are overlays, which are smaller and typically override a handful of settings. For example, the `supports` overlay enables supports, and the `PETG` overlay sets the appropriate temperatures for PETG printing, but they leave the other profile settings alone. 


You can list the available profiles by running `3dm list-profiles`, and the overlays by running `3dm list-overlays`. 3DMake comes with several built-in overlays for common materials. If you have one printer, you'll typically stick with the same default profile you set in `3dm setup`, but choose different overlays using the `-o` option of 3DMake. If you have more than one printer, you can choose to print with a non-default profile using the `-p` option.

You can create your own overlays by making new overlay files. Simply run `3dm edit-overlay -o NEWNAME` where `NEWNAME` is replaced with the name of the overlay you want to make. If your overlay only works on a specific printer, you can tell 3DMake during this process and it will be limited to that printer. For example, if you choose the printer profile Pr's_i3_MK3S, you can make a special overlays/prusa_i3_MK3S/supports.ini. When you are using that printer's profile, 3DMake will use your printer-specific overlay. When you ask for supports on another printer, it will use the default overlay.

These config files have one setting per line, with the setting name, an equals sign, and the setting value. Here are a few example lines:

```
top_solid_infill_speed = 50
top_solid_layers = 5
top_solid_min_thickness = 0.7
```

For options that are either on or off, the value is either 1 or 0. For other options, the value is usually a number as well. If you want to edit a particular option that you have heard of, I recommend opening your printer profile and searching for words from that option name. The most commonly changed options are listed in the overlay template at the end of this README, and this is a good start when creating your own overlays.

The `3dm edit-overlay` command will open an existing overlay for you in your text editor, and will create a new overlay for you if you give it an overlay name that doesn't exist. `3dm edit-profile` will similarly open a printer profile in your editor, although it isn't capable of creating new profiles for an entirely new printer.

## Orienting models

Sometimes the orientation of your model on the build plate can make a big difference in printing time and amount of support needed. 3DMake has an auto-orient function that you can add to your print. It will produce an oriented STL that can then be sliced and printed.

For example, `3dm build orient print` will build your OpenSCAD code as is, then produce an oriented STL file (e.g. build/main-oriented.stl), and then slice and print it.

## Previews

3DMake's preview functionality lets you print flat tactile "previews" of 3D models. These previews usually print in a few minutes, while printing a full model may take several hours. These previews can then be felt directly on the bed of your printer, allowing you to tweak the model or select something different to print.

Of course, they contain significantly less detail than the full model. Specifically, the previews are "silhouettes" which represent the outermost outlines of an object if it were squashed against a particular plane. For example, the silhouette of a pyramid would be a triangle (when viewed from the side), or a square (when viewed from the top or bottom). This is because the silhouette is the combination of all the widest outlines of a shape when viewed from a particular direction. A sphere's silhouette would be a circle when viewed from any angle. For more detailed info on silhouettes, read the [in depth doc on silhouette previews](docs/silhouettes.md).

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

# Producing images of models

The `3dm image` command allows you to make images of your models. These images will automatically be scaled to center the model and zoom in, and the model will sit on a grid indicating the x-y plane. The images will show the model when viewed from a particular angle, and these angles have names for your convenience. You select the angle by adding the `-a` option to the 3dm command, for example `3dm image -a front`.

The possible angle names are below (you can generate multiple images at once by using multiple -a options):

- `-a front` - Camera faces in the +x direction
- `-a back` - Camera faces in the -x direction
- `-a left` - Camera faces in the +y direction
- `-a right` - Camera faces in the -y direction
- `-a top` - Camera faces in the -z directoin
- `-a bottom` - Camera faces in the +z direction
- `-a above_front` - Camera faces in the +x, -z direction (looking down at an angle)
- `-a above_front_left` - Camrea faces in the +x. +y, -z direction (looking down at the front left corner)
- `-a above_front_right` - Camera faces in the -x, +y, -z direction (looking down at the front right corner)
- `-a above_back_left` - Camera faces in the 

The `3dm image` command places your images in the build directory with names indicating the model and view angle. For example, for the "main" model, images might be called "main-above_front_left.png", and "main-above_front_right.png".

The command also supports different color schemes for the model, background, and grid. This can be set with the `--colorscheme` option which has these possible values:

- `--colorscheme slicer_light` - Orange model. light gray background, green and blue grid lines
- `--colorscheme slicer_dark` - Orange model, almost black background, green and blue grid lines
- `--colorscheme light_on_dark` -White model, dark gray background, light gray grid lines

Default color scheme and angles can also be set in your 3dm config files.

# Working with files that aren't part of a project

3DMake can accept individual files to slice, orient, and preview even if they aren't part of a project. For example, you can do `3dm slice turtle.stl` or `3dm build orient print pyramid.stl`.

# Using OpenSCAD libraries

Libraries are collections of pre-written code that you can use in your projects. They can contain modules for useful shapes and transformations that save you a lot of time. 3DMake makes it easier to use popular OpenSCAD libraries with your project using the 3DMake library manager, which is the first package manager for OpenSCAD. You can easily libraries from the library manager to your project by adding a `libraries` line with a list of library names to your project's `3dmake.toml` file. Each 3DMake library has an all lowercase name with no spaces that uniquely identifies that library. You can get a list of available libraries and their documentation pages by running `3dm list-libraries`.

For example, let's say you want to use the [Belfry OpenSCAD library](https://github.com/revarbat/BOSL/wiki) in your project. You can add this line to your 3dmake.toml file:

```TOML
libraries = ["bosl"]
```

If you want to use more than one library, make sure to put each library name in quotes, and have a comma between them. So if you want to use `bosl` and [the `braille-chars` library](https://github.com/tdeck/3dmake_libraries/tree/main/braille-chars), you'd write this:
```TOML
libraries = ["bosl", "braille-chars"]
```

After updating your libraries list, be sure to run `3dm install-libraries`. This will download any library that isn't already on your machine. Then, when you run `3dm build`, the libraries you selected will be available to use with the [`include` and `use` statements](https://en.wikibooks.org/wiki/OpenSCAD_User_Manual/Include_Statement) in OpenSCAD. The first part of the import path will always be the library's lowercase name from your 3dmake.toml. For example, to make a pyramid using BOSL, you can do this in OpenSCAD:

```OpenSCAD
include <bosl/constants.scad>
use <bosl/shapes.scad>

pyramid(n=4, h=30, l=30);
```

You may notice that the BOSL library's documentation documents these imports in uppercase (e.g. `use <BOSL/shapes.scad>` rather than `use <bosl/shapes.scad>`. Some library authors expected their library to be used without an outer folder (e.g. dotSCAD's `use <line2d.scad>` vs the 3DMake version `use <dotscad/line2d.scad`). In order to prevent conflicts between libraries, 3DMake has standardized on always putting the library inside a folder with a lowercase name. So you may need to make small adjustments to the `include` or `use` lines when following examples library documentation.

### Local libraries

You can also include any folder of OpenSCAD code as a local library on your computer. This can be useful if you're developing a library you want to publish with 3DMake, or if you don't want to import files using an absolute path. To include a folder as a local library, add the path to the folder in your 3dmake.toml's `local_libraries` list like this:

```TOML
libraries = ["bosl", "braille-chars"]
local_libraries = ['''C:\custom_openscad_shapes''']  # The three apostrophe here allow you to use backslashes in your path
```

There is no need to run `3dm install-libraries` for local libraries. When you use local libraries, OpenSCAD treats the folder you listed as if it were the same top-level folder as your project. So in the example above, if you had a file at `C:\custom_openscad_shapes\mechanical.scad`, you'd access it with `use <mechanical.scad>` or `<include mechanical.scad>`.

If you come across and OpenSCAD library that you'd like to see included in 3DMake's library manager, please get in touch. I'd like to grow the list of libraries in the future.

<a name="global-config"></a>
## Global and project configuration (defaults.toml and 3dmake.toml)

You can customize a lot of things about 3DMake by editing either the defaults.toml file or a project's 3dmake.toml file with a text editor. The defaults.toml file can be opened by running `3dm edit-global-config`. Both of these files can contain the same set of settings, and settings in a project's 3dmake.toml file override the global defaults in your defaults.toml file. 

The table below lists possible settings, what they're for, and an example configuration line.

Setting         | Description                                   | Default value (if not set) | Example value
----------------|-----------------------------------------------|----------------------------|-------------
project_name    | The project's name, used to name GCODE files      | Project folder name           | `"gear clock"`
model_name      | The project's default model name                  | `"main"`                      | `"box_lid"`
view            | The default view to use in [previews](#Previews)  | `"3sil"`                        | `"topsil"`
printer_profile | The default printer profile name                  | What you set in 3dm setup     | `"prusa_MK4"`
scale           | Uniform scale factor when slicing the model       | `1.0`                         | `1.05`
overlays        | Default overlays to apply when printing           | `[]` (empty list)             | `["supports"]`
octoprint_host  | The URL of your OctoPrint instance                | What you set in 3dm setup     | `"http://192.168.1.10"`
octoprint_key   | The OctoPrint API key (do not share this)         | What you set in 3dm setup     | `"7025A..."`
auto_start_prints | When uploading to `3dm print`, start the print right away | `true`              | `false`
strict_warnings | Fail `3dm build` when OpenSCAD sees a problem with your code | `false`[^1]           | `true`
editor          | Command to open your preferred text editor        | "notepad" in Windows[^2]      | `"code"`
edit_in_background | Exit 3DMake after starting an editor           | `true` when using Notepad, `false` otherwise     | `false`
gemini_key      | Your Gemini API key (do not share this)           | What you set in 3dm setup     | `"47b64..."`
llm_name        | The name of the gemini model to use               | Depends on 3dmake version     | `"gemini-2.5-pro"`
interactive     | Whether to make `3dm info` interactive by default[^3] | `false`                       | `true`
libraries       | List of libraries to use in your project          | `[]` (empty list)             | `["bosl", "dotscad"]`
local_libraries | List of library paths to use in project           | `[]` (empty list)             | `["/home/troy/3d/example"]`
image_angles    | List of viewpoint angle names to use in image export | `["above_front_left", "above_front", "above_front_right"]` | `["top"]`
colorscheme     | Color scheme name to use in image export | `"slicer_dark"` | `"slicer_light"`
debug           | Output a lot more messages when running 3DMake    | `false`                       | `true`

Some of these settings can be further overridden on the command line (for example, `-m` overrides `model_name`, and `-i` overrides `interactive)`. In fact, all of the command line options are reflected here.

[^1]: `strict_warnings` is `false` in your global config, but it's `true` for 3dmake.toml files in newly created projects. This is because if you are trying to build OpenSCAD files you downloaded directly, many of them will produce warnings and be broken by a global setting of `true`. However, setting this to `true` for your new code is a good idea.

[^2]: In Linux, 3DMake tries to use your existing `VISUAL` and `EDITOR` environment variables if you don't set an editor. If it finds none of those, it uses GNU Nano.

[^3]: If your text editor opens a new window, you generally want this to be true so you can keep the editor open and still use 3DMake in your terminal window. However, if your editor runs in the terminal (like Vim, for example), it will be broken by this setting.
