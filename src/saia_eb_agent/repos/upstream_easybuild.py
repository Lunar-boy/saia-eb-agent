from __future__ import annotations

import subprocess
from pathlib import Path

from saia_eb_agent.config import AppSettings
from saia_eb_agent.utils.paths import ensure_dir


class UpstreamEasyBuildRepo:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.repo_dir = settings.cache_dir / settings.upstream_repo_dirname

    def clone_or_refresh(self) -> Path:
        ensure_dir(self.settings.cache_dir)
        if not self.repo_dir.exists():
            cmd = ["git", "clone", "--depth", "1", self.settings.upstream_repo_url, str(self.repo_dir)]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"Unable to clone upstream easybuild repo: {res.stderr.strip()}")
            return self.repo_dir

        res = subprocess.run(["git", "pull", "--ff-only"], cwd=self.repo_dir, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Unable to refresh upstream easybuild repo: {res.stderr.strip()}")
        return self.repo_dir

    def scan_easyconfigs(self) -> list[Path]:
        if not self.repo_dir.exists():
            raise RuntimeError("Upstream repo is not available.")
        return sorted(self.repo_dir.rglob("*.eb"))

    def resolve_patch_path(self, easyconfig_path: Path, patch_filename: str) -> Path | None:
        local_candidates = [
            easyconfig_path.parent / patch_filename,
            easyconfig_path.parent / "patches" / patch_filename,
        ]
        for candidate in local_candidates:
            if candidate.exists():
                return candidate

        for found in self.repo_dir.rglob(patch_filename):
            if found.is_file():
                return found
        return None
