import os
import platform
import shutil
import signal
import sys
import tempfile
import webbrowser
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
from PySide6.QtGui import QAction, QFont, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from platformdirs import user_config_path

from utils.global_settings import load_global_settings, save_global_settings
from utils.print_config import ProfileConfig, list_overlays, list_printer_profiles, read_profile_config, write_overlay_file
from utils.scad_snippets import NAMED_PROJECTION_CODE

CONFIG_DIR = Path(os.environ['THREEDMAKE_CONFIG_DIR']) if 'THREEDMAKE_CONFIG_DIR' in os.environ else user_config_path('3dmake', None)

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

# Duplicated from actions/setup_action.py's BAMBU_CONNECT_DOWNLOAD_PAGE rather
# than imported - gui.py deliberately never imports the actions package (it
# shells out to 3dm.py as a subprocess instead throughout this file), and that
# package's __init__ registers every action on import, pulling in numpy/
# trimesh/vtk/etc. for the sake of one URL string.
BAMBU_CONNECT_DOWNLOAD_PAGE = "https://wiki.bambulab.com/en/software/bambu-connect"

MODE_GCODE = "gcode"
MODE_OCTOPRINT = "octoprint"
MODE_BAMBU_CONNECT = "bambu_connect"

def bold_label(text: str) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


class ConnectionSettingsPanel(QWidget):
    """Lets the user pick how prints get sent out, and configure that mode."""

    def __init__(self, initial_settings: "dict[str, str] | None" = None, parent=None):
        super().__init__(parent)
        initial_settings = initial_settings or {}

        layout = QVBoxLayout(self)

        self.button_group = QButtonGroup(self)
        self.pages = QStackedWidget(self)

        self._mode_order: list[str] = []

        gcode_radio = self._add_mode(MODE_GCODE, "Save prints as GCODE", self._build_gcode_page())
        octoprint_radio = self._add_mode(
            MODE_OCTOPRINT, "Send prints to OctoPrint", self._build_octoprint_page(initial_settings)
        )

        layout.addWidget(gcode_radio)
        layout.addWidget(octoprint_radio)

        if True:  # TODO restore: platform.system() in ("Windows", "Darwin")
            bambu_radio = self._add_mode(
                MODE_BAMBU_CONNECT, "Send prints to Bambu Connect", self._build_bambu_connect_page()
            )
            layout.addWidget(bambu_radio)

        layout.addWidget(self.pages)
        layout.addStretch(1)

        self.button_group.idClicked.connect(self.pages.setCurrentIndex)

        current_mode = initial_settings.get("print_mode", MODE_GCODE)
        self._select_mode(current_mode)

    def _add_mode(self, mode: str, label: str, page: QWidget) -> QRadioButton:
        radio = QRadioButton(label, self)
        index = self.pages.addWidget(page)
        self.button_group.addButton(radio, index)
        self._mode_order.append(mode)
        return radio

    def _select_mode(self, mode: str) -> None:
        if mode not in self._mode_order:
            mode = MODE_GCODE
        index = self._mode_order.index(mode)
        self.button_group.button(index).setChecked(True)
        self.pages.setCurrentIndex(index)

    def collect_settings(self) -> dict[str, str]:
        """Settings this panel controls, suitable for merging into the global settings dict."""
        settings = {"print_mode": self._mode_order[self.button_group.checkedId()]}

        if hasattr(self, "octoprint_host_edit"):
            settings["octoprint_host"] = self.octoprint_host_edit.text()
            settings["octoprint_key"] = self.octoprint_key_edit.text()

        return settings

    def _build_gcode_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(
            "The sliced GCODE file will be saved locally. You can send it to your\n"
            "printer manually (e.g. via SD card or a slicer's own upload feature).",
            page,
        ))
        return page

    def _build_octoprint_page(self, initial_settings: dict[str, str]) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)

        self.octoprint_host_edit = QLineEdit(initial_settings.get("octoprint_host", ""), page)
        self.octoprint_host_edit.setPlaceholderText("http://octopi.local")
        form.addRow("Server URL", self.octoprint_host_edit)

        self.octoprint_key_edit = QLineEdit(initial_settings.get("octoprint_key", ""), page)
        form.addRow("API Key", self.octoprint_key_edit)

        return page

    def _build_bambu_connect_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(
            "3DMake can send prints to your Bambu printer using Bambu Connect,\n"
            "an accessible software tool you can download from Bambu Labs.",
            page,
        ))

        download_button = QPushButton("Open download page", page)
        download_button.clicked.connect(lambda: webbrowser.open(BAMBU_CONNECT_DOWNLOAD_PAGE))
        layout.addWidget(download_button)

        return page


