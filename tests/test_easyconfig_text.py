from pathlib import Path

from saia_eb_agent.parsing.easyconfig_text import extract_metadata


def test_extract_metadata(tmp_path: Path):
    p = tmp_path / "Foo-1.2.3-GCC-13.2.0.eb"
    p.write_text(
        "\n".join(
            [
                "name = 'Foo'",
                "version = '1.2.3'",
                "versionsuffix = '-CUDA-12.2'",
                "toolchain = {'name': 'GCC', 'version': '13.2.0'}",
                "dependencies = [('zlib', '1.2.13')]",
                "sources = [SOURCELOWER_TAR_GZ]",
                "easyblock = 'ConfigureMake'",
            ]
        )
    )

    md = extract_metadata(p)
    assert md.software_name == "Foo"
    assert md.version == "1.2.3"
    assert md.versionsuffix == "-CUDA-12.2"
    assert md.toolchain_name == "GCC"
    assert md.toolchain_version == "13.2.0"
    assert "zlib" in (md.dependencies_raw or "")
