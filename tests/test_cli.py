from pathlib import Path

from typer.testing import CliRunner

from saia_eb_agent.cli import app
from saia_eb_agent.models import Candidate, EasyconfigMetadata, ValidationResult, WorkflowResult


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