class SettingsDialog(QDialog):
    """Tabbed settings dialog, backed by the global defaults.toml."""

    def __init__(self, config_dir: Path, parent=None):
        super().__init__(parent)
        self.config_dir = config_dir
        self.settings = load_global_settings(config_dir)

        self.setWindowTitle("3DMake Settings")
        self.resize(500, 400)

        layout = QVBoxLayout(self)

        tabs = QTabWidget(self)
        layout.addWidget(tabs)

        self.connection_panel = ConnectionSettingsPanel(self.settings, self)
        tabs.addTab(self.connection_panel, "Printer")

        tabs.addTab(self._build_ai_settings_page(), "AI")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save")
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_ai_settings_page(self) -> QWidget:
        # TODO: real AI settings (Gemini API key, model choice, etc.)
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("AI settings go here.", page))
        return page

    def _save_and_accept(self):
        self.settings.update(self.connection_panel.collect_settings())
        save_global_settings(self.config_dir, self.settings)
        self.accept()


def open_settings_dialog(parent: QWidget):
    SettingsDialog(CONFIG_DIR, parent).exec()


class WorkspaceWindow(QMainWindow):
    # Shared by every subclass via inheritance - STL and project wsids can
    # never collide (one's a file path, one's a directory path), so one
    # registry for all workspace window types is fine.
    _registry: dict[str, "WorkspaceWindow"] = {}

    def __init__(self, base_path: Path):
        ''' Do not call this constructor, call open_or_focus(). '''
        super().__init__()
        self.base_path = base_path
        self.setWindowTitle(base_path.name)

    @property
    def wsid(self) -> str:
        return str(self.base_path.absolute())

    @classmethod
    def open_or_focus(cls, base_path: Path) -> "WorkspaceWindow":
        wsid = str(Path(base_path).absolute())
        existing = cls._registry.get(wsid)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return existing

        window = cls(base_path)
        cls._registry[window.wsid] = window
        window.destroyed.connect(lambda: cls._registry.pop(window.wsid, None))
        window.show()
        close_startup_window()
        return window

