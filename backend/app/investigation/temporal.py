"""Temporal reasoning primitives shared by RAG retrieval and evidence correlation.

temporal_score():
    score = exp(-lambda * |dt|),   lambda = ln(2) / half_life
So an item whose time difference equals one half-life has score 0.5, two half-lives 0.25, etc.
The half-life is domain specific:
  * historical incidents: days (default 30 d)      -> recent incidents weigh more
  * SOP versions:         days (default 180 d)     -> newer effective versions weigh slightly more
  * log evidence:         minutes (default 10 min) -> events close to the incident onset weigh more
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

SECONDS_PER_DAY = 86400.0

BEFORE, DURING, AFTER, UNRELATED = ("before_incident", "during_incident", "after_incident", "unrelated")


def decay_lambda(half_life_seconds: float) -> float:
    if half_life_seconds <= 0:
        raise ValueError("half_life_seconds must be > 0")
    return math.log(2.0) / half_life_seconds


def temporal_score(delta_seconds: float, half_life_seconds: float) -> float:
    """Exponential time-decay in [0, 1]. Symmetric in the sign of delta (closeness in time)."""
    return math.exp(-decay_lambda(half_life_seconds) * abs(delta_seconds))


def temporal_score_between(a: datetime, b: datetime, half_life_seconds: float) -> float:
    return temporal_score((a - b).total_seconds(), half_life_seconds)


def temporal_relation(
    event_time: datetime, incident_time: datetime, *, before_margin_s: int = 60, during_after_s: int = 300, unrelated_after_s: int = 3600
) -> str:
    """Classify an event relative to incident onset T.

    before_incident : t < T - 60 s
    during_incident : T - 60 s <= t <= T + 5 min
    after_incident  : T + 5 min < t <= T + 60 min
    unrelated       : farther than 60 min from T (either direction)
    """
    delta = (event_time - incident_time).total_seconds()
    if abs(delta) > unrelated_after_s:
        return UNRELATED
    if delta < -before_margin_s:
        return BEFORE
    if delta <= during_after_s:
        return DURING
    return AFTER


def window(incident_time: datetime, minutes: int) -> tuple[datetime, datetime]:
    return incident_time - timedelta(minutes=minutes), incident_time + timedelta(minutes=minutes)
