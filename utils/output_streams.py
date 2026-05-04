'''
These output streams allow us to create a pipeline of text output that can be
selectively filtered, reprocessed, and accumulated along the way, and can be
fed from a child process's output stream.
'''
import os
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TextIO

class OutputStream(ABC):
    def __init__(self):
        self._incomplete_line = ''

    def write(self, text: str) -> None:
        if text == '':
            return

        # If this is overridden, it must still pass each line through _write_one_line()
        lines =  text.splitlines(keepends=False)
        if text[-1] != '\n':
            remainder = lines.pop()
        else:
            remainder = ''

        for line in lines:
            self._write_one_line(self._incomplete_line + line)
            self._incomplete_line = ''

        self._incomplete_line = remainder

    def writeln(self, text: str) -> None:
        ''' Convenience method. Note that text may contain newlines '''
        self.write(f"{text}\n")

    @abstractmethod
    def _write_one_line(self, line: str) -> None:
        ''' Internal method that processes all lines '''
        pass

class NullOutputStream(OutputStream):
    def __init__(self):
        pass

    def write(self, _: str) -> None:
        pass

    def writeln(self, _: str) -> None:
        pass

    def _write_one_line(self, _: str) -> None:
        pass

class PipeOutputStream(OutputStream):
    def __init__(self, wrapped_stream: TextIO):
        super().__init__()
        self._wrapped_stream = wrapped_stream

    def _write_one_line(self, line: str) -> None:
        self._wrapped_stream.write(f"{line}\n")

class TransformerStream(OutputStream):
    def __init__(
        self,
        sink: OutputStream,
        transform_fn: Callable[[str], str],
    ):
        super().__init__()
        self._sink = sink
        self._transform_fn = transform_fn

    def _write_one_line(self, line: str) -> None:
        self._sink._write_one_line(self._transform_fn(line))

class FilterStream(OutputStream):
    def __init__(
        self,
        sink: OutputStream,
        filter_fn: Callable[[str], bool],
    ):
        super().__init__()
        self._sink = sink
        self._filter_fn = filter_fn

    def _write_one_line(self, line: str) -> None:
        if self._filter_fn(line):
            self._sink._write_one_line(line)

class AccumulatorStream[T](OutputStream):
    def __init__(
        self,
        sink: OutputStream,
        reader_fn: Callable[[str, T], None],
        accumulator: T,
    ):
        super().__init__()
        self._sink = sink
        self._reader_fn = reader_fn
        self.accumulator = accumulator

    def _write_one_line(self, line: str) -> None:
        self._reader_fn(line, self.accumulator)
        self._sink._write_one_line(line)

class OutputPipe:
    '''
    Provides an input stream that can be passed to a subprocess to 
    capture its output. Instantiate using a context like this:
    >>> with OutputPipe(stdout_stream) as pipe:
            subprocess.Popen(..., stdout=pipe, ...)
    '''
    def __init__(self, sink: OutputStream):
        self._sink = sink

    def __enter__(self):
        self._pipe_read, self._pipe_write = os.pipe()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_):
        os.close(self._pipe_write)
        self._thread.join()
        return False

    def _reader(self):
        trailing_newline = True
        with os.fdopen(self._pipe_read, 'r') as f:
            for line in f:
                self._sink.write(line)
                trailing_newline = line.endswith('\n')
        if not trailing_newline:
            # When the pipe closes, if there was no trailing newline we append
            # one to force all the upstream OutputStreams to propagate the line.
            self._sink.write('\n')

    def fileno(self) -> int:
        return self._pipe_write

