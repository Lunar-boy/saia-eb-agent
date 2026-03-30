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
    if not barnard_repo.exists():
        raise RuntimeError("barnard-ci checkout missing or does not contain easyconfigs/")

    target_dir = barnard_repo.target_dir(cluster, release)
    filename = rename_to or candidate.metadata.filename
    target = target_dir / filename

    source_text = candidate.metadata.path.read_text(encoding="utf-8", errors="replace")
    new_text = source_text
    for old, new in (text_replacements or []):
        new_text = new_text.replace(old, new)

    md = extract_metadata(candidate.metadata.path)
    validation = validate_easyconfig(
        metadata=md,
        file_text=new_text,
        target_path=target,
        target_cluster=cluster,
        target_release=release,
        policy=policy,
        existing_paths=barnard_repo.scan_easyconfigs(),
    )

    operations = [f"copy {candidate.metadata.path} -> {target}"]

    if apply:
        if not validation.ok:
            raise RuntimeError("Refusing to apply changes because static validation failed. Run without --apply to inspect issues.")
        target_dir.mkdir(parents=True, exist_ok=True)
        if text_replacements:
            target.write_text(new_text, encoding="utf-8")
        else:
            shutil.copy2(candidate.metadata.path, target)
        operations.append("write applied (--apply enabled)")
    else:
        operations.append("dry-run only (pass --apply to write changes)")

    diff_text = "\n".join(
        difflib.unified_diff(
            source_text.splitlines(),
            new_text.splitlines(),
            fromfile=f"a/{candidate.metadata.filename}",
            tofile=f"b/{filename}",
            lineterm="",
        )
    )

    return target, diff_text, validation, operations
