from pathlib import Path

import pytest

from saia_eb_agent.models import Candidate, EasyconfigMetadata, ValidationIssue, ValidationResult
from saia_eb_agent.policy.rules import PlacementPolicy, expand_target_kind
from saia_eb_agent.repos.barnard_ci import BarnardCIRepo
from saia_eb_agent.workflows.apply import prepare_apply_multi


def _mk_candidate(path: Path, software: str, version: str, toolchain: str = "GCC", tc_version: str = "14.2.0") -> Candidate:
    return Candidate(
        metadata=EasyconfigMetadata(
            path=path,
            filename=path.name,
            software_name=software,
            version=version,
            toolchain_name=toolchain,
            toolchain_version=tc_version,
        ),
        score=100,
        reasons=[],
        likely_edits=[],
        risk_notes=[],
    )


def _mk_barnard(tmp_path: Path, clusters: list[str], release: str) -> BarnardCIRepo:
    barnard = tmp_path / "barnard-ci"
    for cluster in clusters:
        (barnard / "easyconfigs" / cluster / release).mkdir(parents=True)
    return BarnardCIRepo(barnard)


def _write_ec(path: Path, name: str, version: str, dependencies_expr: str | None = None) -> Path:
    lines = [f"name = '{name}'", f"version = '{version}'", "toolchain = {'name': 'GCC', 'version': '14.2.0'}"]
    if dependencies_expr is not None:
        lines.append(f"dependencies = {dependencies_expr}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_prepare_apply_multi_for_cpu_targets(tmp_path: Path):
    upstream_file = _write_ec(tmp_path / "Foo-1.2.3-GCC-14.2.0.eb", "Foo", "1.2.3")
    candidate = _mk_candidate(upstream_file, "Foo", "1.2.3")

    clusters = ["romeo", "barnard", "julia", "capella"]
    repo = _mk_barnard(tmp_path, clusters, "r25.06")

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


def test_main_with_missing_direct_dependency_is_planned_and_copied(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    main = _write_ec(
        upstream / "Foo-1.0-GCC-14.2.0.eb",
        "Foo",
        "1.0",
        "[('zlib', '1.2.13')]",
    )
    dep = _write_ec(upstream / "zlib-1.2.13-GCC-14.2.0.eb", "zlib", "1.2.13")

    candidate = _mk_candidate(main, "Foo", "1.0")
    repo = _mk_barnard(tmp_path, ["romeo"], "r25.06")
    policy = PlacementPolicy()

    _targets, _diffs, _validations, ops = prepare_apply_multi(
        candidate=candidate,
        barnard_repo=repo,
        clusters=["romeo"],
        release="r25.06",
        policy=policy,
        apply=True,
    )

    target_dir = repo.target_dir("romeo", "r25.06")
    assert (target_dir / main.name).exists()
    assert (target_dir / dep.name).exists()
    assert any(f"copy {dep}" in op for op in ops)


def test_transitive_dependency_chain_recursive_closure(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    main = _write_ec(upstream / "Main-1.0-GCC-14.2.0.eb", "Main", "1.0", "[('B', '1.0')]")
    dep_b = _write_ec(upstream / "B-1.0-GCC-14.2.0.eb", "B", "1.0", "[('C', '1.0')]")
    dep_c = _write_ec(upstream / "C-1.0-GCC-14.2.0.eb", "C", "1.0")

    candidate = _mk_candidate(main, "Main", "1.0")
    repo = _mk_barnard(tmp_path, ["romeo"], "r25.06")

    prepare_apply_multi(
        candidate=candidate,
        barnard_repo=repo,
        clusters=["romeo"],
        release="r25.06",
        policy=PlacementPolicy(),
        apply=True,
    )

    target_dir = repo.target_dir("romeo", "r25.06")
    assert (target_dir / main.name).exists()
    assert (target_dir / dep_b.name).exists()
    assert (target_dir / dep_c.name).exists()


def test_dependency_already_present_in_target_release_is_skipped(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    main = _write_ec(upstream / "Foo-1.0-GCC-14.2.0.eb", "Foo", "1.0", "[('zlib', '1.2.13')]")
    _dep = _write_ec(upstream / "zlib-1.2.13-GCC-14.2.0.eb", "zlib", "1.2.13")

    repo = _mk_barnard(tmp_path, ["romeo", "barnard"], "r25.06")
    for cluster in ["romeo", "barnard"]:
        _write_ec(repo.target_dir(cluster, "r25.06") / "zlib-1.2.13-GCC-14.2.0.eb", "zlib", "1.2.13")

    candidate = _mk_candidate(main, "Foo", "1.0")

    _targets, _diffs, _validations, ops = prepare_apply_multi(
        candidate=candidate,
        barnard_repo=repo,
        clusters=["romeo", "barnard"],
        release="r25.06",
        policy=PlacementPolicy(),
        apply=False,
    )

    copy_ops = [op for op in ops if op.startswith("copy")]
    assert all("zlib-1.2.13-GCC-14.2.0.eb" not in op for op in copy_ops)
    assert any("dependency already present for all targets" in op for op in ops)


def test_shared_dependency_is_copied_only_once(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    main = _write_ec(upstream / "Main-1.0-GCC-14.2.0.eb", "Main", "1.0", "[('B', '1.0'), ('C', '1.0')]")
    _write_ec(upstream / "B-1.0-GCC-14.2.0.eb", "B", "1.0", "[('D', '1.0')]")
    _write_ec(upstream / "C-1.0-GCC-14.2.0.eb", "C", "1.0", "[('D', '1.0')]")
    dep_d = _write_ec(upstream / "D-1.0-GCC-14.2.0.eb", "D", "1.0")

    candidate = _mk_candidate(main, "Main", "1.0")
    repo = _mk_barnard(tmp_path, ["romeo"], "r25.06")

    _targets, _diffs, _validations, ops = prepare_apply_multi(
        candidate=candidate,
        barnard_repo=repo,
        clusters=["romeo"],
        release="r25.06",
        policy=PlacementPolicy(),
        apply=False,
    )

    d_copy_ops = [op for op in ops if op.startswith("copy") and dep_d.name in op]
    assert len(d_copy_ops) == 1


def test_cyclic_dependencies_do_not_recurse_forever(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    main = _write_ec(upstream / "A-1.0-GCC-14.2.0.eb", "A", "1.0", "[('B', '1.0')]")
    dep_b = _write_ec(upstream / "B-1.0-GCC-14.2.0.eb", "B", "1.0", "[('A', '1.0')]")

    candidate = _mk_candidate(main, "A", "1.0")
    repo = _mk_barnard(tmp_path, ["romeo"], "r25.06")

    _targets, _diffs, _validations, ops = prepare_apply_multi(
        candidate=candidate,
        barnard_repo=repo,
        clusters=["romeo"],
        release="r25.06",
        policy=PlacementPolicy(),
        apply=False,
    )

    b_copy_ops = [op for op in ops if op.startswith("copy") and dep_b.name in op]
    a_dep_copy_ops = [op for op in ops if op.startswith("copy") and "A-1.0-GCC-14.2.0.eb" in op and "upstream" in op]
    assert len(b_copy_ops) == 1
    # Main file is copied once as the target operation, not recursively as dependency closure.
    assert len(a_dep_copy_ops) == 1


def test_dry_run_plans_dependencies_without_writing(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    main = _write_ec(upstream / "Foo-1.0-GCC-14.2.0.eb", "Foo", "1.0", "[('zlib', '1.2.13')]")
    dep = _write_ec(upstream / "zlib-1.2.13-GCC-14.2.0.eb", "zlib", "1.2.13")

    candidate = _mk_candidate(main, "Foo", "1.0")
    repo = _mk_barnard(tmp_path, ["romeo"], "r25.06")

    _targets, _diffs, _validations, ops = prepare_apply_multi(
        candidate=candidate,
        barnard_repo=repo,
        clusters=["romeo"],
        release="r25.06",
        policy=PlacementPolicy(),
        apply=False,
    )

    target_dir = repo.target_dir("romeo", "r25.06")
    assert not (target_dir / main.name).exists()
    assert not (target_dir / dep.name).exists()
    assert any("dry-run only" in op for op in ops)
    assert any(f"copy {dep}" in op for op in ops)


def test_apply_writes_main_and_missing_dependencies(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    main = _write_ec(upstream / "Foo-1.0-GCC-14.2.0.eb", "Foo", "1.0", "[('zlib', '1.2.13')]")
    dep = _write_ec(upstream / "zlib-1.2.13-GCC-14.2.0.eb", "zlib", "1.2.13")

    candidate = _mk_candidate(main, "Foo", "1.0")
    repo = _mk_barnard(tmp_path, ["romeo"], "r25.06")

    prepare_apply_multi(
        candidate=candidate,
        barnard_repo=repo,
        clusters=["romeo"],
        release="r25.06",
        policy=PlacementPolicy(),
        apply=True,
    )

    target_dir = repo.target_dir("romeo", "r25.06")
    assert (target_dir / main.name).exists()
    assert (target_dir / dep.name).exists()


def test_malformed_dependency_expression_does_not_crash(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    main = _write_ec(upstream / "Foo-1.0-GCC-14.2.0.eb", "Foo", "1.0", "[(]")

    candidate = _mk_candidate(main, "Foo", "1.0")
    repo = _mk_barnard(tmp_path, ["romeo"], "r25.06")

    _targets, _diffs, _validations, ops = prepare_apply_multi(
        candidate=candidate,
        barnard_repo=repo,
        clusters=["romeo"],
        release="r25.06",
        policy=PlacementPolicy(),
        apply=False,
    )

    assert any("dependency parse warning" in op for op in ops)


def test_prepare_apply_multi_apply_force_false_raises_on_any_error(tmp_path: Path):
    upstream_file = tmp_path / "Foo-1.2.3-GCC-14.2.0.eb"
    upstream_file.write_text(
        "name = 'Foo'\nversion = '1.2.3'\nsources = ['/software/util/sources/Foo-1.2.3.tar.gz']\n",
        encoding="utf-8",
    )
    candidate = _mk_candidate(upstream_file, "Foo", "1.2.3")
    repo = _mk_barnard(tmp_path, ["capella"], "r25.06")

    with pytest.raises(RuntimeError, match="blocking validation failed"):
        prepare_apply_multi(
            candidate=candidate,
            barnard_repo=repo,
            clusters=["capella"],
            release="r25.06",
            policy=PlacementPolicy(),
            apply=True,
            force=False,
        )


def test_prepare_apply_multi_apply_force_true_allows_overridable_error(tmp_path: Path):
    upstream_file = tmp_path / "Foo-1.2.3-GCC-14.2.0.eb"
    upstream_file.write_text(
        "name = 'Foo'\nversion = '1.2.3'\nsources = ['/software/util/sources/Foo-1.2.3.tar.gz']\n",
        encoding="utf-8",
    )
    candidate = _mk_candidate(upstream_file, "Foo", "1.2.3")
    repo = _mk_barnard(tmp_path, ["capella"], "r25.06")

    targets, _diffs, validations, _ops = prepare_apply_multi(
        candidate=candidate,
        barnard_repo=repo,
        clusters=["capella"],
        release="r25.06",
        policy=PlacementPolicy(),
        apply=True,
        force=True,
    )

    assert targets["capella"].exists()
    assert any(issue.code == "sources.absolute_path" for issue in validations["capella"].issues)


def test_prepare_apply_multi_apply_force_true_still_blocks_policy_cluster_forbidden(tmp_path: Path):
    upstream_file = tmp_path / "Foo-1.2.3-GCC-14.2.0.eb"
    upstream_file.write_text(
        "name = 'Foo'\nversion = '1.2.3'\nversionsuffix = '-CUDA-12.2'\n",
        encoding="utf-8",
    )
    candidate = _mk_candidate(upstream_file, "Foo", "1.2.3")
    repo = _mk_barnard(tmp_path, ["romeo"], "r25.06")

    with pytest.raises(RuntimeError, match="blocking validation failed"):
        prepare_apply_multi(
            candidate=candidate,
            barnard_repo=repo,
            clusters=["romeo"],
            release="r25.06",
            policy=PlacementPolicy(),
            apply=True,
            force=True,
        )


def test_prepare_apply_multi_apply_force_true_still_blocks_path_invalid(monkeypatch, tmp_path: Path):
    upstream_file = _write_ec(tmp_path / "Foo-1.2.3-GCC-14.2.0.eb", "Foo", "1.2.3")
    candidate = _mk_candidate(upstream_file, "Foo", "1.2.3")
    repo = _mk_barnard(tmp_path, ["capella"], "r25.06")

    def _always_path_invalid(**_kwargs):
        return ValidationResult(ok=False, issues=[ValidationIssue("error", "path.invalid", "invalid target path")])

    monkeypatch.setattr("saia_eb_agent.workflows.apply.validate_easyconfig", _always_path_invalid)

    with pytest.raises(RuntimeError, match="blocking validation failed"):
        prepare_apply_multi(
            candidate=candidate,
            barnard_repo=repo,
            clusters=["capella"],
            release="r25.06",
            policy=PlacementPolicy(),
            apply=True,
            force=True,
        )
