"""Layer 1 — Raw file storage: MEMORY.md, USER.md, session JSONL transcripts."""

import asyncio
import contextlib
import os
import sys
import time
from pathlib import Path

from memory_core.models import Episode, MemoryConfig

# ---------------------------------------------------------------------------
# Platform-specific file locking
# ---------------------------------------------------------------------------


def _lock_file(fd: int) -> None:
    """Acquire an exclusive advisory lock on the open file descriptor."""
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX)


def _unlock_file(fd: int) -> None:
    """Release the advisory lock on the open file descriptor."""
    if sys.platform == "win32":
        import msvcrt

        with contextlib.suppress(OSError):
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# FileLayer
# ---------------------------------------------------------------------------


class FileLayer:
    """Human-readable, git-trackable file-based memory storage.

    Manages three file types under ``memory_dir``:

    * ``MEMORY.md`` — curated facts, always readable, manually editable
    * ``USER.md`` — user profile, preferences, and context
    * ``sessions/<session_id>.jsonl`` — raw session transcripts (one JSON
      object per line representing an :class:`Episode`)

    All file I/O is delegated to a thread pool via :func:`asyncio.to_thread`
    so the event loop stays free.  Writes to ``MEMORY.md`` are atomic
    (write-to-temp then ``os.replace``).
    """

    _MEMORY_FILENAME = "MEMORY.md"
    _USER_FILENAME = "USER.md"
    _SESSIONS_DIR = "sessions"

    def __init__(self, config: MemoryConfig) -> None:
        self._config = config
        self._memory_dir = config.memory_dir
        self._sessions_dir = config.memory_dir / self._SESSIONS_DIR

        # Materialised so callers don't have to compute them.
        self._memory_path = self._memory_dir / self._MEMORY_FILENAME
        self._user_path = self._memory_dir / self._USER_FILENAME

        # Snapshot state — recorded under lock by snapshot_memory().
        self._snapshot_mtime: float = 0.0

        # Instance-level lock for serialising writes to MEMORY.md.
        # Prevents concurrent os.replace races on Windows.
        self._write_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _read_file(path: Path) -> str:
        """Return file contents, or empty string if the file is missing."""

        def _sync() -> str:
            try:
                return path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return ""

        return await asyncio.to_thread(_sync)

    @staticmethod
    async def _write_atomic(path: Path, content: str) -> None:
        """Write *content* to *path* atomically via a temp file + rename.

        Uses a unique temp-file name (UUID-based) to avoid races when
        multiple writers target the same destination concurrently.
        """

        def _sync() -> None:
            import uuid as _uuid

            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.parent / f"{path.name}.{_uuid.uuid4().hex}.tmp"
            tmp.write_text(content, encoding="utf-8")
            # On Windows, os.replace can fail with PermissionError if the
            # destination was recently read (lingering handle).  Retry a few
            # times with a short backoff.
            deadline = time.monotonic() + 2.0
            while True:
                try:
                    os.replace(tmp, path)
                    break
                except PermissionError:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(0.02)
            # Best-effort cleanup on teardown or race.
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)

        await asyncio.to_thread(_sync)

    @staticmethod
    async def _append_line(path: Path, line: str) -> None:
        """Append a single line to *path*, creating parents if needed."""

        def _sync() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

        await asyncio.to_thread(_sync)

    @staticmethod
    async def _read_jsonl_lines(path: Path) -> list[str]:
        """Return every non-empty line in *path*, or an empty list."""

        def _sync() -> list[str]:
            try:
                return path.read_text(encoding="utf-8").rstrip("\n").split("\n")
            except FileNotFoundError:
                return []

        return await asyncio.to_thread(_sync)

    @staticmethod
    async def _list_jsonl_files(directory: Path) -> list[str]:
        """Return the stem of every ``.jsonl`` file in *directory*."""

        def _sync() -> list[str]:
            try:
                return sorted(
                    p.stem
                    for p in directory.iterdir()
                    if p.is_file() and p.suffix == ".jsonl"
                )
            except (FileNotFoundError, NotADirectoryError):
                return []

        return await asyncio.to_thread(_sync)

    async def _get_mtime_sync(self, path: Path) -> float:
        """Return ``os.path.getmtime`` or 0.0 if the file is missing."""

        def _sync() -> float:
            try:
                return os.path.getmtime(path)
            except FileNotFoundError:
                return 0.0

        return await asyncio.to_thread(_sync)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def read_memory(self) -> str:
        """Read the full contents of ``MEMORY.md``.

        Returns an empty string on first run (file does not exist yet).
        """
        return await self._read_file(self._memory_path)

    async def write_memory(self, content: str) -> None:
        """Atomically write *content* to ``MEMORY.md``.

        Uses a temp-file + :func:`os.replace` strategy so readers always see
        either the previous complete file or the new one — never a partial
        write.  Serialised with an instance-level lock to prevent races when
        concurrent callers write to the same destination.
        """
        async with self._write_lock:
            await self._write_atomic(self._memory_path, content)

    async def read_user(self) -> str:
        """Read the full contents of ``USER.md``.

        Returns an empty string on first run.
        """
        return await self._read_file(self._user_path)

    async def append_session(self, episode: Episode) -> None:
        """Append an :class:`Episode` as a JSON line to its session transcript.

        The session file is located at
        ``sessions/<episode.session_id>.jsonl`` inside the memory directory.
        """
        path = self._sessions_dir / f"{episode.session_id}.jsonl"
        line = episode.model_dump_json()
        await self._append_line(path, line)

    async def read_session(self, session_id: str) -> list[Episode]:
        """Read every episode from a session transcript.

        Empty or invalid lines are silently skipped.
        """
        path = self._sessions_dir / f"{session_id}.jsonl"
        lines = await self._read_jsonl_lines(path)
        episodes: list[Episode] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                episodes.append(Episode.model_validate_json(stripped))
            except Exception:
                continue
        return episodes

    async def list_sessions(self) -> list[str]:
        """Return the IDs of all sessions that have transcript files."""
        return await self._list_jsonl_files(self._sessions_dir)

    async def get_memory_mtime(self) -> float:
        """Return the modification time of ``MEMORY.md`` as a Unix timestamp.

        Returns ``0.0`` if the file does not exist.
        """
        return await self._get_mtime_sync(self._memory_path)

    async def snapshot_memory(self) -> str:
        """Read ``MEMORY.md`` content and record its ``mtime`` atomically.

        The recorded mtime can later be compared via :meth:`get_memory_mtime`
        to detect external drift (file modified outside of this layer).
        """
        # We use a dedicated snapshot lock file so that snapshot_memory()
        # and write_memory() can be serialised without blocking plain reads.
        lock_path = self._memory_dir / ".memory_snapshot.lock"

        def _sync() -> str:
            self._memory_dir.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a+") as lf:
                _lock_file(lf.fileno())
                try:
                    content = ""
                    with contextlib.suppress(FileNotFoundError):
                        content = self._memory_path.read_text(encoding="utf-8")
                    self._snapshot_mtime = (
                        os.path.getmtime(self._memory_path)
                        if self._memory_path.exists()
                        else 0.0
                    )
                    return content
                finally:
                    _unlock_file(lf.fileno())

        return await asyncio.to_thread(_sync)

    @property
    def snapshot_mtime(self) -> float:
        """The mtime recorded by the last call to :meth:`snapshot_memory`."""
        return self._snapshot_mtime

    @property
    def memory_dir(self) -> Path:
        """The memory directory path from config."""
        return self._memory_dir

    @property
    def sessions_dir(self) -> Path:
        """The sessions subdirectory path."""
        return self._sessions_dir


# ---------------------------------------------------------------------------
# Backward-compatibility alias
# ---------------------------------------------------------------------------


class FileMemoryLayer(FileLayer):
    """Legacy alias for :class:`FileLayer`."""

    pass