class ProfileEditor(QGroupBox):
    """Shows every key/value pair in a ProfileConfig, grouped by category.

    Categories are listed in a sidebar; picking one shows just that category's
    fields, so keyboard and screen-reader users can jump straight to a category
    instead of tabbing through all of them in sequence.

    Edited fields are outlined and get an enabled revert button; changed_values()
    exposes just the edited key/value pairs, for turning into a temp overlay
    before slicing (see STLWorkspaceWindow._write_edited_settings_overlay).

    THD: The below has not been evaluated for accuracy or whether it actually works!
    Inherits from QGroupBox rather than a plain QWidget so macOS accessibility
    tags the wrapper with the Grouping role - a plain QWidget reports the
    generic Client role, which VoiceOver treats as an opaque container and
    fails to descend into (children like category_list end up invisible to
    screen readers even when they're in the focus chain). setFlat(True) and
    no title keep the visual appearance unchanged.
    """

    CHANGED_COLOR = "#d4900a"
    OVERLAY_COLOR = "#2b7de9"
    CHANGED_STYLE = f"border: 2px solid {CHANGED_COLOR};"
    OVERLAY_STYLE = f"border: 2px solid {OVERLAY_COLOR};"

    def __init__(self, profile_config: ProfileConfig, parent=None):
        super().__init__(parent)
        self.setFlat(True)

        self.profile_config = profile_config
        self.value_edits: dict[str, QLineEdit] = {}
        self.revert_buttons: dict[str, QPushButton] = {}
        self.status_labels: dict[str, QLabel] = {}

        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self.category_list = QListWidget(self)
        self.category_list.setAccessibleName("Setting categories")
        self.category_list.setMaximumWidth(180)
        outer_layout.addWidget(self.category_list)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        outer_layout.addWidget(scroll_area, 1)

        self.category_pages = QStackedWidget()
        scroll_area.setWidget(self.category_pages)

        self.category_list.currentRowChanged.connect(self.category_pages.setCurrentIndex)
        self.category_list.itemActivated.connect(self._focus_first_field)

        self.set_profile_config(profile_config)

    def set_profile_config(self, profile_config: ProfileConfig):
        self.profile_config = profile_config
        self.value_edits.clear()
        self.revert_buttons.clear()
        self.status_labels.clear()

        self.category_list.clear()
        while self.category_pages.count():
            page = self.category_pages.widget(0)
            self.category_pages.removeWidget(page)
            page.deleteLater()

        for category_name, values in profile_config.by_category.items():
            if not values:
                continue
            self.category_list.addItem(category_name or "Uncategorized")
            self.category_pages.addWidget(self._build_category_box(category_name, values))

        if self.category_list.count():
            self.category_list.setCurrentRow(0)

    def _build_category_box(self, category_name: str, values: dict[str, str]) -> QGroupBox:
        box = QGroupBox(category_name or "Uncategorized", self)
        form = QFormLayout(box)

        for key, value in values.items():
            edit = QLineEdit(value, box)
            self.value_edits[key] = edit

            revert_button = QPushButton("↺", box)
            revert_button.setFixedWidth(24)
            revert_button.setEnabled(False)
            revert_button.setAccessibleName(f"Revert {key.replace('_', ' ')} to original value")
            revert_button.setStyleSheet(
                "QPushButton { border: none; background: transparent; border-radius: 8px; }"
                "QPushButton:hover:enabled { background-color: palette(midlight); }"
            )
            revert_button.clicked.connect(lambda _checked, k=key: self._revert_value(k))
            self.revert_buttons[key] = revert_button

            edit.textChanged.connect(lambda _text, k=key: self._on_value_changed(k))

            field_row = QHBoxLayout()
            field_row.addWidget(edit)
            field_row.addWidget(revert_button)

            status_label = QLabel("", box)
            f = status_label.font()
            f.setPointSizeF(f.pointSizeF() * 0.85)
            status_label.setFont(f)
            status_label.setVisible(False)
            self.status_labels[key] = status_label

            field_container = QWidget(box)
            field_vbox = QVBoxLayout(field_container)
            field_vbox.setContentsMargins(0, 0, 0, 0)
            field_vbox.setSpacing(2)
            field_vbox.addLayout(field_row)
            field_vbox.addWidget(status_label)

            self._on_value_changed(key)  # apply initial styling, e.g. an overlay highlight

            # addRow(QWidget*, QWidget*) - unlike the addRow(str, QWidget*)
            # overload used elsewhere in this file - does NOT auto-buddy the
            # label to the field, so it has to be done explicitly here or
            # every field in a category falls back to being announced as the
            # QGroupBox's own title instead of its own setting name.
            label = QLabel(key.replace('_', ' '), box)
            label.setBuddy(edit)
            form.addRow(label, field_container)

        return box

    def _focus_first_field(self, _item: QListWidgetItem):
        page = self.category_pages.currentWidget()
        first_edit = page.findChild(QLineEdit) if page else None
        if first_edit is not None:
            first_edit.setFocus()
            first_edit.selectAll()

    def _on_value_changed(self, key: str):
        edit = self.value_edits[key]
        changed = edit.text() != self.profile_config.get(key)
        overlay_source = self.profile_config.overlay_source(key)

        # A manual change always wins visually over an overlay highlight, even
        # for a field an overlay also touched.
        if changed:
            style, description = self.CHANGED_STYLE, "Changed from original value"
            status_text, status_color = "Edited", self.CHANGED_COLOR
        elif overlay_source:
            style, description = self.OVERLAY_STYLE, f"Set by overlay: {overlay_source}"
            status_text, status_color = f"Set by overlay: {overlay_source}", self.OVERLAY_COLOR
        else:
            style, description = "", ""
            status_text, status_color = "", ""

        edit.setStyleSheet(style)
        edit.setAccessibleDescription(description)
        self.revert_buttons[key].setEnabled(changed)

        status_label = self.status_labels.get(key)
        if status_label is not None:
            status_label.setText(status_text)
            if status_text:
                status_label.setStyleSheet(f"color: {status_color};")
            status_label.setVisible(bool(status_text))

    def _revert_value(self, key: str):
        # Setting text fires textChanged, which re-runs _on_value_changed and
        # clears the styling/accessible description/button state on its own.
        self.value_edits[key].setText(self.profile_config.get(key, ""))

    def changed_values(self) -> dict[str, str]:
        return {
            key: edit.text()
            for key, edit in self.value_edits.items()
            if edit.text() != self.profile_config.get(key)
        }


