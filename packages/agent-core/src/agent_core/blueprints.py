"""BlueprintStore — parameterized automation templates built on cron infra."""

import re
import time
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_PATH = Path.home() / ".jalaagent" / "blueprints"

_NAME_RE = re.compile(r'^[a-zA-Z0-9_-]+$')


def _safe_name(name: str) -> str:
    if not _NAME_RE.match(name):
        raise ValueError(f"Invalid blueprint name: {name!r}. Use only letters, numbers, hyphens, underscores.")
    return name


class BlueprintStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._path.mkdir(parents=True, exist_ok=True)

    def create(self, name: str, template: str, params: list[str] | None = None) -> str:
        _safe_name(name)
        bp = {"name": name, "template": template, "params": params or [], "created": time.time()}
        (self._path / f"{name}.yaml").write_text(yaml.dump(bp), encoding="utf-8")
        return name

    def list_all(self) -> list[dict[str, Any]]:
        return [yaml.safe_load(f.read_text(encoding="utf-8")) for f in sorted(self._path.glob("*.yaml"))]

    def get(self, name: str) -> dict[str, Any] | None:
        _safe_name(name)
        f = self._path / f"{name}.yaml"
        return yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else None

    def delete(self, name: str) -> bool:
        _safe_name(name)
        f = self._path / f"{name}.yaml"
        if f.exists(): f.unlink(); return True
        return False

    def run(self, name: str, params: dict[str, str]) -> str:
        _safe_name(name)
        bp = self.get(name)
        if not bp: return f"Blueprint {name} not found."
        text = bp["template"]
        for k, v in params.items(): text = text.replace(f"{{{{{k}}}}}", v)
        # Warn if template placeholders remain after substitution.
        remaining = set(re.findall(r"\{\{(\w+)\}\}", text))
        if remaining:
            missing = ", ".join(sorted(remaining))
            text += f"\n\n⚠️ Unresolved parameters: {missing}"
        return text
