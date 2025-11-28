# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
- No formal test suite is present in the main codebase
- Testing appears to be manual through the CLI interface
- Sample projects exist in `troys_local_sample_poject/` for testing

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
- `stream_wrappers.py`: Output formatting and indentation

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

### Key Design Patterns
- **Action Pipeline**: Sequential execution of configurable actions
- **Context Passing**: Shared state object passed between all actions
- **Decorator-based Registration**: Actions self-register using decorators
- **File State Tracking**: FileSet tracks intermediate outputs through pipeline
- **Configuration Layering**: Multiple TOML files with override precedence
- **Cross-platform Bundling**: External tools bundled in `deps/` directory