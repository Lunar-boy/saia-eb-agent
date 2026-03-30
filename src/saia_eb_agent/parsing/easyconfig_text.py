from __future__ import annotations

import re
from pathlib import Path

from saia_eb_agent.models import EasyconfigMetadata
from saia_eb_agent.parsing.filename import parse_easyconfig_filename


KEY_RE = re.compile(r"^(name|version|versionsuffix|dependencies|sources|easyblock)\s*=\s*(.+)$")
TOOLCHAIN_RE = re.compile(r"^toolchain\s*=\s*\{\s*'name'\s*:\s*'([^']+)'\s*,\s*'version'\s*:\s*'([^']+)'\s*\}")


def extract_metadata(path: Path) -> EasyconfigMetadata:
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
        if tc_match:
            metadata.toolchain_name = tc_match.group(1)
            metadata.toolchain_version = tc_match.group(2)

    if not metadata.software_name:
        metadata.parse_warnings.append("software name could not be extracted")
        metadata.parsed_ok = False

    return metadata


def _strip_quotes(value: str) -> str:
    return value.strip().strip('"').strip("'")