class STLWorkspaceWindow(WorkspaceWindow):
    def __init__(self, stl_path: Path):
        super().__init__(base_path=stl_path)
        self.resize(800, 600)

        tabs = QTabWidget()
        tabs.addTab(self._build_examine_tab(stl_path), "E&xamine model")
        self._slice_tab_index = tabs.addTab(self._build_slice_tab(), "&Slice")
        tabs.addTab(QWidget(), "&Print")

        build_file_menu(self)
        self.setCentralWidget(tabs)
        # setTabOrder is ignored when the target widgets aren't visible, and
        # QTabWidget hides non-current pages via its internal QStackedWidget.
        # Re-run tab-order setup each time the Slice tab becomes current so
        # our setTabOrder calls happen on visible widgets and take effect.
        tabs.currentChanged.connect(self._on_tab_changed)
        self._start_info_process(stl_path)

    def _on_tab_changed(self, index: int):
        if index == self._slice_tab_index:
            self._setup_tab_order()

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

    def _build_slice_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.printer_profile_selection = QComboBox()
        self.printer_profile_selection.addItems(list_printer_profiles(CONFIG_DIR))

        form = QFormLayout()
        form.addRow("Printer &profile", self.printer_profile_selection)
        layout.addLayout(form)

        self.overlay_selection = QComboBox()
        self.add_overlay_button = QPushButton("&Add")
        self.add_overlay_button.clicked.connect(self._add_overlay)

        overlay_row = QHBoxLayout()
        overlay_row.addWidget(self.overlay_selection)
        overlay_row.addWidget(self.add_overlay_button)

        # addRow(str, QLayout*), unlike addRow(str, QWidget*), does not
        # auto-buddy the label (there's no single field widget to buddy to
        # when the field is a layout) - build the label explicitly and buddy
        # it to the combo box ourselves, same as elsewhere in this file.
        add_overlay_label = QLabel("Add &overlay")
        add_overlay_label.setBuddy(self.overlay_selection)

        overlay_add_form = QFormLayout()
        overlay_add_form.addRow(add_overlay_label, overlay_row)
        layout.addLayout(overlay_add_form)

        self.overlay_list = QListWidget()
        self.overlay_list.setFlow(QListView.Flow.LeftToRight)
        # A single row that scrolls horizontally if it overflows, rather than
        # wrapping to multiple rows - the overlay count is usually small
        # enough to fit on one line, and this makes the list's height
        # trivial to get right (always exactly one row tall) instead of
        # needing to account for however many wrapped rows are showing.
        self.overlay_list.setWrapping(False)
        self.overlay_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.overlay_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.overlay_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.overlay_list.model().rowsMoved.connect(self._rebuild_profile_settings)
        selected_overlays_label = bold_label("Selected overlays (applied in order)")
        selected_overlays_label.setBuddy(self.overlay_list)
        layout.addWidget(selected_overlays_label)
        layout.addWidget(self.overlay_list)

        self._refresh_available_overlays()
        self._update_overlay_list_height()

        layout.addWidget(bold_label("Profile settings"))

        self.profile_settings_layout = QVBoxLayout()
        self.profile_settings_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.profile_settings_layout)

        profile_name = self.printer_profile_selection.currentText()
        initial_config = read_profile_config(CONFIG_DIR, profile_name, self._selected_overlay_names())
        self.profile_editor = ProfileEditor(initial_config)
        self.profile_settings_layout.addWidget(self.profile_editor)

        self.slice_button = QPushButton("&Slice")
        self.slice_button.clicked.connect(self._run_slice)
        layout.addWidget(self.slice_button)

        self.printer_profile_selection.currentTextChanged.connect(self._rebuild_profile_settings)

        # Hidden until the first slice run - nothing to show before then.
        self.slice_console_label = bold_label("Slice output")
        self.slice_console = QTextEdit()
        self.slice_console.setReadOnly(True)
        self.slice_console_label.setBuddy(self.slice_console)
        self.slice_console_label.setVisible(False)
        self.slice_console.setVisible(False)
        layout.addWidget(self.slice_console_label)
        layout.addWidget(self.slice_console)

        return tab

    def _write_edited_settings_overlay(self) -> "Path | None":
        ''' Writes settings edited in the "Profile settings" editor to a temp
        overlay file, returned as a Path - or None if nothing's been changed.
        Shared (not slice-tab-private) since the Print tab will need the exact
        same thing later, as `3dm print` always implies slicing too. '''
        changed = self.profile_editor.changed_values()
        if not changed:
            return None

        # Delete the previous run's temp dir first so these don't pile up
        # across repeated slice/print runs within the same session.
        old_dir = getattr(self, "_edited_settings_temp_dir", None)
        if old_dir is not None:
            shutil.rmtree(old_dir, ignore_errors=True)

        self._edited_settings_temp_dir = Path(tempfile.mkdtemp(prefix="3dmake-gui-"))
        overlay_path = self._edited_settings_temp_dir / "edited_settings.ini"
        write_overlay_file(overlay_path, changed)
        return overlay_path

    def _run_slice(self):
        if getattr(self, "slice_process", None) is not None \
                and self.slice_process.state() != QProcess.ProcessState.NotRunning:
            return

        self.slice_console.clear()
        self.slice_console_label.setVisible(True)
        self.slice_console.setVisible(True)
        self.slice_button.setEnabled(False)

        args = ["slice", str(self.base_path), "--profile", self.printer_profile_selection.currentText()]
        for overlay_name in self._selected_overlay_names():
            args += ["--overlay", overlay_name]

        edited_overlay_path = self._write_edited_settings_overlay()
        if edited_overlay_path is not None:
            args += ["--overlay", str(edited_overlay_path)]

        # Parented to self so Qt keeps it alive for the window's lifetime -
        # an unparented/unreferenced QProcess can get garbage collected mid-run.
        self.slice_process = QProcess(self)
        self.slice_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        env = QProcessEnvironment.systemEnvironment()
        env.insert("_3DMAKE_TEST_FLAGS", "GUI_MODE")
        env.insert("PYTHONUNBUFFERED", "1")
        self.slice_process.setProcessEnvironment(env)

        self.slice_process.readyReadStandardOutput.connect(self._on_slice_output_ready)
        self.slice_process.finished.connect(self._on_slice_finished)
        self.slice_process.start(sys.executable, [str(THREEDMAKE_SCRIPT), *args])

    def _on_slice_finished(self):
        self.slice_button.setEnabled(True)

    def _on_slice_output_ready(self):
        output = bytes(self.slice_process.readAllStandardOutput()).decode()
        self.slice_console.insertPlainText(output)
        # Screen readers are only notified of new text if the caret position
        # changes after the edit - moving just the scrollbar is silent to them.
        self.slice_console.moveCursor(QTextCursor.MoveOperation.End)
        scrollbar = self.slice_console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _rebuild_profile_settings(self, *_):
        profile_name = self.printer_profile_selection.currentText()
        profile_config = read_profile_config(CONFIG_DIR, profile_name, self._selected_overlay_names())
        self.profile_editor.set_profile_config(profile_config)

    def _setup_tab_order(self):
        QWidget.setTabOrder(self.printer_profile_selection, self.overlay_selection)
        QWidget.setTabOrder(self.overlay_selection, self.add_overlay_button)
        QWidget.setTabOrder(self.add_overlay_button, self.overlay_list)
        QWidget.setTabOrder(self.overlay_list, self.profile_editor.category_list)
        # Tab from the category list jumps directly to Slice, skipping the
        # individual setting fields. Press Enter/Return on a category to
        # focus its first field (wired via itemActivated → _focus_first_field).
        QWidget.setTabOrder(self.profile_editor.category_list, self.slice_button)

    def _selected_overlay_names(self) -> list[str]:
        return [self.overlay_list.item(i).text() for i in range(self.overlay_list.count())]

    def _refresh_available_overlays(self):
        selected = set(self._selected_overlay_names())
        all_names = sorted({o.name for o in list_overlays(CONFIG_DIR)})
        self.overlay_selection.clear()
        self.overlay_selection.addItems([n for n in all_names if n not in selected])

    def _add_overlay(self):
        name = self.overlay_selection.currentText()
        if not name:
            return

        item = QListWidgetItem(name)
        self.overlay_list.addItem(item)
        row = self._build_overlay_row(item)
        item.setSizeHint(row.sizeHint())
        self.overlay_list.setItemWidget(item, row)

        self._refresh_available_overlays()
        self._update_overlay_list_height()
        self._rebuild_profile_settings()

    def _build_overlay_row(self, item: QListWidgetItem) -> QWidget:
        row = QWidget()
        row.setObjectName("overlayPill")
        # Scoped to #overlayPill so this doesn't cascade to the label/button
        # inside it - a bare "QWidget { ... }" selector would style children too.
        row.setStyleSheet(
            "QWidget#overlayPill {"
            "  border: 1px solid palette(mid);"
            "  border-radius: 10px;"
            "  background-color: palette(button);"
            "}"
        )
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 2, 2, 2)
        row_layout.addWidget(QLabel(item.text()))

        remove_button = QPushButton("×")
        remove_button.setFixedWidth(20)
        remove_button.setAccessibleName(f"Remove {item.text()}")
        remove_button.clicked.connect(lambda: self._remove_overlay_item(item))
        # De-emphasized so it reads as part of the pill rather than its own
        # separate button - just a faint hover highlight instead of a border.
        remove_button.setStyleSheet(
            "QPushButton { border: none; background: transparent; border-radius: 8px; }"
            "QPushButton:hover { background-color: palette(midlight); }"
        )
        row_layout.addWidget(remove_button)

        return row

    def _remove_overlay_item(self, item: QListWidgetItem):
        # Look up the item's *current* row rather than capturing an index up
        # front, since drag-and-drop reordering can move it after this closure
        # was created.
        self.overlay_list.takeItem(self.overlay_list.row(item))
        self._refresh_available_overlays()
        self._update_overlay_list_height()
        self._rebuild_profile_settings()

    def _update_overlay_list_height(self):
        if self.overlay_list.count() > 0:
            row_height = self.overlay_list.sizeHintForRow(0)
        else:
            row_height = self.overlay_list.fontMetrics().height() + 12
        frame = 2 * self.overlay_list.frameWidth()
        self.overlay_list.setFixedHeight(row_height + frame + 4)

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


