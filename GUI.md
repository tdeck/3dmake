# NiceGUI GUI — developer handoff

Everything lives in `/Users/troy/3dmake/webgui.py`. No changes elsewhere in the repo; the GUI shells out to `python 3dm.py …` as a subprocess for anything it needs from the CLI.

This document assumes you know Python and web dev basics but haven't touched NiceGUI. It's meant to be read once end-to-end.

## Why NiceGUI

There's a parallel PySide6 prototype on the `pyside6-gui` branch. It works, but Qt's macOS accessibility bridge is partial and undocumented — `setBuddy`/`setAccessibleName` don't reach VoiceOver, non-editable `QComboBox` maps to the wrong `NSAccessibility` role, `QTreeView` crashes on expand/collapse with VoiceOver on, and Accessibility Inspector sees nothing at all unless we wrap Python in a `.app` bundle. Our users are visually impaired and macOS + VoiceOver is a target platform, so NiceGUI is a second attempt on top of browser-native accessibility (which is far more mature).

NiceGUI is a Python framework that renders HTML + Vue + Quasar. It runs its own FastAPI/uvicorn server; in "native" mode a pywebview window points at that server. So the shipped app looks and feels desktop-like, but under the hood every interactive element is a real DOM element with real ARIA semantics.

## Running it

Development:

```
uv run python webgui.py
```

If you want to verify the file loads without spawning the native window:

```
uv run python troys_local_load_test.py
```

**macOS accessibility caveat.** VoiceOver only exposes an app's controls if the process is registered with LaunchServices, which basically means it needs to be launched from a `.app` bundle. `uv run python webgui.py` from Terminal works for development but VoiceOver will see nothing. During prototyping we've been building a minimal `.app` bundle by hand:

```
/tmp/3DMake.app/
├── Contents/
│   ├── Info.plist          # CFBundleName=3DMake, CFBundleIdentifier, etc.
│   └── MacOS/
│       └── launch          # #!/bin/bash exec /path/to/.venv/bin/python /path/to/webgui.py
```

Then `open /tmp/3DMake.app`. See git history for the exact Info.plist we've been using. Production packaging (PyInstaller / py2app) hasn't been set up yet.

## Overall shape

The whole GUI is one file, structured top-to-bottom as:

1. Imports, constants (`CONFIG_DIR`, `THREEDMAKE_SCRIPT`, `NAMED_PROJECTION_CODE`, colour palette, etc.).
2. **Module-level state**: `WorkspaceState` (for the STL workflow) and `ProjectState` (for the project editor). Both are `@dataclass` instances at module scope. In NiceGUI's native mode we have a single user with a single window, so a single shared state object is fine.
3. **A UI design note block** — please read it before touching any refreshable/listbox code (see "Design gotcha" below).
4. **Subprocess helper** `stream_3dm(args, on_line, cwd=None)` — runs `python 3dm.py <args>` and streams stdout line-by-line to a callable. All CLI invocations go through this.
5. **`OutputConsole`** — reusable class wrapping a labelled, focusable, fixed-height, screen-reader-friendly `<textarea>`. Used for model info on Examine tab, slice output on Slice tab, and 3dm build info on the project page. Has `.push(line)`, `.clear()`, `.set_visibility()`, `.focus()`, and `.run_3dm(args, cwd)`.
6. **`show_settings_dialog()`** — the tabbed connection-settings modal.
7. **Module-level action flows** — `_open_stl_flow`, `_open_project_flow`, `_new_project_flow`, `_show_settings_flow`, `_save_from_menu`, `_examine_from_menu`. Async coroutines. Callable from both page-scoped handlers (buttons, keyboard) and the cross-process menu bridge.
8. **`_install_global_shortcuts(...)`** — attaches `ui.keyboard` to the current page and dispatches Cmd/Ctrl+O, Cmd/Ctrl+S, and F5 to the right flow.
9. **Menu bridge endpoint** `POST /_menu_bridge/{action}` — how the native menu talks to the NiceGUI server; see "Cross-process menu" below.
10. **Pages** — `startup_page` (`/`), `workspace_page` (`/workspace`), `project_page` (`/project`). Each is decorated with `@ui.page(...)`. Every page function is re-entered fresh on navigation.
11. **Tab builders** for the STL workspace — `build_examine_tab`, `build_slice_tab`.
12. **Menu setup** — imports pywebview's `Menu`/`MenuAction`/`MenuSeparator`, builds the File menu, attaches it via `app.native.window_args["menu"]`. Also flips `webview.settings["SHOW_DEFAULT_MENUS"] = False` so pywebview doesn't add its own Edit and View menus at fixed positions.
13. **`@app.on_startup`** captures NiceGUI's asyncio loop into a module-global `_ui_loop` for later cross-thread scheduling.
14. **`ui.run(native=True, ...)`** — entry point.

