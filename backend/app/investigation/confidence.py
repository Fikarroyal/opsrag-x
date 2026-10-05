"""Evidence confidence score.

hypothesis_score = w_e * evidence_support + w_t * temporal_alignment + w_p * topology_alignment
                 + w_h * historical_similarity + w_s * current_service_state + w_r * source_reliability
(weights configurable, normalised to sum 1; every component is in [0, 1]).

evidence_confidence = clamp(score * coverage_factor * ambiguity_factor, 0, 0.99)
  coverage_factor  = 0.75 + 0.25 * (successful tools / planned tools)     (failed diagnostics lower confidence)
  ambiguity_factor = 0.90 when the best hypothesis leads the runner-up by < 0.10 (competing explanations)

This is an *evidence confidence score*, NOT a calibrated statistical probability, and it never reaches 100%.
"""

from __future__ import annotations

from dataclasses import dataclass

COMPONENTS = ("evidence", "temporal", "topology", "history", "state", "source")


def hypothesis_score(components: dict[str, float], weights: dict[str, float]) -> float:
    s = sum(weights[k] * max(0.0, min(1.0, components.get(k, 0.0))) for k in COMPONENTS)
    return round(max(0.0, min(1.0, s)), 4)


def coverage_factor(tools_ok: int, tools_planned: int) -> float:
    return 0.75 + 0.25 * (tools_ok / tools_planned if tools_planned else 1.0)


def ambiguity_factor(top: float, runner_up: float | None, margin: float = 0.10) -> float:
    return 0.90 if runner_up is not None and (top - runner_up) < margin else 1.0


@dataclass
class ConfidenceResult:
    score: float
    confidence: float
    coverage: float
    ambiguity: float


def evidence_confidence(
    score: float, tools_ok: int, tools_planned: int, top: float, runner_up: float | None, *, is_top: bool
) -> ConfidenceResult:
    cov = coverage_factor(tools_ok, tools_planned)
    amb = ambiguity_factor(top, runner_up) if is_top else 1.0
    return ConfidenceResult(score, round(max(0.0, min(0.99, score * cov * amb)), 4), round(cov, 3), amb)
