from __future__ import annotations

from typing import Iterable

from saia_eb_agent.models import Candidate, EasyconfigMetadata, RecommendRequest
from saia_eb_agent.policy.detection import detect_gpu_intent
from saia_eb_agent.toolchains.resolve import ToolchainResolution


def rank_candidates(
    request: RecommendRequest,
    candidates: Iterable[EasyconfigMetadata],
    toolchain_resolution: ToolchainResolution | None = None,
) -> list[Candidate]:
    ranked: list[Candidate] = []
    query = request.software.lower()
    alias_map = {
        a.value.lower(): a for a in (toolchain_resolution.aliases if toolchain_resolution else [])
    }

    for md in candidates:
        score = 0.0
        reasons: list[str] = []
        likely_edits: list[str] = []
        risk_notes: list[str] = []
        toolchain_match_reason = "not requested"

        name = (md.software_name or "").lower()
        tc = f"{md.toolchain_name or ''}-{md.toolchain_version or ''}".strip("-")
        tc_lower = tc.lower()

        if name == query:
            score += 60
            reasons.append("exact software name match")
        elif query in name:
            score += 30
            reasons.append("partial software name match")
        else:
            score -= 30

        if toolchain_resolution and toolchain_resolution.aliases:
            if tc_lower in alias_map:
                alias = alias_map[tc_lower]
                bonus = 25 if alias.source in {"exact", "normalized"} else 25 * alias.confidence
                score += bonus
                toolchain_match_reason = (
                    f"{alias.value} via {alias.source} ({alias.confidence:.2f}): {alias.reason}"
                )
                reasons.append(f"toolchain match: {alias.value}")
                if alias.confidence < 0.6:
                    risk_notes.append("low-confidence toolchain mapping; review match rationale")
            else:
                score -= 8
                risk_notes.append("no toolchain-family match with requested query")
        else:
            score += 2

        gpu_guess, hits = detect_gpu_intent(md)
        if request.target_kind == "gpu":
            if gpu_guess:
                score += 8
                reasons.append("GPU target matches detected GPU intent")
            else:
                score -= 10
                risk_notes.append("target_kind is gpu but candidate did not show GPU hints")
        else:
            if gpu_guess:
                score -= 6
                risk_notes.append(f"target_kind is cpu but candidate looks GPU-oriented: {', '.join(hits)}")
            else:
                score += 4
                reasons.append("CPU target matches non-GPU candidate hints")

        if md.versionsuffix:
            likely_edits.append("check versionsuffix compatibility for target release")

        if md.patches:
            found = sum(1 for p in md.patches if p.exists)
            if found == len(md.patches):
                score += 4
                reasons.append(f"all {found} declared patches were resolved")
            elif found > 0:
                score += 1
                reasons.append(f"{found}/{len(md.patches)} declared patches were resolved")
                risk_notes.append("some declared patches were not resolved")
            else:
                score -= 2
                risk_notes.append("declared patches were not resolved in upstream tree")

        if md.parse_warnings:
            score -= 8
            risk_notes.extend(md.parse_warnings)

        ranked.append(
            Candidate(
                metadata=md,
                score=score,
                reasons=reasons,
                likely_edits=sorted(set(likely_edits)),
                risk_notes=sorted(set(risk_notes)),
                toolchain_match_reason=toolchain_match_reason,
            )
        )

    return sorted(ranked, key=lambda c: c.score, reverse=True)
