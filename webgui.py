"""3DMake NiceGUI prototype.

Runs in a native window via pywebview. Launch with:
    uv run python webgui.py

This is a parallel prototype to the PySide6 gui.py on the pyside6-gui branch.
It exists to explore whether browser-based accessibility (via NiceGUI's HTML
output) works better than Qt's macOS bridge, especially for VoiceOver users.

Design notes:
- Single-workspace prototype: opening a new file replaces the current view.
- All state lives in a module-level `state` object; page functions are
  re-entered fresh whenever the user navigates.
- Subprocesses to `3dm.py` are streamed via asyncio; each line is pushed
  to a `ui.log` widget marked aria-live=polite so screen readers announce
  new lines without stealing focus.
"""
import asyncio
import os
import platform
import sys
import tempfile
import tomllib
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Coroutine, Optional

import webview
from webview.menu import Menu, MenuAction, MenuSeparator
from nicegui import app, ui
from platformdirs import user_config_path

from utils.global_settings import load_global_settings, save_global_settings
from utils.print_config import (
    list_overlays,
    list_printer_profiles,
    read_profile_config,
    write_overlay_file,
    ProfileConfig,
)
from utils.scad_snippets import NAMED_PROJECTION_CODE


# ---------------------------------------------------------------------------
# Constants (mirrored from gui.py on pyside6-gui to keep visual/behaviour parity)
# ---------------------------------------------------------------------------

CONFIG_DIR = (
    Path(os.environ["THREEDMAKE_CONFIG_DIR"])
    if "THREEDMAKE_CONFIG_DIR" in os.environ
    else user_config_path("3dmake", None)
)

THREEDMAKE_SCRIPT = Path(__file__).parent / "3dm.py"

PROJECTION_LABELS = {
    "3sil": "3 silhouettes (front, top, left)",
    "topsil": "silhouette from top",
    "leftsil": "silhouette from left",
    "rightsil": "silhouette from right",
    "frontsil": "silhouette from front",
    "backsil": "silhouette from back",
}

DESTINATION_3D_PRINTER = "3D Printer"
DESTINATION_EMBOSSER = "Embosser (SVG)"

MODE_GCODE = "gcode"
MODE_OCTOPRINT = "octoprint"
MODE_BAMBU_CONNECT = "bambu_connect"

BAMBU_CONNECT_DOWNLOAD_PAGE = "https://wiki.bambulab.com/en/software/bambu-connect"

# Same colours as the PySide6 build so the visual language matches.
CHANGED_COLOR = "#d4900a"
OVERLAY_COLOR = "#2b7de9"


# ---------------------------------------------------------------------------
# Module-level workspace state
# ---------------------------------------------------------------------------

@dataclass
class WorkspaceState:
    stl_path: Optional[Path] = None
    profile_name: Optional[str] = None
    profile_config: Optional[ProfileConfig] = None
    selected_overlays: list[str] = field(default_factory=list)
    # key -> string; only entries whose value differs from the merged profile.
    edited_values: dict[str, str] = field(default_factory=dict)


state = WorkspaceState()


@dataclass
class ProjectState:
    """State for a 3DMake project (a folder containing 3dmake.toml)."""

    project_path: Optional[Path] = None  # folder containing 3dmake.toml
    project_name: Optional[str] = None   # display name (from toml or dir basename)
    scad_files: list[Path] = field(default_factory=list)  # absolute paths, sorted
    current_file: Optional[Path] = None  # file currently in the editor
    # In-memory buffers: current text for each file the user has touched.
    # Populated lazily on first open. Keyed by absolute Path.
    buffers: dict[Path, str] = field(default_factory=dict)
    # Disk snapshot per file - what was last read from or written to disk.
    # A file is dirty iff buffers[p] != disk_snapshots[p].
    disk_snapshots: dict[Path, str] = field(default_factory=dict)
    # Populated by project_page while active - lets module-scope handlers
    # (menu items, global keyboard shortcuts) reach into the currently-rendered
    # page without those handlers being page-scoped closures. Cleared / re-set
    # whenever project_page re-renders.
    save_fn: Optional[Callable[[], None]] = None
    # F5 (examine current model). Async because it awaits a subprocess.
    examine_fn: Optional[Callable[[], Coroutine]] = None

    def is_dirty(self, p: Path) -> bool:
        return p in self.buffers and self.buffers[p] != self.disk_snapshots.get(p, "")


project_state = ProjectState()


def load_project(folder: Path) -> None:
    """Populate project_state for the given folder. Caller is responsible
    for having already validated that folder / 3dmake.toml exists."""
    toml_data: dict = {}
    try:
        toml_data = tomllib.loads((folder / "3dmake.toml").read_text())
    except (OSError, tomllib.TOMLDecodeError):
        # Fall through with empty toml_data - we still open the project.
        pass

    project_state.project_path = folder
    project_state.project_name = toml_data.get("project_name") or folder.name
    src_dir = folder / "src"
    project_state.scad_files = (
        sorted(src_dir.rglob("*.scad")) if src_dir.is_dir() else []
    )
    project_state.current_file = (
        project_state.scad_files[0] if project_state.scad_files else None
    )
    project_state.buffers = {}
    project_state.disk_snapshots = {}


# ---------------------------------------------------------------------------
# UI design note: `@ui.refreshable` vs update-in-place
# ---------------------------------------------------------------------------
#
# NiceGUI's `@ui.refreshable` is convenient - you call `.refresh()` and the
# function's UI is re-rendered. But every refresh destroys and recreates
# every DOM element the function created. That's a problem for any widget
# the user is currently interacting with:
#
#   * Keyboard focus disappears (browser falls back to <body> or similar).
#     For screen-reader users this is jarring and disorienting.
#   * Native <select> and <input> lose their in-flight state (typed value,
#     caret position, arrow-key selection).
#   * Any per-element JS state a Vue/Quasar component was holding is gone.
#
# Rule of thumb: use `.refresh()` only for regions the user is NOT focused
# on at refresh time - e.g. switching to a different setting category
# rebuilds the fields column, but the category listbox itself stays put.
# When a widget's *display* needs to change (its label, its aria-label,
# its border colour, its enabled state) update the relevant property in
# place on the existing element - no destroy, no focus loss:
#
#     opt._text = new_text
#     opt._props["aria-label"] = new_aria
#     opt.update()                          # syncs to the client
#
# Examples of this pattern in this file:
#   * `refresh_file_marker` in `project_page` - swaps the `*` / "unsaved"
#     marker on a single sidebar <option> without rebuilding the <select>.
#   * `apply_visual_state` in `build_slice_tab`'s `build_field_row` -
#     toggles the border-colour class and revert-button state on each
#     keystroke without rebuilding the input.
#
# History: we've hit this twice. First on the Slice tab's category
# listbox (fixed by splitting into a stable listbox + a refreshable-only
# fields column). Then on the project editor's source-file listbox
# (fixed by switching from `@ui.refreshable` to a build-once + update-in-
# place `refresh_file_marker`). If a new listbox / editable widget starts
# losing focus mid-interaction, this is almost certainly the cause.
#
# ---------------------------------------------------------------------------
# Subprocess streaming helper
# ---------------------------------------------------------------------------

