"""Bounded atomic file sink for provider-generated media bytes."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Self
from uuid import uuid4


class BoundedOutputSink:
    """Write untrusted provider bytes to a private temporary file under a hard cap.

    The caller must call commit() only after the provider's reported byte count
    matches bytes_written. A limit violation aborts and poisons the sink immediately;
    leaving the context without commit also removes the temporary file.
    """

    def __init__(self, target_path: Path, *, max_bytes: int) -> None:
        if max_bytes < 1:
            raise ValueError("Output byte limit must be positive")
        self.target_path = target_path
        self.max_bytes = max_bytes
        self.bytes_written = 0
        self._committed = False
        self._closed = False
        self._temporary_path = target_path.parent / f".{uuid4().hex}.output-part"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self._temporary_path, flags, 0o600)
        self._file = os.fdopen(descriptor, "wb")

    def write(self, content: bytes | bytearray | memoryview) -> int:
        if self._closed or self._committed:
            raise ValueError("Output sink is closed")
        if not isinstance(content, (bytes, bytearray, memoryview)):
            raise TypeError("Output sink accepts bytes only")
        size = len(content)
        if size == 0:
            return 0
        if self.bytes_written + size > self.max_bytes:
            self.abort()
            raise ValueError("Generated output exceeds the configured byte limit")
        written = self._file.write(content)
        if written != size:
            raise OSError("Short write while storing generated output")
        self.bytes_written += written
        return written

    def flush(self) -> None:
        if self._closed:
            raise ValueError("Output sink is closed")
        self._file.flush()

    def commit(self) -> Path:
        if self._closed or self._committed:
            raise ValueError("Output sink cannot be committed")
        if self.bytes_written <= 0:
            raise ValueError("Generated output is empty")
        try:
            self._file.flush()
            os.fsync(self._file.fileno())
            self._file.close()
            self._closed = True
            # A hard link publishes the complete file atomically without replacing
            # an existing target if a path collision or race occurs.
            os.link(self._temporary_path, self.target_path)
            self._temporary_path.unlink()
            self._committed = True
            return self.target_path
        except Exception:
            self.abort()
            raise

    def abort(self) -> None:
        if not self._closed:
            self._file.close()
            self._closed = True
        self._temporary_path.unlink(missing_ok=True)

    def close(self) -> None:
        """Closing without commit is an abort, never a partial publication."""
        self.abort()

    def __enter__(self) -> Self:
        if self._closed:
            raise ValueError("Output sink is closed")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if not self._committed:
            self.abort()
