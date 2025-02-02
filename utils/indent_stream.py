import os
from typing import Callable

class IndentStream:
    """
    This stream reprints everything to the wrapped stream, but indents it.
    """
    def __init__(self, wrapped_stream, indent=4, filter_fn: Callable[[str], bool]=lambda _: True):
        self.wrapped_stream = wrapped_stream
        self.indent_str = ' ' * indent
        self.filter_fn = filter_fn
        self.pipe_read, self.pipe_write = os.pipe()

        # Start a thread to read from the pipe and forward indented output
        self._start_reader_thread()

    def _start_reader_thread(self):
        def _reader():
            with os.fdopen(self.pipe_read, 'r') as pipe:
                for line in pipe:
                    if self.filter_fn(line):
                        # Indent each line and write to the wrapped stream
                        self.wrapped_stream.write(f"{self.indent_str}{line}")
                    self.wrapped_stream.flush()

        threading.Thread(target=_reader, daemon=True).start()

    def fileno(self):
        return self.pipe_write

    def close(self): # TODO do I want this?
        os.close(self.pipe_write)