async def stream_3dm(
    args: list[str],
    on_line: Callable[[str], None],
    cwd: Optional[Path] = None,
) -> int:
    """Run `python 3dm.py <args...>` and pass each stdout line to on_line.
    Optionally set the subprocess cwd - needed for project-mode actions
    like `build info` that look for 3dmake.toml in the working directory.
    Returns the process's exit code."""
    env = os.environ.copy()
    env["_3DMAKE_TEST_FLAGS"] = "GUI_MODE"
    env["PYTHONUNBUFFERED"] = "1"
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(THREEDMAKE_SCRIPT),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
        cwd=str(cwd) if cwd is not None else None,
    )
    assert proc.stdout is not None
    async for raw in proc.stdout:
        line = raw.decode(errors="replace").rstrip("\n")
        on_line(line)
    return await proc.wait()


# ---------------------------------------------------------------------------
# Reusable subprocess-output console
# ---------------------------------------------------------------------------

class OutputConsole:
    """A read-only, fixed-height, screen-reader-friendly text console for
    streaming subprocess output.

    Renders as a Quasar q-input in textarea mode with a proper floating
    label, so it's Tab-focusable and screen readers announce
    "<label>, edit text, <contents>" on focus. Fixed-height with an
    internal scrollbar (not autogrow) so it doesn't push everything else
    around as content streams in.
    """

    def __init__(self, label: str, height_em: float = 15) -> None:
        self.widget = ui.textarea(label=label).classes("w-full").props("readonly")
        # Direct _props to avoid quoting issues in the parsed props string.
        self.widget._props["input-style"] = (
            f"height: {height_em}em; overflow-y: auto; font-family: monospace;"
        )

    def push(self, line: str) -> None:
        """Append a single line of output. Called for each subprocess line."""
        self.widget.value = (
            f"{self.widget.value}\n{line}" if self.widget.value else line
        )

    def clear(self) -> None:
        self.widget.value = ""

    def set_visibility(self, visible: bool) -> None:
        self.widget.set_visibility(visible)

    def focus(self) -> None:
        """Move keyboard focus to the console. Quasar q-input exposes a
        focus() method on the Vue component, callable via run_method."""
        self.widget.run_method("focus")

    async def run_3dm(self, args: list[str], cwd: Optional[Path] = None) -> int:
        """Clear the console then stream `python 3dm.py <args>` output into it.
        Optional cwd for project-mode actions. Returns the exit code."""
        self.clear()
        return await stream_3dm(args, self.push, cwd=cwd)


# ---------------------------------------------------------------------------
# Settings dialog (invoked from startup page)
# ---------------------------------------------------------------------------

