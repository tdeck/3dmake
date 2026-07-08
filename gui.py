import asyncio
import os
import sys
import toga
from toga.constants import BOLD, COLUMN, LEFT, RIGHT, ROW
from pathlib import Path
from typing import Optional
from utils.scad_snippets import NAMED_PROJECTION_CODE

WinID = str

PROJECTION_LABELS = {
    '3sil': '3 silhouettes (front, top, left)',
    'topsil': 'silhouette from top',
    'leftsil': 'silhouette from left',
    'rightsil': 'silhouette from right',
    'frontsil': 'silhouette from front',
    'backsil': 'silhouette from back',
}

THREEDMAKE_SCRIPT = Path(__file__).parent / "3dm.py"

DESTINATION_3D_PRINTER = '3D Printer'
DESTINATION_EMBOSSER = 'Embosser (SVG)'

def winid_for_stl(stl_file: Path) -> WinID:
    return str(stl_file.absolute())

def project_root_for_path(path: Path) -> Path:
    ''' Normalize a path that may be the project directory itself, or the
    3dmake.toml file inside it, to the project root directory. '''
    path = Path(path)
    return path.parent if path.is_file() else path

def is_valid_3dmake_project(root: Path) -> bool:
    return (root / "3dmake.toml").is_file()

async def run_3dmake(*args: str, cwd: Optional[Path] = None, input_text: Optional[str] = None):
    ''' Run the 3dmake CLI with GUI_MODE set, yielding combined stdout/stderr lines as they're produced. '''
    env = os.environ.copy()
    env['_3DMAKE_TEST_FLAGS'] = 'GUI_MODE'
    env['PYTHONUNBUFFERED'] = '1'

    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(THREEDMAKE_SCRIPT), *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.PIPE if input_text is not None else None,
        cwd=cwd,
        env=env,
    )
    if input_text is not None:
        proc.stdin.write(input_text.encode())
        await proc.stdin.drain()
        proc.stdin.close()

    async for line in proc.stdout:
        yield line.decode()
    await proc.wait()

class WorkspaceWindow(toga.DocumentWindow):
    selected_profile: Optional[str] = None # Use system default profile (probs not great)


class STLWorkspaceWindow(WorkspaceWindow):
    def __init__(self, doc, **kwargs):
        super().__init__(doc=doc, **kwargs)
        self.size = (800, 600) # TODO debug
        self.stl_file = None

        examine_tab = toga.Box()
        slice_tab = toga.Box()
        print_tab = toga.Box()
        container = toga.OptionContainer(
            content=[
                ('Examine model', examine_tab),
                ('Slice', slice_tab),
                ('Print', print_tab),
            ]
        )

        #
        # Examine tab
        #
        examine_tab.style.update(direction=COLUMN, margin=10, gap=10)
        self.examining_label = toga.Label("Examining...", text_align=LEFT)
        examine_tab.add(self.examining_label)
        # AI description
        examine_tab.add(toga.Label("Model info", text_align=LEFT, font_weight=BOLD))
        self.info_console_holder = toga.Box(direction=COLUMN, flex=1)
        examine_tab.add(self.info_console_holder)

        # Preview
        examine_tab.add(toga.Label("Tactile preview", text_align=LEFT, font_weight=BOLD))
        self.preview_selection = toga.Selection(
            items=[
                dict(value=k, label=PROJECTION_LABELS.get(k, k))
                for k in NAMED_PROJECTION_CODE.keys()
            ],
            accessor='label',
        )
        examine_tab.add(toga.Box(children=[
            toga.Label("Preview type"),
            self.preview_selection,
        ]))

        self.preview_destination = toga.Selection(items=[DESTINATION_3D_PRINTER, DESTINATION_EMBOSSER])
        examine_tab.add(toga.Box(children=[
            toga.Label("Send to"),
            self.preview_destination,
        ]))
        examine_tab.add(toga.Button('Make tactile preview', on_press=self.make_preview))

        #
        #
        #

        self.content = container

    def load_document(self, stl_file: Path):
        self.stl_file = stl_file
        self.examining_label.text = f"Examining {stl_file.name}"
        self.run_3dm_info()

    def run_3dm_info(self):
        self.info_spinner = toga.ActivityIndicator(running=True)
        self.info_console_holder.add(self.info_spinner)
        asyncio.create_task(self.populate_info_console())

    async def make_preview(self, _):
        preview_type = self.preview_selection.value.value
        destination = self.preview_destination.value

        if destination == DESTINATION_EMBOSSER:
            async for line in run_3dmake("preview", str(self.stl_file), '-p', preview_type):
                pass
                       

        print(f"Asked for a tactile preview {preview_type} -> {destination}")

    async def populate_info_console(self):
        # Built here, not in run_3dm_info, because constructing a readonly
        # MultilineTextInput synchronously during startup hangs GTK:
        # https://github.com/beeware/toga/issues/3943
        info_console = toga.MultilineTextInput(readonly=True, flex=1)
        self.info_console_holder.insert(0, info_console)

        output = ""
        async for line in run_3dmake("info", str(self.stl_file)):
            output += line
            info_console.value = output
            info_console.scroll_to_bottom()
        self.info_console_holder.remove(self.info_spinner)


class STLDocument(toga.Document):
    description = "STL File"
    extensions = ['stl']

    def create(self):
        self.main_window = STLWorkspaceWindow(doc=self)

    def read(self):
        self.main_window.load_document(self.path)


