from __future__ import annotations

import difflib
import shutil
from dataclasses import dataclass
from pathlib import Path

from saia_eb_agent.models import Candidate, EasyconfigMetadata, RecommendRequest, ValidationIssue, ValidationResult
from saia_eb_agent.parsing.easyconfig_text import DependencySpec, extract_dependencies, extract_metadata
from saia_eb_agent.policy.rules import PlacementPolicy
from saia_eb_agent.ranking.engine import rank_candidates
from saia_eb_agent.repos.barnard_ci import BarnardCIRepo
from saia_eb_agent.toolchains.resolve import ToolchainResolver
from saia_eb_agent.validation.checks import validate_easyconfig

NON_OVERRIDABLE_ERROR_CODES = {
    "path.invalid",
    "policy.cluster_forbidden",
}


@dataclass(frozen=True)
class ValidationBlockingSummary:
    has_errors: bool
    has_non_overridable_errors: bool
    non_overridable_error_codes: set[str]


@dataclass
class _PlannedEasyconfig:
    path: Path
    filename: str
    metadata: EasyconfigMetadata
    source: str


def prepare_apply(
    candidate: Candidate,
    barnard_repo: BarnardCIRepo,
    cluster: str,
    release: str,
    policy: PlacementPolicy,
    apply: bool = False,
    force: bool = False,
    rename_to: str | None = None,
    text_replacements: list[tuple[str, str]] | None = None,
) -> tuple[Path, str, ValidationResult, list[str]]:
    targets, _diffs, validations, operations = prepare_apply_multi(
        candidate=candidate,
        barnard_repo=barnard_repo,
        clusters=[cluster],
        release=release,
        policy=policy,
        apply=apply,
        force=force,
        rename_to=rename_to,
        text_replacements=text_replacements,
    )
    target = targets[cluster]
    validation = validations[cluster]
    return target, _diffs[cluster], validation, operations


def prepare_apply_multi(
    candidate: Candidate,
    barnard_repo: BarnardCIRepo,
    clusters: list[str],
    release: str,
    policy: PlacementPolicy,
    apply: bool = False,
    force: bool = False,
    rename_to: str | None = None,
    text_replacements: list[tuple[str, str]] | None = None,
) -> tuple[dict[str, Path], dict[str, str], dict[str, ValidationResult], list[str]]:
    if not barnard_repo.exists():
        raise RuntimeError("barnard-ci checkout missing or does not contain easyconfigs/")

    targets: dict[str, Path] = {}
    diffs: dict[str, str] = {}
    operations: list[str] = []

    filename = rename_to or candidate.metadata.filename

    source_text = candidate.metadata.path.read_text(encoding="utf-8", errors="replace")
    new_text = source_text
    for old, new in (text_replacements or []):
        new_text = new_text.replace(old, new)

    main_md = extract_metadata(candidate.metadata.path)
    existing = barnard_repo.scan_easyconfigs()

    cluster_existing = _scan_existing_target_metadata(barnard_repo, clusters, release)
    dependency_plan, dependency_notes = _resolve_missing_dependency_closure(
        root_metadata=main_md,
        root_source_path=candidate.metadata.path,
        cluster_existing=cluster_existing,
        fallback_toolchain_name=main_md.toolchain_name,
        fallback_toolchain_version=main_md.toolchain_version,
    )
    operations.extend(dependency_notes)

    validations: dict[str, ValidationResult] = {}
    dependency_targets: dict[str, list[Path]] = {cluster: [] for cluster in clusters}

    for cluster in clusters:
        target_dir = barnard_repo.target_dir(cluster, release)
        target = target_dir / filename
        validation = validate_easyconfig(
            metadata=main_md,
            file_text=new_text,
            target_path=target,
            target_cluster=cluster,
            target_release=release,
            policy=policy,
            existing_paths=existing,
        )

        dep_results = [validation]
        for dep in dependency_plan:
            dep_target = target_dir / dep.filename
            dependency_targets[cluster].append(dep_target)
            dep_text = dep.path.read_text(encoding="utf-8", errors="replace")
            dep_results.append(
                validate_easyconfig(
                    metadata=dep.metadata,
                    file_text=dep_text,
                    target_path=dep_target,
                    target_cluster=cluster,
                    target_release=release,
                    policy=policy,
                    existing_paths=existing,
                )
            )

        validations[cluster] = _merge_validations(dep_results)
        targets[cluster] = target
        operations.append(f"copy {candidate.metadata.path} -> {target}")
        for dep_target, dep in zip(dependency_targets[cluster], dependency_plan):
            operations.append(f"copy {dep.path} -> {dep_target}")

        diffs[cluster] = "\n".join(
            difflib.unified_diff(
                source_text.splitlines(),
                new_text.splitlines(),
                fromfile=f"a/{candidate.metadata.filename}",
                tofile=f"b/{filename}",
                lineterm="",
            )
        )

    if apply and _has_blocking_errors(validations, force=force):
        raise RuntimeError("Refusing to apply changes because blocking validation failed on at least one target cluster.")

    if apply:
        for cluster, target in targets.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            if text_replacements:
                target.write_text(new_text, encoding="utf-8")
            else:
                shutil.copy2(candidate.metadata.path, target)

            for dep, dep_target in zip(dependency_plan, dependency_targets[cluster]):
                dep_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dep.path, dep_target)
            operations.append(f"write applied for cluster {cluster} (--apply enabled)")
    else:
        operations.append("dry-run only (pass --apply to write changes)")

    return targets, diffs, validations, operations


