from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Literal, Union, List, Tuple


# For now this is a holding area for classes used in multiple places
# It will likely be refactored in the future

@dataclass(kw_only=True)
class CommandOptions:
    min_3dmake_version: Optional[str] = None # This really only makes sense in project .toml files

    project_name: Optional[str] = None # This will be populated automatically with the project's parent dir if not overridden
    model_name: str = "main"
    view: str
    printer_profile: str
    copies: int = 1
    scale: Union[float, Literal["auto"]] = 1.0
    overlays: List[str] = field(default_factory=list)
    auto_start_prints: bool = False
    debug: bool = False
    strict_warnings: bool = False # This will default to True in new projects though
    editor: Optional[str] = None
    edit_in_background: bool = False # This causes edit commands to open the editor in a BG process; breaks terminal editors
    interactive: bool = False

    # Libraries
    libraries: List[str] = field(default_factory=list)
    local_libraries: List[str] = field(default_factory=list) # Note: these should contain paths

    # Printer connection mode
    print_mode: str = 'octoprint' # Options are "octoprint", "bambu_lan", and "bambu_connect"

    # Octoprint
    octoprint_host: Optional[str] = None
    octoprint_key: Optional[str] = None

    # Bambu labs
    bambu_host: Optional[str] = None
    bambu_serial_number: Optional[str] = None
    bambu_access_code: Optional[str] = None

    # LLM config
    #
    # Priority order (first one configured wins):
    #   1. openai_compat_host — local/self-hosted servers (Ollama, LM Studio, llama.cpp, ramalama, …)
    #   2. openrouter_key     — OpenRouter cloud API (default cloud path)
    #   3. gemini_key         — Google Gemini API
    #
    # llm_name is used by all three backends.  The default is a string
    # OpenRouter model so that setting only openrouter_key "just works".
    gemini_key: Optional[str] = None
    openrouter_key: Optional[str] = None

    # Generic OpenAI-compatible host for local/self-hosted LLMs.
    # Set to the bare server URL, e.g. "http://localhost:11434" (Ollama) or
    # "http://localhost:1234" (LM Studio).  The /v1 suffix is added automatically.
    # Takes precedence over openrouter_key when both are set.
    openai_compat_host: Optional[str] = None
    openai_api_key: Optional[str] = None

    # Default model used by whichever backend is active.
    # Works out of the box with openrouter_key; swap for a local model name
    # (e.g. "llava", "llama3.2-vision") when using openai_compat_host.
    llm_name: str = 'gemini-2.5-pro'

    # Image rendering
    image_angles: List[str] = field(default_factory=lambda: ['above_front_left', 'above_front', 'above_front_right'])
    colorscheme: str = "slicer_dark"
    image_size: str = "1080x720"

    # SVG preview options
    svg_stroke_width: float = 1
    svg_fill_color: str = 'oldLace'


class FileSet:
    def __init__(self, options: CommandOptions, project_root: Optional[Path]):
        if project_root:
            self.build_dir = project_root / "build"
            self.scad_source = project_root / "src" / f"{options.model_name}.scad"
            self.model = self.build_dir / f"{options.model_name}.stl"
        self.rendered_images = {}

    # This will only stay null if not initialized properly or not needed
    build_dir: Optional[Path] = None
    explicit_input_file: Optional[Path] = None
    scad_source: Optional[Path] = None
    model: Optional[Path] = None

    oriented_model: Optional[Path] = None
    projected_model: Optional[Path] = None
    preview_svg: Optional[Path] = None
    sliced_gcode: Optional[Path] = None
    rendered_images: dict[str, Optional[Path]]

    def model_to_project(self) -> Optional[Path]:
        return self.oriented_model or self.model

    def model_to_slice(self) -> Optional[Path]:
        return self.projected_model or self.oriented_model or self.model

    def final_outputs(self) -> list[Path]:
        """ Returns the most processed output file; which will be the command's final result in single file mode. """
        if self.sliced_gcode:
            return [self.sliced_gcode]

        if self.rendered_images:
            return list(self.rendered_images.values())

        if self.projected_model:
            outputs = [self.projected_model]
            if self.preview_svg:
                outputs.append(self.preview_svg)
            return outputs

        res = self.oriented_model or (self.scad_source and self.model)

        if res:
            return [res]
        else:
            return []

@dataclass
class Thruple:
    x: float
    y: float
    z: float

@dataclass
class MeshMetrics:
    xrange: Tuple[float, float]
    yrange: Tuple[float, float]
    zrange: Tuple[float, float]

    def sizes(self) -> Thruple:
        return Thruple(
            self.xrange[1] - self.xrange[0],
            self.yrange[1] - self.yrange[0],
            self.zrange[1] - self.zrange[0]
        )

    def midpoints(self) -> Thruple:
        return Thruple(
            (self.xrange[1] + self.xrange[0]) / 2,
            (self.yrange[1] + self.yrange[0]) / 2,
            (self.zrange[1] + self.zrange[0]) / 2,
        )