from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


TargetKind = Literal["cpu", "gpu"]


@dataclass
class EasyconfigPatch:
    declared_as: str
    filename: str
    resolved_path: Path | None = None
    exists: bool = False


@dataclass
class EasyconfigMetadata:
    path: Path
    filename: str
    software_name: str | None = None
    version: str | None = None
    versionsuffix: str | None = None
    toolchain_name: str | None = None
    toolchain_version: str | None = None
    dependencies_raw: str | None = None
    sources_raw: str | None = None
    easyblock: str | None = None
    patches: list[EasyconfigPatch] = field(default_factory=list)
    parsed_ok: bool = True
    parse_warnings: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    metadata: EasyconfigMetadata
    score: float
    reasons: list[str]
    likely_edits: list[str]
    risk_notes: list[str]
    toolchain_match_reason: str = ""


@dataclass
class ValidationIssue:
    severity: str
    code: str
    message: str


@dataclass
class ValidationResult:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)


@dataclass
class RecommendRequest:
    software: str
    toolchain_query: str | None
    target_kind: TargetKind
    release: str | None = None
    keywords: list[str] = field(default_factory=list)


@dataclass
class WorkflowResult:
    request: dict[str, Any]
    candidates: list[Candidate]
    selected: Candidate | None
    validation: ValidationResult | None
    operations: list[str]
    mr_artifacts: dict[str, str]
    cluster_validations: dict[str, ValidationResult] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