def show_settings_dialog() -> None:
    settings = load_global_settings(CONFIG_DIR)

    with ui.dialog() as dialog, ui.card().style("min-width: 480px"):
        ui.label("3DMake Settings").classes("text-h6")

        with ui.tabs() as tabs:
            printer_tab = ui.tab("Printer")
            ai_tab = ui.tab("AI")
        with ui.tab_panels(tabs, value=printer_tab).classes("w-full"):
            with ui.tab_panel(printer_tab):
                mode_radio = ui.radio(
                    {
                        MODE_GCODE: "Save prints as GCODE",
                        MODE_OCTOPRINT: "Send prints to OctoPrint",
                        MODE_BAMBU_CONNECT: "Send prints to Bambu Connect",
                    },
                    value=settings.get("print_mode", MODE_GCODE),
                )

                # OctoPrint fields - shown only when that mode is picked.
                with ui.column().bind_visibility_from(mode_radio, "value", value=MODE_OCTOPRINT):
                    host_input = ui.input(
                        "Server URL",
                        value=settings.get("octoprint_host", ""),
                        placeholder="http://octopi.local",
                    ).classes("w-full")
                    key_input = ui.input(
                        "API Key",
                        value=settings.get("octoprint_key", ""),
                    ).classes("w-full")

                with ui.column().bind_visibility_from(mode_radio, "value", value=MODE_BAMBU_CONNECT):
                    ui.label(
                        "3DMake can send prints to your Bambu printer using "
                        "Bambu Connect, an accessible software tool you can "
                        "download from Bambu Labs."
                    )
                    ui.button(
                        "Open download page",
                        on_click=lambda: webbrowser.open(BAMBU_CONNECT_DOWNLOAD_PAGE),
                    )

                with ui.column().bind_visibility_from(mode_radio, "value", value=MODE_GCODE):
                    ui.label(
                        "The sliced GCODE file will be saved locally. "
                        "You can send it to your printer manually."
                    )

            with ui.tab_panel(ai_tab):
                ui.label("AI settings coming soon.")

        def save_and_close():
            new_settings = dict(settings)
            new_settings["print_mode"] = mode_radio.value
            new_settings["octoprint_host"] = host_input.value
            new_settings["octoprint_key"] = key_input.value
            save_global_settings(CONFIG_DIR, new_settings)
            dialog.close()

        with ui.row().classes("justify-end w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("OK", on_click=save_and_close).props("color=primary")

    dialog.open()


# ---------------------------------------------------------------------------
# Module-level action flows
# ---------------------------------------------------------------------------
#
# These async helpers implement the app's global actions - open an STL,
# open a project, create a new project, open settings, save the current
# project file. They live at module scope so both in-page callers (buttons,
# keyboard shortcuts) AND the native menu callbacks (which run outside any
# page context) can invoke them via the same code path.
#
# UI operations here (ui.navigate, ui.notify, opening dialogs) rely on being
# scheduled onto NiceGUI's asyncio loop. From a page callback that's already
# true; from a menu callback that runs on pywebview's thread we go through
# `_run_on_ui` (defined further down) to bridge.

async def _open_stl_flow() -> None:
    paths = await app.native.main_window.create_file_dialog(
        allow_multiple=False,
        file_types=("STL files (*.stl)", "All files (*.*)"),
    )
    if not paths:
        return
    state.stl_path = Path(paths[0])
    state.profile_name = None
    state.profile_config = None
    state.selected_overlays = []
    state.edited_values = {}
    ui.navigate.to("/workspace")


async def _open_project_flow() -> None:
    paths = await app.native.main_window.create_file_dialog(
        dialog_type=webview.FileDialog.FOLDER,
    )
    if not paths:
        return
    folder = Path(paths[0])
    if not (folder / "3dmake.toml").is_file():
        ui.notify(
            f"{folder.name} is not a 3DMake project (no 3dmake.toml).",
            type="warning",
        )
        return
    load_project(folder)
    ui.navigate.to("/project")


async def _new_project_flow() -> None:
    paths = await app.native.main_window.create_file_dialog(
        dialog_type=webview.FileDialog.FOLDER,
    )
    if not paths:
        return
    folder = Path(paths[0])
    # `3dm new` reads the target directory from stdin. Pipe "." so it
    # creates the project in `folder` (which we set as cwd here).
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(THREEDMAKE_SCRIPT),
        "new",
        cwd=str(folder),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate(input=b".\n")
    if proc.returncode != 0:
        ui.notify(
            f"3dm new failed: {stdout.decode(errors='replace')}",
            type="negative",
        )
        return
    load_project(folder)
    ui.navigate.to("/project")


async def _show_settings_flow() -> None:
    show_settings_dialog()


async def _save_from_menu() -> None:
    if project_state.save_fn is None:
        ui.notify("No project file open to save.", type="info")
        return
    project_state.save_fn()


async def _examine_from_menu() -> None:
    """F5 action - runs `3dm build info` on the currently-selected model.
    Delegates to the async closure published by project_page (which has
    access to the editor widget and the info panel/console)."""
    if project_state.examine_fn is None:
        ui.notify("No project file open to examine.", type="info")
        return
    await project_state.examine_fn()


def _install_global_shortcuts(
    *, include_save: bool = False, include_examine: bool = False,
) -> None:
    """Add ui.keyboard to the current page so keyboard shortcuts dispatch
    the same actions as the native menu items.

    Call from within a @ui.page function. Shortcuts fire on the NiceGUI
    (parent) process, so they call _dispatch_menu_action directly - no
    cross-process bridge needed. pywebview's MenuAction has no working
    accelerator field, which is why we implement the shortcuts here
    instead of on the menu items themselves.

    Shortcuts:
      Cmd/Ctrl+O           always
      Cmd/Ctrl+S           when `include_save` (project page only)
      F5                   when `include_examine` (project page only)
    """
    def on_key(e) -> None:
        if not e.action.keydown or e.action.repeat:
            return
        name = (e.key.name or "").lower()
        modded = e.modifiers.ctrl or e.modifiers.meta
        if modded and name == "o":
            _dispatch_menu_action("open_stl")
        elif modded and include_save and name == "s":
            _dispatch_menu_action("save")
        elif include_examine and name == "f5":
            # No modifier required; F5 alone triggers examine (page-wide,
            # not just when the editor is focused - so you can hit F5
            # while the sidebar has focus after picking a different file).
            _dispatch_menu_action("examine")

    # ui.keyboard's default `ignore` list already skips <input>, <select>,
    # <button>, <textarea> - so typing "o" or "s" in a real text input
    # won't trigger the shortcut. CodeMirror uses a contenteditable div
    # (not <textarea>) so Cmd+S / F5 while editing DO reach us. F5 is
    # also allowed to fire from the sidebar <select> because we don't
    # add 'select' to the ignore list... actually we do inherit the
    # default which includes 'select'. Override to only ignore real
    # text inputs so F5 works from the file listbox.
    ui.keyboard(on_key=on_key, ignore=["input", "textarea"])


# --- Menu bridge endpoint ---
#
# Hit by a browser fetch() dispatched from _menu_bridge (which runs in
# pywebview's child process). Runs on NiceGUI's asyncio loop in the
# parent process. We enter the current client's context so the flow's
# ui.notify / ui.navigate.to / ui.dialog calls target the actual open
# window rather than failing for lack of a client context. Returns
# immediately - the fetch is fire-and-forget from the browser's side.

@app.post("/_menu_bridge/{action}")
async def _menu_bridge_endpoint(action: str) -> dict:
    from nicegui.client import Client
    # In native mode there's one interactive client for the current page.
    # Pick the newest non-auto-index client.
    candidates = [
        c for c in Client.instances.values()
        if not getattr(c, "is_auto_index_client", False)
    ]
    if not candidates:
        return {"ok": False, "error": "no active client"}
    client = candidates[-1]
    with client:
        await _dispatch_menu_action_sync(action)
    return {"ok": True}


async def _dispatch_menu_action_sync(action: str) -> None:
    """Await-based dispatcher used by the menu bridge endpoint."""
    flows: dict[str, Callable[[], Coroutine]] = {
        "open_stl": _open_stl_flow,
        "open_project": _open_project_flow,
        "new_project": _new_project_flow,
        "settings": _show_settings_flow,
        "save": _save_from_menu,
        "examine": _examine_from_menu,
    }
    flow = flows.get(action)
    if flow is None:
        return
    await flow()

@ui.page("/")
def startup_page() -> None:
    ui.page_title("3DMake")
    _install_global_shortcuts()  # Cmd/Ctrl+O

    with ui.column().classes("q-pa-lg gap-3"):
        ui.label("3DMake").classes("text-h4")
        ui.label("Use the File menu to open an STL model or a project.")


# ---------------------------------------------------------------------------
# Workspace page
# ---------------------------------------------------------------------------

@ui.page("/workspace")
def workspace_page() -> None:
    if state.stl_path is None:
        ui.navigate.to("/")
        return

    _install_global_shortcuts()  # Cmd/Ctrl+O

    ui.page_title(f"3DMake - {state.stl_path.name}")

    # Compact-mode overrides. Quasar's default spacing is generous
    # (dashboard/marketing app style); for a desktop-tool UI it wastes a
    # lot of vertical real estate. Trim the biggest offenders: the tab-
    # panel padding, tab-header padding, ui.header height, separator
    # margins, dense-field height, and the default gap NiceGUI puts on
    # its rows and columns.
    ui.add_css(
        f"""
        /* -- edited/overlay field borders (see :before pseudo below) --*/
        .pf-edited .q-field__control:before {{
            border-color: {CHANGED_COLOR} !important;
            border-width: 2px !important;
        }}
        .pf-overlay .q-field__control:before {{
            border-color: {OVERLAY_COLOR} !important;
            border-width: 2px !important;
        }}

        /* -- compact-mode overrides -- */
        /* NiceGUI wraps every @ui.page body in .nicegui-content with q-pa-md.
           Cut that in half. */
        .nicegui-content {{
            padding: 8px !important;
            gap: 6px !important;
        }}
        /* Tab-panel padding is the single biggest waste - default 16px both axes. */
        .q-tab-panels .q-tab-panel {{
            padding: 8px 12px !important;
        }}
        /* Tab header (the row of tab titles) - default is quite tall. */
        .q-tab {{
            min-height: 36px !important;
            padding: 0 16px !important;
        }}
        .q-tabs__content {{
            min-height: 36px !important;
        }}
        /* App header + toolbar - default ~64px. */
        .q-header .q-toolbar {{
            min-height: 40px !important;
            padding: 0 12px !important;
        }}
        /* Separator vertical margin - default 8px each side. */
        .q-separator--horizontal {{
            margin: 4px 0 !important;
        }}
        /* NiceGUI rows/columns default to gap 1rem (16px). Halve it. */
        .nicegui-row, .nicegui-column {{
            gap: 8px;
        }}
        """
    )

    # Filename shown as an inline caption instead of a full header - the
    # native menu now carries the global actions that used to be in the header.
    ui.label(state.stl_path.name).classes("text-h6 q-mb-sm")

    with ui.tabs().classes("w-full") as tabs:
        examine_tab = ui.tab("Examine model")
        slice_tab = ui.tab("Slice")
        print_tab = ui.tab("Print")

    with ui.tab_panels(tabs, value=examine_tab).classes("w-full"):
        with ui.tab_panel(examine_tab):
            build_examine_tab()
        with ui.tab_panel(slice_tab):
            build_slice_tab()
        with ui.tab_panel(print_tab):
            ui.label("Print tab coming soon.")


# ---------------------------------------------------------------------------
# Project editor page
# ---------------------------------------------------------------------------

@ui.page("/project")
def project_page() -> None:
    if project_state.project_path is None:
        ui.navigate.to("/")
        return

    _install_global_shortcuts(
        include_save=True,      # Cmd/Ctrl+S
        include_examine=True,   # F5
    )

    ui.page_title(f"3DMake - {project_state.project_name}")

    # Project name as inline caption - the native menu carries global actions.
    ui.label(project_state.project_name or "").classes("text-h6 q-mb-sm")

    # Empty-project case: still show the caption above, but nothing to edit.
    if not project_state.scad_files:
        ui.label(
            f"No .scad files found under {project_state.project_path / 'src'}."
        ).classes("q-mt-md")
        return

    # These widgets are created below inside the row/column contexts but the
    # helper functions above them close over these names (late-bound - Python
    # resolves free variables at call time, not def time). Declaring them
    # None here just documents the shape.
    editor: Optional[ui.codemirror] = None
    editor_label: Optional[ui.label] = None
    info_expansion: Optional[ui.expansion] = None
    info_console: Optional[OutputConsole] = None

    def relative_display(p: Path) -> str:
        """Path relative to the project root - used in notifications,
        editor label, etc. where the src/ prefix carries useful context."""
        try:
            return str(p.relative_to(project_state.project_path))
        except ValueError:
            return str(p)

    def display_in_sidebar(p: Path) -> str:
        """Path shown in the sidebar listbox - relative to src/ so we don't
        waste horizontal space repeating the src/ prefix on every row.
        (Every file in the list is under src/ by construction.)"""
        src_dir = project_state.project_path / "src"
        try:
            return str(p.relative_to(src_dir))
        except ValueError:
            return relative_display(p)

    def save_current_file() -> None:
        p = project_state.current_file
        if p is None or editor is None:
            return
        text = editor.value
        try:
            p.write_text(text)
        except OSError as e:
            ui.notify(f"Save failed: {e}", type="negative")
            return
        project_state.buffers[p] = text
        project_state.disk_snapshots[p] = text
        refresh_file_marker(p)
        ui.notify(f"Saved {relative_display(p)}", type="positive")

    # Map of file Path -> its <option> element in the sidebar. Populated
    # when the list is first built (below). We update individual options in
    # place when their dirty state changes rather than refreshing the whole
    # <select>; the latter destroys the DOM element the user has focused
    # and drops keyboard focus on file switch.
    option_elements: dict[Path, ui.element] = {}

    def option_display(p: Path) -> str:
        rel = display_in_sidebar(p)
        return f"* {rel}" if project_state.is_dirty(p) else rel

    def option_aria_label(p: Path) -> str:
        rel = display_in_sidebar(p)
        return f"{rel}, unsaved" if project_state.is_dirty(p) else rel

    def refresh_file_marker(p: Path) -> None:
        """Update the visible text + aria-label for a single option so its
        dirty state (asterisk / 'unsaved') is current. Cheap - no
        rebuild - so it can be called on switch and on save without
        interfering with keyboard focus on the <select> itself."""
        opt = option_elements.get(p)
        if opt is None:
            return
        opt._text = option_display(p)
        opt._props["aria-label"] = option_aria_label(p)
        opt.update()

    def load_file_into_editor(new_path: Path) -> None:
        """Sync current editor content to buffers, then load new_path."""
        if editor is None:
            return
        # Sync current editor value into its buffer so switching away preserves edits.
        previous = project_state.current_file
        if previous is not None:
            project_state.buffers[previous] = editor.value

        project_state.current_file = new_path
        if new_path not in project_state.buffers:
            try:
                text = new_path.read_text()
            except OSError as e:
                ui.notify(f"Could not read {new_path.name}: {e}", type="negative")
                text = ""
            project_state.buffers[new_path] = text
            project_state.disk_snapshots[new_path] = text
        editor.set_value(project_state.buffers[new_path])
        if editor_label is not None:
            editor_label.text = relative_display(new_path)
        # Only the file we just left could have changed dirty state (its
        # buffer just got a fresh copy of editor.value). Update just its
        # marker - not the whole list - to preserve the select's focus.
        if previous is not None:
            refresh_file_marker(previous)

    async def examine_current_file() -> None:
        """F5 handler: save the current file if it has unsaved changes,
        then run `3dm -m <model> build info` from the project directory and
        stream output into the info console below the editor."""
        p = project_state.current_file
        if p is None or editor is None or info_expansion is None or info_console is None:
            return

        # Only save if there are unsaved changes - avoids a misleading
        # "Saved <name>" toast when nothing had changed.
        disk = project_state.disk_snapshots.get(p, "")
        if editor.value != disk:
            save_current_file()

        # Model name = the file's path relative to <project>/src/ with the
        # .scad extension stripped (matches how 3dm.py's -m flag maps a
        # model name to src/<name>.scad).
        try:
            rel_to_src = p.relative_to(project_state.project_path / "src")
        except ValueError:
            ui.notify(
                f"{relative_display(p)} isn't under src/ - can't examine.",
                type="warning",
            )
            return
        model_name = str(rel_to_src.with_suffix(""))

        info_expansion.value = True   # expand + reveal the console
        info_console.focus()          # move focus so screen reader reads output
        await info_console.run_3dm(
            ["-m", model_name, "build", "info"],
            cwd=project_state.project_path,
        )

    SIDEBAR_LABEL_ID = "project-file-list-label"

    def build_file_list() -> None:
        """Build the sidebar <select> exactly once. Individual options are
        updated in place via refresh_file_marker when their dirty state
        changes; this avoids destroying the DOM element the user is
        interacting with (which drops keyboard focus)."""
        if not project_state.scad_files:
            ui.label("(none)")
            return
        visible_rows = min(max(len(project_state.scad_files), 6), 20)
        sel = ui.element("select")
        sel._props["size"] = visible_rows
        sel._props["aria-labelledby"] = SIDEBAR_LABEL_ID
        sel.classes("w-full")
        sel.style(
            "border: 1px solid #ccc; border-radius: 4px; "
            "padding: 4px; font-size: 14px;"
        )
        with sel:
            for p in project_state.scad_files:
                opt = ui.element("option")
                opt._props["value"] = str(p)
                if p == project_state.current_file:
                    opt._props["selected"] = True
                opt._text = option_display(p)
                # Screen readers use aria-label when navigating options -
                # more explicit than the visible "*".
                opt._props["aria-label"] = option_aria_label(p)
                option_elements[p] = opt

        def on_pick(e) -> None:
            chosen = Path(e.args)
            if chosen == project_state.current_file:
                return
            load_file_into_editor(chosen)
        sel.on(
            "change",
            on_pick,
            js_handler="(event) => emit(event.target.value)",
        )
        # Enter on the listbox jumps into the CodeMirror editor. Client-side
        # handler = no server round-trip; .cm-content is CodeMirror 6's
        # contenteditable element and receives keyboard focus reliably.
        # `.prevent` stops the Enter keydown's default action so the key
        # doesn't reach CodeMirror after we focus it (which would insert a
        # newline at the cursor).
        sel.on(
            "keydown.enter.prevent",
            js_handler=(
                "(...args) => { const el = document.querySelector('.cm-content'); "
                "if (el) el.focus(); }"
            ),
        )

    # Prime the initial file's buffer/snapshot so is_dirty and save-button
    # state read consistent values right from the first render.
    initial_path = project_state.current_file
    if initial_path is not None and initial_path not in project_state.buffers:
        try:
            initial_text = initial_path.read_text()
        except OSError:
            initial_text = ""
        project_state.buffers[initial_path] = initial_text
        project_state.disk_snapshots[initial_path] = initial_text

    # Fill screen below the header. calc keeps the layout from scrolling the
    # page as a whole - the editor scrolls internally instead.
    with ui.row().classes("w-full items-stretch no-wrap").style(
        "height: calc(100vh - 80px)"
    ):
        # --- Sidebar (file list) ---
        with ui.column().classes("shrink-0 gap-2").style("width: 260px"):
            list_label = ui.label("Source files").classes("text-weight-bold")
            list_label._props["id"] = SIDEBAR_LABEL_ID
            build_file_list()

        # --- Editor + info panel (right) ---
        with ui.column().classes("flex-1 h-full no-wrap"):
            editor_label = ui.label(
                relative_display(initial_path) if initial_path else ""
            ).classes("text-caption")
            editor = (
                ui.codemirror(
                    value=(
                        project_state.buffers.get(initial_path, "")
                        if initial_path
                        else ""
                    ),
                    language="C",
                    line_wrapping=True,
                    # Ctrl/Cmd+S also lives in the page-wide ui.keyboard
                    # (via _install_global_shortcuts), but keeping it in
                    # the CodeMirror keymap costs nothing and covers the
                    # case where the ui.keyboard would ignore contenteditable
                    # for some reason. F5 is handled ONLY via ui.keyboard
                    # so it fires page-wide (including when the sidebar has
                    # focus) - having it here too would double-dispatch.
                    keymap={
                        "Mod-s": lambda _e=None: save_current_file(),
                    },
                )
                .classes("w-full")
                .style("flex: 1 1 0; min-height: 0;")
            )

            # Collapsible info panel below the editor. Default collapsed;
            # F5 (or clicking the header) expands it. Wrapping the
            # q-expansion-item in a `ui.list().props("bordered")` (Quasar's
            # q-list) is the idiomatic way to give an expansion panel a
            # proper docked-panel look - border + rounded corners - without
            # any custom CSS.
            with (
                ui.list()
                .props("bordered")
                .classes("w-full shrink-0 rounded-borders")
            ):
                info_expansion = ui.expansion("Model info", value=False)
                with info_expansion:
                    info_console = OutputConsole(
                        "Model info output", height_em=10
                    )

    # Publish save_current_file and examine_current_file so menu / keyboard
    # handlers can invoke them without needing access to this closure.
    project_state.save_fn = save_current_file
    project_state.examine_fn = examine_current_file


# ---------------------------------------------------------------------------
# Examine tab
# ---------------------------------------------------------------------------

def build_examine_tab() -> None:
    assert state.stl_path is not None

    ui.label(f"Examining {state.stl_path.name}").classes("text-subtitle1")

    # Fixed-height, scrollable, screen-reader-friendly console for the model
    # info output. See OutputConsole - reused by the Slice tab too.
    info_console = OutputConsole("Model info", height_em=10)

    # Kick off the info subprocess as soon as the tab is built.
    ui.timer(
        0.0,
        lambda: asyncio.create_task(
            info_console.run_3dm(["info", str(state.stl_path)])
        ),
        once=True,
    )

    ui.separator()
    ui.label("Tactile preview").classes("text-weight-bold")

    preview_type = ui.select(
        options={k: PROJECTION_LABELS.get(k, k) for k in NAMED_PROJECTION_CODE.keys()},
        value=next(iter(NAMED_PROJECTION_CODE.keys())),
        label="Preview type",
    ).classes("w-64")

    destination = ui.select(
        options=[DESTINATION_3D_PRINTER, DESTINATION_EMBOSSER],
        value=DESTINATION_3D_PRINTER,
        label="Send to",
    ).classes("w-64")

    def make_preview() -> None:
        # Matches the PySide6 stub - the actual `3dm preview` subprocess wire-up
        # is deferred until we know the prototype is worth investing more in.
        ui.notify(
            f"[stub] Would make preview: {preview_type.value} to {destination.value}"
        )

    ui.button("Make tactile preview", on_click=make_preview)


# ---------------------------------------------------------------------------
# Slice tab
# ---------------------------------------------------------------------------

def build_slice_tab() -> None:
    profile_names = list_printer_profiles(CONFIG_DIR)

    if not profile_names:
        ui.label("No printer profiles configured. See Settings.").classes("text-negative")
        return

    if state.profile_name not in profile_names:
        state.profile_name = profile_names[0]

    def refresh_profile_config() -> None:
        state.profile_config = read_profile_config(
            CONFIG_DIR, state.profile_name, state.selected_overlays
        )
        # Drop any edited values whose keys no longer exist in the merged config.
        state.edited_values = {
            k: v for k, v in state.edited_values.items() if k in state.profile_config
        }

    refresh_profile_config()

    profile_select = ui.select(
        options=profile_names,
        value=state.profile_name,
        label="Printer profile",
    ).classes("w-64")

    # ---- Overlay picker ----
    overlays_by_name = {o.name: o for o in list_overlays(CONFIG_DIR)}

    def available_overlay_names() -> list[str]:
        return [n for n in sorted(overlays_by_name.keys()) if n not in state.selected_overlays]

    with ui.row().classes("items-end gap-2"):
        overlay_select = ui.select(
            options=available_overlay_names() or [""],
            label="Add overlay",
        ).classes("w-64")

        def add_overlay() -> None:
            name = overlay_select.value
            if not name or name in state.selected_overlays:
                return
            state.selected_overlays.append(name)
            refresh_profile_config()
            overlay_pills.refresh()
            overlay_select.set_options(available_overlay_names() or [""], value=None)
            profile_editor.refresh()

        ui.button("Add", on_click=add_overlay)

    # The bold label doubles as the accessible name for the list container
    # below (via aria-labelledby), so it gets announced when a screen reader
    # enters the list.
    OVERLAY_LIST_LABEL_ID = "overlay-list-label"
    overlay_list_label = ui.label("Selected overlays (applied in order)").classes(
        "text-weight-bold"
    )
    overlay_list_label._props["id"] = OVERLAY_LIST_LABEL_ID

    @ui.refreshable
    def overlay_pills() -> None:
        if not state.selected_overlays:
            # Render an empty semantic list so the aria-label still applies
            # even when there's nothing in it - keeps the tree consistent.
            empty_ul = ui.element("ul")
            empty_ul._props["role"] = "list"
            empty_ul._props["aria-labelledby"] = OVERLAY_LIST_LABEL_ID
            empty_ul.classes("list-none p-0 m-0")
            with empty_ul:
                ui.label("(none)").classes("text-italic")
            return

        # Semantic <ul role="list" aria-labelledby="...">; each pill is an
        # <li role="listitem"> containing the name and a per-overlay Remove
        # button whose aria-label names the overlay so VoiceOver announces
        # e.g. "Remove overlay foo, button" instead of just "Remove button".
        ul = ui.element("ul")
        ul._props["role"] = "list"
        ul._props["aria-labelledby"] = OVERLAY_LIST_LABEL_ID
        ul.classes("flex flex-wrap gap-2 list-none p-0 m-0")

        with ul:
            for name in list(state.selected_overlays):
                def make_remove(n: str = name) -> Callable[[], None]:
                    def _remove() -> None:
                        if n in state.selected_overlays:
                            state.selected_overlays.remove(n)
                        refresh_profile_config()
                        overlay_pills.refresh()
                        overlay_select.set_options(
                            available_overlay_names() or [""], value=None
                        )
                        profile_editor.refresh()
                    return _remove

                li = ui.element("li")
                li._props["role"] = "listitem"
                with li:
                    with ui.row().classes(
                        "items-center gap-1 rounded-full px-3 py-1"
                    ).style("background: #e3f2fd;"):
                        ui.label(name).classes("text-body2")
                        ui.button(icon="close", on_click=make_remove()).props(
                            f'dense flat round size=sm '
                            f'aria-label="Remove overlay {name}"'
                        )

    overlay_pills()

    ui.separator()
    ui.label("Profile settings").classes("text-weight-bold")

    # UI-only state (which category is currently selected).
    ui_state = {"category": None}

    # CSS marker on the fields column so an Enter keypress in the category
    # listbox can find the first field input to focus (via querySelector).
    FIELDS_MARKER_CLASS = "profile-fields-container"

    def focus_first_field_js() -> str:
        return (
            f"const el = document.querySelector('.{FIELDS_MARKER_CLASS} input, "
            f".{FIELDS_MARKER_CLASS} textarea'); if (el) el.focus();"
        )

    # Two-level structure so we can rebuild the parts that need rebuilding
    # without touching parts the user is interacting with:
    #   - profile_editor: rebuilt on profile/overlay changes (categories differ)
    #   - fields_area:    rebuilt on category-selection change
    #   - field edits:    imperative style/enabled updates, NO rebuild - if we
    #                     refreshed on every keystroke the input would be
    #                     destroyed mid-typing and focus would jump.

    @ui.refreshable
    def profile_editor() -> None:
        cfg = state.profile_config
        assert cfg is not None
        categories = [c for c, values in cfg.by_category.items() if values]
        if not categories:
            ui.label("(no settings in profile)")
            return
        if ui_state["category"] not in categories:
            ui_state["category"] = categories[0]

        with ui.row().classes("w-full items-start gap-4"):
            # Category picker: a native HTML <select size=N> - this is exactly
            # the "inline listbox" pattern QListWidget provides. Single tab
            # stop, arrow keys change selection, and it gets first-class
            # macOS/Windows/Linux screen-reader support because it's the
            # browser's own listbox control. Radio buttons made every category
            # a tab stop, which was tedious with ~28 categories.
            visible_rows = min(max(len(categories), 6), 18)
            cat_select = ui.element("select")
            cat_select._props["size"] = visible_rows
            cat_select._props["aria-label"] = "Setting categories"
            cat_select.classes("w-56 shrink-0")
            cat_select.style(
                "border: 1px solid #ccc; border-radius: 4px; padding: 4px; "
                "font-size: 14px;"
            )

            with cat_select:
                for c in categories:
                    opt = ui.element("option")
                    opt._props["value"] = c
                    if c == ui_state["category"]:
                        opt._props["selected"] = True
                    opt._text = c or "Uncategorized"

            # Field editor container. We rebuild its contents on category
            # change via clear() + repopulate rather than a nested
            # @ui.refreshable, because nested refreshables inside another
            # refreshable don't reliably know where to re-render (the outer
            # rebuild reconstructs the inner function object each time and
            # the anchor gets lost). The marker class is what the Enter
            # handler below uses to locate the first input.
            fields_container = ui.column().classes(
                f"flex-1 gap-2 {FIELDS_MARKER_CLASS}"
            )

            def render_fields() -> None:
                fields_container.clear()
                with fields_container:
                    cat = ui_state["category"]
                    values = cfg.by_category.get(cat, {})
                    for key, base_value in values.items():
                        build_field_row(key, base_value)

            render_fields()

            def on_cat_change(e) -> None:
                # NiceGUI's args=['target.value'] path extraction returned a
                # dict for us (not a scalar) on this build - the safest bet
                # is a js_handler that pulls the value on the client and
                # emits it explicitly.
                ui_state["category"] = e.args
                # Rebuild ONLY the fields column - leave the select alone so
                # the user's keyboard focus and visual selection stay put.
                render_fields()
            cat_select.on(
                "change",
                on_cat_change,
                js_handler="(event) => emit(event.target.value)",
            )

            # Enter jumps to the first field in the current category - same as
            # Qt's itemActivated behaviour. Handled in JS so it's snappy and
            # doesn't need a round-trip.
            cat_select.on(
                # `.prevent` so the Enter keydown doesn't propagate into the
                # newly-focused input (would submit a form or type a newline
                # depending on the widget).
                "keydown.enter.prevent",
                js_handler=f"(...args) => {{ {focus_first_field_js()} }}",
            )

    def build_field_row(key: str, base_value: str) -> None:
        cfg = state.profile_config
        assert cfg is not None
        overlay_source = cfg.overlay_source(key)
        pretty_name = key.replace("_", " ")
        initial = state.edited_values.get(key, base_value)

        # HTML-safe id so <label for=...> can bind to the input.
        input_id = "pf-" + "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        # Description-element id for aria-describedby - the input references
        # this so screen readers read "Edited" / "Set by overlay X" after the
        # value on focus.
        desc_id = f"desc-{input_id}"

        with ui.row().classes("items-center gap-2 w-full no-wrap"):
            # Quasar q-input:
            # - `for=<input_id>`: sets id on the inner native <input> so
            #   <label for="..."> associates for screen readers.
            # - `aria-describedby=<desc_id>`: screen readers read the
            #   description span (edited / overlay-source) after the value.
            # - `dense outlined hide-bottom-space`: compact style, no reserved
            #   error/hint space below.
            # - `before` slot with a <label for=input_id>: Quasar's
            #   recommended pattern for horizontal label-to-the-left layout.
            inp = ui.input(value=initial).classes("flex-1")
            inp.props(
                f'dense outlined hide-bottom-space for="{input_id}" '
                f'aria-describedby="{desc_id}"'
            )

            with inp.add_slot("before"):
                lbl = ui.element("label")
                lbl._props["for"] = input_id
                lbl._text = pretty_name
                lbl.classes("w-40 shrink-0 text-right text-body2")

            revert_btn = ui.button(icon="undo").props(
                f'dense flat aria-label="Revert {pretty_name} to original value"'
            )

            # Status label: doubles as the aria-describedby target and the
            # visible "Edited" / "Set by overlay X" text. Hidden when neither
            # applies so it doesn't announce nothing.
            status_label = ui.label("").classes("text-caption")
            status_label._props["id"] = desc_id

            def apply_visual_state() -> None:
                """Recompute per-field visual + accessibility state from the
                current input value. Runs on every keystroke - no widget
                teardown, so focus and caret position are preserved."""
                edited = inp.value != base_value

                # Border colour: applied via CSS class + descendant selector
                # so it sits on the input's own frame (.q-field__control)
                # rather than being an outer outline around the whole wrapper.
                inp.classes(remove="pf-edited pf-overlay")
                if edited:
                    inp.classes(add="pf-edited")
                elif overlay_source:
                    inp.classes(add="pf-overlay")

                # Revert button: hidden entirely when unchanged (nothing to
                # revert to), not just disabled - keeps the row less busy.
                revert_btn.set_visibility(edited)

                # Status text: edited overrides overlay-source. Hidden when
                # neither state applies so aria-describedby announces nothing.
                if edited:
                    status_label.text = "Edited"
                    status_label.style(f"color: {CHANGED_COLOR}")
                    status_label.set_visibility(True)
                elif overlay_source:
                    status_label.text = f"Set by overlay: {overlay_source}"
                    status_label.style(f"color: {OVERLAY_COLOR}")
                    status_label.set_visibility(True)
                else:
                    status_label.text = ""
                    status_label.set_visibility(False)

            def on_change(e) -> None:
                v = e.value
                if v == base_value:
                    state.edited_values.pop(key, None)
                else:
                    state.edited_values[key] = v
                apply_visual_state()
            inp.on_value_change(on_change)

            def on_revert() -> None:
                state.edited_values.pop(key, None)
                inp.set_value(base_value)  # triggers on_change -> apply_visual_state
            revert_btn.on_click(on_revert)

            apply_visual_state()

    profile_editor()

    ui.separator()
    slice_button = ui.button("Slice").props("color=primary")

    # Same widget style as the Examine tab's model-info console. ui.log
    # renders as a non-focusable <pre>-like block that VoiceOver skips
    # entirely - OutputConsole gives us a labelled, focusable, readable
    # textarea that screen-reader users can actually navigate. Placed
    # BELOW the Slice button so activating the button naturally leads the
    # eye (and the just-moved focus) to the output that just started.
    slice_console = OutputConsole("Slice output", height_em=16)
    slice_console.set_visibility(False)  # only appears after first Slice

    async def run_slice() -> None:
        slice_button.disable()
        slice_console.set_visibility(True)
        # Move keyboard focus to the output so screen-reader users start
        # reading the streamed lines immediately without having to Tab.
        slice_console.focus()

        args = ["slice", str(state.stl_path), "--profile", state.profile_name]
        for name in state.selected_overlays:
            args += ["--overlay", name]

        if state.edited_values:
            tmp_dir = Path(tempfile.mkdtemp(prefix="3dmake-webgui-"))
            edited_overlay = tmp_dir / "edited_settings.ini"
            write_overlay_file(edited_overlay, state.edited_values)
            args += ["--overlay", str(edited_overlay)]

        try:
            await slice_console.run_3dm(args)
        finally:
            slice_button.enable()

    slice_button.on_click(run_slice)

    # Wire the profile-change listener late so it doesn't fire during initial build.
    def on_profile_change(e) -> None:
        state.profile_name = e.value
        refresh_profile_config()
        profile_editor.refresh()
    profile_select.on_value_change(on_profile_change)


# ---------------------------------------------------------------------------
# Native menubar
# ---------------------------------------------------------------------------
#
# pywebview supports a native OS menubar (Cocoa on macOS, Win32 on Windows,
# GTK/Qt on Linux) attached at window-creation time. NiceGUI exposes this
# via `app.native.window_args`; anything set there is forwarded to
# `webview.create_window(**window_args)`.
#
# Pitfalls:
# * pywebview's `MenuAction` has no working accelerator field, so we bake
#   the shortcut into the visible label text and wire the real shortcut
#   separately via `ui.keyboard` on each page.
# * Menu callbacks run on pywebview's own thread. UI operations (navigate,
#   notify, opening dialogs from Python) need to run on NiceGUI's asyncio
#   loop, so `_run_on_ui` bridges via `asyncio.run_coroutine_threadsafe`.
# * Menus are static after creation. `File > Save` is always visible; when
#   invoked outside project mode the handler notifies the user instead.

_IS_MAC = platform.system() == "Darwin"
_MOD_LABEL = "⌘" if _IS_MAC else "Ctrl+"


def _shortcut_hint(letter: str) -> str:
    """Human-readable shortcut suffix baked into a menu label (pywebview
    can't attach real accelerators)."""
    return f" ({_MOD_LABEL}{letter})"


# The asyncio loop NiceGUI runs on (captured at startup). Used by
# in-process handlers (ui.keyboard shortcut callbacks) that already run on
# it - we schedule via create_task in that case.
_ui_loop: Optional[asyncio.AbstractEventLoop] = None


def _dispatch_menu_action(action: str) -> None:
    """Dispatch a menu action name to its async flow. Called from the
    NiceGUI server side (either via ui.keyboard shortcut on the current
    page, or via the /_menu_bridge/<action> endpoint hit by pywebview
    menu callbacks)."""
    flows: dict[str, Callable[[], Coroutine]] = {
        "open_stl": _open_stl_flow,
        "open_project": _open_project_flow,
        "new_project": _new_project_flow,
        "settings": _show_settings_flow,
        "save": _save_from_menu,
        "examine": _examine_from_menu,
    }
    flow = flows.get(action)
    if flow is None:
        return
    coro = flow()
    try:
        # We're on a running asyncio loop (NiceGUI's) - schedule as a task.
        asyncio.get_running_loop()
        asyncio.create_task(coro)
    except RuntimeError:
        # No running loop in this thread - marshal to the captured loop.
        if _ui_loop is not None and _ui_loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, _ui_loop)


