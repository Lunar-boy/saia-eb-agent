from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class FilenameInfo:
    software_name: str | None
    version: str | None
    toolchain: str | None


def parse_easyconfig_filename(filename: str) -> FilenameInfo:
    if not filename.endswith(".eb"):
        return FilenameInfo(None, None, None)
    stem = filename[:-3]
    parts = stem.split("-")
    version_idx = next((i for i, p in enumerate(parts) if p and p[0].isdigit()), None)
    if version_idx is None or version_idx == 0:
        return FilenameInfo(None, None, None)

    software_name = "-".join(parts[:version_idx])
    version = parts[version_idx]
    toolchain = "-".join(parts[version_idx + 1 :]) or None
    return FilenameInfo(software_name, version, toolchain)


def parse_toolchain_identifier(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    compact = value.strip().replace("_", "-")
    if not compact:
        return None, None
    if compact.lower() == "system":
        return "system", None

    m = re.match(r"(?i)^(gcccore|gcc|foss|gfbf|system)-?([A-Za-z0-9.]+)?$", compact)
    if m:
        family = m.group(1).lower()
        version = m.group(2) or None
        canonical = {
            "gcc": "GCC",
            "gcccore": "GCCcore",
            "foss": "foss",
            "gfbf": "gfbf",
            "system": "system",
        }[family]
        return canonical, version

    if "-" in compact:
        name, version = compact.split("-", 1)
        return name, version or None
    return compact, None


def version_sort_key(value: str | None) -> tuple[int, tuple[int, ...], str]:
    if not value:
        return (0, tuple(), "")
    normalized = value.strip().lower()
    nums = tuple(int(part) for part in re.findall(r"\d+", normalized))
    return (1 if nums else 0, nums, normalized)
