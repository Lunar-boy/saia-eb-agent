from __future__ import annotations

from pathlib import Path

from saia_eb_agent.config import AppSettings
from saia_eb_agent.models import RecommendRequest
from saia_eb_agent.providers.saia import SAIAProvider
from saia_eb_agent.parsing.easyconfig_text import extract_metadata
from saia_eb_agent.ranking.engine import rank_candidates
from saia_eb_agent.repos.upstream_easybuild import UpstreamEasyBuildRepo
from saia_eb_agent.toolchains.resolve import ToolchainResolution, ToolchainResolver


def resolve_toolchain_query(settings: AppSettings, query: str | None) -> ToolchainResolution:
    provider = SAIAProvider(settings.provider)
    cache_file = settings.cache_dir / "toolchain_aliases.json"
    resolver = ToolchainResolver(cache_file=cache_file, provider=provider)
    return resolver.resolve(query)


def search_candidates(
    settings: AppSettings,
    request: RecommendRequest,
    local_upstream_path: Path | None = None,
) -> list:
    toolchain_resolution = resolve_toolchain_query(settings, request.toolchain_query)
    if local_upstream_path:
        paths = sorted(local_upstream_path.rglob("*.eb"))
        patch_resolver = _build_patch_resolver(local_upstream_path)
    else:
        upstream = UpstreamEasyBuildRepo(settings)
        upstream.clone_or_refresh()
        paths = upstream.scan_easyconfigs()
        patch_resolver = upstream.resolve_patch_path

    metas = []
    for p in paths:
        if request.software.lower() in p.name.lower():
            metas.append(extract_metadata(p, patch_resolver=patch_resolver))

    if not metas:
        for p in paths[:3000]:
            metas.append(extract_metadata(p, patch_resolver=patch_resolver))

    return rank_candidates(request, metas, toolchain_resolution=toolchain_resolution)


def _build_patch_resolver(root: Path):
    def _resolve(ec_path: Path, patch_filename: str) -> Path | None:
        local_candidates = [
            ec_path.parent / patch_filename,
            ec_path.parent / "patches" / patch_filename,
        ]
        for candidate in local_candidates:
            if candidate.exists():
                return candidate
        for found in root.rglob(patch_filename):
            if found.is_file():
                return found
        return None

    return _resolve
