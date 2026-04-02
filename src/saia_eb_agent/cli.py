from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from saia_eb_agent.config import load_settings
from saia_eb_agent.models import RecommendRequest, WorkflowResult
from saia_eb_agent.parsing.easyconfig_text import extract_metadata
from saia_eb_agent.policy.rules import expand_target_kind, load_policy
from saia_eb_agent.reporting.markdown import render_report, write_report
from saia_eb_agent.repos.barnard_ci import BarnardCIRepo
from saia_eb_agent.state.store import StateStore
from saia_eb_agent.validation.checks import validate_easyconfig
from saia_eb_agent.workflows.agent import AgentInputs, AgentWorkflow
from saia_eb_agent.workflows.apply import prepare_apply_multi
from saia_eb_agent.workflows.prepare_mr import build_mr_artifacts, build_mr_artifacts_for_clusters
from saia_eb_agent.workflows.search import resolve_toolchain_query, search_candidates
from saia_eb_agent.utils.logging import console

app = typer.Typer(no_args_is_help=True, help="Safe local EasyBuild assistant for barnard-ci workflows")
memory_app = typer.Typer(help="Persistent memory management")
app.add_typer(memory_app, name="memory")


def _build_request(
    software: str,
    tc: str | None,
    target_kind: str,
    release: str | None,
    keywords: list[str] | None,
) -> RecommendRequest:
    return RecommendRequest(
        software=software,
        toolchain_query=tc,
        target_kind=target_kind,
        release=release,
        keywords=keywords or [],
    )


def _render_search_table(ranked: list, top: int) -> None:
    table = Table(title="Search Results")
    table.add_column("Rank")
    table.add_column("Score")
    table.add_column("File")
    table.add_column("Software Version")
    table.add_column("Toolchain")
    table.add_column("Toolchain Match Reason")
    table.add_column("Patches")
    for i, c in enumerate(ranked[:top], start=1):
        toolchain = "-".join(filter(None, [c.metadata.toolchain_name, c.metadata.toolchain_version]))
        patches_total = len(c.metadata.patches)
        patches_found = sum(1 for p in c.metadata.patches if p.exists)
        patch_text = "-" if patches_total == 0 else f"{patches_found}/{patches_total}"
        table.add_row(
            str(i),
            f"{c.score:.1f}",
            c.metadata.path.as_posix(),
            c.metadata.version or "-",
            toolchain or "-",
            c.toolchain_match_reason or "-",
            patch_text,
        )
    console.print(table)


@app.command()
def search(
    software: str = typer.Option(..., "--software"),
    tc: str | None = typer.Option(None, "--tc"),
    keyword: list[str] = typer.Option([], "--keyword"),
    settings: Path | None = typer.Option(None, "--settings"),
    local_upstream: Path | None = typer.Option(None, "--local-upstream"),
    top: int = typer.Option(10, "--top"),
) -> None:
    cfg = load_settings(settings)
    req = _build_request(software, tc, "cpu", release=None, keywords=keyword)
    ranked = search_candidates(cfg, req, local_upstream_path=local_upstream)
    resolution = resolve_toolchain_query(cfg, tc)

    _render_search_table(ranked, top)
    if resolution.aliases:
        console.print("\nToolchain equivalence expansion:")
        for alias in resolution.aliases:
            prefix = "!" if alias.confidence < 0.6 else "-"
            console.print(f"{prefix} {alias.value} [{alias.source}, confidence={alias.confidence:.2f}] {alias.reason}")

    if ranked:
        console.print("\nPatch details for top matches:")
        for cand in ranked[: min(top, 5)]:
            if not cand.metadata.patches:
                continue
            console.print(f"* {cand.metadata.filename}")
            for patch in cand.metadata.patches:
                status = "found" if patch.exists else "missing"
                resolved = patch.resolved_path.as_posix() if patch.resolved_path else "-"
                console.print(f"  - {patch.filename}: {status} ({resolved})")


@app.command(name="recommend")
def recommend_cmd(
    software: str = typer.Option(..., "--software"),
    tc: str | None = typer.Option(None, "--tc"),
    target_kind: str = typer.Option("cpu", "--cluster"),
    release: str = typer.Option(..., "--release"),
    keyword: list[str] = typer.Option([], "--keyword"),
    report: Path | None = typer.Option(None, "--report"),
    settings: Path | None = typer.Option(None, "--settings"),
    local_upstream: Path | None = typer.Option(None, "--local-upstream"),
) -> None:
    if target_kind not in {"cpu", "gpu"}:
        raise typer.BadParameter("--cluster must be 'cpu' or 'gpu'")
    cfg = load_settings(settings)
    req = _build_request(software, tc, target_kind, release=release, keywords=keyword)
    ranked = search_candidates(cfg, req, local_upstream_path=local_upstream)

    if ranked:
        selected = ranked[0]
        console.print(f"Selected: {selected.metadata.path} (score={selected.score:.1f})")
        console.print(f"Toolchain reason: {selected.toolchain_match_reason or '-'}")
    else:
        console.print("No candidate selected.")

    if report:
        result = WorkflowResult(
            request=req.__dict__,
            candidates=ranked,
            selected=ranked[0] if ranked else None,
            validation=None,
            operations=[],
            mr_artifacts={},
            notes=[],
        )
        write_report(report, render_report(result))