## Runtime model

- **Single window, multi-page routing.** NiceGUI is single-window in native mode; we navigate between `/`, `/workspace`, `/project` for the different modes. Only one workspace open at a time.
- **Single user.** Module-level state is fine.
- **Every page function re-runs on navigation.** Anything you want to persist across page changes must live in module state, not a page closure.

## Two important classes to know

### `WorkspaceState` — the STL workflow

`stl_path`, `profile_name`, `profile_config`, `selected_overlays`, `edited_values`. Populated when the user opens an STL; consumed by the workspace page's tabs.

### `ProjectState` — the project editor

The interesting fields:

- `project_path`, `project_name`, `scad_files` — populated by `load_project(folder)`.
- `current_file` — path currently in the editor.
- `buffers: dict[Path, str]` — in-memory content per file. Populated lazily when a file is first opened. Kept up-to-date so **saving doesn't need the editor widget** — module-level save reads from here.
- `disk_snapshots: dict[Path, str]` — the last content read from or written to disk. A file is dirty iff `buffers[p] != disk_snapshots[p]`.
- `save_fn` / `examine_fn` — Optional callables. **Published by `project_page` while it's active.** This is how module-level handlers (menu, keyboard shortcuts) reach into the currently-rendered page. They're set to closures that capture the editor widget; they only work while the project page is rendered.

## Design gotcha: `@ui.refreshable` vs update-in-place

There's a design-note block near the top of `webgui.py`. **Please read it.** Summary: `@ui.refreshable` destroys and recreates every widget its function created. That means keyboard focus is lost, text-input caret positions are lost, native `<select>` in-flight selections are lost. We've hit this twice — once on the Slice tab's category listbox and once on the project sidebar. Both fixes were the same: build the widget once, then update individual sub-elements imperatively via `.update()` when their state changes.

Concrete pattern used in this file:

```python
option_elements: dict[Path, ui.element] = {}   # remember each <option>

with sel:
    for p in files:
        opt = ui.element("option")
        opt._text = ...
        opt._props["aria-label"] = ...
        option_elements[p] = opt

def refresh_marker(p):
    opt = option_elements[p]
    opt._text = new_text
    opt._props["aria-label"] = new_aria
    opt.update()
```

Rule of thumb: **use `@ui.refreshable` only for regions the user is NOT focused on when the refresh fires** (e.g. switching profile categories rebuilds the fields column, not the category list).

## Accessibility patterns worth knowing

- **All form inputs use their `label` parameter.** NiceGUI attaches a proper `<label>` element; screen readers announce it on focus.
- **Compact form rows** use Quasar's `before` slot with an explicit `<label for=input_id>` next to the input. Set `for=input_id` on the input (Quasar q-input's `for` prop) so the label associates with the native inner input. See `build_field_row` in `build_slice_tab`.
- **Field state (edited / overlay-sourced)** is announced via `aria-describedby` pointing at a live status label ("Edited" / "Set by overlay: X").
- **Native `<select size=N>` listboxes** are the accessible workhorse for pick-one-of-many. Same tab-stop, arrow-key semantics as QListWidget. Used for setting categories, source files, etc.
- **Live-output consoles** are `ui.textarea` (via `OutputConsole`), not `ui.log`. `ui.log` renders as an unfocusable `<pre>`-ish block; screen readers skip it entirely. `OutputConsole`'s textarea has a real label and is focusable.
- **Border-colour indicators** on form fields go on Quasar's `.q-field__control:before` pseudo-element, not on an outer outline of the wrapper (see the `ui.add_css` block in `workspace_page`).

