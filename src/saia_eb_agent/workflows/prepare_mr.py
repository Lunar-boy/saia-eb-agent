from __future__ import annotations

from saia_eb_agent.models import EasyconfigMetadata


def build_mr_artifacts(cluster: str, release: str, metadata: EasyconfigMetadata) -> dict[str, str]:
    sw = metadata.software_name or "software"
    ver = metadata.version or "unknown"
    tc = "-".join(filter(None, [metadata.toolchain_name, metadata.toolchain_version])) or "toolchain-unknown"
    branch = f"easyconfig/{cluster}/{release}/{sw.lower()}-{ver}".replace(" ", "-")

    return {
        "branch_name": branch,
        "issue_title": f"Add {sw} {ver} easyconfig for {cluster}/{release}",
        "commit_message": f"easyconfigs: add {sw}-{ver} for {cluster}/{release} ({tc})",
        "mr_title": f"[{cluster}/{release}] Add {sw} {ver} easyconfig",
        "mr_description": (
            "Summary:\n"
            f"- Adds {metadata.filename} to easyconfigs/{cluster}/{release}/\n"
            "\nChecklist:\n"
            "- [ ] Local static validation reviewed\n"
            "- [ ] GPU/CPU placement policy validated\n"
            "- [ ] Draft MR opened first\n"
            "- [ ] HPC CI build passed\n"
        ),
    }
