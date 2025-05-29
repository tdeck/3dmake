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
                    if self.wrapped_stream == subprocess.DEVNULL:
                        continue
                    # Indent each line and write to the wrapped stream
                    self.wrapped_stream.write(f"{self.indent_str}{line}")
                    self.wrapped_stream.flush()

        threading.Thread(target=_reader, daemon=True).start()

    def write(self, text, *args, **kwargs):
        os.write(self.pipe_write, text.encode('utf-8'))

    def fileno(self):
        return self.pipe_write

    def close(self): # TODO do I want this?
        os.close(self.pipe_write)

    def flush(self):
        # Not needed because every write flushes anyway
        pass

class FilterPipe:
    ''' This pipe filters things that don't match filter_fn. '''
    def __init__(self, wrapped_stream, filter_fn: Callable[[str], bool], pad_lines_to=0):
        self.wrapped_stream = wrapped_stream
        self.pipe_read, self.pipe_write = os.pipe()
        self.filter_fn = filter_fn
        # Pad lines to overwrite the build time in build_action
        self.pad_lines_to = pad_lines_to

        # Start a thread to read from the pipe and forward indented output
        self._start_reader_thread()

    def _start_reader_thread(self):
        def _reader():
            with os.fdopen(self.pipe_read, 'r') as pipe:
                for line in pipe:
                    # Indent each line and write to the wrapped stream
                    if self.filter_fn(line):
                        line = line.rstrip('\n').ljust(self.pad_lines_to) + '\n'
                        self.wrapped_stream.write(line)
                        self.wrapped_stream.flush()


        threading.Thread(target=_reader, daemon=True).start()

    def fileno(self):
        return self.pipe_write

    def close(self): # TODO do I want this?
        os.close(self.pipe_write)

class StoreAndForwardStream:
    """ This class reprints everything to the wrapped stream, but also stores it in a .content string """
    def __init__(self, wrapped_stream):
        self.wrapped_stream = wrapped_stream
        self.pipe_read, self.pipe_write = os.pipe()
        self.content = ''
        self._content_lock = threading.Lock()

        # Start a thread to read from the pipe and forward output
        self._start_reader_thread()

    def _start_reader_thread(self):
        def _reader():
            with os.fdopen(self.pipe_read, 'r') as pipe:
                for line in pipe:
                    with self._content_lock:
                        self.content += line

                    if self.wrapped_stream == subprocess.DEVNULL:
                        continue
                    self.wrapped_stream.write(line)
                    self.wrapped_stream.flush()

        threading.Thread(target=_reader, daemon=True).start()

    def write(self, text, *args, **kwargs):
        os.write(self.pipe_write, text.encode('utf-8'))

    def fileno(self):
        return self.pipe_write

    def close(self): # TODO do I want this?
        os.close(self.pipe_write)

    def flush(self):
        # Not needed because every write flushes anyway
        pass