# --- Cross-process menu bridge ---
#
# NiceGUI native mode spawns pywebview in a SEPARATE process, so pywebview
# menu callbacks run in the child process. They can't reach NiceGUI's
# asyncio loop, module state, or dispatch functions in the parent.
#
# The only cross-process channels available without patching NiceGUI's
# private internals are: pipes it uses for its own pywebview events, or
# the browser (via webview.evaluate_js). We use the latter, but with a
# background fetch() rather than a full navigation - the fetch hits a
# server endpoint on our own NiceGUI process where we can safely dispatch
# to the action's flow. The current page is NOT reloaded, so an open
# editor keeps its cursor / undo history / focus.

def _menu_bridge(action: str) -> None:
    """Called by pywebview from its own process. Fires a fetch() from
    the browser to /_menu_bridge/<action>, which the NiceGUI server (in
    the parent process) picks up and dispatches to the right flow. No
    page navigation - the fetch is async and fire-and-forget."""
    if not webview.windows:
        return
    webview.windows[0].evaluate_js(
        f'fetch("/_menu_bridge/{action}", {{method: "POST"}})'
    )


def _menu_open_stl() -> None:
    _menu_bridge("open_stl")


def _menu_open_project() -> None:
    _menu_bridge("open_project")


def _menu_new_project() -> None:
    _menu_bridge("new_project")