def _has_blocking_errors(validations: dict[str, ValidationResult], force: bool) -> bool:
    summary = summarize_validation_blocking(validations)
    if not summary.has_errors:
        return False
    if not force:
        return True
    # Forced apply may override content-level errors like absolute source paths,
    # but never placement/path policy errors.
    return summary.has_non_overridable_errors


def summarize_validation_blocking(validations: dict[str, ValidationResult]) -> ValidationBlockingSummary:
    has_errors = False
    non_overridable_error_codes: set[str] = set()
    for result in validations.values():
        for issue in result.issues:
            if issue.severity != "error":
                continue
            has_errors = True
            if issue.code in NON_OVERRIDABLE_ERROR_CODES:
                non_overridable_error_codes.add(issue.code)
    return ValidationBlockingSummary(
        has_errors=has_errors,
        has_non_overridable_errors=bool(non_overridable_error_codes),
        non_overridable_error_codes=non_overridable_error_codes,
    )


def _merge_validations(results: list[ValidationResult]) -> ValidationResult:
    issues: list[ValidationIssue] = []
    for result in results:
        issues.extend(result.issues)
    return ValidationResult(ok=all(r.ok for r in results), issues=issues)


def _scan_existing_target_metadata(
    barnard_repo: BarnardCIRepo,
    clusters: list[str],
    release: str,
) -> dict[str, list[EasyconfigMetadata]]:
    out: dict[str, list[EasyconfigMetadata]] = {}
    for cluster in clusters:
        target_dir = barnard_repo.target_dir(cluster, release)
        if not target_dir.exists():
            out[cluster] = []
            continue
        out[cluster] = [extract_metadata(path) for path in sorted(target_dir.rglob("*.eb"))]
    return out


def _resolve_missing_dependency_closure(
    root_metadata: EasyconfigMetadata,
    root_source_path: Path,
    cluster_existing: dict[str, list[EasyconfigMetadata]],
    fallback_toolchain_name: str | None,
    fallback_toolchain_version: str | None,
) -> tuple[list[_PlannedEasyconfig], list[str]]:
    notes: list[str] = []

    dependency_pool = _load_upstream_metadata_pool(root_source_path)
    if not dependency_pool:
        return [], notes

    planned: list[_PlannedEasyconfig] = []
    planned_keys: set[tuple[str, str, str, str, str]] = set()
    visited: set[tuple[str, str, str, str, str]] = set()
    root_key = _metadata_key(root_metadata)

    pending: list[tuple[DependencySpec, str]] = []
    root_specs, root_warnings = extract_dependencies(root_source_path)
    for warning in root_warnings:
        notes.append(f"dependency parse warning in {root_source_path.name}: {warning}")
    pending.extend((spec, root_source_path.name) for spec in root_specs)

    while pending:
        dep, parent_name = pending.pop(0)
        if dep.key in visited:
            continue
        visited.add(dep.key)

        if _dependency_satisfied_in_targets(dep, cluster_existing):
            notes.append(f"dependency already present for all targets: {_format_dep(dep)}")
            continue

        selected = _search_best_dependency_candidate(
            dep,
            dependency_pool,
            fallback_toolchain_name=fallback_toolchain_name,
            fallback_toolchain_version=fallback_toolchain_version,
        )
        if not selected:
            notes.append(f"dependency unresolved from {parent_name}: {_format_dep(dep)}")
            continue

        selected_key = _metadata_key(selected.metadata)
        if selected_key == root_key:
            notes.append(f"dependency resolved to root easyconfig and skipped: {selected.metadata.filename}")
        elif selected_key not in planned_keys:
            planned_keys.add(selected_key)
            planned.append(
                _PlannedEasyconfig(
                    path=selected.metadata.path,
                    filename=selected.metadata.filename,
                    metadata=selected.metadata,
                    source=parent_name,
                )
            )
            notes.append(f"dependency selected from {parent_name}: {selected.metadata.filename}")

        child_specs, child_warnings = extract_dependencies(selected.metadata.path)
        for warning in child_warnings:
            notes.append(f"dependency parse warning in {selected.metadata.filename}: {warning}")
        pending.extend((spec, selected.metadata.filename) for spec in child_specs)

    return planned, notes


