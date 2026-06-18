"""TopicSessionManager — Telegram multi-session topic routing."""

from pathlib import Path
import json


class TopicSessionManager:
    """Each Telegram thread/topic gets own session ID + memory context."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or Path.home() / ".jalaagent" / "topic_sessions.json"
        self._sessions: dict[str, str] = {}  # chat_id → session_id
        self._enabled = True
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            self._sessions = json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._sessions, indent=2), encoding="utf-8")

    def get_session(self, chat_id: str) -> str:
        if not self._enabled: return "default"
        if chat_id not in self._sessions:
            self._sessions[chat_id] = f"topic-{chat_id}"
            self._save()
        return self._sessions[chat_id]

    def set_session(self, chat_id: str, session_id: str) -> None:
        self._sessions[chat_id] = session_id
        self._save()

    def disable(self) -> str:
        self._enabled = False
        return "Topic mode disabled — all chats share one session."

    def enable(self) -> str:
        self._enabled = True
        return "Topic mode enabled — each chat has own session."

    @property
    def enabled(self) -> bool:
        return self._enabled

    def status(self) -> str:
        return f"Topic mode: {'ON' if self._enabled else 'OFF'}, {len(self._sessions)} sessions tracked."
