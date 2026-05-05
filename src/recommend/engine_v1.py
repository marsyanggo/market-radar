"""Phase 3 MVP recommendation rules — heat + technicals only.

Categories:
  strong_long: Heat > 80 AND RSI < 70 AND close > sma_20
  watch:       Heat > 70 AND RSI < 70
  avoid:       Heat > 90 AND RSI > 80   (overheated)

This is intentionally conservative for MVP. Phase 6 introduces multi-signal
resonance with smart-money + sentiment + risk filters.
"""

from dataclasses import dataclass


@dataclass
class Recommendation:
    symbol: str
    as_of: str
    category: str  # 'strong_long' | 'watch' | 'avoid'
    heat_score: float
    rsi_14: float | None
    close: float | None
    sma_20: float | None
    reason: dict


def classify(
    symbol: str,
    as_of: str,
    heat_score: float,
    rsi_14: float | None,
    close: float | None,
    sma_20: float | None,
) -> Recommendation | None:
    """Return a Recommendation or None if no rule fires."""
    above_sma20 = close is not None and sma_20 is not None and close > sma_20

    # Avoid (overheated)
    if heat_score > 90 and rsi_14 is not None and rsi_14 > 80:
        return Recommendation(
            symbol=symbol,
            as_of=as_of,
            category="avoid",
            heat_score=heat_score,
            rsi_14=rsi_14,
            close=close,
            sma_20=sma_20,
            reason={"signals": ["overheated"], "rsi": rsi_14, "heat": heat_score},
        )

    # Strong long
    if heat_score > 80 and rsi_14 is not None and rsi_14 < 70 and above_sma20:
        return Recommendation(
            symbol=symbol,
            as_of=as_of,
            category="strong_long",
            heat_score=heat_score,
            rsi_14=rsi_14,
            close=close,
            sma_20=sma_20,
            reason={
                "signals": ["heat", "rsi_ok", "above_sma20"],
                "rsi": rsi_14,
                "heat": heat_score,
            },
        )

    # Watch
    if heat_score > 70 and (rsi_14 is None or rsi_14 < 70):
        return Recommendation(
            symbol=symbol,
            as_of=as_of,
            category="watch",
            heat_score=heat_score,
            rsi_14=rsi_14,
            close=close,
            sma_20=sma_20,
            reason={"signals": ["heat"], "rsi": rsi_14, "heat": heat_score},
        )

    return None
