from __future__ import annotations

import re
from pathlib import Path

from saia_eb_agent.models import EasyconfigMetadata, ValidationIssue, ValidationResult
from saia_eb_agent.parsing.filename import parse_easyconfig_filename
from saia_eb_agent.policy.detection import detect_gpu_intent
from saia_eb_agent.policy.rules import PlacementPolicy, cluster_allowed

SUSPICIOUS_PATTERNS = [r"cuda", r"nvhpc", r"gompic", r"nvompi", r"/software/util/sources", r"/site/"]


def validate_easyconfig(
    metadata: EasyconfigMetadata,
    file_text: str,
    target_path: Path,
    target_cluster: str,
    target_release: str,
    policy: PlacementPolicy,
    existing_paths: list[Path] | None = None,
) -> ValidationResult:
    issues: list[ValidationIssue] = []

    expected_dir = Path("easyconfigs") / target_cluster / target_release
    if expected_dir.as_posix() not in target_path.as_posix():
        issues.append(
            ValidationIssue("error", "path.invalid", f"target path must be under {expected_dir.as_posix()}/")
        )

    if not target_path.parent.exists():
        issues.append(ValidationIssue("error", "release.missing", "target release directory does not exist"))

    fn = parse_easyconfig_filename(target_path.name)
    if metadata.software_name and fn.software_name and metadata.software_name != fn.software_name:
        issues.append(ValidationIssue("warning", "filename.name_mismatch", "filename software name differs from content"))
    if metadata.version and fn.version and metadata.version != fn.version:
        issues.append(ValidationIssue("warning", "filename.version_mismatch", "filename version differs from content"))

    is_gpu, hits = detect_gpu_intent(metadata, file_text)
    allowed, reason = cluster_allowed(target_cluster, is_gpu, policy)
    if not allowed:
        issues.append(ValidationIssue("error", "policy.cluster_forbidden", reason))

    if "/software/util/sources" in file_text:
        issues.append(
            ValidationIssue("error", "sources.absolute_path", "absolute /software/util/sources path detected")
        )

    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, file_text, flags=re.IGNORECASE):
            issues.append(ValidationIssue("warning", "pattern.suspicious", f"suspicious pattern detected: {pattern}"))

    if existing_paths:
        same_name = [p for p in existing_paths if p.name == target_path.name and p != target_path]
        if same_name:
            issues.append(ValidationIssue("warning", "duplicate.filename", "same filename exists elsewhere in repository"))
        near_dup = [p for p in existing_paths if metadata.software_name and metadata.software_name in p.name and p != target_path]
        if near_dup:
            issues.append(
                ValidationIssue(
                    "info",
                    "duplicate.near",
                    f"found {len(near_dup)} near-duplicate(s) with same software stem",
                )
            )

    has_error = any(i.severity == "error" for i in issues)
    return ValidationResult(ok=not has_error, issues=issues)
