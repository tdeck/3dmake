# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Design advice
Please ask for clarification when necessary when responding to requests.

When extending existing code to a new use case, it's better to refactor the existing code cleanly rather than adding a patch around it. For example, if we have a function that produces metadata objects and JSON serializes them, and we now need one that produces similar metadata in YAML with a couple added fields, it's better to factor out the logic for the common metadata into a new function that returns a dict, then add JSON and YAML functions. It's not good to take the JSON function and write a wrapper that deserializes it, adds a couple fields, and then serializes it into YAML. This principle generalizes

## Commands

### Development Environment
- **Dependencies**: Uses Pipenv for dependency management
  - `pipenv install` - Install dependencies
  - `pipenv shell` - Activate virtual environment
  - Python 3.13 is required (see Pipfile)

### Running the Application
- **Main entry point**: `python 3dm.py` or `./3dm.py` (executable Python script)
- **Common commands**:
  - `python 3dm.py setup` - Initial configuration setup
  - `python 3dm.py new` - Create new 3DMake project
  - `python 3dm.py build` - Build OpenSCAD model to STL
  - `python 3dm.py build slice` - Build and slice to GCODE
  - `python 3dm.py build slice print` - Full pipeline to printing
  - `python 3dm.py help` - Show all available actions

### Testing
- E2E tests live in `e2e_test.py`, run with `pytest e2e_test.py`
- Test fixture files (STL, SCAD, sample projects) live in `test_fixtures/`

## Coding Style

### Comments
- Avoid obvious comments that merely restate what the code does
- Only add comments when they explain *why* something is done or provide non-obvious context
- Examples of comments to avoid:
  - `# Load existing cache if it exists` (obvious from the code)
  - `# Check if we need to fetch` (obvious from the conditional)
  - `# Update cache with new timestamp` (obvious from the assignment)
- Prefer clear variable names and simple code structure over explanatory comments
- Docstrings should be concise and focus on the function's purpose, not implementation details

## Architecture Overview

### Core Architecture
3DMake follows a **command-action pipeline architecture** where:
1. Commands are parsed from CLI arguments into "verbs" (actions)
2. Actions can imply other actions (e.g., `print` implies `slice`)
3. Actions run in sequence, passing a shared `Context` object
4. Each action can be either `isolated` (runs alone) or `pipeline` (part of a workflow)

### Key Components

#### Main Entry Point (`3dm.py`)
- Parses command-line arguments using argparse
- Loads configuration from TOML files (global `defaults.toml` + project `3dmake.toml`)
- Builds a `Context` object with options, file paths, and config directory
- Executes actions in sequence from `ALL_ACTIONS_IN_ORDER`

#### Action Framework (`actions/framework.py`)
- **Context**: Shared state object containing config, file paths, and intermediate results
- **Action**: Dataclass defining action metadata and implementation
- **Decorators**:
  - `@isolated_action`: Actions that run alone (setup, help, version)
  - `@pipeline_action`: Actions that are part of build/print workflows
  - `@internal_action`: Internal steps that don't show user output

#### Core Types (`coretypes.py`)
- **CommandOptions**: Configuration settings merged from defaults.toml, 3dmake.toml, and CLI args
- **FileSet**: Tracks input files and outputs through the pipeline (scad → stl → oriented_stl → gcode)
- **MeshMetrics**: 3D mesh analysis data (bounding box, dimensions)

#### Actions (`actions/` directory)
Actions are organized by functionality:
- **Project management**: `new_action.py`, `edit_actions.py`
- **Build pipeline**: `build_action.py`, `measure_action.py`, `orient_action.py`, `slice_action.py`
- **Output**: `preview_action.py`, `image_action.py`, `print_action.py`
- **Information**: `info_action.py`, `list_config_actions.py`, `help_action.py`
- **Setup**: `setup_action.py`, `library_actions.py`

#### Utilities (`utils/` directory)
- `openscad.py`: OpenSCAD integration and STL generation
- `renderer.py`: 3D model rendering for images and analysis
- `print_config.py`: PrusaSlicer configuration management
- `ftp.py`: Bambu Labs printer FTP integration
- `prompts.py`: CLI interaction utilities

### Configuration System
- **Global config**: `~/.config/3dmake/defaults.toml` (via platformdirs)
- **Project config**: `./3dmake.toml` in project directory
- **Printer profiles**: `~/.config/3dmake/profiles/` (PrusaSlicer INI format)
- **Overlays**: `~/.config/3dmake/overlays/` (setting modifications)
- Settings cascade: defaults.toml → 3dmake.toml → CLI arguments

