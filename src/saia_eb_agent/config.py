from __future__ import annotations

from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    cache_dir: Path = Field(default_factory=lambda: Path.home() / ".cache" / "saia-eb-agent")
    upstream_repo_url: str = "https://github.com/easybuilders/easybuild-easyconfigs.git"
    upstream_repo_dirname: str = "easybuild-easyconfigs"


def load_settings(settings_path: Path | None = None) -> AppSettings:
    load_dotenv()
    data: dict = {}
    if settings_path and settings_path.exists():
        data = yaml.safe_load(settings_path.read_text()) or {}
    return AppSettings.model_validate(data)
