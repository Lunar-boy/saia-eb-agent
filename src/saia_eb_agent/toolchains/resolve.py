from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from saia_eb_agent.providers.base import LLMProvider


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
    def __init__(self, cache_file: Path | None = None, provider: LLMProvider | None = None) -> None:
        self.cache_file = cache_file
        self.provider = provider
        self._cache = self._load_cache()

    def resolve(self, query: str | None, allow_llm: bool = True) -> ToolchainResolution:
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

        self._merge_cached_llm(raw, aliases)

        if allow_llm and self.provider and self.provider.available() and raw not in self._cache:
            llm_aliases = self._resolve_with_llm(raw)
            if llm_aliases:
                self._cache[raw] = [asdict(a) for a in llm_aliases]
                self._save_cache()
                aliases.extend(llm_aliases)

        deduped = self._dedupe_aliases(aliases)
        return ToolchainResolution(query=raw, normalized=normalized, aliases=deduped)

    def _normalize(self, value: str) -> str:
        compact = re.sub(r"\s+", "", value)
        compact = compact.replace("_", "-")
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

    def _resolve_with_llm(self, query: str) -> list[ToolchainAlias]:
        assert self.provider
        prompt = (
            "Return up to 5 likely equivalent EasyBuild toolchain identifiers for this query. "
            "Use only plain comma-separated values, no prose: "
            f"{query}"
        )
        try:
            text = self.provider.generate_text(prompt)
        except Exception:
            return []

        values = [v.strip() for v in text.replace("\n", ",").split(",") if v.strip()]
        return [
            ToolchainAlias(
                value=self._normalize(v),
                source="llm",
                confidence=0.45,
                reason="provider-suggested relation; review recommended",
            )
            for v in values[:5]
        ]

    def _dedupe_aliases(self, aliases: list[ToolchainAlias]) -> list[ToolchainAlias]:
        by_key: dict[str, ToolchainAlias] = {}
        for a in aliases:
            key = a.value.lower()
            if key not in by_key or by_key[key].confidence < a.confidence:
                by_key[key] = a
        return sorted(by_key.values(), key=lambda a: (-a.confidence, a.value.lower()))

    def _load_cache(self) -> dict[str, list[dict[str, object]]]:
        if not self.cache_file or not self.cache_file.exists():
            return {}
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            return {}
        return {}

    def _save_cache(self) -> None:
        if not self.cache_file:
            return
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._cache, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.cache_file)

    def _merge_cached_llm(self, query: str, aliases: list[ToolchainAlias]) -> None:
        rows = self._cache.get(query, [])
        for row in rows:
            try:
                aliases.append(
                    ToolchainAlias(
                        value=str(row["value"]),
                        source=str(row.get("source", "llm")),
                        confidence=float(row.get("confidence", 0.45)),
                        reason=str(row.get("reason", "cached provider suggestion")),
                    )
                )
            except Exception:
                continue
