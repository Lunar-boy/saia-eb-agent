from pathlib import Path

from saia_eb_agent.state.store import AgentPersistentState, StateStore


def test_state_store_load_save_clear(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    state = store.load()
    assert state.schema_version == 1
    assert state.last_release is None

    state.last_release = "r25.06"
    state.remembered_barnard_ci_path = "/tmp/barnard-ci"
    state.release_history = ["r25.06"]
    store.save(state)

    loaded = store.load()
    assert loaded.last_release == "r25.06"
    assert loaded.remembered_barnard_ci_path == "/tmp/barnard-ci"

    store.clear()
    assert not (tmp_path / "state.json").exists()
