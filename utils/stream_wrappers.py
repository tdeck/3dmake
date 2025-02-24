import os
import threading
import re
import subprocess
from typing import Callable

class IndentStream:
    """
    This stream reprints everything to the wrapped stream, but indents it.
    """
    def __init__(self, wrapped_stream, indent=4):
        self.wrapped_stream = wrapped_stream
        self.indent_str = ' ' * indent
        self.pipe_read, self.pipe_write = os.pipe()

        # Start a thread to read from the pipe and forward indented output
        self._start_reader_thread()

    def _start_reader_thread(self):
        def _reader():
            with os.fdopen(self.pipe_read, 'r') as pipe:
                for line in pipe:
                    # Indent each line and write to the wrapped stream
                    self.wrapped_stream.write(f"{self.indent_str}{line}")
                    self.wrapped_stream.flush()

        threading.Thread(target=_reader, daemon=True).start()

    def write(self, text, *args, **kwargs):
        if self.wrapped_stream == subprocess.DEVNULL:
            return

        for line in text.splitlines(True):
            self.wrapped_stream.write(f"{self.indent_str}{line}", *args, **kwargs)
        self.wrapped_stream.flush()

    def fileno(self):
        return self.pipe_write

    def close(self): # TODO do I want this?
        os.close(self.pipe_write)

    def flush(self):
        # Not needed because every write flushes anyway
        pass

class FilterPipe:
    ''' This pipe filters things that don't match filter_fn. '''
    def __init__(self, wrapped_stream, filter_fn: Callable[[str], bool]):
        self.wrapped_stream = wrapped_stream
        self.pipe_read, self.pipe_write = os.pipe()
        self.filter_fn = filter_fn

        # Start a thread to read from the pipe and forward indented output
        self._start_reader_thread()

    def _start_reader_thread(self):
        def _reader():
            with os.fdopen(self.pipe_read, 'r') as pipe:
                for line in pipe:
                    # Indent each line and write to the wrapped stream
                    if self.filter_fn(line):
                        self.wrapped_stream.write(line)
                        self.wrapped_stream.flush()


        threading.Thread(target=_reader, daemon=True).start()

    def fileno(self):
        return self.pipe_write

    def close(self): # TODO do I want this?
        os.close(self.pipe_write)
