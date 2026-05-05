"""Insider trading score — derive a 0-100 signal from recent Form 4 transactions.

Open-market purchases (P) are the highest-signal: an executive paid their own
money to buy shares. Open-market sales (S) are weaker bearish signal because
many sales are scheduled (10b5-1), tax events, or option exercises.

Score 0-100; > 50 = bullish insider activity; < 50 = bearish.
"""

from __future__ import annotations

from src.db.connection import get_conn
from src.scoring.normalize import clamp


def insider_buy_sell_value(symbol: str, since_iso_date: str) -> tuple[float, float]:
    """Sum total_value of open-market buys (P) and sells (S) since a date."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN transaction_code='P' AND total_value > 0 THEN total_value ELSE 0 END), 0) AS buy_val,
                COALESCE(SUM(CASE WHEN transaction_code='S' AND total_value < 0 THEN -total_value ELSE 0 END), 0) AS sell_val
            FROM insider_trades
            WHERE symbol = ? AND transaction_date >= ?
            """,
            (symbol, since_iso_date),
        ).fetchone()
    return float(row["buy_val"] or 0), float(row["sell_val"] or 0)


def insider_score(symbol: str, since_iso_date: str) -> float | None:
    """0-100. None if no insider activity in window."""
    buy, sell = insider_buy_sell_value(symbol, since_iso_date)
    total = buy + sell
    if total == 0:
        return None
    # Bias buys: a $1M buy is more bullish than a $1M sale is bearish.
    # Use weighted ratio: 2× weight on buys.
    weighted_buy = 2.0 * buy
    weighted_total = weighted_buy + sell
    if weighted_total == 0:
        return None
    raw = weighted_buy / weighted_total  # 0..1
    return clamp(raw * 100, 0, 100)