### File Processing Pipeline
1. **Input**: OpenSCAD `.scad` files or STL files
2. **Build**: OpenSCAD → STL conversion
3. **Measure**: Extract mesh metrics (dimensions, bounds)
4. **Orient**: Auto-orient for optimal printing (optional)
5. **Preview**: Generate 2D "silhouette" previews (optional)
6. **Slice**: PrusaSlicer integration for GCODE generation
7. **Print**: Send to OctoPrint or Bambu Labs printers

### Dependencies and External Tools
- **OpenSCAD**: 3D modeling (bundled in `deps/` for Windows)
- **PrusaSlicer**: Slicing engine (bundled in `deps/` for Windows)
- **VTK/vtkplotlib**: 3D mesh processing and rendering
- **Tweaker3**: Auto-orientation algorithm
- **Google Generative AI**: Model description via image analysis
- **paho-mqtt**: Bambu Labs printer communication

### Preview Planes

Preview planes generate 2D cross-sectional slices through a model at an arbitrary plane, producing an SVG and a thin extruded STL suitable for tactile graphics printing.

#### How they work

1. **SCAD definition** — The user places marker modules from `scad_library/3dmake/preview.scad` in their OpenSCAD source:
   ```scad
   use <3dmake/preview.scad>
   xy_preview_plane("level", 1);                           // XY plane named "level#1"
   translate([0, 0, 10]) xy_preview_plane("level", 2);    // XY plane named "level#2"
   xz_preview_plane("front");
   rotate([0, 0, 45]) xz_preview_plane("diagonal");
   ```
   Each module renders a pentagonal pyramid whose base defines the plane. The pyramid only renders when `$THREEDMAKE_PREVIEW_PLANE` matches its name, otherwise it only logs its name via `echo`.

2. **Build phase** (`build_action.py`) — During a normal build, OpenSCAD stderr is parsed for `_3dm_log_scalar` log lines. All available plane names are collected into `ctx.build_metadata.preview_plane_names`.

3. **Plane location** (`preview_action.py: build_and_locate_preview_plane`) — When the user runs `3dm preview --view level#1`, OpenSCAD is invoked again with `-D '$THREEDMAKE_PREVIEW_PLANE="level#1"'` so only that pyramid renders. The resulting STL is parsed to find the 5 extreme vertices (coordinates ≥ 100,000). Four of these are the square base corners; the fifth is an orientation marker on the +X side of the base that sticks out to `SIZE+1000` (making it the outlier by Euclidean distance from origin). The 4 corners are used to fit the plane and determine normal direction from the apex position. The marker direction from the corner centroid gives the in-plane `right` vector. This yields a `Plane(origin, normal, right)`.

4. **Projection** — OpenSCAD is called with `projection(cut=true)` after aligning the model so the target plane sits at z=0. The alignment uses a `multmatrix` built from `[plane_right, plane_up, n_hat]` as rows, where `plane_up = cross(n_hat, plane_right)`. This fully constrains the in-plane orientation so that rotating the plane marker in SCAD produces a correspondingly rotated cross-section in the output. Output: `{stem}-{plane_name}.svg`.

5. **SVG styling** — Path fill and stroke-width are updated in the SVG XML for tactile printing aesthetics.

6. **STL extrusion** — The SVG is extruded 0.6mm via `linear_extrude` to produce `{stem}-{plane_name}.stl`.

#### Key implementation details

- Preview planes always use the un-oriented model (`ctx.files.model`, not `oriented_model`) because plane coordinates are defined in the original SCAD coordinate system.
- `ensure_previewable_model` forces a fresh build when a preview plane is requested, since plane coordinates must match the current SCAD source.
- The `PLANE_TOLERANCE` for coplanarity checks is 1 unit (may need tuning).
- The orientation marker is identified as the outlier among the 5 far vertices using `argmax(|distance - median(distances)|)`, which works whether the marker is closer or farther than the corners depending on SIZE.
- Silhouette previews (`topsil`, `3sil`, etc.) are a separate code path using orthographic projection; they don't go through the plane location machinery.

#### Relevant files
- `scad_library/3dmake/preview.scad` — User-facing SCAD modules
- `scad_library/3dmake/_internal.scad` — `_3dm_log_scalar` logging helper
- `actions/preview_action.py` — All plane location, projection, and styling logic
- `actions/build_action.py` — Collects plane names from build stderr
- `utils/openscad.py` — Log line parsing (`_3DM_PATTERN` regex)

### Key Design Patterns
- **Action Pipeline**: Sequential execution of configurable actions
- **Context Passing**: Shared state object passed between all actions
- **Decorator-based Registration**: Actions self-register using decorators
- **File State Tracking**: FileSet tracks intermediate outputs through pipeline
- **Configuration Layering**: Multiple TOML files with override precedence
- **Cross-platform Bundling**: External tools bundled in `deps/` directory
