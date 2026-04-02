from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from saia_eb_agent.config import AppSettings
from saia_eb_agent.models import RecommendRequest, WorkflowResult
from saia_eb_agent.policy.rules import PlacementPolicy, expand_target_kind
from saia_eb_agent.repos.barnard_ci import BarnardCIRepo
from saia_eb_agent.state.store import StateStore
from saia_eb_agent.workflows.apply import prepare_apply_multi
from saia_eb_agent.workflows.prepare_mr import build_mr_artifacts_for_clusters
from saia_eb_agent.workflows.search import search_candidates


PromptFn = Callable[[str], str]
ConfirmFn = Callable[[str, bool], bool]


@dataclass
class AgentInputs:
    software: str | None = None
    target_kind: str | None = None
    toolchain_query: str | None = None
    release: str | None = None
    barnard_ci: Path | None = None
    apply_changes: bool = False


class AgentWorkflow:
    def __init__(self, state_store: StateStore) -> None:
        self.state_store = state_store

    def run(
        self,
        settings: AppSettings,
        policy: PlacementPolicy,
        inputs: AgentInputs,
        prompt: PromptFn,
        confirm: ConfirmFn,
        local_upstream_path: Path | None = None,
    ) -> WorkflowResult:
        state = self.state_store.load()

        software = (inputs.software or prompt("Enter software name:")).strip()
        target_kind = (inputs.target_kind or prompt("Target kind [cpu/gpu]:")).strip().lower()
        while target_kind not in {"cpu", "gpu"}:
            target_kind = prompt("Target kind [cpu/gpu]:").strip().lower()

        tc_prompt = "Enter toolchain query (example: GCC14.2.0 or foss2025a):"
        toolchain_query = (inputs.toolchain_query or state.last_toolchain_query or prompt(tc_prompt)).strip()

        release = (inputs.release or "").strip()
        if not release and state.last_release:
            release = prompt(
                f"Last release was {state.last_release}. Press Enter to reuse it, or type a new release:"
            ).strip()
            if not release:
                release = state.last_release
        if not release:
            release = prompt("Enter release (example: r25.06):").strip()

        barnard_ci = inputs.barnard_ci
        if not barnard_ci and state.remembered_barnard_ci_path:
            barnard_ci = Path(state.remembered_barnard_ci_path)
        if not barnard_ci:
            barnard_ci = Path(prompt("Enter barnard-ci path:").strip())

        req = RecommendRequest(
            software=software,
            toolchain_query=toolchain_query,
            target_kind=target_kind,
            release=release,
            keywords=[],
        )

        ranked = search_candidates(settings, req, local_upstream_path=local_upstream_path)
        selected = ranked[0] if ranked else None
        if not selected:
            return WorkflowResult(
                request=req.__dict__,
                candidates=[],
                selected=None,
                validation=None,
                operations=[],
                mr_artifacts={},
                notes=["No matching candidate found."],
            )

        repo = BarnardCIRepo(barnard_ci)
        if not repo.exists():
            raise RuntimeError("Provided barnard-ci path does not contain easyconfigs/")

        target_clusters = expand_target_kind(target_kind, policy)

        targets, _diffs, validations, operations = prepare_apply_multi(
            candidate=selected,
            barnard_repo=repo,
            clusters=target_clusters,
            release=release,
            policy=policy,
            apply=False,
        )

        all_ok = all(v.ok for v in validations.values())
        can_apply = inputs.apply_changes and all_ok
        if inputs.apply_changes and not all_ok:
            if confirm("Validation has failures. Continue and apply anyway?", False):
                can_apply = True

        if can_apply:
            targets, _diffs, validations, operations = prepare_apply_multi(
                candidate=selected,
                barnard_repo=repo,
                clusters=target_clusters,
                release=release,
                policy=policy,
                apply=True,
            )

        state.last_release = release
        if release not in state.release_history:
            state.release_history.append(release)
        state.last_target_kind = target_kind
        state.last_toolchain_query = toolchain_query
        self.state_store.save(state)

        mr = build_mr_artifacts_for_clusters(target_clusters, release, selected.metadata)
        notes = [
            f"Selected candidate: {selected.metadata.filename}",
            "Validation completed for all expanded clusters.",
            f"Prepared {len(targets)} target file location(s).",
        ]
        return WorkflowResult(
            request=req.__dict__,
            candidates=ranked,
            selected=selected,
            validation=next(iter(validations.values())) if validations else None,
            operations=operations,
            mr_artifacts=mr,
            cluster_validations=validations,
            notes=notes,
        )