@app.command(name="validate")
def validate_cmd(
    file: Path = typer.Option(..., "--file"),
    cluster: str = typer.Option(..., "--cluster"),
    release: str = typer.Option(..., "--release"),
    barnard_ci: Path | None = typer.Option(None, "--barnard-ci"),
    policy_file: Path | None = typer.Option(None, "--policy-file"),
) -> None:
    md = extract_metadata(file)
    text = file.read_text(encoding="utf-8", errors="replace")
    policy = load_policy(policy_file)
    existing = []
    target = file
    if barnard_ci:
        repo = BarnardCIRepo(barnard_ci)
        existing = repo.scan_easyconfigs() if repo.exists() else []
        target = repo.target_dir(cluster, release) / file.name

    result = validate_easyconfig(md, text, target, cluster, release, policy, existing_paths=existing)
    console.print(f"Validation: {'PASS' if result.ok else 'FAIL'}")
    for issue in result.issues:
        console.print(f"[{issue.severity}] {issue.code}: {issue.message}")


@app.command()
def apply(
    software: str = typer.Option(..., "--software"),
    tc: str | None = typer.Option(None, "--tc"),
    cluster: str = typer.Option(..., "--cluster"),
    release: str = typer.Option(..., "--release"),
    barnard_ci: Path = typer.Option(..., "--barnard-ci"),
    settings: Path | None = typer.Option(None, "--settings"),
    policy_file: Path | None = typer.Option(None, "--policy-file"),
    local_upstream: Path | None = typer.Option(None, "--local-upstream"),
    apply: bool = typer.Option(False, "--apply", help="Actually write file changes"),
    report: Path | None = typer.Option(None, "--report"),
) -> None:
    if cluster not in {"cpu", "gpu"}:
        raise typer.BadParameter("--cluster must be 'cpu' or 'gpu'")

    cfg = load_settings(settings)
    policy = load_policy(policy_file)
    req = _build_request(software, tc, cluster, release, [])
    ranked = search_candidates(cfg, req, local_upstream_path=local_upstream)
    if not ranked:
        raise typer.Exit(code=2)

    repo = BarnardCIRepo(barnard_ci)
    if not repo.exists():
        raise typer.BadParameter("Provided --barnard-ci path does not contain easyconfigs/.")

    target_clusters = expand_target_kind(cluster, policy)
    discovered_clusters = set(repo.discover_clusters())
    missing_clusters = [c for c in target_clusters if c not in discovered_clusters]
    if missing_clusters:
        raise typer.BadParameter(f"Missing target cluster directories in barnard-ci: {missing_clusters}")

    targets, _diffs, validations, operations = prepare_apply_multi(
        candidate=ranked[0],
        barnard_repo=repo,
        clusters=target_clusters,
        release=release,
        policy=policy,
        apply=apply,
    )

    console.print("Validation summary:")
    for c in target_clusters:
        status = "PASS" if validations[c].ok else "FAIL"
        console.print(f"- {c}: {status}")
        for issue in validations[c].issues:
            console.print(f"  [{issue.severity}] {issue.code}: {issue.message}")

    console.print("Planned targets:")
    for c in target_clusters:
        console.print(f"- {c}: {targets[c]}")

    mr = build_mr_artifacts_for_clusters(target_clusters, release, ranked[0].metadata)
    console.print("MR artifacts:")
    for key, value in mr.items():
        console.print(f"{key}: {value}")

    if report:
        result = WorkflowResult(
            request=req.__dict__,
            candidates=ranked,
            selected=ranked[0],
            validation=next(iter(validations.values())) if validations else None,
            operations=operations,
            mr_artifacts=mr,
            cluster_validations=validations,
            notes=["Apply command completed."],
        )
        write_report(report, render_report(result))


@app.command(name="prepare-mr")
def prepare_mr_cmd(
    file: Path = typer.Option(..., "--file"),
    cluster: str = typer.Option(..., "--cluster"),
    release: str = typer.Option(..., "--release"),
) -> None:
    md = extract_metadata(file)
    artifacts = build_mr_artifacts(cluster, release, md)
    for k, v in artifacts.items():
        console.print(f"{k}: {v}")


