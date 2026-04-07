from pathlib import Path

from saia_eb_agent.toolchains.resolve import ToolchainResolver


def test_toolchain_normalization_and_alias_expansion(tmp_path: Path):
    resolver = ToolchainResolver(cache_file=tmp_path / "aliases.json")
    res = resolver.resolve("GCC14.2.0")
    values = {a.value for a in res.aliases}
    assert "GCC-14.2.0" in values
    assert "GCCcore-14.2.0" in values
    assert "foss-2025a" in values
    assert "gfbf-2025a" in values


def test_toolchain_system_resolution_is_local_and_deterministic(tmp_path: Path):
    cache = tmp_path / "aliases.json"
    cache.write_text(
        '{"system": [{"value": "GCC-99", "source": "llm", "confidence": 0.1, "reason": "stale"}]}',
        encoding="utf-8",
    )

    resolver = ToolchainResolver(cache_file=cache)
    res = resolver.resolve("system")

    assert [a.value for a in res.aliases] == ["system"]
    assert res.aliases[0].source == "exact"
