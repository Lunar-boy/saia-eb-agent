from __future__ import annotations

from pathlib import Path

from saia_eb_agent.models import WorkflowResult


def render_report(result: WorkflowResult) -> str:
    lines: list[str] = []
    lines.append("# SAIA EB Agent Report")
    lines.append("")
    lines.append("## Request Summary")
    for k, v in result.request.items():
        lines.append(f"- **{k}**: {v}")

    lines.append("")
    lines.append("## Candidate Selection")
    if not result.candidates:
        lines.append("- No candidates found")
    else:
        for idx, cand in enumerate(result.candidates[:5], start=1):
            lines.append(f"- {idx}. `{cand.metadata.filename}` (score={cand.score:.1f})")
            if cand.reasons:
                lines.append(f"  - reasons: {', '.join(cand.reasons)}")
            if cand.risk_notes:
                lines.append(f"  - risk: {', '.join(cand.risk_notes)}")
            if cand.likely_edits:
                lines.append(f"  - likely edits: {', '.join(cand.likely_edits)}")

    lines.append("")
    lines.append("## Validation")
    if result.validation is None:
        lines.append("- Validation not executed")
    else:
        lines.append(f"- Result: {'PASS' if result.validation.ok else 'FAIL'}")
        for issue in result.validation.issues:
            lines.append(f"- [{issue.severity}] {issue.code}: {issue.message}")

    lines.append("")
    lines.append("## Operations")
    if not result.operations:
        lines.append("- No file operations")
    for op in result.operations:
        lines.append(f"- {op}")

    lines.append("")
    lines.append("## MR Artifacts")
    for k, v in result.mr_artifacts.items():
        lines.append(f"- **{k}**: {v}")

    lines.append("")
    lines.append("## HPC Follow-Up")
    lines.append("- Local checks are heuristic only and do not replace HPC CI EasyBuild execution.")
    lines.append("- Open Draft MR first, validate with HPC CI, then promote to non-draft after review.")

    return "\n".join(lines)


def write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
