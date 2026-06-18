"""SkillCurator — background skill maintenance daemon."""

import time
from pathlib import Path
from typing import Any


class SkillCurator:
    """Evaluates skills: usage frequency, staleness, errors. Runs as background task."""

    def __init__(self, stats_path: Path | None = None) -> None:
        self._path = stats_path or Path.home() / ".jalaagent" / "skill_stats.json"
        self._stats: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        import json
        if self._path.exists():
            self._stats = json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        import json
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._stats, indent=2), encoding="utf-8")

    def record_use(self, skill_name: str) -> None:
        s = self._stats.setdefault(skill_name, {"uses": 0, "first_used": time.time()})
        s["uses"] += 1
        s["last_used"] = time.time()
        self._save()

    def get_stats(self, skill_name: str) -> dict[str, Any]:
        return self._stats.get(skill_name, {})

    def list_all(self) -> dict[str, Any]:
        return dict(self._stats)

    def list_stale(self, days: int = 30) -> list[str]:
        cutoff = time.time() - days * 86400
        return [n for n, s in self._stats.items() if s.get("last_used", 0) < cutoff]

    def pin(self, skill_name: str) -> None:
        self._stats.setdefault(skill_name, {})["pinned"] = True
        self._save()

    def unpin(self, skill_name: str) -> None:
        if skill_name in self._stats:
            self._stats[skill_name]["pinned"] = False
            self._save()
