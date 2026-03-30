from pathlib import Path

from saia_eb_agent.models import Candidate, EasyconfigMetadata
from saia_eb_agent.policy.rules import PlacementPolicy
from saia_eb_agent.repos.barnard_ci import BarnardCIRepo
from saia_eb_agent.workflows.apply import prepare_apply


def test_prepare_apply_dry_run_and_apply(tmp_path: Path):
    upstream_file = tmp_path / "Foo-1.2.3-GCC-13.2.0.eb"
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
    target_release_dir = barnard / "easyconfigs" / "capella" / "r25.06"
    target_release_dir.mkdir(parents=True)

    repo = BarnardCIRepo(barnard)

    target, _diff, _validation, ops = prepare_apply(
        candidate=candidate,
        barnard_repo=repo,
        cluster="capella",
        release="r25.06",
        policy=PlacementPolicy(),
        apply=False,
    )
    assert target.exists() is False
    assert any("dry-run" in o for o in ops)

    target2, _diff2, _validation2, ops2 = prepare_apply(
        candidate=candidate,
        barnard_repo=repo,
        cluster="capella",
        release="r25.06",
        policy=PlacementPolicy(),
        apply=True,
    )
    assert target2.exists()
    assert any("--apply" in o for o in ops2)