class ProjectWorkspaceWindow(WorkspaceWindow):
    def __init__(self, base_path: Path):
        super().__init__(base_path)
        self.resize(800, 600)
        build_file_menu(self)

        box = QWidget()
        layout = QVBoxLayout(box)
        layout.addWidget(bold_label(base_path.name))
        self.setCentralWidget(box)


def build_file_menu(window: QMainWindow):
    ''' Shared by every window type (startup, STL, project) so Open/New are
    available everywhere, not just from the startup window. '''
    file_menu = window.menuBar().addMenu("&File")

    open_model_action = QAction("Open &Model…", window)
    open_model_action.setShortcut(QKeySequence.Open)  # Ctrl+O
    open_model_action.triggered.connect(lambda: open_model(window))
    file_menu.addAction(open_model_action)

    open_project_action = QAction("Open &Project…", window)
    open_project_action.triggered.connect(lambda: open_project(window))
    file_menu.addAction(open_project_action)

    new_project_action = QAction("&New Project…", window)
    new_project_action.triggered.connect(lambda: new_project(window))
    file_menu.addAction(new_project_action)

    file_menu.addSeparator()

    settings_action = QAction("&Settings…", window)
    settings_action.triggered.connect(lambda: open_settings_dialog(window))
    file_menu.addAction(settings_action)


