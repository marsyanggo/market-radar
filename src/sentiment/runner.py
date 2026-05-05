"""Sentiment pipeline: score news with LLM (if key), fetch StockTwits, persist daily summary."""

from __future__ import annotations

from datetime import datetime, timezone

from src.db.connection import get_conn, transaction
from src.logger import logger
from src.scoring.sentiment_score import compute_sentiment
from src.sentiment.news_llm import score_recent_news
from src.sentiment.stocktwits import fetch_many


def _persist(symbol: str, as_of: str, breakdown, news_count: int, st) -> None:
    with get_conn() as conn:
        with transaction(conn):
            conn.execute(
                """
                INSERT INTO sentiment_daily
                  (symbol, as_of, news_count, news_avg_sentiment,
                   stocktwits_bullish, stocktwits_bearish, stocktwits_bullish_ratio,
                   sentiment_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, as_of) DO UPDATE SET
                  news_count=excluded.news_count,
                  news_avg_sentiment=excluded.news_avg_sentiment,
                  stocktwits_bullish=excluded.stocktwits_bullish,
                  stocktwits_bearish=excluded.stocktwits_bearish,
                  stocktwits_bullish_ratio=excluded.stocktwits_bullish_ratio,
                  sentiment_score=excluded.sentiment_score
                """,
                (
                    symbol, as_of,
                    news_count, breakdown.news_avg,
                    st.bullish if st else None,
                    st.bearish if st else None,
                    breakdown.stocktwits_ratio,
                    breakdown.score,
                ),
            )


def run_sentiment_pipeline(
    symbols: list[str],
    as_of: str,
    window_start_iso: str,
    score_news: bool = True,
    fetch_stocktwits: bool = True,
    news_limit: int = 100,
) -> dict[str, int]:
    """End-to-end: optionally LLM-score news → fetch StockTwits → write daily summary."""
    summary = {"news_scored": 0, "stocktwits": 0, "persisted": 0}

    if score_news:
        try:
            summary["news_scored"] = score_recent_news(limit=news_limit)
        except Exception:
            logger.exception("LLM news scoring failed (non-fatal)")

    st_data = fetch_many(symbols) if fetch_stocktwits else {}
    summary["stocktwits"] = len(st_data)

    with get_conn() as conn:
        for sym in symbols:
            row = conn.execute(
                """
                SELECT AVG(sentiment_score) AS avg, COUNT(*) AS n
                FROM news
                WHERE ts >= ? AND symbols LIKE ? AND sentiment_score IS NOT NULL
                """,
                (window_start_iso, f'%"{sym}"%'),
            ).fetchone()
            news_avg = row["avg"]
            news_count = row["n"] or 0
            st = st_data.get(sym.upper())

            breakdown = compute_sentiment(
                symbol=sym,
                news_avg=news_avg,
                news_count=news_count,
                stocktwits_ratio=st.bullish_ratio if st else None,
            )
            _persist(sym, as_of, breakdown, news_count, st)
            summary["persisted"] += 1

    logger.info(f"sentiment pipeline: {summary}")
    return summary


def main() -> None:
    """Standalone CLI entry — pulls symbols from stocks table."""
    from datetime import timedelta

    from src.db.repos import StocksRepo

    with get_conn() as conn:
        symbols = [r["symbol"] for r in StocksRepo(conn).list_recent(limit=50)]
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    window_start = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_sentiment_pipeline(symbols, today, window_start)
