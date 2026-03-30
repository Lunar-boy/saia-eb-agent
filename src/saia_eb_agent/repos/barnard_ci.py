from __future__ import annotations

from pathlib import Path


class BarnardCIRepo:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.easyconfigs_dir = self.root / "easyconfigs"

    def exists(self) -> bool:
        return self.root.exists() and self.easyconfigs_dir.exists()

    def discover_clusters(self) -> list[str]:
        if not self.easyconfigs_dir.exists():
            return []
        return sorted([p.name for p in self.easyconfigs_dir.iterdir() if p.is_dir()])

    def discover_releases(self, cluster: str | None = None) -> list[str]:
        releases: set[str] = set()
        clusters = [cluster] if cluster else self.discover_clusters()
        for c in clusters:
            c_path = self.easyconfigs_dir / c
            if not c_path.exists():
                continue
            releases.update([p.name for p in c_path.iterdir() if p.is_dir()])
        return sorted(releases)

    def target_dir(self, cluster: str, release: str) -> Path:
        return self.easyconfigs_dir / cluster / release

    def scan_easyconfigs(self) -> list[Path]:
        if not self.easyconfigs_dir.exists():
            return []
        return sorted(self.easyconfigs_dir.rglob("*.eb"))