class ProjectWorkspaceWindow(WorkspaceWindow):
    def __init__(self, doc, **kwargs):
        super().__init__(doc=doc, **kwargs)
        self.size = (800, 600)

        box = toga.Box(direction=COLUMN, margin=10, gap=10)
        self.project_name_label = toga.Label("", text_align=LEFT, font_weight=BOLD)
        box.add(self.project_name_label)

        self.content = box

    def load_document(self, project_root: Path):
        # By the time this window is ever shown, MainApp's open flow has already
        # verified the project is valid (see MainApp._open_project_document) - an
        # invalid folder results in an error dialog and this window never being shown.
        self.project_root = project_root
        self.project_name_label.text = project_root.name


class ProjectDocument(toga.Document):
    description = "3DMake Project"
    extensions = ["toml"]  # only relevant if a 3dmake.toml file is opened directly; the primary entry point is the Open Project Folder command, which bypasses extension dispatch entirely

    def create(self):
        self.main_window = ProjectWorkspaceWindow(doc=self)

    def read(self):
        self.main_window.load_document(project_root_for_path(self.path))

    @property
    def is_valid(self) -> bool:
        return is_valid_3dmake_project(project_root_for_path(self.path))

    @property
    def title(self) -> str:
        return f"{self.description}: {project_root_for_path(self.path).name}" if self.path else super().title


class WelcomeWindow(toga.MainWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        box = toga.Box(direction=COLUMN, margin=10, gap=10)
        box.add(toga.Label(
            "No project or STL file is open.",
            text_align=LEFT, font_weight=BOLD,
        ))
        box.add(toga.Label(
            "Use File → Open… to open an STL file, File → Open Project "
            "Folder… to open an existing 3DMake project, or File → New "
            "3DMake Project to create one.",
            text_align=LEFT,
        ))
        self.content = box


class MainApp(toga.App):
    def startup(self):
        self.main_window = WelcomeWindow(title=self.formal_name)
        self.main_window.show()

        # There's no "blank STL" concept in this app, so the stock "New STL File"
        # command (auto-generated because STLDocument is a registered document type)
        # has nothing useful to do.
        del self.commands["documents.new"]

        self.commands.add(
            # Overrides the stock "Open…" command. Toga's stock documents.request_open()
            # closes/replaces the current window when it's a DocumentWindow (GTK/Windows
            # "single window" behavior via CLOSE_ON_LAST_WINDOW) - we want every opened
            # file to get its own independent window instead.
            toga.Command(
                self.open_stl_file,
                text="Open 3D Model…",
                id="documents.request_open",
                group=toga.Group.FILE,
                section=0,
                order=self.commands["documents.request_open"].order,
            ),
            toga.Command(
                self.open_project_folder,
                text="Open Project Folder…",
                shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + "o",
                group=toga.Group.FILE,
                section=0,
                order=11,
            ),
            toga.Command(
                self.new_project_folder,
                text="New 3DMake Project",
                id="documents.new:toml",
                group=toga.Group.FILE,
                section=0,
                order=self.commands["documents.new:toml"].order,
            ),
        )

    def _close_welcome_window(self):
        if isinstance(self.main_window, WelcomeWindow):
            welcome = self.main_window
            self.main_window = None
            welcome.close()

    def _focus_if_already_open(self, path: Path) -> bool:
        try:
            existing = self.documents[path]
            existing.focus()
            return True
        except KeyError:
            return False

    async def open_stl_file(self, command, **kwargs):
        path = await self.dialog(toga.OpenFileDialog("Open STL File", file_types=["stl"]))
        if path is None:
            return

        # Some file choosers allow selecting a folder from an "open file" dialog;
        # if that happens, open it as a project instead of trying (and failing) to
        # treat it as an STL file.
        if path.is_dir():
            if not self._focus_if_already_open(path):
                await self._open_project_document(path)
            return

        if self._focus_if_already_open(path):
            return

        document = STLDocument(app=self)
        try:
            document.open(path)
            document.show()
            self._close_welcome_window()
        except Exception:
            document.main_window.close()
            raise

    async def _open_project_document(self, path: Path):
        document = ProjectDocument(app=self)
        try:
            document.open(path)
        except Exception:
            document.main_window.close()
            raise

        if not document.is_valid:
            document.main_window.close()
            await self.dialog(toga.ErrorDialog(
                "Not a 3DMake Project",
                f"'{project_root_for_path(path)}' does not contain a 3dmake.toml file.",
            ))
            return

        document.show()
        self._close_welcome_window()

    async def open_project_folder(self, command, **kwargs):
        path = await self.dialog(toga.SelectFolderDialog("Open 3DMake Project Folder"))
        if path is None:
            return

        if self._focus_if_already_open(path):
            return

        await self._open_project_document(path)

    async def new_project_folder(self, command, **kwargs):
        target = await self.dialog(toga.SaveFileDialog("New 3DMake Project", suggested_filename="MyProject"))
        # TODO you should select the parent folder and a project name
        # Maybe there should be a default place to put these
        if target is None:
            return

        async for line in run_3dmake("new", cwd=target.parent, input_text=f"{target.name}\n"):
            pass

        await self._open_project_document(target)

def main():
    return MainApp(
        formal_name='3DMake',
        app_id='net.blindmakers.threedmake',
        document_types=[STLDocument, ProjectDocument],
    )

main().main_loop()

# TODO audit labels for arrows and unicode ellipses and things
