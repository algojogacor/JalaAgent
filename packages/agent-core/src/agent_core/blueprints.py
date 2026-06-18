"""BlueprintStore — parameterized automation templates built on cron infra."""

import time
from pathlib import Path
from typing import Any
import yaml

_DEFAULT_PATH = Path.home() / ".jalaagent" / "blueprints"


class BlueprintStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._path.mkdir(parents=True, exist_ok=True)

    def create(self, name: str, template: str, params: list[str] | None = None) -> str:
        bp = {"name": name, "template": template, "params": params or [], "created": time.time()}
        (self._path / f"{name}.yaml").write_text(yaml.dump(bp), encoding="utf-8")
        return name

    def list_all(self) -> list[dict[str, Any]]:
        return [yaml.safe_load(f.read_text(encoding="utf-8")) for f in sorted(self._path.glob("*.yaml"))]

    def get(self, name: str) -> dict[str, Any] | None:
        f = self._path / f"{name}.yaml"
        return yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else None

    def delete(self, name: str) -> bool:
        f = self._path / f"{name}.yaml"
        if f.exists(): f.unlink(); return True
        return False

    def run(self, name: str, params: dict[str, str]) -> str:
        bp = self.get(name)
        if not bp: return f"Blueprint {name} not found."
        text = bp["template"]
        for k, v in params.items(): text = text.replace(f"{{{{{k}}}}}", v)
        return text
