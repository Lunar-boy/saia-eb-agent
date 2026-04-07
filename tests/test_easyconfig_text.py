from pathlib import Path

from saia_eb_agent.parsing.easyconfig_text import extract_metadata


def test_extract_metadata(tmp_path: Path):
    p = tmp_path / "Foo-1.2.3-GCC-13.2.0.eb"
    patch_path = tmp_path / "foo-fix.patch"
    patch_path.write_text("diff --git a b")
    p.write_text(
        "\n".join(
            [
                "name = 'Foo'",
                "version = '1.2.3'",
                "versionsuffix = '-CUDA-12.2'",
                "toolchain = {'name': 'GCC', 'version': '13.2.0'}",
                "patches = ['foo-fix.patch', ('foo-missing.patch', 1)]",
                "dependencies = [('zlib', '1.2.13')]",
                "sources = [SOURCELOWER_TAR_GZ]",
                "easyblock = 'ConfigureMake'",
            ]
        )
    )

    md = extract_metadata(p, patch_resolver=lambda _p, n: tmp_path / n)
    assert md.software_name == "Foo"
    assert md.version == "1.2.3"
    assert md.versionsuffix == "-CUDA-12.2"
    assert md.toolchain_name == "GCC"
    assert md.toolchain_version == "13.2.0"
    assert "zlib" in (md.dependencies_raw or "")
    assert [patch.filename for patch in md.patches] == ["foo-fix.patch", "foo-missing.patch"]
    assert md.patches[0].exists is True
    assert md.patches[1].exists is False


def test_extract_metadata_toolchain_system_from_content_and_filename(tmp_path: Path):
    p = tmp_path / "Foo-2.0-system.eb"
    p.write_text(
        "\n".join(
            [
                "name = 'Foo'",
                "version = '2.0'",
                "toolchain = {'name': 'system'}",
            ]
        ),
        encoding="utf-8",
    )

    md = extract_metadata(p)
    assert md.toolchain_name == "system"
    assert md.toolchain_version is None
