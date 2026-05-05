"""Combine news LLM sentiment + StockTwits ratio into a single 0-100 score.

Sentiment 0-100 → higher = more bullish.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.scoring.normalize import clamp, linear


@dataclass
class SentimentBreakdown:
    symbol: str
    news_avg: float | None      # -1..+1
    news_count: int
    stocktwits_ratio: float | None  # 0..1 (bullish / (bullish+bearish))
    score: float | None         # 0..100, None if no signal


def news_score(avg: float | None) -> float | None:
    if avg is None:
        return None
    return linear(avg, -1.0, 1.0)


def stocktwits_score(ratio: float | None) -> float | None:
    """Bullish ratio 0.5 = neutral (50). Reverse: 1.0 = bullish (100), 0.0 = bearish (0)."""
    if ratio is None:
        return None
    return clamp(ratio * 100, 0, 100)


def compute_sentiment(
    symbol: str,
    news_avg: float | None,
    news_count: int,
    stocktwits_ratio: float | None,
) -> SentimentBreakdown:
    """Weighted: news 0.6 + stocktwits 0.4. Falls back to whichever exists."""
    components = []
    n = news_score(news_avg)
    s = stocktwits_score(stocktwits_ratio)

    if n is not None:
        components.append((n, 0.6))
    if s is not None:
        components.append((s, 0.4))

    if not components:
        score = None
    else:
        total_w = sum(w for _, w in components)
        score = round(sum(v * w for v, w in components) / total_w, 2)

    return SentimentBreakdown(
        symbol=symbol,
        news_avg=news_avg,
        news_count=news_count,
        stocktwits_ratio=stocktwits_ratio,
        score=score,
    )
