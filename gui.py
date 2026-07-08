import os
import signal
import sys
from pathlib import Path

# Must be set before QApplication is constructed - Qt reads this during
# platform-plugin init. Forces the AT-SPI accessibility bridge active from
# startup instead of lazily activating only once a screen reader connects.
os.environ["QT_LINUX_ACCESSIBILITY_ALWAYS_ON"] = "1"

# PySide6 bundles its own private copy of Qt, which only ships "gtk3" and
# "xdgdesktopportal" platform theme plugins - not desktop-specific ones like
# "lxqt" or "kde" that a system-wide QT_QPA_PLATFORMTHEME might request (or
# that Qt might auto-detect from XDG_CURRENT_DESKTOP when unset). Either way
# Qt then silently falls back to a generic default font instead of the real
# system font. Force "gtk3" (confirmed to correctly read the system font via
# GTK/gsettings) unless QT_QPA_PLATFORMTHEME is already explicitly set to one
# of the two plugins we actually have - don't second-guess a deliberate,
# working choice.
if os.environ.get("QT_QPA_PLATFORMTHEME") not in ("gtk3", "xdgdesktopportal"):
    os.environ["QT_QPA_PLATFORMTHEME"] = "gtk3"

from PySide6.QtCore import QProcess, QProcessEnvironment, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from utils.scad_snippets import NAMED_PROJECTION_CODE

PROJECTION_LABELS = {
    '3sil': '3 silhouettes (front, top, left)',
    'topsil': 'silhouette from top',
    'leftsil': 'silhouette from left',
    'rightsil': 'silhouette from right',
    'frontsil': 'silhouette from front',
    'backsil': 'silhouette from back',
}

DESTINATION_3D_PRINTER = '3D Printer'
DESTINATION_EMBOSSER = 'Embosser (SVG)'

THREEDMAKE_SCRIPT = Path(__file__).parent / "3dm.py"

def bold_label(text: str) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label

class WorkspaceWindow(QMainWindow):
    def __init__(self, base_path: Path):
        super().__init__()
        self.base_path = base_path
        self.setWindowTitle(base_path.name)

    @property
    def wsid(self) -> str:
        return str(self.base_path.absolute())

class STLWorkspaceWindow(WorkspaceWindow):
    def __init__(self, stl_path: Path):
        super().__init__(base_path=stl_path)
        self.resize(800, 600)

        tabs = QTabWidget()
        tabs.addTab(self._build_examine_tab(stl_path), "E&xamine model")
        tabs.addTab(QWidget(), "&Slice")
        tabs.addTab(QWidget(), "&Print")

        self._build_menu_bar()
        self.setCentralWidget(tabs)
        self._start_info_process(stl_path)

    def _build_menu_bar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        open_model_action = QAction("&Open model", self)

        open_project = QAction("Open &project", self)
        open_model_action.setShortcut(QKeySequence.Open) # Ctrl+O
        file_menu.addAction(open_model_action)

        pass

    def _build_examine_tab(self, stl_path: Path) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        layout.addWidget(QLabel(f"Examining {stl_path.name}"))

        # Model info
        self.info_console = QTextEdit()
        self.info_console.setReadOnly(True)

        self.model_info_label = bold_label("Model &info (loading...)")
        self.model_info_label.setBuddy(self.info_console)
        layout.addWidget(self.model_info_label)
        layout.addWidget(self.info_console)

        # Tactile preview
        layout.addWidget(bold_label("Tactile preview"))

        self.preview_selection = QComboBox()
        for key in NAMED_PROJECTION_CODE.keys():
            self.preview_selection.addItem(PROJECTION_LABELS.get(key, key), userData=key)

        self.preview_destination = QComboBox()
        self.preview_destination.addItems([DESTINATION_3D_PRINTER, DESTINATION_EMBOSSER])

        # QFormLayout.addRow(labelText, field) creates the QLabel and calls
        # label.setBuddy(field) for us - this is what actually associates the
        # label with the control for screen readers (not just visual proximity),
        # and gives free Alt+mnemonic keyboard navigation from the "&" markers.
        preview_form = QFormLayout()
        preview_form.addRow("Pre&view type", self.preview_selection)
        preview_form.addRow("Send &to", self.preview_destination)
        layout.addLayout(preview_form)

        make_preview_button = QPushButton("Make tactile preview")
        make_preview_button.clicked.connect(self.make_preview)
        layout.addWidget(make_preview_button)

        return tab

    def make_preview(self):
        preview_type = self.preview_selection.currentData()
        destination = self.preview_destination.currentText()
        # TODO: actually run `3dm preview` (see make_preview in the old Toga
        # version) once subprocess handling is wired up in this port.
        print(f"Asked for a tactile preview {preview_type} -> {destination}")

    def _start_info_process(self, stl_path: Path):
        # Parented to self so Qt keeps it alive for the window's lifetime -
        # an unparented/unreferenced QProcess can get garbage collected mid-run.
        self.info_process = QProcess(self)
        self.info_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        env = QProcessEnvironment.systemEnvironment()
        env.insert("_3DMAKE_TEST_FLAGS", "GUI_MODE")
        env.insert("PYTHONUNBUFFERED", "1")
        self.info_process.setProcessEnvironment(env)

        self.info_process.readyReadStandardOutput.connect(self._on_info_output_ready)
        self.info_process.finished.connect(self._on_info_loading_done)
        self.info_process.start(sys.executable, [str(THREEDMAKE_SCRIPT), "info", str(stl_path)])

    def _on_info_loading_done(self):
        self.model_info_label.setText("Model &info")

    def _on_info_output_ready(self):
        output = bytes(self.info_process.readAllStandardOutput()).decode()
        self.info_console.insertPlainText(output)
        scrollbar = self.info_console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


# Subclass QMainWindow to customize your application's main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("My App")

        button = QPushButton("Press Me!")

        # Set the central widget of the Window.
        self.setCentralWidget(button)


app = QApplication(sys.argv)
signal.signal(signal.SIGINT, signal.SIG_DFL)

window = STLWorkspaceWindow(Path('/home/troy/Downloads/tiny_bottle_S_pet.stl'))
window.show()

app.exec()
