from __future__ import annotations

from typing import Iterable

from saia_eb_agent.models import Candidate, EasyconfigMetadata, RecommendRequest
from saia_eb_agent.policy.detection import detect_gpu_intent


def rank_candidates(request: RecommendRequest, candidates: Iterable[EasyconfigMetadata]) -> list[Candidate]:
    ranked: list[Candidate] = []
    query = request.software.lower()
    req_version = (request.version or "").lower()

    for md in candidates:
        score = 0.0
        reasons: list[str] = []
        likely_edits: list[str] = []
        risk_notes: list[str] = []

        name = (md.software_name or "").lower()
        version = (md.version or "").lower()
        tc = f"{md.toolchain_name or ''}-{md.toolchain_version or ''}".lower().strip("-")

        if name == query:
            score += 50
            reasons.append("exact software name match")
        elif query in name:
            score += 25
            reasons.append("partial software name match")
        else:
            score -= 20

        if req_version and version == req_version:
            score += 30
            reasons.append("exact version match")
        elif req_version and req_version in version:
            score += 15
            reasons.append("partial version match")
        elif not req_version:
            score += 5
            reasons.append("no explicit version requested")
        else:
            risk_notes.append("exact requested version not found")

        if request.preferred_toolchain:
            if request.preferred_toolchain.lower() in tc:
                score += 15
                reasons.append("preferred toolchain match")
            else:
                score -= 5
                likely_edits.append("toolchain adjustment may be required")

        gpu_guess, hits = detect_gpu_intent(md)
        if request.gpu == gpu_guess:
            score += 10
            reasons.append("CPU/GPU intent appears aligned")
        else:
            score -= 20
            risk_notes.append(f"CPU/GPU mismatch; detected hints: {', '.join(hits) if hits else 'none'}")

        if md.versionsuffix:
            likely_edits.append("check versionsuffix compatibility for target release")

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
            )
        )

    return sorted(ranked, key=lambda c: c.score, reverse=True)
