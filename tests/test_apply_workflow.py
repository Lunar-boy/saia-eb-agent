from pathlib import Path

from saia_eb_agent.models import Candidate, EasyconfigMetadata
from saia_eb_agent.policy.rules import PlacementPolicy, expand_target_kind
from saia_eb_agent.repos.barnard_ci import BarnardCIRepo
from saia_eb_agent.workflows.apply import prepare_apply_multi


def test_prepare_apply_multi_for_cpu_targets(tmp_path: Path):
    upstream_file = tmp_path / "Foo-1.2.3-GCC-14.2.0.eb"
    upstream_file.write_text("name = 'Foo'\nversion = '1.2.3'\n")

    candidate = Candidate(
        metadata=EasyconfigMetadata(
            path=upstream_file,
            filename=upstream_file.name,
            software_name="Foo",
            version="1.2.3",
        ),
        score=100,
        reasons=[],
        likely_edits=[],
        risk_notes=[],
    )

    barnard = tmp_path / "barnard-ci"
    for cluster in ["romeo", "barnard", "julia", "capella"]:
        (barnard / "easyconfigs" / cluster / "r25.06").mkdir(parents=True)

    repo = BarnardCIRepo(barnard)
    policy = PlacementPolicy()
    targets = expand_target_kind("cpu", policy)

    out_targets, _diffs, validations, ops = prepare_apply_multi(
        candidate=candidate,
        barnard_repo=repo,
        clusters=targets,
        release="r25.06",
        policy=policy,
        apply=True,
    )
    assert set(out_targets.keys()) == set(targets)
    assert set(validations.keys()) == set(targets)
    for target in out_targets.values():
        assert target.exists()
    assert any("write applied for cluster" in op for op in ops)
