"""Recommendation engine v2 — multi-signal resonance + risk gating.

Decision flow:
  1. Compute every available signal (0-100)
  2. Count bullish vs bearish (resonance)
  3. Run risk assessment — veto overrides any positive signal
  4. Map (bullish count, bearish count) to category

Categories:
  strong_long: ≥4 bullish, ≤1 bearish, no veto, weighted_score ≥ 65
  watch:       ≥3 bullish, no veto
  avoid:       overheated veto OR (≥3 bearish AND high heat ≥ 60)
  none:        no resonance
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.recommend.risk_score import RiskAssessment, assess_risk
from src.recommend.signals import (
    SignalSnapshot,
    count_bullish_bearish,
    evaluate_signals,
)

WEIGHTS: dict[str, float] = {
    "heat": 0.16,
    "smart_money": 0.16,
    "technical_alignment": 0.12,
    "rsi": 0.07,
    "volume": 0.07,
    "options_skew": 0.10,
    "sentiment": 0.11,
    "insider": 0.10,
    "fifty_two_week": 0.11,
}


@dataclass
class RecommendationV2:
    symbol: str
    as_of: str
    category: str  # strong_long / watch / avoid / none
    signals: dict[str, float] = field(default_factory=dict)
    bullish_count: int = 0
    bearish_count: int = 0
    weighted_score: float = 0.0
    risk: RiskAssessment | None = None
    reason_signals: list[str] = field(default_factory=list)


def _weighted_score(scores: dict[str, float]) -> float:
    if not scores:
        return 0.0
    weighted_sum = sum(scores[k] * WEIGHTS[k] for k in scores if k in WEIGHTS)
    weight_sum = sum(WEIGHTS[k] for k in scores if k in WEIGHTS)
    if weight_sum == 0:
        return 0.0
    return weighted_sum / weight_sum


def classify(
    symbol: str,
    as_of: str,
    snap: SignalSnapshot,
    avg_volume: int | None = None,
    earnings_date=None,
) -> RecommendationV2:
    scores = evaluate_signals(snap)
    bullish, bearish, _ = count_bullish_bearish(scores)
    weighted = _weighted_score(scores)
    risk = assess_risk(snap, avg_volume=avg_volume, earnings_date=earnings_date)

    bullish_signals = [k for k, v in scores.items() if v > 60]
    bearish_signals = [k for k, v in scores.items() if v < 40]

    rec = RecommendationV2(
        symbol=symbol,
        as_of=as_of,
        category="none",
        signals=scores,
        bullish_count=bullish,
        bearish_count=bearish,
        weighted_score=round(weighted, 2),
        risk=risk,
        reason_signals=bullish_signals,
    )

    # Avoid (vetoed or strongly bearish)
    if risk.veto:
        rec.category = "avoid"
        rec.reason_signals = risk.reasons
        return rec
    if bearish >= 3 and snap.heat_score is not None and snap.heat_score >= 60:
        rec.category = "avoid"
        rec.reason_signals = bearish_signals
        return rec

    # Strong long
    if bullish >= 4 and bearish <= 1 and weighted >= 65:
        rec.category = "strong_long"
        return rec

    # Watch
    if bullish >= 3:
        rec.category = "watch"
        return rec

    return rec
