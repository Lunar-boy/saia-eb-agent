from __future__ import annotations

import difflib
import shutil
from pathlib import Path

from saia_eb_agent.models import Candidate, ValidationResult
from saia_eb_agent.parsing.easyconfig_text import extract_metadata
from saia_eb_agent.policy.rules import PlacementPolicy
from saia_eb_agent.repos.barnard_ci import BarnardCIRepo
from saia_eb_agent.validation.checks import validate_easyconfig


def prepare_apply(
    candidate: Candidate,
    barnard_repo: BarnardCIRepo,
    cluster: str,
    release: str,
    policy: PlacementPolicy,
    apply: bool = False,
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
    rename_to: str | None = None,
    text_replacements: list[tuple[str, str]] | None = None,
) -> tuple[dict[str, Path], dict[str, str], dict[str, ValidationResult], list[str]]:
    if not barnard_repo.exists():
        raise RuntimeError("barnard-ci checkout missing or does not contain easyconfigs/")

    targets: dict[str, Path] = {}
    diffs: dict[str, str] = {}
    validations: dict[str, ValidationResult] = {}
    operations: list[str] = []

    filename = rename_to or candidate.metadata.filename

    source_text = candidate.metadata.path.read_text(encoding="utf-8", errors="replace")
    new_text = source_text
    for old, new in (text_replacements or []):
        new_text = new_text.replace(old, new)

    md = extract_metadata(candidate.metadata.path)
    existing = barnard_repo.scan_easyconfigs()
    for cluster in clusters:
        target_dir = barnard_repo.target_dir(cluster, release)
        target = target_dir / filename
        validation = validate_easyconfig(
            metadata=md,
            file_text=new_text,
            target_path=target,
            target_cluster=cluster,
            target_release=release,
            policy=policy,
            existing_paths=existing,
        )
        targets[cluster] = target
        validations[cluster] = validation
        operations.append(f"copy {candidate.metadata.path} -> {target}")
        diffs[cluster] = "\n".join(
            difflib.unified_diff(
                source_text.splitlines(),
                new_text.splitlines(),
                fromfile=f"a/{candidate.metadata.filename}",
                tofile=f"b/{filename}",
                lineterm="",
            )
        )

    if apply and any(not v.ok for v in validations.values()):
        raise RuntimeError("Refusing to apply changes because static validation failed on at least one target cluster.")

    if apply:
        for cluster, target in targets.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            if text_replacements:
                target.write_text(new_text, encoding="utf-8")
            else:
                shutil.copy2(candidate.metadata.path, target)
            operations.append(f"write applied for cluster {cluster} (--apply enabled)")
    else:
        operations.append("dry-run only (pass --apply to write changes)")

    return targets, diffs, validations, operations
