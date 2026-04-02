from pathlib import Path

from saia_eb_agent.models import Candidate, EasyconfigMetadata, ValidationResult
from saia_eb_agent.state.store import AgentPersistentState, StateStore
from saia_eb_agent.workflows.agent import AgentInputs, AgentWorkflow


def _fake_settings():
    class _Settings:
        cache_dir = Path("/tmp")

    return _Settings()


def _fake_policy():
    class _Policy:
        cpu_clusters = ["romeo", "barnard", "julia", "capella"]
        gpu_clusters = ["alpha", "capella"]

    return _Policy()


def test_agent_workflow_reuses_release_and_remembered_barnard_path(monkeypatch, tmp_path: Path):
    state_file = tmp_path / "state.json"
    store = StateStore(state_file)
    store.save(
        AgentPersistentState(
            remembered_barnard_ci_path=(tmp_path / "barnard-ci").as_posix(),
            last_release="r25.06",
            release_history=["r25.06"],
        )
    )

    barnard_ci = tmp_path / "barnard-ci"
    (barnard_ci / "easyconfigs" / "romeo" / "r25.06").mkdir(parents=True)
    (barnard_ci / "easyconfigs" / "barnard" / "r25.06").mkdir(parents=True)
    (barnard_ci / "easyconfigs" / "julia" / "r25.06").mkdir(parents=True)
    (barnard_ci / "easyconfigs" / "capella" / "r25.06").mkdir(parents=True)

    candidate = Candidate(
        metadata=EasyconfigMetadata(
            path=tmp_path / "Foo-1.2.3-GCC-14.2.0.eb",
            filename="Foo-1.2.3-GCC-14.2.0.eb",
            software_name="Foo",
            version="1.2.3",
            toolchain_name="GCC",
            toolchain_version="14.2.0",
        ),
        score=100.0,
        reasons=[],
        likely_edits=[],
        risk_notes=[],
    )
    candidate.metadata.path.write_text("name = 'Foo'\nversion = '1.2.3'\n")

    monkeypatch.setattr("saia_eb_agent.workflows.agent.search_candidates", lambda *_a, **_k: [candidate])

    captured = {"clusters": None, "release": None, "apply": None, "root": None}

    def _fake_prepare_apply_multi(candidate, barnard_repo, clusters, release, policy, apply=False, **_kwargs):
        captured["clusters"] = clusters
        captured["release"] = release
        captured["apply"] = apply
        captured["root"] = barnard_repo.root
        targets = {c: barnard_repo.target_dir(c, release) / candidate.metadata.filename for c in clusters}
        validations = {c: ValidationResult(ok=True, issues=[]) for c in clusters}
        return targets, {c: "" for c in clusters}, validations, ["dry-run"]

    monkeypatch.setattr("saia_eb_agent.workflows.agent.prepare_apply_multi", _fake_prepare_apply_multi)

    seen_prompts: list[str] = []

    def _prompt(msg: str) -> str:
        seen_prompts.append(msg)
        return ""

    workflow = AgentWorkflow(store)
    result = workflow.run(
        settings=_fake_settings(),
        policy=_fake_policy(),
        inputs=AgentInputs(software="Foo", target_kind="cpu", toolchain_query="GCC14.2.0", apply_changes=False),
        prompt=_prompt,
        confirm=lambda _m, _d: False,
    )
    assert result.selected is not None
    assert captured["release"] == "r25.06"
    assert set(captured["clusters"]) == {"romeo", "barnard", "julia", "capella"}
    assert captured["root"] == barnard_ci
    assert any("Last release was r25.06." in p for p in seen_prompts)
