# Developer documentation
This developer documentation is very much a work in progress. If you're working on 3DMake and are confused by anything, please let Troy know and he'll document that part better.

It's always better to document what a field or datatype means in the code, rather than somewhere else. Prefer meaningful names + comments that don't require external documentation.

## Program structure
3DMake is a Python program that ships with two embedded binaries (OpenSCAD for building models, and PrusaSlicer for slicing).  Python dependencies are managed using [PipEnv](https://pipenv.pypa.io/en/latest/). The entry point is `3dm.py`. This top level file mainly loads configuration from your global config, the project 3dmake.toml, and the command line, and figures out what to do next.

Running 3DMake means invoking one or more top-level commands called actions (for example, `new`, `build`, and `slice` are all actions). These actions are defined in functions in the `actions/` folder, and the selected actions will be run in a specific order according to the list in (actions/__init__.py)[../actions/__init__.py]. So evn if

Actions receive arguments and input from previous steps through an argument of type `Context` (defined in [framework.py](../actions/framework.py). Some parts of this `Context` are mutated during the course of a run by the various actions. This is (unfortunately) an implicit way of passing information around.

When actions generate files, they should be attached to `FileSet` in (coretypes.py)[../coretypes.py]. Generated files should be placed in the `build_dir` which is `./build` for 3DMake projects, and a temp directory when working with ad-hoc models (e.g. `3dm slice foo.stl`). These files should have a naming scheme that is derived from the model name and references what was done to them (e.g. `modelname-oriented-topsil.stl`).

Functions used by more than one action should be placed in a file in the (utils directory)[../utils].

### Current model
3DMake has a concept of the "current model" which saves the user a lot of typing when working in a 3DMake project. If you're running 3DMake with an explicit input file from the command line (e.g. `3dm info pikachu.stl`) then the current model will be that input file. Otherwise, if you're in a 3DMake project, it will be `main.stl` by default. You can change it in `3dmake.toml` using the `model_name` property, and you can change it on the command line using the `-m` option (note: `-m` is the name of the model, NOT the name of the SCAD file, so if you have a `src/assembly.scad` you'd do `-m assembly`).


## Release builds
In order to avoid making the user install Python and a bunch of dependences, we use [PyInstaller](https://pyinstaller.org/en/stable/) to create a directory with an executable entry point. PyInstaller can also bundle everything into an EXE, but we don't do that because it works by extracting the EXE every single time, and we have very large bundled binaries that would be inefficient to extract.

Release builds must be created on the operating system they're targeting. To make a release build, you must first install pipenv and pyenv. Then cd into the 3dmake repo's root directory and run `pipenv install`. Finally, you can run one of the build scripts `scripts/linux_build.sh` or `scripts/windows_build.ps1` from the repo's root dir.

### Steps to make a new release:
For now Troy will make all the releases, following this process:

1. Bump the version in version.py and check in
2. Tag the version (`git tag v0.123`) and push it (`git push origin v0.123`)
3. Create a draft release based on that tag
4. Run the build scripts in each OS, test the result, and upload them to GitHub
5. Read through git log from the last release and write release notes
