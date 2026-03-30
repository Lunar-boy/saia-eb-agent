from saia_eb_agent.policy.rules import PlacementPolicy, cluster_allowed, dependency_search_clusters


def test_gpu_forbidden_on_romeo():
    policy = PlacementPolicy()
    allowed, reason = cluster_allowed("romeo", is_gpu=True, policy=policy)
    assert not allowed
    assert "cannot be placed" in reason


def test_alpha_dependency_domain_includes_romeo():
    policy = PlacementPolicy()
    assert dependency_search_clusters("alpha", policy) == ["alpha", "romeo"]