def _run_guide(
    software: str | None,
    cluster: str | None,
    tc: str | None,
    release: str | None,
    barnard_ci: Path | None,
    apply_changes: bool,
    settings: Path | None,
    policy_file: Path | None,
    local_upstream: Path | None,
    state_file: Path | None,
) -> None:
    def _prompt(message: str, allow_empty: bool) -> str:
        if allow_empty:
            return typer.prompt(
                message,
                prompt_suffix=" ",
                default="",
                show_default=False,
            )
        return typer.prompt(message, prompt_suffix=" ")

    cfg = load_settings(settings)
    policy = load_policy(policy_file)
    workflow = AgentWorkflow(StateStore(state_file))
    inputs = AgentInputs(
        software=software,
        target_kind=cluster,
        toolchain_query=tc,
        release=release,
        barnard_ci=barnard_ci,
        apply_changes=apply_changes,
    )
    result = workflow.run(
        settings=cfg,
        policy=policy,
        inputs=inputs,
        prompt=_prompt,
        confirm=lambda m, d: typer.confirm(m, default=d),
        local_upstream_path=local_upstream,
    )

    if result.selected:
        console.print(f"Selected candidate: {result.selected.metadata.filename}")
    _render_search_table(result.candidates, top=5)

    console.print("Validation summary:")
    for c, res in result.cluster_validations.items():
        console.print(f"- {c}: {'PASS' if res.ok else 'FAIL'}")
        for issue in res.issues:
            console.print(f"  [{issue.severity}] {issue.code}: {issue.message}")

    console.print("File operations:")
    for op in result.operations:
        console.print(f"- {op}")

    console.print("Prepared MR artifacts:")
    for k, v in result.mr_artifacts.items():
        console.print(f"- {k}: {v}")


@app.command(name="guide")
def guide_cmd(
    software: str | None = typer.Option(None, "--software"),
    cluster: str | None = typer.Option(None, "--cluster"),
    tc: str | None = typer.Option(None, "--tc"),
    release: str | None = typer.Option(None, "--release"),
    barnard_ci: Path | None = typer.Option(None, "--barnard-ci"),
    apply_changes: bool = typer.Option(True, "--apply/--dry-run"),
    settings: Path | None = typer.Option(None, "--settings"),
    policy_file: Path | None = typer.Option(None, "--policy-file"),
    local_upstream: Path | None = typer.Option(None, "--local-upstream"),
    state_file: Path | None = typer.Option(None, "--state-file"),
) -> None:
    _run_guide(
        software=software,
        cluster=cluster,
        tc=tc,
        release=release,
        barnard_ci=barnard_ci,
        apply_changes=apply_changes,
        settings=settings,
        policy_file=policy_file,
        local_upstream=local_upstream,
        state_file=state_file,
    )


@app.command(name="agent")
def agent_cmd(
    software: str | None = typer.Option(None, "--software"),
    cluster: str | None = typer.Option(None, "--cluster"),
    tc: str | None = typer.Option(None, "--tc"),
    release: str | None = typer.Option(None, "--release"),
    barnard_ci: Path | None = typer.Option(None, "--barnard-ci"),
    apply_changes: bool = typer.Option(True, "--apply/--dry-run"),
    settings: Path | None = typer.Option(None, "--settings"),
    policy_file: Path | None = typer.Option(None, "--policy-file"),
    local_upstream: Path | None = typer.Option(None, "--local-upstream"),
    state_file: Path | None = typer.Option(None, "--state-file"),
) -> None:
    _run_guide(
        software=software,
        cluster=cluster,
        tc=tc,
        release=release,
        barnard_ci=barnard_ci,
        apply_changes=apply_changes,
        settings=settings,
        policy_file=policy_file,
        local_upstream=local_upstream,
        state_file=state_file,
    )


@memory_app.command(name="show")
def memory_show(state_file: Path | None = typer.Option(None, "--state-file")) -> None:
    store = StateStore(state_file)
    state = store.load()
    console.print(f"schema_version: {state.schema_version}")
    console.print(f"remembered_barnard_ci_path: {state.remembered_barnard_ci_path}")
    console.print(f"last_release: {state.last_release}")
    console.print(f"release_history: {state.release_history}")
    console.print(f"last_target_kind: {state.last_target_kind}")
    console.print(f"last_toolchain_query: {state.last_toolchain_query}")


@memory_app.command(name="set-barnard-ci")
def memory_set_barnard_ci(path: Path, state_file: Path | None = typer.Option(None, "--state-file")) -> None:
    store = StateStore(state_file)
    state = store.load()
    normalized = path.expanduser().resolve(strict=False)
    state.remembered_barnard_ci_path = normalized.as_posix()
    store.save(state)
    console.print(f"remembered_barnard_ci_path set to: {normalized}")


@memory_app.command(name="clear")
def memory_clear(state_file: Path | None = typer.Option(None, "--state-file")) -> None:
    store = StateStore(state_file)
    store.clear()
    console.print("Persistent memory cleared.")


if __name__ == "__main__":
    app()
