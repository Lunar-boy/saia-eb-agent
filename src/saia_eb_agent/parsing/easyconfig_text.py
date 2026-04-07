from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Callable

from saia_eb_agent.models import EasyconfigMetadata, EasyconfigPatch
from saia_eb_agent.parsing.filename import parse_easyconfig_filename, parse_toolchain_identifier


KEY_RE = re.compile(r"^(name|version|versionsuffix|dependencies|sources|easyblock)\s*=\s*(.+)$")
TOOLCHAIN_RE = re.compile(
    r"""^toolchain\s*=\s*\{\s*["']name["']\s*:\s*["']([^"']+)["'](?:\s*,\s*["']version["']\s*:\s*["']([^"']+)["'])?\s*\}"""
)


def extract_metadata(
    path: Path,
    patch_resolver: Callable[[Path, str], Path | None] | None = None,
) -> EasyconfigMetadata:
    text = path.read_text(encoding="utf-8", errors="replace")
    filename_info = parse_easyconfig_filename(path.name)

    metadata = EasyconfigMetadata(
        path=path,
        filename=path.name,
        software_name=filename_info.software_name,
        version=filename_info.version,
    )

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key_match = KEY_RE.match(stripped)
        if key_match:
            key = key_match.group(1)
            value = key_match.group(2).strip()
            if key == "name":
                metadata.software_name = _strip_quotes(value)
            elif key == "version":
                metadata.version = _strip_quotes(value)
            elif key == "versionsuffix":
                metadata.versionsuffix = _strip_quotes(value)
            elif key == "dependencies":
                metadata.dependencies_raw = value
            elif key == "sources":
                metadata.sources_raw = value
            elif key == "easyblock":
                metadata.easyblock = _strip_quotes(value)
            continue

        tc_match = TOOLCHAIN_RE.match(stripped)
        if tc_match and not metadata.toolchain_name:
            metadata.toolchain_name = tc_match.group(1)
            metadata.toolchain_version = tc_match.group(2) or None

    tc_name, tc_version = _extract_toolchain(text)
    if tc_name:
        metadata.toolchain_name = tc_name
        metadata.toolchain_version = tc_version
    elif filename_info.toolchain:
        metadata.toolchain_name, metadata.toolchain_version = parse_toolchain_identifier(filename_info.toolchain)

    for declared_patch in _extract_patch_entries(text):
        filename = Path(declared_patch).name
        resolved = patch_resolver(path, filename) if patch_resolver else None
        metadata.patches.append(
            EasyconfigPatch(
                declared_as=declared_patch,
                filename=filename,
                resolved_path=resolved,
                exists=bool(resolved and resolved.exists()),
            )
        )

    if not metadata.software_name:
        metadata.parse_warnings.append("software name could not be extracted")
        metadata.parsed_ok = False

    return metadata


def _extract_patch_entries(text: str) -> list[str]:
    expr = _extract_assignment_expression(text, "patches")
    if not expr:
        return []

    try:
        parsed = ast.literal_eval(expr)
    except Exception:
        return []

    values: list[str] = []
    if isinstance(parsed, (list, tuple)):
        for item in parsed:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, (list, tuple)) and item and isinstance(item[0], str):
                values.append(item[0])
    return values


def _extract_toolchain(text: str) -> tuple[str | None, str | None]:
    expr = _extract_assignment_expression(text, "toolchain")
    if not expr:
        return None, None
    try:
        parsed = ast.literal_eval(expr)
    except Exception:
        return None, None

    if isinstance(parsed, dict):
        name = parsed.get("name")
        version = parsed.get("version")
        if isinstance(name, str):
            version_text = str(version) if version is not None else None
            return name, version_text
    if isinstance(parsed, str):
        return parse_toolchain_identifier(parsed)
    return None, None


def _extract_assignment_expression(text: str, variable: str) -> str | None:
    lines = text.splitlines()
    start_idx: int | None = None
    start_line = ""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.match(rf"^{re.escape(variable)}\s*=", stripped):
            start_idx = i
            start_line = stripped
            break

    if start_idx is None:
        return None

    expr = start_line.split("=", 1)[1].strip()
    if not expr:
        return None

    if _looks_complete_expr(expr):
        return expr

    chunks = [expr]
    for next_line in lines[start_idx + 1 :]:
        stripped = next_line.strip()
        if stripped.startswith("#"):
            continue
        chunks.append(stripped)
        joined = "\n".join(chunks)
        if _looks_complete_expr(joined):
            return joined
    return None


def _looks_complete_expr(expr: str) -> bool:
    opens = sum(expr.count(ch) for ch in "([")
    closes = sum(expr.count(ch) for ch in ")]")
    return opens == closes and opens > 0


def _strip_quotes(value: str) -> str:
    return value.strip().strip('"').strip("'")
