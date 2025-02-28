import platform
import os
import shutil
import json
import platform
from pathlib import Path
from typing import TextIO

from prompt_toolkit import prompt

from .framework import Context, isolated_action
from utils.print_config import list_printer_profiles
from utils.prompts import yes_or_no, option_select
from utils.bundle_paths import SCRIPT_DIR, SCRIPT_BIN_PATH
from version import VERSION

@isolated_action
def setup(ctx: Context, stdout: TextIO, debug_stdout: TextIO):
    ''' Set up 3DMake for the first time, or overwrite existing settings '''
    CONFIG_DIR = ctx.config_dir
    DEFAULTS_TOML = CONFIG_DIR / "defaults.toml" 

    overwrite_old_profiles = True
    if DEFAULTS_TOML.exists():
        print(f"The configuration directory {CONFIG_DIR} already exists.")
        print(f"I can overwrite the configuration files and printer profiles that came")
        print(f"with 3Mmake, which will upgrade them to the latest version. But if you")
        print(f"customized one of the built-in profiles, your changes will be lost.")
        overwrite_old_profiles = yes_or_no("Do you want to upgrade profiles?")

    def copy_fn(src, dest):
        # When overwrite_old_profiles is false, this will ignore any file that
        # already exists
        if overwrite_old_profiles or not Path(dest).exists():
            shutil.copy2(src, dest)

    default_conf_dir = SCRIPT_DIR / 'default_config'
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

    if DEFAULTS_TOML.exists():
        print("Your global settings were carried over from the last 3DMake version.")
        return

    settings_dict = dict(
        view='3sil',
        model_name='main',
        auto_start_prints=True,
    )

    # For the most common platform, we pre-populate the defaults so that it makes
    # the file easier to edit
    if platform.system() == 'Windows':
        settings_dict['editor'] = 'notepad'
        settings_dict['edit_in_background'] = True

    profile_names = list_printer_profiles(CONFIG_DIR)

    profile_options = [
        (p.replace('_', ' '), p)
        for p in profile_names
    ]

    profile_name = option_select("Choose a default printer model", profile_options)
    settings_dict['printer_profile'] = profile_name

    print()
    print("3DMake can use the Gemini AI to describe your models when you run 3dm info")
    print("This requires you to get a free Gemini API key, and has a limit of 50 runs per day.")
    if yes_or_no("Do you want to set up Gemini?"):
        print("The Gemini API key is a string of text that 3DMake needs to access the Gemini AI.")
        print("Copy your API key from this page while logged into your Google account:")
        print("https://aistudio.google.com/app/apikey")
        key = prompt("What is your Gemini API key? ").strip()
        print()
        if key:
            settings_dict['gemini_key'] = key
            print("Before using the AI descriptions, you should understand that they sometimes make")
            print("surprising mistakes, such as miscounting parts, describing things that aren't there,")
            print("or missing obvious flaws in models. This is part of the challenge of using today's AI,")
            print("so take care when relying on it.")
        else:
            print("Empty response, leaving this unconfigured for now.")

    print()
    if yes_or_no("Do you want to set up an OctoPrint connection?"):
        server = prompt("What is the web address of your OctoPrint server (including http://)? ").strip()

        print("You must set up an OctoPrint API key for 3DMake if you do not have one already.")
        print("To do this, open the OctoPrint settings in your browser, navigate to Application Keys,")
        print("and manually generate a key.")

        key = prompt("What is your OctoPrint application key? ").strip()

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

