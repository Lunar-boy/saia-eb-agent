from __future__ import annotations

from pathlib import Path

from saia_eb_agent.config import AppSettings
from saia_eb_agent.models import RecommendRequest, WorkflowResult
from saia_eb_agent.reporting.markdown import render_report, write_report
from saia_eb_agent.workflows.prepare_mr import build_mr_artifacts_for_clusters
from saia_eb_agent.workflows.search import search_candidates


def recommend(
    settings: AppSettings,
    request: RecommendRequest,
    report_path: Path | None = None,
    local_upstream_path: Path | None = None,
) -> WorkflowResult:
    ranked = search_candidates(settings, request, local_upstream_path=local_upstream_path)
    selected = ranked[0] if ranked else None

    notes = ["Rule-based mode: deterministic local ranking and validation only."]

    mr = {}
    if selected and request.release:
        mr = build_mr_artifacts_for_clusters([request.target_kind], request.release, selected.metadata)
    result = WorkflowResult(
        request=request.__dict__,
        candidates=ranked,
        selected=selected,
        validation=None,
        operations=[],
        mr_artifacts=mr,
        notes=notes,
    )
    if report_path:
        write_report(report_path, render_report(result))
    return result
