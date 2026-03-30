from __future__ import annotations

import re

from saia_eb_agent.models import EasyconfigMetadata

GPU_PATTERNS = [
    r"cuda",
    r"cudnn",
    r"nccl",
    r"nvidia",
    r"nvhpc",
    r"gompic",
    r"nvompi",
]


def detect_gpu_intent(metadata: EasyconfigMetadata, text: str = "") -> tuple[bool, list[str]]:
    haystack = " ".join(
        filter(
            None,
            [
                metadata.filename,
                metadata.software_name,
                metadata.toolchain_name,
                metadata.dependencies_raw,
                metadata.sources_raw,
                text,
            ],
        )
    ).lower()

    hits: list[str] = []
    for pattern in GPU_PATTERNS:
        if re.search(pattern, haystack):
            hits.append(pattern)
    return bool(hits), hits
