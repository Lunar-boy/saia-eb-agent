from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
    parsed_ok: bool = True
    parse_warnings: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    metadata: EasyconfigMetadata
    score: float
    reasons: list[str]
    likely_edits: list[str]
    risk_notes: list[str]


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
    version: str | None
    cluster: str
    release: str
    gpu: bool
    preferred_toolchain: str | None = None
    keywords: list[str] = field(default_factory=list)


@dataclass
class WorkflowResult:
    request: dict[str, Any]
    candidates: list[Candidate]
    selected: Candidate | None
    validation: ValidationResult | None
    operations: list[str]
    mr_artifacts: dict[str, str]
    notes: list[str] = field(default_factory=list)
