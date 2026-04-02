from pathlib import Path

from saia_eb_agent.models import EasyconfigMetadata, RecommendRequest
from saia_eb_agent.ranking.engine import rank_candidates
from saia_eb_agent.toolchains.resolve import ToolchainAlias, ToolchainResolution


def test_rank_prefers_toolchain_family_match():
    req = RecommendRequest(
        software="Foo",
        toolchain_query="GCC14.2.0",
        target_kind="cpu",
        release="r25.06",
    )
    c1 = EasyconfigMetadata(
        path=Path("/tmp/Foo-1.2.3-GCC-14.2.0.eb"),
        filename="Foo-1.2.3-GCC-14.2.0.eb",
        software_name="Foo",
        version="1.2.3",
        toolchain_name="GCC",
        toolchain_version="14.2.0",
    )
    c2 = EasyconfigMetadata(
        path=Path("/tmp/Foo-1.2.3-foss-2024a.eb"),
        filename="Foo-1.2.3-foss-2024a.eb",
        software_name="Foo",
        version="1.2.3",
        toolchain_name="foss",
        toolchain_version="2024a",
    )
    resolution = ToolchainResolution(
        query="GCC14.2.0",
        normalized="GCC-14.2.0",
        aliases=[
            ToolchainAlias("GCC-14.2.0", "exact", 1.0, "normalized user query"),
            ToolchainAlias("foss-2025a", "heuristic", 0.75, "mapped from GCC 14.2.0"),
        ],
    )
    ranked = rank_candidates(req, [c2, c1], toolchain_resolution=resolution)
    assert ranked[0].metadata.filename == "Foo-1.2.3-GCC-14.2.0.eb"
