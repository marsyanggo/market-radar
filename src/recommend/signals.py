"""Independent bullish/bearish signal scorers (each 0-100).

Used by engine_v2 to count resonance — how many signals point the same way.
A scoring function returns None if it lacks data, otherwise 0-100 where:
  - score > 60 = bullish
  - score < 40 = bearish
  - 40-60 = neutral
"""

from __future__ import annotations

from dataclasses import dataclass

from src.scoring.normalize import clamp, linear


@dataclass
class SignalSnapshot:
    """Inputs from various tables for one (symbol, as_of) pair."""
    heat_score: float | None = None
    smart_money_score: float | None = None
    rsi_14: float | None = None
    close: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    atr_14: float | None = None
    volume_vs_adv: float | None = None
    pct_from_high_52w: float | None = None
    put_call_ratio: float | None = None
    iv_skew_25d: float | None = None


# ---------- individual signal scorers ----------

def heat_signal(snap: SignalSnapshot) -> float | None:
    """Heat is a composite metric. Use as-is, but clamp to (0, 100)."""
    if snap.heat_score is None:
        return None
    return clamp(snap.heat_score, 0, 100)


def smart_money_signal(snap: SignalSnapshot) -> float | None:
    return snap.smart_money_score


def technical_alignment_signal(snap: SignalSnapshot) -> float | None:
    """Are price + MAs aligned for an uptrend? close > sma20 > sma50 → 100."""
    if snap.close is None or snap.sma_20 is None or snap.sma_50 is None:
        return None
    score = 50.0
    if snap.close > snap.sma_20:
        score += 17
    elif snap.close < snap.sma_20:
        score -= 17
    if snap.sma_20 > snap.sma_50:
        score += 17
    elif snap.sma_20 < snap.sma_50:
        score -= 17
    if snap.sma_200 is not None:
        if snap.sma_50 > snap.sma_200:
            score += 16
        elif snap.sma_50 < snap.sma_200:
            score -= 16
    return clamp(score, 0, 100)


def rsi_signal(snap: SignalSnapshot) -> float | None:
    """RSI sweet spot 50-65 = bullish-but-not-overbought.
    < 30 = oversold (could be reversal long, but bearish in trend);
    > 75 = overbought.
    Map: 30-50 → 0-50, 50-65 → 50-100, 65-80 → 100→50, >80 → 0.
    """
    if snap.rsi_14 is None:
        return None
    r = snap.rsi_14
    if r < 30:
        return clamp(linear(r, 20, 30) * 0.4, 0, 100)  # 0..40
    if r < 50:
        return clamp(linear(r, 30, 50) * 0.5 + 25, 25, 75)  # 25..75
    if r <= 65:
        return clamp(linear(r, 50, 65) * 0.5 + 50, 50, 100)  # 50..100
    if r <= 80:
        return clamp(100 - linear(r, 65, 80) * 0.5, 50, 100)  # 100..50
    # r > 80: linear from 50 at r=80 down to 0 at r=100
    return clamp(linear(100 - r, 0, 20) * 0.5, 0, 50)


def volume_confirmation_signal(snap: SignalSnapshot) -> float | None:
    """volume_vs_adv 1.0 = neutral (50), 2.0+ = strong (100), 0.5 = weak (0)."""
    if snap.volume_vs_adv is None:
        return None
    return linear(snap.volume_vs_adv, 0.5, 2.0)


def options_skew_signal(snap: SignalSnapshot) -> float | None:
    """Negative IV skew (put IV < call IV) = bullish.
    -0.05 → 100, 0 → 50, +0.10 → 0.
    """
    if snap.iv_skew_25d is None:
        return None
    return clamp(linear(0.10 - snap.iv_skew_25d, 0.0, 0.15), 0, 100)


def fifty_two_week_signal(snap: SignalSnapshot) -> float | None:
    """Distance from 52w high. Near high (>-5%) = strong, <-30% = weak."""
    if snap.pct_from_high_52w is None:
        return None
    pct = snap.pct_from_high_52w  # negative or zero
    if pct >= -5:
        return 100.0
    if pct >= -15:
        return 75.0
    if pct >= -30:
        return 50.0
    return 25.0


# ---------- aggregate ----------

ALL_SCORERS: dict[str, callable] = {
    "heat": heat_signal,
    "smart_money": smart_money_signal,
    "technical_alignment": technical_alignment_signal,
    "rsi": rsi_signal,
    "volume": volume_confirmation_signal,
    "options_skew": options_skew_signal,
    "fifty_two_week": fifty_two_week_signal,
}


def evaluate_signals(snap: SignalSnapshot) -> dict[str, float]:
    """Return {signal_name: score} for every scorer that has data."""
    out: dict[str, float] = {}
    for name, fn in ALL_SCORERS.items():
        v = fn(snap)
        if v is not None:
            out[name] = v
    return out


def count_bullish_bearish(scores: dict[str, float],
                          bullish_threshold: float = 60,
                          bearish_threshold: float = 40) -> tuple[int, int, int]:
    bullish = sum(1 for v in scores.values() if v > bullish_threshold)
    bearish = sum(1 for v in scores.values() if v < bearish_threshold)
    neutral = len(scores) - bullish - bearish
    return bullish, bearish, neutral
