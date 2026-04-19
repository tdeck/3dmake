import shutil

def shell_command_exists(name):
    ''' Returns true if a command by this name is in PATH '''
    return shutil.which(name) is not None
