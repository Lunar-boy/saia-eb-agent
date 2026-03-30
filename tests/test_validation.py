from pathlib import Path

from saia_eb_agent.models import EasyconfigMetadata
from saia_eb_agent.policy.rules import PlacementPolicy
from saia_eb_agent.validation.checks import validate_easyconfig


def test_validation_flags_gpu_on_forbidden_cluster(tmp_path: Path):
    target_dir = tmp_path / "easyconfigs" / "romeo" / "r24.10"
    target_dir.mkdir(parents=True)
    target_file = target_dir / "Foo-1.2.3.eb"

    md = EasyconfigMetadata(path=target_file, filename=target_file.name, software_name="Foo", version="1.2.3")
    text = "name = 'Foo'\nversion = '1.2.3'\nversionsuffix = '-CUDA-12.2'"

    res = validate_easyconfig(
        metadata=md,
        file_text=text,
        target_path=target_file,
        target_cluster="romeo",
        target_release="r24.10",
        policy=PlacementPolicy(),
        existing_paths=[],
    )
    assert not res.ok
    assert any(i.code == "policy.cluster_forbidden" for i in res.issues)


def test_validation_rejects_absolute_sources(tmp_path: Path):
    target_dir = tmp_path / "easyconfigs" / "capella" / "r25.06"
    target_dir.mkdir(parents=True)
    target_file = target_dir / "Foo-1.2.3.eb"
    md = EasyconfigMetadata(path=target_file, filename=target_file.name, software_name="Foo", version="1.2.3")
    text = "sources = ['/software/util/sources/Foo-1.2.3.tar.gz']"

    res = validate_easyconfig(md, text, target_file, "capella", "r25.06", PlacementPolicy(), existing_paths=[])
    assert not res.ok
    assert any(i.code == "sources.absolute_path" for i in res.issues)
