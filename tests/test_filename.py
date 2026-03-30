from saia_eb_agent.parsing.filename import parse_easyconfig_filename


def test_parse_easyconfig_filename_standard():
    info = parse_easyconfig_filename("GROMACS-2024.4-foss-2023b.eb")
    assert info.software_name == "GROMACS"
    assert info.version == "2024.4"
    assert info.toolchain == "foss-2023b"


def test_parse_easyconfig_filename_invalid():
    info = parse_easyconfig_filename("not-an-eb-file.txt")
    assert info.software_name is None
    assert info.version is None
