from pathlib import Path

from saia_eb_agent.models import EasyconfigMetadata, RecommendRequest
from saia_eb_agent.ranking.engine import rank_candidates


def test_rank_prefers_exact_match():
    req = RecommendRequest(
        software="Foo",
        version="1.2.3",
        cluster="capella",
        release="r25.06",
        gpu=False,
    )
    c1 = EasyconfigMetadata(path=Path("/tmp/Foo-1.2.3-GCC.eb"), filename="Foo-1.2.3-GCC.eb", software_name="Foo", version="1.2.3")
    c2 = EasyconfigMetadata(path=Path("/tmp/Foo-1.2.2-GCC.eb"), filename="Foo-1.2.2-GCC.eb", software_name="Foo", version="1.2.2")
    ranked = rank_candidates(req, [c2, c1])
    assert ranked[0].metadata.filename == "Foo-1.2.3-GCC.eb"
