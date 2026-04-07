from pathlib import Path

from typer.testing import CliRunner

from saia_eb_agent.cli import app
from saia_eb_agent.models import Candidate, EasyconfigMetadata, ValidationResult, WorkflowResult
from saia_eb_agent.state.store import AgentPersistentState, StateStore


runner = CliRunner()


def test_search_uses_tc_and_does_not_need_old_options(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    (upstream / "Foo-1.2.3-GCC-14.2.0.eb").write_text(
        "name = 'Foo'\nversion = '1.2.3'\ntoolchain = {'name': 'GCC', 'version': '14.2.0'}",
        encoding="utf-8",
    )
    ok = runner.invoke(
        app,
        [
            "search",
            "--software",
            "Foo",
            "--tc",
            "GCC14.2.0",
            "--local-upstream",
            str(upstream),
        ],
    )
    assert ok.exit_code == 0
    bad = runner.invoke(app, ["search", "--software", "Foo", "--version", "1.2.3"])
    assert bad.exit_code != 0


def test_search_accepts_system_toolchain(tmp_path: Path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    (upstream / "Foo-2.0-system.eb").write_text(
        "name = 'Foo'\nversion = '2.0'\ntoolchain = {'name': 'system'}",
        encoding="utf-8",
    )
    res = runner.invoke(
        app,
        [
            "search",
            "--software",
            "Foo",
            "--tc",
            "system",
            "--local-upstream",
            str(upstream),
        ],
    )
    assert res.exit_code == 0
    assert "Toolchain equivalence expansion" in res.stdout
    assert "system" in res.stdout


def test_memory_commands(tmp_path: Path):
    state_file = tmp_path / "state.json"
    set_res = runner.invoke(
        app,
        ["memory", "set-barnard-ci", str(tmp_path / "barnard-ci"), "--state-file", str(state_file)],
    )
    assert set_res.exit_code == 0

    show_res = runner.invoke(app, ["memory", "show", "--state-file", str(state_file)])
    assert show_res.exit_code == 0
    assert "remembered_barnard_ci_path" in show_res.stdout


def test_guide_happy_path(monkeypatch, tmp_path: Path):
    cand = Candidate(
        metadata=EasyconfigMetadata(
            path=tmp_path / "Foo-1.2.3-GCC-14.2.0.eb",
            filename="Foo-1.2.3-GCC-14.2.0.eb",
            software_name="Foo",
            version="1.2.3",
            toolchain_name="GCC",
            toolchain_version="14.2.0",
        ),
        score=99.0,
        reasons=["x"],
        likely_edits=[],
        risk_notes=[],
        toolchain_match_reason="GCC-14.2.0 via exact",
    )
    cand.metadata.path.write_text("name = 'Foo'\nversion = '1.2.3'\n", encoding="utf-8")

    fake_result = WorkflowResult(
        request={},
        candidates=[cand],
        selected=cand,
        validation=ValidationResult(ok=True, issues=[]),
        operations=["dry-run only"],
        mr_artifacts={"mr_title": "title"},
        cluster_validations={"romeo": ValidationResult(ok=True, issues=[])},
        notes=[],
    )
    monkeypatch.setattr("saia_eb_agent.cli.AgentWorkflow.run", lambda *a, **k: fake_result)

    barnard_ci = tmp_path / "barnard-ci"
    barnard_ci.mkdir()
    res = runner.invoke(
        app,
        [
            "guide",
            "--software",
            "Foo",
            "--cluster",
            "cpu",
            "--tc",
            "GCC14.2.0",
            "--release",
            "r25.06",
            "--barnard-ci",
            str(barnard_ci),
            "--dry-run",
        ],
    )
    assert res.exit_code == 0
    assert "Selected candidate" in res.stdout


def test_agent_cli_press_enter_reuses_last_release(monkeypatch, tmp_path: Path):
    class _Settings:
        cache_dir = tmp_path / "cache"

    class _Policy:
        cpu_clusters = ["romeo"]
        gpu_clusters = ["capella"]

    monkeypatch.setattr("saia_eb_agent.cli.load_settings", lambda _p: _Settings())
    monkeypatch.setattr("saia_eb_agent.cli.load_policy", lambda _p: _Policy())

    barnard_ci = tmp_path / "barnard-ci"
    (barnard_ci / "easyconfigs" / "romeo" / "r2026").mkdir(parents=True)
    state_file = tmp_path / "state.json"
    store = StateStore(state_file)
    store.save(
        AgentPersistentState(
            remembered_barnard_ci_path=barnard_ci.resolve(strict=False).as_posix(),
            last_release="r2026",
            release_history=["r2026"],
        )
    )

    cand = Candidate(
        metadata=EasyconfigMetadata(
            path=tmp_path / "mm-common-1.0-GCC-14.2.0.eb",
            filename="mm-common-1.0-GCC-14.2.0.eb",
            software_name="mm-common",
            version="1.0",
            toolchain_name="GCC",
            toolchain_version="14.2.0",
        ),
        score=99.0,
        reasons=["x"],
        likely_edits=[],
        risk_notes=[],
        toolchain_match_reason="GCC-14.2.0 via exact",
    )
    cand.metadata.path.write_text("name = 'mm-common'\nversion = '1.0'\n", encoding="utf-8")
    monkeypatch.setattr("saia_eb_agent.workflows.agent.search_candidates", lambda *_a, **_k: [cand])

    captured: dict = {"release": None}

    def _fake_prepare_apply_multi(candidate, barnard_repo, clusters, release, policy, apply=False, **_kwargs):
        captured["release"] = release
        targets = {c: barnard_repo.target_dir(c, release) / candidate.metadata.filename for c in clusters}
        validations = {c: ValidationResult(ok=True, issues=[]) for c in clusters}
        return targets, {c: "" for c in clusters}, validations, ["dry-run"]

    monkeypatch.setattr("saia_eb_agent.workflows.agent.prepare_apply_multi", _fake_prepare_apply_multi)

    res = runner.invoke(
        app,
        [
            "agent",
            "--software",
            "mm-common",
            "--cluster",
            "cpu",
            "--tc",
            "GCC14.2.0",
            "--dry-run",
            "--state-file",
            str(state_file),
        ],
        input="\n",
    )
    assert res.exit_code == 0
    assert "Last release was r2026. Press Enter to reuse it, or type a new release:" in res.stdout
    assert captured["release"] == "r2026"
