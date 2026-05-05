"""Risk score — flag positions that should be avoided regardless of bullish signals.

Higher risk_score (0-100) → higher reasons to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from src.recommend.signals import SignalSnapshot

MIN_AVG_VOLUME = 500_000
MIN_PRICE = 5.0
MAX_ATR_PCT = 8.0  # ATR / close


@dataclass
class RiskAssessment:
    score: float           # 0-100
    veto: bool             # if True, never recommend regardless of signals
    reasons: list[str]


def assess_risk(
    snap: SignalSnapshot,
    avg_volume: int | None = None,
    earnings_date: date | None = None,
    today: date | None = None,
) -> RiskAssessment:
    today = today or datetime.now(timezone.utc).date()
    reasons: list[str] = []
    score = 0.0
    veto = False

    # 1. Overheated
    if (snap.heat_score is not None and snap.heat_score > 90
            and snap.rsi_14 is not None and snap.rsi_14 > 80):
        score += 50
        reasons.append("overheated (heat>90 + RSI>80)")
        veto = True

    # 2. Earnings within 3 trading days
    if earnings_date and 0 <= (earnings_date - today).days <= 4:
        score += 40
        reasons.append(f"earnings in {(earnings_date - today).days} day(s)")
        veto = True

    # 3. Liquidity
    if avg_volume is not None and avg_volume < MIN_AVG_VOLUME:
        score += 25
        reasons.append(f"low liquidity (avg_vol={avg_volume:,} < {MIN_AVG_VOLUME:,})")

    # 4. Penny-stock-ish
    if snap.close is not None and snap.close < MIN_PRICE:
        score += 30
        reasons.append(f"price < ${MIN_PRICE} (current ${snap.close:.2f})")

    # 5. Crazy volatility
    if snap.atr_14 is not None and snap.close is not None and snap.close > 0:
        atr_pct = snap.atr_14 / snap.close * 100
        if atr_pct > MAX_ATR_PCT:
            score += 20
            reasons.append(f"high ATR% ({atr_pct:.1f}% > {MAX_ATR_PCT}%)")

    # 6. Below 50MA when also above heat = stretched short setup
    if (snap.close is not None and snap.sma_50 is not None
            and snap.close < snap.sma_50 * 0.92):
        score += 15
        reasons.append("close < 92% of 50MA (broken trend)")

    return RiskAssessment(score=min(score, 100), veto=veto, reasons=reasons)