## Cross-process menu

**pywebview's menu callbacks run in a different process** than NiceGUI's server. `ui.run(native=True)` spawns pywebview via `multiprocessing.Process`. Anything a menu handler does happens over there and can't directly touch NiceGUI state, the asyncio loop, or the DOM.

The bridge we use, in `_menu_bridge(action)`:

```python
webview.windows[0].evaluate_js(
    f'fetch("/_menu_bridge/{action}", {{method: "POST"}})'
)
```

- Menu callback (child process) uses `evaluate_js` to fire a `fetch()` from the browser.
- The browser hits `POST /_menu_bridge/{action}` on the NiceGUI server (parent process).
- Endpoint picks the current `Client` from `nicegui.client.Client.instances`, enters its context via `with client:`, and awaits the matching flow.
- Because it's a fetch (not a navigation), the current page's DOM is not destroyed — the editor keeps its cursor, undo history, and focus.

Alternatives we considered and rejected: `window.location` navigation (destroys page state); monkey-patching NiceGUI's internal `event_sender` pipe (fragile across versions); building our own multiprocessing.Queue wrapper around pywebview + uvicorn (huge undertaking). The fetch-based bridge is the pattern the NiceGUI community converges on for this use case — see [zauberzeug/nicegui#2277](https://github.com/zauberzeug/nicegui/discussions/2277).

### Menu limitations to know

- **No native keyboard accelerators.** pywebview's `MenuAction.shortcut` is stubbed out in the version we use. We bake the shortcut hint into the label text ("Save (⌘S)") and implement the real shortcut via `ui.keyboard` on the NiceGUI side.
- **Menu is static.** No API to enable/disable items dynamically. `File > Save` and `F5` outside the project page just show a "no project open" toast rather than being greyed out.
- **`SHOW_DEFAULT_MENUS = False`** removes pywebview's built-in Edit and View menus. That's why the menu bar is just `[python3, File]`. If we later need Cut/Copy/Paste, add our own `Menu("Edit", …)` with Python handlers that invoke `document.execCommand("cut")` etc. via evaluate_js.

## Keyboard shortcuts

`_install_global_shortcuts(include_save=…, include_examine=…)` attaches `ui.keyboard` to a page:

- `Cmd/Ctrl+O` — always (opens the STL picker).
- `Cmd/Ctrl+S` — when `include_save=True` (project page only).
- `F5` — when `include_examine=True` (project page only).

The default `ignore` list is overridden to `["input", "textarea"]` so shortcuts fire on the file listbox (`<select>`) but not while the user is typing into a real text input. CodeMirror uses a contenteditable div (not a `<textarea>`) so `F5` and `Cmd/Ctrl+S` fire correctly while editing.

The CodeMirror keymap also has a `Mod-s` binding for defence in depth. F5 is only in the global handler — having it in both would double-dispatch.

## Compact-mode CSS

Quasar defaults are generous with padding. There's a page-level CSS block in `workspace_page` (top of function) that trims tab-panel padding, tab header height, toolbar height, separator margins, and the default row/column gap. Copy that block into any new page that needs the same tightening.

## What each page does

### `/` (startup)

Bare landing page — "Use the File menu to open an STL model or a project." No buttons. Everything goes through the menu now.

### `/workspace` (STL workflow)

Three tabs:

- **Examine model** — streams `python 3dm.py info <stl>` into a `OutputConsole`. Has a stub "Make tactile preview" button.
- **Slice** — printer profile combo, overlay pill list, profile-settings editor (categories listbox on the left, fields on the right), Slice button, streaming `OutputConsole` for slice output.
- **Print** — placeholder.

