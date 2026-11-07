"""
Multi-process and multi-thread safe RotatingFileHandler.

Prevents race conditions during log rollover across multiple Uvicorn worker
processes and reopens stale file descriptors on POSIX when a sibling worker
rotates the underlying log file.
"""

from __future__ import annotations

import os
import time
import threading
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler

if os.name == "nt":
    import msvcrt
else:
    import fcntl


_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.Lock] = {}


def _get_thread_lock(lock_path: str) -> threading.Lock:
    norm = os.path.normcase(os.path.abspath(lock_path))
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(norm)
        if lock is None:
            lock = threading.Lock()
            _THREAD_LOCKS[norm] = lock
        return lock


class MultiProcessRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler guarded by an inter-process lock file."""

    def __init__(
        self,
        filename: str,
        mode: str = "a",
        maxBytes: int = 0,
        backupCount: int = 0,
        encoding: str | None = "utf-8",
        delay: bool = True,
        errors: str | None = None,
    ) -> None:
        super().__init__(
            filename,
            mode=mode,
            maxBytes=maxBytes,
            backupCount=backupCount,
            encoding=encoding,
            delay=delay,
            errors=errors,
        )
        self._lock_file_path = f"{self.baseFilename}.lock"
        self._thread_lock = _get_thread_lock(self._lock_file_path)

    @contextmanager
    def _interprocess_lock(self):
        with self._thread_lock:
            os.makedirs(os.path.dirname(self._lock_file_path) or ".", exist_ok=True)
            fd = os.open(self._lock_file_path, os.O_CREAT | os.O_RDWR, 0o666)
            locked = False
            try:
                if os.name == "nt":
                    os.lseek(fd, 0, os.SEEK_SET)
                    deadline = time.monotonic() + 5.0
                    while True:
                        try:
                            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                            locked = True
                            break
                        except OSError:
                            if time.monotonic() >= deadline:
                                raise
                            time.sleep(0.005)
                else:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                    locked = True
                yield
            finally:
                if locked:
                    try:
                        if os.name == "nt":
                            os.lseek(fd, 0, os.SEEK_SET)
                            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                        else:
                            fcntl.flock(fd, fcntl.LOCK_UN)
                    except OSError:
                        pass
                os.close(fd)

    def _refresh_stream_if_rotated(self) -> None:
        """Reopen stream if a sibling worker rotated or removed baseFilename."""
        if self.stream is None:
            return
        if os.name == "nt":
            if not os.path.exists(self.baseFilename):
                self._close_stream()
            return
        try:
            disk_stat = os.stat(self.baseFilename)
            stream_stat = os.fstat(self.stream.fileno())
            if disk_stat.st_ino != stream_stat.st_ino or disk_stat.st_dev != stream_stat.st_dev:
                self._close_stream()
        except OSError:
            self._close_stream()

    def _close_stream(self) -> None:
        if self.stream is not None:
            try:
                self.stream.flush()
                self.stream.close()
            except OSError:
                pass
            self.stream = None

    def emit(self, record) -> None:
        try:
            with self._interprocess_lock():
                self._refresh_stream_if_rotated()
                if self.stream is None:
                    self.stream = self._open()
                if self.shouldRollover(record):
                    self.doRollover()
                if self.stream is None:
                    self.stream = self._open()
                msg = self.format(record)
                self.stream.write(msg + self.terminator)
                self.flush()
                if os.name == "nt":
                    # Release Windows file handle so other workers/threads can rename on rollover
                    self._close_stream()
        except Exception:
            self.handleError(record)
