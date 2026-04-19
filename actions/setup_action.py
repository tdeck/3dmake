import platform
import os
import shutil
import json
import hashlib
import platform
import tomllib
import requests
import webbrowser
from pathlib import Path
from typing import TextIO, Dict, Any

from .framework import Context, isolated_action
from utils.print_config import list_printer_profiles, read_profile_config
from utils.prompts import yes_or_no, option_select, prompt
from utils.bundle_paths import SCRIPT_DIR, SCRIPT_BIN_PATH
from version import VERSION
from default_file_hashes import BUNDLED_PATH_HASHES
from utils.shell import shell_command_exists
from utils.bambu import vendor_is_bambu

DEFAULT_WINDOWS_EDITOR = 'notepad'
OLLAMA_LOCALHOST = 'http://localhost:11434'
BAMBU_CONNECT_DOWNLOAD_PAGE = "https://wiki.bambulab.com/en/software/bambu-connect"

def ollama_detected() -> bool:
    if shell_command_exists('ollama'):
        return True
    else:
        # If it's not in PATH for some reason but the server is running
        try:
            response = requests.get(OLLAMA_LOCALHOST, timeout=0.5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b'\r', b''), usedforsecurity=False).hexdigest()

def get_default_settings() -> Dict[str, Any]:
    """Get the default settings for initial setup"""
    settings = dict(
        view='3sil',
        model_name='main',
        auto_start_prints=True,
    )

    # For the most common platform, we pre-populate the defaults so that it makes
    # the file easier to edit
    if platform.system() == 'Windows':
        settings['editor'] = DEFAULT_WINDOWS_EDITOR
        settings['edit_in_background'] = True

    return settings

def load_existing_settings(defaults_toml_path: Path) -> Dict[str, Any]:
    """Load existing settings from defaults.toml if it exists"""
    if defaults_toml_path.exists():
        with open(defaults_toml_path, 'rb') as fh:
            return tomllib.load(fh)
    return {}

# TODO Consider merging these with existing prompt functions
def prompt_with_current(question: str, current_value: Any = None) -> str:
    """Prompt with current value shown and option to keep it"""
    if current_value is not None:
        result = prompt(f"{question}, or press ENTER to keep current value ({current_value}): ").strip()
        if not result:
            return current_value
        return result
    else:
        return prompt(f"{question}: ").strip()

def option_select_with_current(question: str, options, current_value: str = None):
    """Option select with current value shown and option to keep it"""
    if current_value is not None:
        print(f"{question}, or press ENTER to keep current value ({current_value}):")
        result = option_select("", options, allow_none=True)
        if result is None:
            return current_value
        return result
    else:
        return option_select(question, options)

