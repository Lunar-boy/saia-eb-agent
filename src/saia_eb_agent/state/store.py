from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


SCHEMA_VERSION = 1


@dataclass
class AgentPersistentState:
    schema_version: int = SCHEMA_VERSION
    remembered_barnard_ci_path: str | None = None
    last_release: str | None = None
    release_history: list[str] = field(default_factory=list)
    last_target_kind: str | None = None
    last_toolchain_query: str | None = None


class StateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (Path.home() / ".config" / "saia-eb-agent" / "state.json")

    def load(self) -> AgentPersistentState:
        if not self.path.exists():
            return AgentPersistentState()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return AgentPersistentState()

        if not isinstance(raw, dict):
            return AgentPersistentState()
        if raw.get("schema_version") != SCHEMA_VERSION:
            return AgentPersistentState()

        return AgentPersistentState(
            schema_version=SCHEMA_VERSION,
            remembered_barnard_ci_path=raw.get("remembered_barnard_ci_path"),
            last_release=raw.get("last_release"),
            release_history=list(raw.get("release_history") or []),
            last_target_kind=raw.get("last_target_kind"),
            last_toolchain_query=raw.get("last_toolchain_query"),
        )

    def save(self, state: AgentPersistentState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(state), indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
