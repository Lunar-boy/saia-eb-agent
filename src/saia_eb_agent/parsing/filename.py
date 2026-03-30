from __future__ import annotations

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
