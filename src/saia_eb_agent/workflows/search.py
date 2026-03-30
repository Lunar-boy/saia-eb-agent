from __future__ import annotations

from pathlib import Path

from saia_eb_agent.config import AppSettings
from saia_eb_agent.models import RecommendRequest
from saia_eb_agent.parsing.easyconfig_text import extract_metadata
from saia_eb_agent.ranking.engine import rank_candidates
from saia_eb_agent.repos.upstream_easybuild import UpstreamEasyBuildRepo


def search_candidates(
    settings: AppSettings,
    request: RecommendRequest,
    refresh_upstream: bool = False,
    local_upstream_path: Path | None = None,
) -> list:
    if local_upstream_path:
        paths = sorted(local_upstream_path.rglob("*.eb"))
    else:
        upstream = UpstreamEasyBuildRepo(settings)
        if refresh_upstream or not upstream.repo_dir.exists():
            upstream.clone_or_refresh()
        paths = upstream.scan_easyconfigs()

    metas = []
    for p in paths:
        if request.software.lower() in p.name.lower():
            metas.append(extract_metadata(p))

    if not metas:
        for p in paths[:3000]:
            metas.append(extract_metadata(p))

    return rank_candidates(request, metas)