### `/project` (project editor)

- Sidebar: `<select size=N>` of `.scad` files under `src/` (paths shown relative to `src/`, dirty files prefixed with `*` and marked `unsaved` for screen readers). Enter jumps to the editor.
- Editor: `ui.codemirror` with `language='C'` (best fallback — no OpenSCAD mode). `Mod-s` saves.
- Collapsible "Model info" panel below the editor (`ui.list().props("bordered")` wrapping a `ui.expansion`), containing an `OutputConsole` for `3dm build info` output. `F5` runs the build+info flow.

## Environment / subprocesses

Every `python 3dm.py …` invocation sets:

- `_3DMAKE_TEST_FLAGS=GUI_MODE` — the CLI checks this to skip interactive stdin behaviour (except where we explicitly want it, e.g. `3dm new` in `_new_project_flow` which pipes `b".\n"`).
- `PYTHONUNBUFFERED=1` — so we get line-by-line output.

`stream_3dm` handles both; call it via `OutputConsole.run_3dm(args, cwd=…)` when the output should go to a console. `cwd` is needed for project-mode actions (`3dm` looks for `3dmake.toml` in cwd).

## What's stubbed / deferred

- **Print tab** — placeholder label.
- **Make tactile preview** — button on Examine tab prints a `ui.notify` intent; doesn't run the actual subprocess.
- **Overlay reordering** — drag-and-drop is not implemented; overlays are added at end and removed individually.
- **New file / delete file / rename** in project editor.
- **"Prompt on close if unsaved changes"** — opening a different project or STL silently discards unsaved edits.
- **Live dirty markers** — the sidebar's `* filename` marker updates on file-switch and save, not on every keystroke. See the design-note block for the reason.
- **Multi-workspace** — one workspace at a time. Would need URL-scoped state; NiceGUI's `app.storage.tab` is the right primitive for it.

## When something breaks

- **Load-check first.** `uv run python troys_local_load_test.py` catches import-time errors without opening the window.
- **VoiceOver seeing nothing.** Almost certainly running the app as `python webgui.py` from Terminal instead of via a `.app` bundle. See the caveat above.
- **Keyboard focus dropped after some action.** Look for a `@ui.refreshable` in the vicinity — see the design-note block, then refactor to a build-once + update-in-place pattern.
- **Menu item does nothing / "coroutine never awaited" warning.** The menu bridge fetch might not be reaching the server; check the browser devtools network tab (right-click in a NiceGUI page during dev, or launch with `debug=True`).
- **`F5` in the browser reloading the whole app instead of examining.** Shouldn't happen in the pywebview window (it doesn't implement F5 = reload), but if you're testing in a real browser during dev, you'll see this. Add a JS handler to preventDefault F5 at the document level if it becomes a real problem.
- **Any Quasar-styling puzzle** — the widget's actual DOM is a q-* component with slots and pseudo-elements. Right-click → Inspect gives you the real markup and lets you target the right thing via CSS.

## Version pins

- `pyside6==6.9.0` is on the sibling `pyside6-gui` branch — irrelevant here.
- `nicegui[native]` (currently 3.15.0) is what this branch uses. NiceGUI is a moving target; if you upgrade, walk through the design-gotcha section again and re-verify that `@ui.refreshable`, `ui.element._props`/`._text`, and `app.native.window_args` still behave as described.

## Useful references

- Nicegui source (clone: `~/Downloads/nicegui-src` on Troy's machine, checked out to `v3.15.0`). Docs first, then code.
- Quasar q-input docs — https://quasar.dev/vue-components/input
- pywebview menu API — `~/Downloads/pywebview/webview/menu.py` and `platforms/cocoa.py` for behaviour details.
- The plan file for this GUI work — `/Users/troy/.claude/plans/glimmering-enchanting-quiche.md` (the last approved version).
