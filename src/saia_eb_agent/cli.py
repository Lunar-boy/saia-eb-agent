from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from saia_eb_agent.config import load_settings
from saia_eb_agent.models import RecommendRequest
from saia_eb_agent.parsing.easyconfig_text import extract_metadata
from saia_eb_agent.policy.rules import dependency_search_clusters, load_policy
from saia_eb_agent.reporting.markdown import render_report, write_report
from saia_eb_agent.repos.barnard_ci import BarnardCIRepo
from saia_eb_agent.validation.checks import validate_easyconfig
from saia_eb_agent.workflows.apply import prepare_apply
from saia_eb_agent.workflows.prepare_mr import build_mr_artifacts
from saia_eb_agent.workflows.recommend import recommend
from saia_eb_agent.workflows.search import search_candidates
from saia_eb_agent.utils.logging import console

app = typer.Typer(no_args_is_help=True, help="Safe local EasyBuild assistant for barnard-ci workflows")


def _build_request(
    software: str,
    version: str | None,
    cluster: str,
    release: str,
    gpu: bool,
    preferred_toolchain: str | None,
    keywords: list[str] | None,
) -> RecommendRequest:
    return RecommendRequest(
        software=software,
        version=version,
        cluster=cluster,
        release=release,
        gpu=gpu,
        preferred_toolchain=preferred_toolchain,
        keywords=keywords or [],
    )


@app.command()
def search(
    software: str = typer.Option(..., "--software"),
    version: str | None = typer.Option(None, "--version"),
    cluster: str = typer.Option(..., "--cluster"),
    release: str = typer.Option(..., "--release"),
    gpu: bool = typer.Option(False, "--gpu/--cpu"),
    preferred_toolchain: str | None = typer.Option(None, "--preferred-toolchain"),
    keyword: list[str] = typer.Option([], "--keyword"),
    settings: Path | None = typer.Option(None, "--settings"),
    local_upstream: Path | None = typer.Option(None, "--local-upstream"),
    refresh_upstream: bool = typer.Option(False, "--refresh-upstream"),
    top: int = typer.Option(10, "--top"),
) -> None:
    cfg = load_settings(settings)
    req = _build_request(software, version, cluster, release, gpu, preferred_toolchain, keyword)
    ranked = search_candidates(cfg, req, refresh_upstream=refresh_upstream, local_upstream_path=local_upstream)

    table = Table(title="Search Results")
    table.add_column("Rank")
    table.add_column("Score")
    table.add_column("File")
    table.add_column("Reason")
    for i, c in enumerate(ranked[:top], start=1):
        table.add_row(str(i), f"{c.score:.1f}", c.metadata.path.as_posix(), "; ".join(c.reasons[:2]))
    console.print(table)


@app.command(name="recommend")
def recommend_cmd(
    software: str = typer.Option(..., "--software"),
    version: str | None = typer.Option(None, "--version"),
    cluster: str = typer.Option(..., "--cluster"),
    release: str = typer.Option(..., "--release"),
    gpu: bool = typer.Option(False, "--gpu/--cpu"),
    preferred_toolchain: str | None = typer.Option(None, "--preferred-toolchain"),
    keyword: list[str] = typer.Option([], "--keyword"),
    report: Path | None = typer.Option(None, "--report"),
    settings: Path | None = typer.Option(None, "--settings"),
    policy_file: Path | None = typer.Option(None, "--policy-file"),
    barnard_ci: Path | None = typer.Option(None, "--barnard-ci"),
    local_upstream: Path | None = typer.Option(None, "--local-upstream"),
    refresh_upstream: bool = typer.Option(False, "--refresh-upstream"),
) -> None:
    cfg = load_settings(settings)
    policy = load_policy(policy_file)
    req = _build_request(software, version, cluster, release, gpu, preferred_toolchain, keyword)
    res = recommend(cfg, req, report_path=report, refresh_upstream=refresh_upstream, local_upstream_path=local_upstream)

    if res.selected:
        console.print(f"Selected: {res.selected.metadata.path} (score={res.selected.score:.1f})")
        clusters = dependency_search_clusters(cluster, policy)
        console.print(f"Dependency search domain for {cluster}: {clusters}")
    else:
        console.print("No candidate selected.")
    if barnard_ci:
        repo = BarnardCIRepo(barnard_ci)
        if repo.exists():
            clusters = repo.discover_clusters()
            releases = repo.discover_releases(cluster)
            console.print(f"Discovered barnard-ci clusters: {clusters}")
            console.print(f"Discovered releases for {cluster}: {releases}")
        else:
            console.print("barnard-ci path provided but easyconfigs/ layout was not found.")
    for note in res.notes:
        console.print(f"Note: {note}")


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
    version: str | None = typer.Option(None, "--version"),
    cluster: str = typer.Option(..., "--cluster"),
    release: str = typer.Option(..., "--release"),
    barnard_ci: Path = typer.Option(..., "--barnard-ci"),
    gpu: bool = typer.Option(False, "--gpu/--cpu"),
    preferred_toolchain: str | None = typer.Option(None, "--preferred-toolchain"),
    settings: Path | None = typer.Option(None, "--settings"),
    policy_file: Path | None = typer.Option(None, "--policy-file"),
    local_upstream: Path | None = typer.Option(None, "--local-upstream"),
    refresh_upstream: bool = typer.Option(False, "--refresh-upstream"),
    apply: bool = typer.Option(False, "--apply", help="Actually write file changes"),
    report: Path | None = typer.Option(None, "--report"),
) -> None:
    cfg = load_settings(settings)
    policy = load_policy(policy_file)
    req = _build_request(software, version, cluster, release, gpu, preferred_toolchain, [])
    ranked = search_candidates(cfg, req, refresh_upstream=refresh_upstream, local_upstream_path=local_upstream)
    if not ranked:
        raise typer.Exit(code=2)

    repo = BarnardCIRepo(barnard_ci)
    if not repo.exists():
        raise typer.BadParameter("Provided --barnard-ci path does not contain easyconfigs/.")
    discovered_clusters = repo.discover_clusters()
    if cluster not in discovered_clusters:
        raise typer.BadParameter(
            f"Cluster '{cluster}' not found in barnard-ci easyconfigs. Available: {discovered_clusters}"
        )
    discovered_releases = repo.discover_releases(cluster)
    if release not in discovered_releases:
        raise typer.BadParameter(
            f"Release '{release}' not found under cluster '{cluster}'. Available: {discovered_releases}"
        )

    target, diff_text, validation, operations = prepare_apply(
        candidate=ranked[0],
        barnard_repo=repo,
        cluster=cluster,
        release=release,
        policy=policy,
        apply=apply,
    )

    console.print(f"Target: {target}")
    console.print(f"Validation: {'PASS' if validation.ok else 'FAIL'}")
    for issue in validation.issues:
        console.print(f"[{issue.severity}] {issue.code}: {issue.message}")
    if diff_text:
        console.print(diff_text)

    mr = build_mr_artifacts(cluster, release, ranked[0].metadata)
    for key, value in mr.items():
        console.print(f"{key}: {value}")

    if report:
        from saia_eb_agent.models import WorkflowResult

        result = WorkflowResult(
            request=req.__dict__,
            candidates=ranked,
            selected=ranked[0],
            validation=validation,
            operations=operations,
            mr_artifacts=mr,
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


if __name__ == "__main__":
    app()
