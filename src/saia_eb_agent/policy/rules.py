from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class PlacementPolicy(BaseModel):
    gpu_clusters: list[str] = Field(default_factory=lambda: ["alpha", "capella"])
    cpu_clusters: list[str] = Field(default_factory=lambda: ["romeo", "barnard", "julia", "capella"])
    forbidden_gpu_clusters: list[str] = Field(default_factory=lambda: ["romeo", "barnard", "julia"])
    shared_install_domains: list[list[str]] = Field(default_factory=lambda: [["alpha", "romeo"]])
    alpha_dependency_search_clusters: list[str] = Field(default_factory=lambda: ["alpha", "romeo"])


def load_policy(path: Path | None = None) -> PlacementPolicy:
    if path and path.exists():
        data = yaml.safe_load(path.read_text()) or {}
        return PlacementPolicy.model_validate(data)
    return PlacementPolicy()


def dependency_search_clusters(target_cluster: str, policy: PlacementPolicy) -> list[str]:
    if target_cluster == "alpha":
        return policy.alpha_dependency_search_clusters
    return [target_cluster]


def cluster_allowed(target_cluster: str, is_gpu: bool, policy: PlacementPolicy) -> tuple[bool, str]:
    if is_gpu and target_cluster in policy.forbidden_gpu_clusters:
        return False, f"GPU software cannot be placed in '{target_cluster}'"
    if is_gpu and target_cluster not in policy.gpu_clusters:
        return False, f"Cluster '{target_cluster}' is not listed in gpu_clusters"
    if not is_gpu and target_cluster not in (set(policy.cpu_clusters) | set(policy.gpu_clusters)):
        return False, f"Cluster '{target_cluster}' not recognized in policy"
    return True, "allowed"


def expand_target_kind(target_kind: str, policy: PlacementPolicy) -> list[str]:
    kind = target_kind.strip().lower()
    if kind == "cpu":
        return sorted(set(policy.cpu_clusters))
    if kind == "gpu":
        return sorted(set(policy.gpu_clusters))
    raise ValueError("target_kind must be 'cpu' or 'gpu'")
