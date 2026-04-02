from pathlib import Path

from saia_eb_agent.providers.base import LLMProvider
from saia_eb_agent.toolchains.resolve import ToolchainResolver


class _FakeProvider(LLMProvider):
    def __init__(self, text: str, available: bool = True, fail: bool = False) -> None:
        self.text = text
        self._available = available
        self._fail = fail

    def available(self) -> bool:
        return self._available

    def generate_text(self, prompt: str) -> str:
        if self._fail:
            raise RuntimeError("boom")
        return self.text


def test_toolchain_normalization_and_alias_expansion(tmp_path: Path):
    resolver = ToolchainResolver(cache_file=tmp_path / "aliases.json", provider=None)
    res = resolver.resolve("GCC14.2.0", allow_llm=False)
    values = {a.value for a in res.aliases}
    assert "GCC-14.2.0" in values
    assert "GCCcore-14.2.0" in values
    assert "foss-2025a" in values
    assert "gfbf-2025a" in values


def test_toolchain_llm_fallback_is_optional_and_cached(tmp_path: Path):
    cache = tmp_path / "aliases.json"
    provider = _FakeProvider("foss-2025a, gfbf-2025a")
    resolver = ToolchainResolver(cache_file=cache, provider=provider)

    res = resolver.resolve("mystery-tc", allow_llm=True)
    llm_aliases = [a for a in res.aliases if a.source == "llm"]
    assert llm_aliases

    resolver2 = ToolchainResolver(cache_file=cache, provider=_FakeProvider("", available=False))
    cached = resolver2.resolve("mystery-tc", allow_llm=True)
    assert any(a.source == "llm" for a in cached.aliases)


def test_toolchain_llm_failure_is_safe(tmp_path: Path):
    resolver = ToolchainResolver(cache_file=tmp_path / "aliases.json", provider=_FakeProvider("", fail=True))
    res = resolver.resolve("GCC14.2.0", allow_llm=True)
    assert any(a.source in {"exact", "normalized", "heuristic"} for a in res.aliases)
