from __future__ import annotations

from saia_eb_agent.models import EasyconfigMetadata


def build_mr_artifacts(cluster: str, release: str, metadata: EasyconfigMetadata) -> dict[str, str]:
    return build_mr_artifacts_for_clusters([cluster], release, metadata)


def build_mr_artifacts_for_clusters(clusters: list[str], release: str, metadata: EasyconfigMetadata) -> dict[str, str]:
    sw = metadata.software_name or "software"
    ver = metadata.version or "unknown"
    tc = "-".join(filter(None, [metadata.toolchain_name, metadata.toolchain_version])) or "toolchain-unknown"
    cluster_label = "+".join(sorted(clusters))
    branch = f"easyconfig/{cluster_label}/{release}/{sw.lower()}-{ver}".replace(" ", "-")
    install_lines = "\n".join([f"- Adds {metadata.filename} to easyconfigs/{cluster}/{release}/" for cluster in sorted(clusters)])

    return {
        "branch_name": branch,
        "issue_title": f"Add {sw} {ver} easyconfig for {cluster_label}/{release}",
        "commit_message": f"easyconfigs: add {sw}-{ver} for {cluster_label}/{release} ({tc})",
        "mr_title": f"[{cluster_label}/{release}] Add {sw} {ver} easyconfig",
        "mr_description": (
            "Summary:\n"
            f"{install_lines}\n"
            "\nChecklist:\n"
            "- [ ] Local static validation reviewed\n"
            "- [ ] GPU/CPU placement policy validated\n"
            "- [ ] Draft MR opened first\n"
            "- [ ] HPC CI build passed\n"
        ),
    }
