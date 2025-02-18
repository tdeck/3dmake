from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Literal, Union, List, Tuple


# For now this is a holding area for classes used in multiple places
# It will likely be refactored in the future

@dataclass(kw_only=True)
class CommandOptions:
    project_name: Optional[str] = None # This will be populated automatically with the project's parent dir if not overridden
    model_name: str = "main"
    view: str
    printer_profile: str
    scale: Union[float, Literal["auto"]] = 1.0
    overlays: List[str] = field(default_factory=list)
    octoprint_host: Optional[str] = None
    octoprint_key: Optional[str] = None
    auto_start_prints: bool = False
    debug: bool = False
    strict_warnings: bool = False # This will default to True in new projects though
    editor: Optional[str] = None
    edit_in_background: bool = False # This causes edit commands to open the editor in a BG process; breaks terminal editors
    gemini_key: Optional[str] = None
    interactive: bool = False


class FileSet:
    def __init__(self, options: CommandOptions):
        self.build_dir: Path = Path('build') # TODO based on options

        self.scad_source = Path("src") / f"{options.model_name}.scad"
        self.model = self.build_dir / f"{options.model_name}.stl"

    build_dir: Path
    scad_source: Optional[Path]
    model: Optional[Path]
    oriented_model: Optional[Path] = None
    projected_model: Optional[Path] = None
    sliced_gcode: Optional[Path] = None

    def model_to_project(self) -> Optional[Path]:
        return self.oriented_model or self.model

    def model_to_slice(self) -> Optional[Path]:
        return self.projected_model or self.oriented_model or self.model

    def final_output(self) -> Optional[Path]:
        """ Returns the most processed output file; which will be the command's final result in single file mode. """
        if self.sliced_gcode:
            return self.sliced_gcode

        return self.projected_model or self.oriented_model or (self.scad_source and self.model)

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


