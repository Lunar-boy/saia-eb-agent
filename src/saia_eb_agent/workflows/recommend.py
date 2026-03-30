from __future__ import annotations

from pathlib import Path

from saia_eb_agent.config import AppSettings
from saia_eb_agent.models import RecommendRequest, WorkflowResult
from saia_eb_agent.providers.saia import SAIAProvider
from saia_eb_agent.reporting.markdown import render_report, write_report
from saia_eb_agent.workflows.prepare_mr import build_mr_artifacts
from saia_eb_agent.workflows.search import search_candidates


def recommend(
    settings: AppSettings,
    request: RecommendRequest,
    report_path: Path | None = None,
    refresh_upstream: bool = False,
    local_upstream_path: Path | None = None,
) -> WorkflowResult:
    ranked = search_candidates(settings, request, refresh_upstream=refresh_upstream, local_upstream_path=local_upstream_path)
    selected = ranked[0] if ranked else None

    notes = []
    provider = SAIAProvider(settings.provider)
    if provider.available() and selected:
        prompt = (
            "Provide concise HPC CI risk notes for this EasyBuild candidate:\n"
            f"software={selected.metadata.software_name}\n"
            f"version={selected.metadata.version}\n"
            f"toolchain={selected.metadata.toolchain_name}-{selected.metadata.toolchain_version}\n"
            f"cluster={request.cluster}, release={request.release}, gpu={request.gpu}\n"
        )
        try:
            notes.append(provider.generate_text(prompt))
        except Exception as exc:  # noqa: BLE001
            notes.append(f"LLM advisory unavailable: {exc}")
    else:
        notes.append("Rule-only mode: SAIA provider not configured or unavailable.")

    mr = build_mr_artifacts(request.cluster, request.release, selected.metadata) if selected else {}
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
