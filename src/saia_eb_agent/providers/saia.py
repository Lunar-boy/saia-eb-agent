from __future__ import annotations

import httpx

from saia_eb_agent.config import ProviderSettings
from saia_eb_agent.providers.base import LLMProvider


class SAIAProvider(LLMProvider):
    def __init__(self, settings: ProviderSettings) -> None:
        self._settings = settings

    def available(self) -> bool:
        return bool(self._settings.saia_api_key)

    def generate_text(self, prompt: str) -> str:
        if not self.available():
            raise RuntimeError("SAIA API key not configured. Set SAIA_API_KEY or use rule-only mode.")

        headers = {
            "Authorization": f"Bearer {self._settings.saia_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._settings.saia_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{self._settings.saia_base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Unexpected SAIA response format: {data}") from exc
