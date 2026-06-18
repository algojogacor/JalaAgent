"""Drift detection for external modifications to MEMORY.md mid-session.

Implements the **frozen snapshot pattern** (see CLAUDE.md):
memory is captured at session start and never updated mid-session in the
prompt.  If MEMORY.md is modified externally during a session, the agent
detects the drift and refuses to write, preventing corruption.

Usage
-----
.. code-block:: python

    detector = DriftDetector(file_layer)
    snapshot = await detector.take_snapshot()
    # ... session runs ...
    if await detector.check_drift():
        print("MEMORY.md was modified externally — write refused")
"""

import logging

from memory_core.file_layer import FileLayer

logger = logging.getLogger(__name__)


class DriftDetector:
    """Detects and handles external modifications to ``MEMORY.md`` mid-session.

    The **frozen snapshot pattern** works as follows:

    1. At session start, :meth:`take_snapshot` is called once.  It reads the
       full content of ``MEMORY.md`` and records its ``mtime``.
    2. During the session, :meth:`check_drift` is called before any memory
       write.  If the file's current ``mtime`` differs from the snapshot,
       **drift is detected** and the write is refused.
    3. The agent can still read the snapshot content via
       :meth:`get_snapshot_content` — it just cannot mutate the live file.

    This prevents two sessions (or an external editor) from racing on the
    same file and silently corrupting each other's work.
    """

    def __init__(self, file_layer: FileLayer) -> None:
        """Create a drift detector backed by *file_layer*.

        Parameters
        ----------
        file_layer:
            The :class:`FileLayer` that manages ``MEMORY.md``.  The detector
            delegates all file operations to it.
        """
        self._file_layer = file_layer
        self._snapshot_mtime: float = 0.0
        self._snapshot_content: str = ""
        self._has_snapshot: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def take_snapshot(self) -> str:
        """Capture the current ``MEMORY.md`` content and ``mtime`` atomically.

        This must be called **once** at session start.  Subsequent calls
        overwrite the previous snapshot (useful for sessions that explicitly
        reset their memory view, but generally not recommended for the
        frozen snapshot pattern).

        Returns
        -------
        str
            The full content of ``MEMORY.md`` (or ``""`` on first run).

        Raises
        ------
        RuntimeError
            If the file layer's own snapshot mechanism fails (e.g. the lock
            file cannot be created).
        """
        self._snapshot_content = await self._file_layer.snapshot_memory()
        self._snapshot_mtime = self._file_layer.snapshot_mtime
        self._has_snapshot = True
        logger.debug(
            "Drift snapshot taken — mtime=%s, len=%d",
            self._snapshot_mtime,
            len(self._snapshot_content),
        )
        return self._snapshot_content

    async def check_drift(self) -> bool:
        """Check whether ``MEMORY.md`` has been modified since the snapshot.

        Compares the **current** ``mtime`` of ``MEMORY.md`` against the
        value recorded by :meth:`take_snapshot`.  A difference means the
        file was modified externally.

        Returns
        -------
        bool
            ``True`` if the file has been modified externally (drift
            detected), ``False`` otherwise.
        """
        if not self._has_snapshot:
            logger.warning(
                "check_drift() called before take_snapshot() — "
                "assuming no drift"
            )
            return False

        current_mtime = await self._file_layer.get_memory_mtime()

        # Floating-point mtime values can have sub-second differences on
        # some filesystems, but os.path.getmtime returns a float and we
        # store it faithfully.  Use exact equality — any difference is
        # meaningful because the snapshot and the check both go through
        # the same syscall.
        drifted = current_mtime != self._snapshot_mtime

        if drifted:
            logger.warning(
                "Drift detected! snapshot_mtime=%s, current_mtime=%s",
                self._snapshot_mtime,
                current_mtime,
            )

        return drifted

    async def get_snapshot_content(self) -> str:
        """Return the ``MEMORY.md`` content captured at session start.

        Returns
        -------
        str
            The snapshot content, or ``""`` if :meth:`take_snapshot` has
            not been called yet.
        """
        return self._snapshot_content

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def snapshot_mtime(self) -> float:
        """The ``mtime`` recorded by the last call to :meth:`take_snapshot`."""
        return self._snapshot_mtime

    @property
    def has_snapshot(self) -> bool:
        """Whether :meth:`take_snapshot` has been called at least once."""
        return self._has_snapshot