def _dependency_satisfied_in_targets(dep: DependencySpec, cluster_existing: dict[str, list[EasyconfigMetadata]]) -> bool:
    for metas in cluster_existing.values():
        if not any(_metadata_matches_dependency(md, dep) for md in metas):
            return False
    return True


def _metadata_matches_dependency(md: EasyconfigMetadata, dep: DependencySpec) -> bool:
    if (md.software_name or "").strip().lower() != dep.software_name.strip().lower():
        return False
    if dep.version and (md.version or "").strip().lower() != dep.version.strip().lower():
        return False
    if dep.versionsuffix and (md.versionsuffix or "").strip().lower() != dep.versionsuffix.strip().lower():
        return False
    if dep.toolchain_name and (md.toolchain_name or "").strip().lower() != dep.toolchain_name.strip().lower():
        return False
    if dep.toolchain_version and (md.toolchain_version or "").strip().lower() != dep.toolchain_version.strip().lower():
        return False
    return True


def _search_best_dependency_candidate(
    dep: DependencySpec,
    metadata_pool: list[EasyconfigMetadata],
    fallback_toolchain_name: str | None,
    fallback_toolchain_version: str | None,
) -> Candidate | None:
    requested_tc = None
    if dep.toolchain_name:
        requested_tc = dep.toolchain_name
        if dep.toolchain_version:
            requested_tc = f"{dep.toolchain_name}-{dep.toolchain_version}"
    elif fallback_toolchain_name:
        requested_tc = fallback_toolchain_name
        if fallback_toolchain_version:
            requested_tc = f"{fallback_toolchain_name}-{fallback_toolchain_version}"

    request = RecommendRequest(
        software=dep.software_name,
        toolchain_query=requested_tc,
        target_kind="cpu",
    )
    toolchain_resolution = ToolchainResolver(cache_file=None).resolve(requested_tc)
    ranked = rank_candidates(request, metadata_pool, toolchain_resolution=toolchain_resolution)
    if not ranked:
        return None

    exact_name = [c for c in ranked if (c.metadata.software_name or "").strip().lower() == dep.software_name.strip().lower()]
    pool = exact_name or ranked

    def _pref_key(c: Candidate) -> tuple[int, int, int, float, str]:
        version_ok = int(not dep.version or (c.metadata.version or "").strip().lower() == dep.version.strip().lower())
        suffix_ok = int(
            not dep.versionsuffix
            or (c.metadata.versionsuffix or "").strip().lower() == dep.versionsuffix.strip().lower()
        )
        tc_ok = int(
            not dep.toolchain_name
            or (
                (c.metadata.toolchain_name or "").strip().lower() == dep.toolchain_name.strip().lower()
                and (
                    not dep.toolchain_version
                    or (c.metadata.toolchain_version or "").strip().lower() == dep.toolchain_version.strip().lower()
                )
            )
        )
        return (version_ok, suffix_ok, tc_ok, c.score, c.metadata.filename.lower())

    pool_sorted = sorted(pool, key=_pref_key, reverse=True)
    return pool_sorted[0] if pool_sorted else None


def _load_upstream_metadata_pool(root_source_path: Path) -> list[EasyconfigMetadata]:
    root = _discover_scan_root(root_source_path)
    paths = sorted(root.rglob("*.eb"))
    return [extract_metadata(path) for path in paths]


def _discover_scan_root(path: Path) -> Path:
    for parent in [path.parent, *path.parents]:
        if (parent / ".git").exists():
            return parent
    return path.parent


def _metadata_key(md: EasyconfigMetadata) -> tuple[str, str, str, str, str]:
    return (
        (md.software_name or "").strip().lower(),
        (md.version or "").strip().lower(),
        (md.versionsuffix or "").strip().lower(),
        (md.toolchain_name or "").strip().lower(),
        (md.toolchain_version or "").strip().lower(),
    )


def _format_dep(dep: DependencySpec) -> str:
    bits = [dep.software_name]
    if dep.version:
        bits.append(dep.version)
    if dep.versionsuffix:
        bits.append(dep.versionsuffix)
    if dep.toolchain_name:
        if dep.toolchain_version:
            bits.append(f"{dep.toolchain_name}-{dep.toolchain_version}")
        else:
            bits.append(dep.toolchain_name)
    return " ".join(bits)
