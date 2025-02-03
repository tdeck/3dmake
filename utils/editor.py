import platform
import os

from coretypes import CommandOptions

def choose_editor(options: CommandOptions) -> str:
    if options.editor:
        return options.editor
    
    if platform.system() == 'Windows':
        return 'notepad'
    else:
        # nano is an arbitrary fallback that we might improve in the future
        return os.getenv('VISUAL') or os.getenv('EDITOR') or 'nano'
