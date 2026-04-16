from pathlib import Path

from saia_eb_agent.models import Candidate, EasyconfigMetadata, ValidationIssue, ValidationResult
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


def _fake_prepare_apply_multi_capture(captured: dict):
    def _fake_prepare_apply_multi(candidate, barnard_repo, clusters, release, policy, apply=False, **_kwargs):
        captured["clusters"] = clusters
        captured["release"] = release
        captured["apply"] = apply
        captured["root"] = barnard_repo.root
        targets = {c: barnard_repo.target_dir(c, release) / candidate.metadata.filename for c in clusters}
        validations = {c: ValidationResult(ok=True, issues=[]) for c in clusters}
        return targets, {c: "" for c in clusters}, validations, ["dry-run"]

    return _fake_prepare_apply_multi


def _mk_candidate(tmp_path: Path, name: str = "Foo-1.2.3-GCC-14.2.0.eb") -> Candidate:
    candidate = Candidate(
        metadata=EasyconfigMetadata(
            path=tmp_path / name,
            filename=name,
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
    return candidate


def _mk_barnard_ci(tmp_path: Path, release: str = "r25.06") -> Path:
    barnard_ci = tmp_path / "barnard-ci"
    for cluster in ("romeo", "barnard", "julia", "capella"):
        (barnard_ci / "easyconfigs" / cluster / release).mkdir(parents=True, exist_ok=True)
    return barnard_ci


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

    barnard_ci = _mk_barnard_ci(tmp_path, "r25.06")

    candidate = _mk_candidate(tmp_path)

    monkeypatch.setattr("saia_eb_agent.workflows.agent.search_candidates", lambda *_a, **_k: [candidate])

    captured = {"clusters": None, "release": None, "apply": None, "root": None}

    monkeypatch.setattr("saia_eb_agent.workflows.agent.prepare_apply_multi", _fake_prepare_apply_multi_capture(captured))

    seen_prompts: list[str] = []

    def _prompt(msg: str, allow_empty: bool) -> str:
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


def test_agent_workflow_saves_newly_entered_barnard_path(monkeypatch, tmp_path: Path):
    state_file = tmp_path / "state.json"
    store = StateStore(state_file)
    barnard_ci = _mk_barnard_ci(tmp_path, "r25.06")
    candidate = _mk_candidate(tmp_path)
    monkeypatch.setattr("saia_eb_agent.workflows.agent.search_candidates", lambda *_a, **_k: [candidate])
    captured: dict = {"root": None}
    monkeypatch.setattr("saia_eb_agent.workflows.agent.prepare_apply_multi", _fake_prepare_apply_multi_capture(captured))

    prompts = iter([str(barnard_ci)])
    workflow = AgentWorkflow(store)
    workflow.run(
        settings=_fake_settings(),
        policy=_fake_policy(),
        inputs=AgentInputs(software="Foo", target_kind="cpu", toolchain_query="GCC14.2.0", release="r25.06"),
        prompt=lambda _m, _allow_empty: next(prompts),
        confirm=lambda _m, _d: False,
    )

    loaded = store.load()
    assert loaded.remembered_barnard_ci_path == barnard_ci.resolve(strict=False).as_posix()
    assert captured["root"] == barnard_ci.resolve(strict=False)


def test_agent_workflow_reuses_remembered_barnard_path_on_next_run(monkeypatch, tmp_path: Path):
    state_file = tmp_path / "state.json"
    store = StateStore(state_file)
    barnard_ci = _mk_barnard_ci(tmp_path, "r25.06").resolve(strict=False)
    store.save(AgentPersistentState(remembered_barnard_ci_path=barnard_ci.as_posix(), last_release="r25.06"))
    candidate = _mk_candidate(tmp_path)
    monkeypatch.setattr("saia_eb_agent.workflows.agent.search_candidates", lambda *_a, **_k: [candidate])
    captured: dict = {"root": None}
    monkeypatch.setattr("saia_eb_agent.workflows.agent.prepare_apply_multi", _fake_prepare_apply_multi_capture(captured))

    seen_prompts: list[str] = []
    workflow = AgentWorkflow(store)
    workflow.run(
        settings=_fake_settings(),
        policy=_fake_policy(),
        inputs=AgentInputs(software="Foo", target_kind="cpu", toolchain_query="GCC14.2.0", release="r25.06"),
        prompt=lambda msg, _allow_empty: seen_prompts.append(msg) or "",
        confirm=lambda _m, _d: False,
    )

    assert captured["root"] == barnard_ci
    assert all("Enter barnard-ci path:" not in msg for msg in seen_prompts)


def test_agent_workflow_reprompts_when_remembered_barnard_path_is_invalid(monkeypatch, tmp_path: Path):
    state_file = tmp_path / "state.json"
    store = StateStore(state_file)
    invalid = tmp_path / "missing-barnard-ci"
    store.save(
        AgentPersistentState(
            remembered_barnard_ci_path=invalid.as_posix(),
            last_release="r25.06",
            release_history=["r25.06"],
        )
    )
    valid_barnard_ci = _mk_barnard_ci(tmp_path, "r25.06").resolve(strict=False)
    candidate = _mk_candidate(tmp_path)
    monkeypatch.setattr("saia_eb_agent.workflows.agent.search_candidates", lambda *_a, **_k: [candidate])
    captured: dict = {"root": None}
    monkeypatch.setattr("saia_eb_agent.workflows.agent.prepare_apply_multi", _fake_prepare_apply_multi_capture(captured))

    prompts = iter([str(valid_barnard_ci)])
    seen_prompts: list[str] = []

    def _prompt(msg: str, allow_empty: bool) -> str:
        seen_prompts.append(msg)
        return next(prompts)

    workflow = AgentWorkflow(store)
    workflow.run(
        settings=_fake_settings(),
        policy=_fake_policy(),
        inputs=AgentInputs(software="Foo", target_kind="cpu", toolchain_query="GCC14.2.0", release="r25.06"),
        prompt=_prompt,
        confirm=lambda _m, _d: False,
    )

    assert any("Enter barnard-ci path:" in msg for msg in seen_prompts)
    assert captured["root"] == valid_barnard_ci
    assert store.load().remembered_barnard_ci_path == valid_barnard_ci.as_posix()


def test_agent_workflow_apply_uses_force_when_confirming_failed_validation(monkeypatch, tmp_path: Path):
    state_file = tmp_path / "state.json"
    store = StateStore(state_file)
    barnard_ci = _mk_barnard_ci(tmp_path, "r25.06")
    candidate = _mk_candidate(tmp_path)
    monkeypatch.setattr("saia_eb_agent.workflows.agent.search_candidates", lambda *_a, **_k: [candidate])

    calls: list[tuple[bool, bool]] = []

    def _fake_prepare_apply_multi(candidate, barnard_repo, clusters, release, policy, apply=False, force=False, **_kwargs):
        calls.append((apply, force))
        targets = {c: barnard_repo.target_dir(c, release) / candidate.metadata.filename for c in clusters}
        if not apply:
            failed = ValidationResult(
                ok=False,
                issues=[ValidationIssue("error", "sources.absolute_path", "absolute path detected")],
            )
            return targets, {c: "" for c in clusters}, {c: failed for c in clusters}, ["dry-run"]
        return targets, {c: "" for c in clusters}, {c: ValidationResult(ok=False, issues=[]) for c in clusters}, ["applied"]

    monkeypatch.setattr("saia_eb_agent.workflows.agent.prepare_apply_multi", _fake_prepare_apply_multi)

    confirm_messages: list[str] = []

    workflow = AgentWorkflow(store)
    result = workflow.run(
        settings=_fake_settings(),
        policy=_fake_policy(),
        inputs=AgentInputs(
            software="Foo",
            target_kind="cpu",
            toolchain_query="GCC14.2.0",
            release="r25.06",
            barnard_ci=barnard_ci,
            apply_changes=True,
        ),
        prompt=lambda _m, _allow_empty: "",
        confirm=lambda m, _d: confirm_messages.append(m) or True,
    )

    assert result.selected is not None
    assert calls == [(False, False), (True, True)]
    assert confirm_messages == ["Validation has overridable failures. Force apply anyway?"]
    assert "applied" in result.operations


def test_agent_workflow_does_not_apply_when_validation_fails_and_confirm_is_false(monkeypatch, tmp_path: Path):
    state_file = tmp_path / "state.json"
    store = StateStore(state_file)
    barnard_ci = _mk_barnard_ci(tmp_path, "r25.06")
    candidate = _mk_candidate(tmp_path)
    monkeypatch.setattr("saia_eb_agent.workflows.agent.search_candidates", lambda *_a, **_k: [candidate])

    calls: list[tuple[bool, bool]] = []

    def _fake_prepare_apply_multi(candidate, barnard_repo, clusters, release, policy, apply=False, force=False, **_kwargs):
        calls.append((apply, force))
        targets = {c: barnard_repo.target_dir(c, release) / candidate.metadata.filename for c in clusters}
        failed = ValidationResult(
            ok=False,
            issues=[ValidationIssue("error", "sources.absolute_path", "absolute path detected")],
        )
        return targets, {c: "" for c in clusters}, {c: failed for c in clusters}, ["dry-run"]

    monkeypatch.setattr("saia_eb_agent.workflows.agent.prepare_apply_multi", _fake_prepare_apply_multi)

    confirm_messages: list[str] = []

    workflow = AgentWorkflow(store)
    result = workflow.run(
        settings=_fake_settings(),
        policy=_fake_policy(),
        inputs=AgentInputs(
            software="Foo",
            target_kind="cpu",
            toolchain_query="GCC14.2.0",
            release="r25.06",
            barnard_ci=barnard_ci,
            apply_changes=True,
        ),
        prompt=lambda _m, _allow_empty: "",
        confirm=lambda m, _d: confirm_messages.append(m) or False,
    )

    assert calls == [(False, False)]
    assert confirm_messages == ["Validation has overridable failures. Force apply anyway?"]
    assert any("Apply skipped: user declined force apply" in op for op in result.operations)


def test_agent_workflow_non_overridable_validation_skips_apply_without_confirmation(monkeypatch, tmp_path: Path):
    state_file = tmp_path / "state.json"
    store = StateStore(state_file)
    barnard_ci = _mk_barnard_ci(tmp_path, "r25.06")
    candidate = _mk_candidate(tmp_path)
    monkeypatch.setattr("saia_eb_agent.workflows.agent.search_candidates", lambda *_a, **_k: [candidate])

    calls: list[tuple[bool, bool]] = []

    def _fake_prepare_apply_multi(candidate, barnard_repo, clusters, release, policy, apply=False, force=False, **_kwargs):
        calls.append((apply, force))
        targets = {c: barnard_repo.target_dir(c, release) / candidate.metadata.filename for c in clusters}
        failed = ValidationResult(
            ok=False,
            issues=[ValidationIssue("error", "path.invalid", "invalid target path")],
        )
        return targets, {c: "" for c in clusters}, {c: failed for c in clusters}, ["dry-run"]

    monkeypatch.setattr("saia_eb_agent.workflows.agent.prepare_apply_multi", _fake_prepare_apply_multi)

    confirm_messages: list[str] = []

    workflow = AgentWorkflow(store)
    result = workflow.run(
        settings=_fake_settings(),
        policy=_fake_policy(),
        inputs=AgentInputs(
            software="Foo",
            target_kind="cpu",
            toolchain_query="GCC14.2.0",
            release="r25.06",
            barnard_ci=barnard_ci,
            apply_changes=True,
        ),
        prompt=lambda _m, _allow_empty: "",
        confirm=lambda m, _d: confirm_messages.append(m) or True,
    )

    assert result.selected is not None
    assert calls == [(False, False)]
    assert confirm_messages == []
    assert any("non-overridable error(s) (path.invalid)" in note for note in result.notes)
    assert any("non-overridable error(s) (path.invalid)" in op for op in result.operations)


def test_agent_workflow_apply_without_force_when_validation_is_ok(monkeypatch, tmp_path: Path):
    state_file = tmp_path / "state.json"
    store = StateStore(state_file)
    barnard_ci = _mk_barnard_ci(tmp_path, "r25.06")
    candidate = _mk_candidate(tmp_path)
    monkeypatch.setattr("saia_eb_agent.workflows.agent.search_candidates", lambda *_a, **_k: [candidate])

    calls: list[tuple[bool, bool]] = []

    def _fake_prepare_apply_multi(candidate, barnard_repo, clusters, release, policy, apply=False, force=False, **_kwargs):
        calls.append((apply, force))
        targets = {c: barnard_repo.target_dir(c, release) / candidate.metadata.filename for c in clusters}
        ok_validation = ValidationResult(ok=True, issues=[])
        op = "applied" if apply else "dry-run"
        return targets, {c: "" for c in clusters}, {c: ok_validation for c in clusters}, [op]

    monkeypatch.setattr("saia_eb_agent.workflows.agent.prepare_apply_multi", _fake_prepare_apply_multi)

    workflow = AgentWorkflow(store)
    result = workflow.run(
        settings=_fake_settings(),
        policy=_fake_policy(),
        inputs=AgentInputs(
            software="Foo",
            target_kind="cpu",
            toolchain_query="GCC14.2.0",
            release="r25.06",
            barnard_ci=barnard_ci,
            apply_changes=True,
        ),
        prompt=lambda _m, _allow_empty: "",
        confirm=lambda _m, _d: True,
    )

    assert result.selected is not None
    assert calls == [(False, False), (True, False)]
    assert "applied" in result.operations
