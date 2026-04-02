from saia_eb_agent.policy.rules import PlacementPolicy, cluster_allowed, dependency_search_clusters, expand_target_kind


def test_gpu_forbidden_on_romeo():
    policy = PlacementPolicy()
    allowed, reason = cluster_allowed("romeo", is_gpu=True, policy=policy)
    assert not allowed
    assert "cannot be placed" in reason


def test_alpha_dependency_domain_includes_romeo():
    policy = PlacementPolicy()
    assert dependency_search_clusters("alpha", policy) == ["alpha", "romeo"]


def test_target_kind_expansion():
    policy = PlacementPolicy()
    assert set(expand_target_kind("gpu", policy)) == {"alpha", "capella"}
    assert set(expand_target_kind("cpu", policy)) == {"romeo", "barnard", "julia", "capella"}
