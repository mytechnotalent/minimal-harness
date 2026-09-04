"""Data models used by the adversarial harness search."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Candidate:
    """Represent one proposed harness and its evaluation artifacts."""

    candidate_id: str
    source: str
    proposal: str
    score: float | None = None
    review: dict[str, Any] = field(default_factory=dict)
    dynamic_test: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchConfig:
    """Configure search iterations, gates, and the target score."""

    iterations: int = 5
    proposers_per_iteration: int = 2
    target_score: float = 1.0
    docker_image: str = "python:3.12-slim"
    use_docker: bool = True
    use_web_search: bool = True


@dataclass(frozen=True)
class SearchResult:
    """Report the selected candidate and the complete search outcome."""

    winner: Candidate | None
    history: tuple[Candidate, ...]
    stopped_on_target: bool
    stop_reason: str
