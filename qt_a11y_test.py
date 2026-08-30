#!/usr/bin/env python3
"""
Qt / PySide6 accessibility test bench.

Reproduces the widget accessibility issues documented in qt_issues.md so they
can be re-tested against different PySide6 / Qt versions and in different
launch contexts (Terminal vs .app bundle).

Usage:
    # Run directly. On macOS, VoiceOver will typically NOT see the app when
    # launched this way — the process isn't registered with LaunchServices.
    uv run python qt_a11y_test.py

    # Build a minimal .app wrapper alongside this script (for VoiceOver
    # testing on macOS) and launch it in one step.
    uv run python qt_a11y_test.py --run-app

    # Build the .app wrapper but don't launch it (useful for scripting).
    uv run python qt_a11y_test.py --build-app
    open ./QtA11yTest.app

    # Build the .app somewhere else:
    uv run python qt_a11y_test.py --build-app /tmp

The window title includes the PySide6 and Qt runtime versions so you can tell
runs apart when you compare across versions.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


APP_NAME = "QtA11yTest"
BUNDLE_ID = "net.blindmakers.qta11ytest"


def build_app_bundle(dest_dir: Path) -> Path:
    """Build a minimal .app wrapper that launches this script via the current
    Python interpreter. Returns the path to the created bundle."""
    script_path = Path(__file__).resolve()
    # Do NOT .resolve() the interpreter: .venv/bin/python is a symlink to the
    # base interpreter, and resolving it bypasses the venv (site-packages,
    # including PySide6, wouldn't be visible).
    python_path = Path(sys.executable)
    if not python_path.is_absolute():
        python_path = python_path.absolute()

    app_dir = dest_dir / f"{APP_NAME}.app"
    contents = app_dir / "Contents"
    macos = contents / "MacOS"
    macos.mkdir(parents=True, exist_ok=True)

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>{APP_NAME}</string>
    <key>CFBundleDisplayName</key><string>Qt A11y Test</string>
    <key>CFBundleIdentifier</key><string>{BUNDLE_ID}</string>
    <key>CFBundleVersion</key><string>1.0</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>CFBundleExecutable</key><string>launch</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>LSUIElement</key><false/>
</dict>
</plist>
"""

    launcher = f"""#!/bin/bash
exec "{python_path}" "{script_path}" "$@"
"""

    (contents / "Info.plist").write_text(plist)
    launcher_path = macos / "launch"
    launcher_path.write_text(launcher)
    launcher_path.chmod(0o755)

    return app_dir


