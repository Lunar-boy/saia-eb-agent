from __future__ import annotations

import subprocess
from pathlib import Path


def run_git(args: list[str], cwd: Path) -> str:
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout.strip()


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()
