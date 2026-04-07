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

    monkeypatch.setattr("saia_eb_agent.workflows.search.UpstreamEasyBuildRepo", _FakeRepo)
    req = RecommendRequest(software="Foo", toolchain_query="GCC14.2.0", target_kind="cpu")
    ranked = search_candidates(_Settings(), req)
    assert called["refresh"] == 1
    assert ranked


def test_search_system_prefers_newest_candidate(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    (upstream / "Foo-1.2.0-system.eb").write_text(
        "name = 'Foo'\nversion = '1.2.0'\ntoolchain = {'name': 'system'}",
        encoding="utf-8",
    )
    (upstream / "Foo-1.10.0-system.eb").write_text(
        "name = 'Foo'\nversion = '1.10.0'\ntoolchain = {'name': 'system'}",
        encoding="utf-8",
    )

    class _Settings:
        cache_dir = tmp_path / "cache"

    req = RecommendRequest(software="Foo", toolchain_query="system", target_kind="cpu")
    ranked = search_candidates(_Settings(), req, local_upstream_path=upstream)
    assert ranked
    assert ranked[0].metadata.filename == "Foo-1.10.0-system.eb"


def test_search_no_toolchain_prefers_newest_candidate(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    (upstream / "Anaconda3-2020.11.eb").write_text(
        "name = 'Anaconda3'\nversion = '2020.11'",
        encoding="utf-8",
    )
    (upstream / "Anaconda3-2022.10.eb").write_text(
        "name = 'Anaconda3'\nversion = '2022.10'",
        encoding="utf-8",
    )

    class _Settings:
        cache_dir = tmp_path / "cache"

    req = RecommendRequest(software="Anaconda3", target_kind="cpu")
    ranked = search_candidates(_Settings(), req, local_upstream_path=upstream)
    assert ranked
    assert ranked[0].metadata.filename == "Anaconda3-2022.10.eb"
