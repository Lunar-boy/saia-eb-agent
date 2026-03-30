from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class ProviderSettings(BaseModel):
    saia_api_key: str | None = None
    saia_base_url: str = "https://api.saia.ai/v1"
    saia_model: str = "saia-default"


class AppSettings(BaseModel):
    cache_dir: Path = Field(default_factory=lambda: Path.home() / ".cache" / "saia-eb-agent")
    upstream_repo_url: str = "https://github.com/easybuilders/easybuild-easyconfigs.git"
    upstream_repo_dirname: str = "easybuild-easyconfigs"
    provider: ProviderSettings = Field(default_factory=ProviderSettings)


def load_settings(settings_path: Path | None = None) -> AppSettings:
    load_dotenv()
    data: dict = {}
    if settings_path and settings_path.exists():
        data = yaml.safe_load(settings_path.read_text()) or {}

    env_provider = {
        "saia_api_key": os.getenv("SAIA_API_KEY"),
        "saia_base_url": os.getenv("SAIA_BASE_URL"),
        "saia_model": os.getenv("SAIA_MODEL"),
    }
    provider_data = {**(data.get("provider", {}) if data else {}), **{k: v for k, v in env_provider.items() if v}}
    merged = {**data, "provider": provider_data}
    return AppSettings.model_validate(merged)
