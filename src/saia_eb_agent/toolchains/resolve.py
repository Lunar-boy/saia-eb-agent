from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


RELEASE_TO_GCC = {
    "2025a": "14.2.0",
}
GCC_TO_RELEASE = {v: k for k, v in RELEASE_TO_GCC.items()}


@dataclass
class ToolchainAlias:
    value: str
    source: str
    confidence: float
    reason: str


@dataclass
class ToolchainResolution:
    query: str
    normalized: str
    aliases: list[ToolchainAlias]

    @property
    def uncertain(self) -> bool:
        return any(a.confidence < 0.6 for a in self.aliases)


class ToolchainResolver:
    def __init__(self, cache_file: Path | None = None) -> None:
        self.cache_file = cache_file

    def resolve(self, query: str | None) -> ToolchainResolution:
        raw = (query or "").strip()
        if not raw:
            return ToolchainResolution(query="", normalized="", aliases=[])

        normalized = self._normalize(raw)
        aliases: list[ToolchainAlias] = [
            ToolchainAlias(value=normalized, source="exact", confidence=1.0, reason="normalized user query")
        ]

        family, version = self._parse_family_version(normalized)
        if family and version:
            self._add_family_aliases(aliases, family, version)

        deduped = self._dedupe_aliases(aliases)
        return ToolchainResolution(query=raw, normalized=normalized, aliases=deduped)

    def _normalize(self, value: str) -> str:
        compact = re.sub(r"\s+", "", value)
        compact = compact.replace("_", "-")
        if compact.lower() == "system":
            return "system"
        compact = re.sub(r"(?i)^(GCCcore)(\d)", r"\1-\2", compact)
        compact = re.sub(r"(?i)^(GCC)(\d)", r"\1-\2", compact)
        compact = re.sub(r"(?i)^(foss)(\d)", r"\1-\2", compact)
        compact = re.sub(r"(?i)^(gfbf)(\d)", r"\1-\2", compact)
        return compact

    def _parse_family_version(self, normalized: str) -> tuple[str | None, str | None]:
        m = re.match(r"(?i)^(gcccore|gcc|foss|gfbf)-?([A-Za-z0-9.]+)$", normalized)
        if not m:
            return None, None
        return m.group(1).lower(), m.group(2)

    def _add_family_aliases(self, aliases: list[ToolchainAlias], family: str, version: str) -> None:
        if family in {"gcc", "gcccore"}:
            aliases.append(
                ToolchainAlias(value=f"GCC-{version}", source="normalized", confidence=0.95, reason="GCC family variant")
            )
            aliases.append(
                ToolchainAlias(
                    value=f"GCCcore-{version}",
                    source="normalized",
                    confidence=0.95,
                    reason="GCCcore family variant",
                )
            )
            if version in GCC_TO_RELEASE:
                release = GCC_TO_RELEASE[version]
                aliases.append(
                    ToolchainAlias(
                        value=f"foss-{release}",
                        source="heuristic",
                        confidence=0.75,
                        reason=f"mapped from GCC {version} to EasyBuild release {release}",
                    )
                )
                aliases.append(
                    ToolchainAlias(
                        value=f"gfbf-{release}",
                        source="heuristic",
                        confidence=0.72,
                        reason=f"mapped from GCC {version} to EasyBuild release {release}",
                    )
                )

        if family in {"foss", "gfbf"}:
            aliases.append(
                ToolchainAlias(value=f"foss-{version}", source="normalized", confidence=0.95, reason="foss family variant")
            )
            aliases.append(
                ToolchainAlias(value=f"gfbf-{version}", source="normalized", confidence=0.95, reason="gfbf family variant")
            )
            gcc = RELEASE_TO_GCC.get(version)
            if gcc:
                aliases.append(
                    ToolchainAlias(
                        value=f"GCC-{gcc}",
                        source="heuristic",
                        confidence=0.75,
                        reason=f"mapped from release {version} to GCC {gcc}",
                    )
                )
                aliases.append(
                    ToolchainAlias(
                        value=f"GCCcore-{gcc}",
                        source="heuristic",
                        confidence=0.75,
                        reason=f"mapped from release {version} to GCCcore {gcc}",
                    )
                )

    def _dedupe_aliases(self, aliases: list[ToolchainAlias]) -> list[ToolchainAlias]:
        by_key: dict[str, ToolchainAlias] = {}
        for a in aliases:
            key = a.value.lower()
            if key not in by_key or by_key[key].confidence < a.confidence:
                by_key[key] = a
        return sorted(by_key.values(), key=lambda a: (-a.confidence, a.value.lower()))
