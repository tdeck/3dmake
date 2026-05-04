import subprocess
import sys
from datetime import timedelta
from time import time, sleep
from typing import Any, Union

from utils.output_streams import OutputStream

def throw_subprogram_error(program_type: str, exit_code: int, debug: bool):
    if debug:
        print(f"Subprogram exited with return code {exit_code}")
    raise RuntimeError(
        f"The {program_type} program reported an error. "
        "There should be more info above this line."
    )

def check_if_value_in_options(thing_name: str, value: str, options: Union[list[str], dict[str, Any]]) -> None:
    if value not in options:
        opt_names = options if isinstance(options, list) else options.keys()
        raise RuntimeError(f"No {thing_name} named {value}, options are {', '.join(opt_names)}")

def format_run_time(seconds: float) -> str:
    td = timedelta(seconds=int(seconds))
    return str(td) # This does an OK job; could be better

def show_subprocess_timer(subproc: subprocess.Popen, label: str, output: OutputStream):
    '''
    Polls the subprocess at appropriate intervals and prints build time updates on the last
    line. When streaming log output at the same time, logs should be padded to 20 characters.
    '''
    tty_output_mode = sys.stdout.isatty()
    start_time = time()
    last_printed_time = None

    while subproc.poll() is None:
        runtime = time() - start_time
        # We don't want to be chewing up CPU busy-waiting, but we also don't
        # want to make short builds slower, so we try to strike a balance with
        # these sleeps
        if runtime < 1:
            sleep(.05)
        elif runtime < 10:
            sleep(.1)
        else:
            sleep(.5)
        if tty_output_mode:  # Print running build time indicator in TTY
            time_str = format_run_time(runtime)
            # Our printed timestamps have a 1 second granularity; if we write out lines
            # multiple times per second the screen reader may flood us with updates,
            # so we don't print every single time
            if time_str != last_printed_time:
                last_printed_time = time_str
                print("\r" + ' ' * 20, end='') # Clear the line
                print("\r" + f"{label} {time_str}", end='\r', flush=True)
                # Note: The \r at the end here means that if another thread
                # writes a log, it'll appear at the start of the line and
                # (most likely) overwrite the build time

    runtime = time() - start_time
    if tty_output_mode:
        print()
    else:
        output.writeln(f"{label} {format_run_time(runtime)}")