def open_model(parent: QWidget):
    path, _ = QFileDialog.getOpenFileName(parent, "Open STL File", "", "STL Files (*.stl)")
    if not path:
        return
    path = Path(path)
    if path.is_dir():
        # Some file choosers allow selecting a folder from an "open file" dialog;
        # if that happens, open it as a project instead of failing on it as an STL.
        open_project_path(parent, path)
        return
    STLWorkspaceWindow.open_or_focus(path)


def open_project(parent: QWidget):
    path = QFileDialog.getExistingDirectory(parent, "Open 3DMake Project Folder")
    if not path:
        return
    open_project_path(parent, Path(path))


def open_project_path(parent: QWidget, path: Path):
    if not (path / "3dmake.toml").is_file():
        QMessageBox.critical(parent, "Not a 3DMake Project", f"'{path}' does not contain a 3dmake.toml file.")
        return
    ProjectWorkspaceWindow.open_or_focus(path)


_pending_processes: list[QProcess] = []

def new_project(parent: QWidget):
    filename, _ = QFileDialog.getSaveFileName(parent, "New 3DMake Project", str(Path.home() / "MyProject"))
    if not filename:
        return
    target = Path(filename)

    # Not owned by any window (the project window doesn't exist until this
    # finishes), so parented to the app and kept alive via this list until done -
    # an unparented/unreferenced QProcess can get garbage collected mid-run.
    process = QProcess(QApplication.instance())
    process.setWorkingDirectory(str(target.parent))
    process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

    env = QProcessEnvironment.systemEnvironment()
    env.insert("_3DMAKE_TEST_FLAGS", "GUI_MODE")
    env.insert("PYTHONUNBUFFERED", "1")
    process.setProcessEnvironment(env)

    def on_finished():
        _pending_processes.remove(process)
        open_project_path(parent, target)

    _pending_processes.append(process)
    process.finished.connect(on_finished)
    process.start(sys.executable, [str(THREEDMAKE_SCRIPT), "new"])
    process.write(f"{target.name}\n".encode())
    process.closeWriteChannel()


class StartupWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3DMake")
        build_file_menu(self)

        label = QLabel(
            "No project or STL file is open.\n\n"
            "Use File → Open Model… to open an STL file, File → Open "
            "Project… to open an existing 3DMake project, or File → New "
            "Project… to create one."
        )
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.addWidget(label)
        self.setCentralWidget(box)


_startup_window: "StartupWindow | None" = None

def close_startup_window():
    global _startup_window
    if _startup_window is not None:
        _startup_window.close()
        _startup_window = None


app = QApplication(sys.argv)
signal.signal(signal.SIGINT, signal.SIG_DFL)

_startup_window = StartupWindow()
_startup_window.show()

app.exec()