def run_gui() -> int:
    from PySide6 import QtCore, QtGui, QtWidgets

    class TreeCrashDialog(QtWidgets.QDialog):
        """Isolated dialog for the QTreeView expand/collapse crash test.

        Kept off the main window so a crash here doesn't take out access to
        the other tests. Historically QTreeView with VoiceOver on crashed on
        expand/collapse of a node."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("QTreeView crash test")
            self.setAccessibleName("QTreeView crash test dialog")

            layout = QtWidgets.QVBoxLayout(self)
            explainer = QtWidgets.QLabel(
                "Turn VoiceOver on, focus the tree, then expand and collapse "
                "the top-level items with left/right arrow keys. Historically "
                "this crashed the process."
            )
            explainer.setWordWrap(True)
            layout.addWidget(explainer)

            tree = QtWidgets.QTreeWidget()
            tree.setHeaderLabels(["Name", "Kind"])
            tree.setAccessibleName("Sample tree")
            for i in range(3):
                top = QtWidgets.QTreeWidgetItem([f"Group {i + 1}", "group"])
                for j in range(4):
                    child = QtWidgets.QTreeWidgetItem(
                        [f"Item {i + 1}.{j + 1}", "leaf"]
                    )
                    top.addChild(child)
                tree.addTopLevelItem(top)
            tree.expandAll()
            tree.collapseAll()
            layout.addWidget(tree)

            close_btn = QtWidgets.QPushButton("Close")
            close_btn.clicked.connect(self.accept)
            layout.addWidget(close_btn)

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            pyside_ver = QtCore.__version__
            qt_ver = QtCore.qVersion()
            self.setWindowTitle(
                f"Qt A11y Test — PySide6 {pyside_ver} / Qt {qt_ver}"
            )
            self.resize(720, 900)

            central = QtWidgets.QWidget()
            self.setCentralWidget(central)
            outer = QtWidgets.QVBoxLayout(central)

            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            outer.addWidget(scroll)

            content = QtWidgets.QWidget()
            scroll.setWidget(content)
            v = QtWidgets.QVBoxLayout(content)

            v.addWidget(self._build_intro())
            v.addWidget(self._build_labels_group())
            v.addWidget(self._build_combobox_group())
            v.addWidget(self._build_listwidget_group())
            v.addWidget(self._build_info_display_group())
            v.addWidget(self._build_tree_launcher_group())
            v.addStretch(1)

            self.statusBar().showMessage(
                f"PySide6 {pyside_ver} · Qt {qt_ver} · "
                f"Launched from: {'.app bundle' if _launched_from_app() else 'Terminal / uv'}"
            )

        def _build_intro(self) -> QtWidgets.QWidget:
            box = QtWidgets.QGroupBox("How to use this bench")
            lay = QtWidgets.QVBoxLayout(box)
            text = QtWidgets.QLabel(
                "Turn a screen reader on (VoiceOver on macOS, NVDA on "
                "Windows) and tab through each section. Each group tests one "
                "known issue. See qt_issues.md for the history behind each "
                "case. The window title shows the PySide6 / Qt version so "
                "you can distinguish runs."
            )
            text.setWordWrap(True)
            lay.addWidget(text)
            return box

        def _build_labels_group(self) -> QtWidgets.QWidget:
            """Test: does setBuddy / setAccessibleName reach the screen reader?

            Four QLineEdits, each associated with its label a different way.
            Focus each in turn and note whether the label is announced."""
            box = QtWidgets.QGroupBox("1. Label association (setBuddy / setAccessibleName)")
            form = QtWidgets.QFormLayout(box)

            # Case A: setBuddy only.
            edit_a = QtWidgets.QLineEdit()
            label_a = QtWidgets.QLabel("&Buddy only (Alt+B):")
            label_a.setBuddy(edit_a)
            form.addRow(label_a, edit_a)

            # Case B: setAccessibleName only.
            edit_b = QtWidgets.QLineEdit()
            edit_b.setAccessibleName("Accessible name only")
            label_b = QtWidgets.QLabel("Accessible name only:")
            form.addRow(label_b, edit_b)

            # Case C: both.
            edit_c = QtWidgets.QLineEdit()
            edit_c.setAccessibleName("Both buddy and accessible name")
            label_c = QtWidgets.QLabel("Bo&th (Alt+T):")
            label_c.setBuddy(edit_c)
            form.addRow(label_c, edit_c)

            # Case D: neither (control).
            edit_d = QtWidgets.QLineEdit()
            label_d = QtWidgets.QLabel("Neither (control):")
            form.addRow(label_d, edit_d)

            note = QtWidgets.QLabel(
                "Expected on macOS/VoiceOver: only 'Accessible name only' "
                "and 'Both' should have any spoken label. Historically "
                "setBuddy did not reach VoiceOver."
            )
            note.setWordWrap(True)
            form.addRow(note)
            return box

        def _build_combobox_group(self) -> QtWidgets.QWidget:
            """Test: does non-editable QComboBox map to the correct
            NSAccessibility role?

            Compare it against an editable QComboBox with the same items."""
            box = QtWidgets.QGroupBox("2. QComboBox role (editable vs non-editable)")
            form = QtWidgets.QFormLayout(box)

            items = ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]

            non_edit = QtWidgets.QComboBox()
            non_edit.addItems(items)
            non_edit.setEditable(False)
            non_edit.setAccessibleName("Non-editable combo")
            form.addRow("Non-editable:", non_edit)

            edit = QtWidgets.QComboBox()
            edit.addItems(items)
            edit.setEditable(True)
            edit.setAccessibleName("Editable combo")
            form.addRow("Editable:", edit)

            note = QtWidgets.QLabel(
                "Historically the non-editable combo was announced with the "
                "wrong role on macOS. Check the announced role for each."
            )
            note.setWordWrap(True)
            form.addRow(note)
            return box

        def _build_listwidget_group(self) -> QtWidgets.QWidget:
            """Test: PYSIDE-3305 — QListWidget item announcement in VoiceOver."""
            box = QtWidgets.QGroupBox("3. QListWidget (PYSIDE-3305)")
            lay = QtWidgets.QVBoxLayout(box)

            label = QtWidgets.QLabel("&Sample list:")
            lay.addWidget(label)

            lw = QtWidgets.QListWidget()
            lw.setAccessibleName("Sample list")
            for i in range(10):
                item = QtWidgets.QListWidgetItem(f"Row {i + 1}")
                lw.addItem(item)
            label.setBuddy(lw)
            lay.addWidget(lw)

            note = QtWidgets.QLabel(
                "Focus the list, then arrow up/down. VoiceOver should "
                "announce each row as you move. On affected PySide6 "
                "versions items were not read at all."
            )
            note.setWordWrap(True)
            lay.addWidget(note)
            return box

        def _build_info_display_group(self) -> QtWidgets.QWidget:
            """Test: readonly QLineEdit vs QLabel for a static info display.

            NVDA-driven case: the readonly QLineEdit for model info didn't
            announce well; swapping to a QLabel worked better."""
            box = QtWidgets.QGroupBox("4. Info display (readonly QLineEdit vs QLabel)")
            form = QtWidgets.QFormLayout(box)

            info_text = "Bounds: 42.0 x 18.5 x 6.2 mm · Volume: 3820 mm^3"

            ro_edit = QtWidgets.QLineEdit(info_text)
            ro_edit.setReadOnly(True)
            ro_edit.setAccessibleName("Model info (readonly edit)")
            form.addRow("Readonly QLineEdit:", ro_edit)

            plain_label = QtWidgets.QLabel(info_text)
            plain_label.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
                | QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
            plain_label.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
            plain_label.setAccessibleName("Model info (label)")
            form.addRow("QLabel (selectable):", plain_label)

            note = QtWidgets.QLabel(
                "Compare how the value is announced by each. On Windows/NVDA "
                "the readonly QLineEdit was troublesome, and the label form "
                "worked better."
            )
            note.setWordWrap(True)
            form.addRow(note)
            return box

        def _build_tree_launcher_group(self) -> QtWidgets.QWidget:
            """Test: QTreeView crash on expand/collapse with VoiceOver on.

            Behind a button so a crash doesn't take out the whole bench."""
            box = QtWidgets.QGroupBox("5. QTreeView crash test (opt-in)")
            lay = QtWidgets.QVBoxLayout(box)

            warn = QtWidgets.QLabel(
                "This has historically CRASHED the process on macOS with "
                "VoiceOver enabled when expanding or collapsing a node. "
                "Test the other groups first so you don't lose the session."
            )
            warn.setWordWrap(True)
            lay.addWidget(warn)

            btn = QtWidgets.QPushButton("Open tree test dialog")
            btn.setAccessibleName("Open QTreeView crash test dialog")
            btn.clicked.connect(self._open_tree_dialog)
            lay.addWidget(btn)
            return box

        def _open_tree_dialog(self):
            dlg = TreeCrashDialog(self)
            dlg.exec()

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName("Qt A11y Test")

    win = MainWindow()
    win.show()
    return app.exec()


