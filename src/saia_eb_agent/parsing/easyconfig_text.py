from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from saia_eb_agent.models import EasyconfigMetadata, EasyconfigPatch
from saia_eb_agent.parsing.filename import parse_easyconfig_filename, parse_toolchain_identifier


KEY_RE = re.compile(r"^(name|version|versionsuffix|dependencies|sources|easyblock)\s*=\s*(.+)$")
TOOLCHAIN_RE = re.compile(
    r"""^toolchain\s*=\s*\{\s*["']name["']\s*:\s*["']([^"']+)["'](?:\s*,\s*["']version["']\s*:\s*["']([^"']+)["'])?\s*\}"""
)


@dataclass(frozen=True)
class DependencySpec:
    software_name: str
    version: str | None = None
    versionsuffix: str | None = None
    toolchain_name: str | None = None
    toolchain_version: str | None = None
    raw: str | None = None

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return (
            (self.software_name or "").strip().lower(),
            (self.version or "").strip().lower(),
            (self.versionsuffix or "").strip().lower(),
            (self.toolchain_name or "").strip().lower(),
            (self.toolchain_version or "").strip().lower(),
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


def extract_dependencies(path: Path) -> tuple[list[DependencySpec], list[str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return extract_dependencies_from_text(text)


def extract_dependencies_from_text(text: str) -> tuple[list[DependencySpec], list[str]]:
    expr = _extract_assignment_expression(text, "dependencies")
    if not expr:
        if re.search(r"(?m)^\s*dependencies\s*=", text):
            return [], ["dependencies assignment could not be fully parsed"]
        return [], []
    return _parse_dependencies_expression(expr)


def _parse_dependencies_expression(expr: str) -> tuple[list[DependencySpec], list[str]]:
    try:
        node = ast.parse(expr, mode="eval")
    except SyntaxError:
        return [], ["could not parse dependencies expression"]

    values = _coerce_node(node.body)
    if not isinstance(values, list):
        return [], ["dependencies expression was not a list/tuple"]

    specs: list[DependencySpec] = []
    warnings: list[str] = []
    for i, item in enumerate(values):
        spec, warning = _parse_dependency_item(item, raw=repr(item))
        if warning:
            warnings.append(f"dependency[{i}]: {warning}")
        if spec:
            specs.append(spec)
    return specs, warnings


def _parse_dependency_item(item: object, raw: str) -> tuple[DependencySpec | None, str | None]:
    if isinstance(item, dict):
        name = _as_text(item.get("name") or item.get("software_name"))
        if not name:
            return None, "missing dependency name"
        if _is_skip_dependency(name):
            return None, None
        tc_name, tc_version, tc_warning = _parse_toolchain_value(item.get("toolchain"))
        return (
            DependencySpec(
                software_name=name,
                version=_as_text(item.get("version")),
                versionsuffix=_as_text(item.get("versionsuffix")),
                toolchain_name=tc_name,
                toolchain_version=tc_version,
                raw=raw,
            ),
            tc_warning,
        )

    if isinstance(item, list):
        if not item:
            return None, "empty dependency entry"
        name = _as_text(item[0])
        if not name:
            return None, "missing dependency name"
        if _is_skip_dependency(name):
            return None, None

        version = _as_text(item[1]) if len(item) > 1 else None
        versionsuffix = _as_text(item[2]) if len(item) > 2 else None
        tc_name = None
        tc_version = None
        tc_warning = None
        if len(item) > 3:
            tc_name, tc_version, tc_warning = _parse_toolchain_value(item[3])
        return (
            DependencySpec(
                software_name=name,
                version=version,
                versionsuffix=versionsuffix,
                toolchain_name=tc_name,
                toolchain_version=tc_version,
                raw=raw,
            ),
            tc_warning,
        )

    return None, "unsupported dependency entry format"


def _parse_toolchain_value(value: object) -> tuple[str | None, str | None, str | None]:
    if value is None:
        return None, None, None
    if isinstance(value, _NameRef):
        if value.name.upper() == "SYSTEM":
            return "system", None, None
        return None, None, f"unsupported toolchain symbol '{value.name}'"
    if isinstance(value, str):
        return *parse_toolchain_identifier(value), None
    if isinstance(value, list):
        if not value:
            return None, None, None
        if len(value) >= 2:
            name = _as_text(value[0])
            version = _as_text(value[1])
            if name:
                return name, version, None
        if len(value) == 1:
            name = _as_text(value[0])
            if name:
                tc_name, tc_version = parse_toolchain_identifier(name)
                return tc_name, tc_version, None
    if isinstance(value, dict):
        name = _as_text(value.get("name"))
        version = _as_text(value.get("version"))
        if name:
            return name, version, None
    return None, None, "could not parse dependency toolchain info"


def _is_skip_dependency(name: str) -> bool:
    lowered = name.strip().lower()
    return lowered in {"system"}


def _as_text(value: object) -> str | None:
    if isinstance(value, _NameRef):
        return value.name
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return None


@dataclass(frozen=True)
class _NameRef:
    name: str


def _coerce_node(node: ast.AST) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return _NameRef(node.id)
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_coerce_node(elt) for elt in node.elts]
    if isinstance(node, ast.Dict):
        obj: dict[object, object] = {}
        for k, v in zip(node.keys, node.values):
            key = _coerce_node(k) if k is not None else None
            if isinstance(key, _NameRef):
                key = key.name
            obj[key] = _coerce_node(v)
        return obj
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _coerce_node(node.operand)
        if isinstance(inner, (int, float)):
            return -inner
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _coerce_node(node.left)
        right = _coerce_node(node.right)
        if isinstance(left, str) and isinstance(right, str):
            return left + right
    return _NameRef(f"<unsupported:{node.__class__.__name__}>")


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