@isolated_action
def setup(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Set up 3DMake for the first time, or overwrite existing settings '''
    CONFIG_DIR = ctx.config_dir
    DEFAULTS_TOML = CONFIG_DIR / "defaults.toml"

    # Load existing settings if they exist
    existing_settings = load_existing_settings(DEFAULTS_TOML)

    default_conf_dir = SCRIPT_DIR / 'default_config'

    def copy_fn(src, dest):
        dest_path = Path(dest)
        if not dest_path.exists():
            shutil.copy2(src, dest)
            return

        rel_path = str(Path(src).relative_to(default_conf_dir)).replace('\\', '/')
        existing_hash = hash_file(dest_path)
        if existing_hash in BUNDLED_PATH_HASHES.get(rel_path, set()):
            shutil.copy2(src, dest)
        elif existing_hash == hash_file(Path(src)):
            return # File hasn't changed
        elif yes_or_no(f"'{rel_path}' has been customized. Overwrite with the new version?"):
                shutil.copy2(src, dest)
    shutil.copytree(
        default_conf_dir,
        CONFIG_DIR,
        copy_function=copy_fn,
        dirs_exist_ok=True, # Don't need to mkdir -p as shutil will do this
    )

    add_self_to_path()
    with open(CONFIG_DIR / ".installed_version", 'w') as fh:
        # This is to help later versions of 3DMake which may need to migrate
        # settings when upgrading
        fh.write(VERSION)

    # Start with defaults, then overlay existing settings
    settings_dict = get_default_settings()
    settings_dict.update(existing_settings)

    profile_names = list_printer_profiles(CONFIG_DIR)

    profile_options = [
        (p.replace('_', ' '), p)
        for p in profile_names
    ]

    profile_name = option_select_with_current("Choose a printer model", profile_options, settings_dict.get('printer_profile'))
    settings_dict['printer_profile'] = profile_name

    # Read the printer profile config, some other settings vary based on this
    print_profile_config: dict[str, str] = read_profile_config(CONFIG_DIR, profile_name)

    # For Windows users, we have a slightly nicer editor select flow
    if platform.system() == 'Windows':
        from utils.editor import list_windows_editors

        non_notepad_editors = [
            e for e in list_windows_editors(debug_stdout)
            if e.human_name.lower() != 'notepad.exe'
        ]

        if non_notepad_editors:
            print()
            current_editor = settings_dict.get('editor')

            ask_editor = True
            if current_editor and current_editor != DEFAULT_WINDOWS_EDITOR:
                ask_editor = yes_or_no("Do you want to change your editor?")

            if ask_editor:
                editor_options = [(e.human_name, e.command) for e in non_notepad_editors]
                editor_options.append(('Notepad', 'notepad'))
                selected_command = option_select("Choose an editor", editor_options)
                settings_dict['editor'] = selected_command
                settings_dict['edit_in_background'] = True

    # We support all kinds of local LLM backends but only provide an easy setup
    # path for ollama right now. 
    current_has_ollama = settings_dict.get("openai_compat_host") == OLLAMA_LOCALHOST
    ollama_question = None
    if current_has_ollama:
        ollama_question = "Do you want to change your ollama configuration?"
    elif ollama_detected():
        ollama_question = "Do you want to set up an ollama connection?"
    if ollama_question:
        print()
        print("3DMake can use local ollama AI to describe your models when you run 3dm info")
        if yes_or_no(ollama_question):
            model_name = prompt_with_current(
                "What is the ollama model name?",
                settings_dict.get('llm_name')
            )
            if model_name:
                settings_dict['openai_compat_host'] = OLLAMA_LOCALHOST
                settings_dict['llm_name'] = model_name.strip()
            else:
                print("Empty response. Disabling ollama for now.")
                settings_dict.pop('openai_compat_host', None)
                settings_dict.pop('llm_name', None)
        
    if not settings_dict.get('openai_compat_host'):
        print()
        print("3DMake can use the Gemini AI to describe your models when you run 3dm info")
        print("This requires you to get a free Gemini API key, and has a limit of 50 runs per day.")
        current_has_gemini = bool(settings_dict.get('gemini_key'))
        if current_has_gemini:
            gemini_question = "Do you want to change your Gemini configuration?"
        else:
            gemini_question = "Do you want to set up Gemini?"

        if yes_or_no(gemini_question):
            print("The Gemini API key is a string of text that 3DMake needs to access the Gemini AI.")
            print("Copy your API key from this page while logged into your Google account:")
            print("https://aistudio.google.com/app/apikey")
            current_key = settings_dict.get('gemini_key')
            key = prompt_with_current("What is your Gemini API key?", current_key)
            print()
            if key:
                settings_dict['gemini_key'] = key
                print("Before using the AI descriptions, you should understand that they sometimes make")
                print("surprising mistakes, such as miscounting parts, describing things that aren't there,")
                print("or missing obvious flaws in models. This is part of the challenge of using today's AI,")
                print("so take care when relying on it.")
            else:
                print("Empty response, leaving this unconfigured for now.")

    #
    # Printer connection methods
    #
    current_print_mode = settings_dict.get("print_mode", "octoprint")
    is_bambu_printer = vendor_is_bambu(print_profile_config['printer_vendor'])
    
    if is_bambu_printer and current_print_mode not in ["bambu_connect", "bambu_lan"]:
        print()
        print("3DMake can send prints to your Bambu printer using Bambu Connect,")
        print("when you run 3dm print. Bambu Connect is an accessible software")
        print("tool you can download from Bambu Labs.")
        if yes_or_no("Do you want to enable Bambu Connect?"):
            settings_dict['print_mode'] = 'bambu_connect' 
            print("You must download and install Bambu Connect from the Bambu Labs website.")
            if yes_or_no("Do you want to open the download page now?"):
                print(f"Opening {BAMBU_CONNECT_DOWNLOAD_PAGE}")
                webbrowser.open(BAMBU_CONNECT_DOWNLOAD_PAGE)
            else:
                print(f"You can find it at {BAMBU_CONNECT_DOWNLOAD_PAGE}")
    
    if not is_bambu_printer:
        print()
        current_has_octoprint = bool(settings_dict.get('octoprint_host'))
        if current_has_octoprint:
            octoprint_question = "Do you want to change your OctoPrint configuration?"
        else:
            octoprint_question = "Do you want to set up an OctoPrint connection?"

        if yes_or_no(octoprint_question):
            current_host = settings_dict.get('octoprint_host')
            server = prompt_with_current("What is the web address of your OctoPrint server (including http://)?", current_host)

            print("You must set up an OctoPrint API key for 3DMake if you do not have one already.")
            print("To do this, open the OctoPrint settings in your browser, navigate to Application Keys,")
            print("and manually generate a key.")

            current_key = settings_dict.get('octoprint_key')
            key = prompt_with_current("What is your OctoPrint application key?", current_key)

            settings_dict['print_mode'] = "octoprint"
            settings_dict['octoprint_host'] = server
            settings_dict['octoprint_key'] = key
    

    with open(DEFAULTS_TOML, 'w') as fh:
        # TODO write this properly; it's brittle
        for k, v in settings_dict.items():
            fh.write(f"{k} = {json.dumps(v)}\n")
        

def add_self_to_path():
    os_type = platform.system()

    if os_type == 'Windows':
        bin_dir = Path(os.getenv('USERPROFILE')) / "AppData" / "Local" / "Microsoft" / "WindowsApps"

        if bin_dir.exists():
            import mslex
            # Windows requires special admin permission to create symlinks
            # So instead we create a batch file in this directory that simply runs 3DMake
            with open(bin_dir / '3dm.bat', 'w') as fh:
                fh.write("@echo off\r\n")
                fh.write(f"{mslex.quote(str(SCRIPT_BIN_PATH))} %*\r\n")
        else:
            print("3DMake was not added to your PATH automatically. Consider adding this folder")
            print("to your PATH environment variable:")
            print(SCRIPT_BIN_PATH.parent)
            # TODO not sure whether to give a setx command or not, hopefully this is a rare case

    else:  # Assume a Linux/Unix platform
        bin_dir = Path(os.getenv('HOME')) / '.local' / 'bin' # This is in the XDG spec

        if bin_dir.exists():
            symlink_path = bin_dir / '3dm'
            symlink_path.unlink(missing_ok=True) # Replace if one already exists
            symlink_path.symlink_to(SCRIPT_BIN_PATH)
        else:
            # If it doesn't exist, maybe we could create it and it'll be in the PATH, but maybe
            # not. Better to assume it won't work and tell the user to set things up themselves.

            user_shell = os.getenv('SHELL', '')
            shell_config_file = '~/.profile'
            if 'bash' in user_shell:
                shell_config_file = '~/.bashrc'
            elif 'zsh' in user_shell:
                shell_config_file = '~/.zshrc'

            print("3DMake was not added to your PATH automatically. Consider adding a line like")
            print(f"this to your shell config file (e.g. {shell_config_file}):")
            print(f'export PATH="{SCRIPT_BIN_PATH.parent}:$PATH"')
            print(f"After doing this, you must reload your shell.")