def _launched_from_app() -> bool:
    """Rough heuristic: are we running inside a .app bundle launched via
    LaunchServices? True when our parent path chain includes '.app/Contents/MacOS'."""
    return ".app/Contents/MacOS" in str(Path(sys.argv[0]).resolve()) or (
        os.environ.get("__CFBundleIdentifier", "") == BUNDLE_ID
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-app",
        nargs="?",
        const=".",
        metavar="DIR",
        help=(
            "Build a minimal .app wrapper in DIR (default: current directory) "
            "and exit. Then run `open DIR/QtA11yTest.app`."
        ),
    )
    parser.add_argument(
        "--run-app",
        nargs="?",
        const=".",
        metavar="DIR",
        help=(
            "Build the .app wrapper in DIR (default: current directory) and "
            "immediately launch it via `open`. This is the one-shot way to "
            "test under LaunchServices / VoiceOver."
        ),
    )
    args = parser.parse_args()

    build_dest = args.run_app if args.run_app is not None else args.build_app
    if build_dest is not None:
        dest = Path(build_dest).resolve()
        if not dest.is_dir():
            print(f"error: {dest} is not a directory", file=sys.stderr)
            return 2
        app_path = build_app_bundle(dest)
        print(f"Built {app_path}")
        if args.run_app is not None:
            print(f"Launching {app_path}...")
            subprocess.run(["open", str(app_path)], check=True)
        else:
            print(f"Launch with:  open {app_path}")
        return 0

    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
