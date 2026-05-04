import subprocess
import platform
import os
from time import time
from pathlib import Path
from dataclasses import dataclass
from coretypes import CommandOptions
from utils.output_streams import OutputStream

MIN_BLOCKING_SECONDS = 0.5

def launch_editor(options: CommandOptions, file: Path, blocking: bool = False) -> None:
    """Launch the configured editor to edit a file"""
    background = options.edit_in_background
    editor = options.editor

    if not editor:
        if platform.system() == 'Windows':
            # If you change this, change the defaults populated in setup_action also
            editor = 'notepad'
            background = True
        else:
            # nano is an arbitrary fallback that we might improve in the future
            editor = os.getenv('VISUAL') or os.getenv('EDITOR') or 'nano'

    # We make sure the path is resolved to an external path to work
    # around a weird bug on Windows, where the Python process will
    # see its own AppData/Local dir sanboxed to another location (but
    # where this won't happen to subprocesses we launch in the shell)
    # See this bug: https://github.com/python/cpython/issues/122057
    resolved_file = file.resolve(strict=False)

    # Use shell=True to handle editor commands with arguments
    cmd = f'{editor} "{resolved_file}"'

    if background and not blocking:
        subprocess.Popen(cmd, shell=True)
    else:
        start_time = time()
        subprocess.run(cmd, shell=True)
        elapsed = time() - start_time
        # In case we need a write->edit->read workflow and the editor
        # command doesn't actually block, we can detect that it ended
        # too early and ask the user to press a key when they finished.
        if blocking and elapsed < MIN_BLOCKING_SECONDS:
            input("Press ENTER when finished editing:")

@dataclass
class WindowsEditor:
    human_name: str
    command: str

def list_windows_editors(debug_stdout: OutputStream) -> list[WindowsEditor]:
    import winreg

    results: list[WindowsEditor] = []

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.txt\OpenWithList",
        0,
        winreg.KEY_READ,
    ) as open_with_list:
        mru_list, _ = winreg.QueryValueEx(open_with_list, "MRUList")
        for c in mru_list:
            progid, _ = winreg.QueryValueEx(open_with_list, c)

            command = None
            for key_path in [
                rf"Applications\{progid}\shell\open\command",
                rf"{progid}\shell\open\command",
            ]:
                try:
                    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, key_path, 0, winreg.KEY_READ) as command_key:
                        command, _ = winreg.QueryValueEx(command_key, "")
                        break
                except FileNotFoundError:
                    pass

            if not command:
                for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                    try:
                        with winreg.OpenKey(
                            hive,
                            rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{progid}",
                            0,
                        winreg.KEY_READ) as app_key:
                            exe_path, _ = winreg.QueryValueEx(app_key, "")
                            if exe_path:
                                command = f'"{exe_path}" %1'
                                break
                    except FileNotFoundError:
                        pass

            if not command:
                debug_stdout.writeln(f"No command for progid {progid}")
                continue

            # Typically the commands contain "%1" to tell you where to put
            # the filename, but 3DMake only supports the filename at the end
            # of the command, so we strip this. If the command has a different
            # format, we need to exclude it.
            if command.endswith(' "%1"'):
                command = command[:-5]
            elif command.endswith(' %1'):
                command = command[:-3]
            else:
                debug_stdout.writeln(f"Unexpected editor cmd: progid={progid}, command={command}")
                continue

            # Find the best name we can display for the program
            human_name = progid
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid, 0, winreg.KEY_READ) as progid_key:
                    try:
                        human_name, _ = winreg.QueryValueEx(progid_key, "FriendlyAppName")
                    except FileNotFoundError:
                        # This usually contains a display name
                        human_name, _ = winreg.QueryValueEx(progid_key, "")
            except FileNotFoundError:
                pass

            results.append(WindowsEditor(human_name=human_name, command=command))

    return results
