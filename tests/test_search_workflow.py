from pathlib import Path

from saia_eb_agent.models import RecommendRequest
from saia_eb_agent.workflows.search import search_candidates


def test_search_auto_refresh_calls_upstream_clone(monkeypatch, tmp_path: Path):
    called = {"refresh": 0}

    class _FakeRepo:
        def __init__(self, _settings):
            self.repo_dir = tmp_path / "upstream"
            self.repo_dir.mkdir()
            (self.repo_dir / "Foo-1.2.3-GCC-14.2.0.eb").write_text(
                "name = 'Foo'\nversion = '1.2.3'\ntoolchain = {'name': 'GCC', 'version': '14.2.0'}",
                encoding="utf-8",
            )

        def clone_or_refresh(self):
            called["refresh"] += 1
            return self.repo_dir

        def scan_easyconfigs(self):
            return sorted(self.repo_dir.rglob("*.eb"))

        def resolve_patch_path(self, _ec_path, _patch):
            return None

    class _Settings:
        cache_dir = tmp_path / "cache"

        class provider:
            saia_api_key = None
            saia_base_url = "https://example.com"
            saia_model = "none"

    monkeypatch.setattr("saia_eb_agent.workflows.search.UpstreamEasyBuildRepo", _FakeRepo)
    req = RecommendRequest(software="Foo", toolchain_query="GCC14.2.0", target_kind="cpu")
    ranked = search_candidates(_Settings(), req)
    assert called["refresh"] == 1
    assert ranked
