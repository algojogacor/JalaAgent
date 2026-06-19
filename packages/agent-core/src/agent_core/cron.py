"""CronScheduler — general scheduled task manager with yaml storage."""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)
_DEFAULT_PATH = Path.home() / ".jalaagent" / "cron.yaml"


class CronScheduler:
    """Simple cron-like scheduler using asyncio. Stores tasks in yaml."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._tasks: dict[str, dict[str, Any]] = {}
        self._running = False
        self._task: asyncio.Task[Any] | None = None
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            self._tasks = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(yaml.dump(self._tasks), encoding="utf-8")

    def add(self, name: str, schedule: str, prompt: str) -> str:
        self._tasks[name] = {"schedule": schedule, "prompt": prompt, "paused": False, "created": time.time()}
        self._save()
        return name

    def remove(self, name: str) -> bool:
        if name in self._tasks:
            del self._tasks[name]; self._save(); return True
        return False

    def pause(self, name: str) -> bool:
        if name in self._tasks:
            self._tasks[name]["paused"] = True; self._save(); return True
        return False

    def resume(self, name: str) -> bool:
        if name in self._tasks:
            self._tasks[name]["paused"] = False; self._save(); return True
        return False

    def list_all(self) -> list[dict[str, Any]]:
        return [{"name": k, **v} for k, v in self._tasks.items()]

    def get(self, name: str) -> dict[str, Any] | None:
        return self._tasks.get(name)

    async def start(self, callback: Any) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop(callback))

    async def stop(self) -> None:
        self._running = False
        if self._task: self._task.cancel()

    async def _loop(self, callback: Any) -> None:
        while self._running:
            now = time.strftime("%M %H %d %m %w").split()
            for name, t in list(self._tasks.items()):
                if t.get("paused"): continue
                parts = t["schedule"].split()
                if len(parts) == 5 and _cron_match(parts, now):
                    logger.info("Cron firing: %s", name)
                    try: await callback(t["prompt"], name)
                    except Exception: logger.exception("Cron task %s failed", name)
            await asyncio.sleep(60)


def _cron_match(parts: list[str], now: list[str]) -> bool:
    for i, pat in enumerate(parts):
        if pat == "*":
            continue
        if pat.startswith("*/"):
            interval = int(pat[2:])
            if int(now[i]) % interval != 0:
                return False
        elif "," in pat:
            allowed = {v.strip() for v in pat.split(",")}
            if now[i] not in allowed:
                return False
        elif pat != now[i]:
            return False
    return True