def _menu_settings() -> None:
    _menu_bridge("settings")


def _menu_save() -> None:
    _menu_bridge("save")


# Suppress pywebview's built-in Edit and View menus. Their positions are
# hardcoded (inserted at index 1 in _recreate_menus), which pushes our
# File menu to the far right - not what users expect. With defaults off,
# only our File menu appears after the app menu. If we later need
# Cut/Copy/Paste we can add our own Edit menu explicitly.
webview.settings["SHOW_DEFAULT_MENUS"] = False

# Build the menu once and attach to the window args before ui.run.
_file_menu = Menu(
    "File",
    items=[
        MenuAction(f"Open STL...{_shortcut_hint('O')}", _menu_open_stl),
        MenuAction("Open project...", _menu_open_project),
        MenuAction("New project...", _menu_new_project),
        MenuSeparator(),
        MenuAction("Settings...", _menu_settings),
        MenuSeparator(),
        MenuAction(f"Save{_shortcut_hint('S')}", _menu_save),
    ],
)
app.native.window_args["menu"] = [_file_menu]


@app.on_startup
def _capture_ui_loop() -> None:
    """Called on NiceGUI's event loop after startup. Grab the loop so
    menu-callback threads can schedule work back onto it."""
    global _ui_loop
    _ui_loop = asyncio.get_running_loop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ in {"__main__", "__mp_main__"}:
    # NiceGUI's native mode uses multiprocessing under the hood, hence the
    # `__mp_main__` guard alongside `__main__`.
    ui.run(
        native=True,
        title="3DMake",
        window_size=(1000, 750),
        reload=False,
    )
