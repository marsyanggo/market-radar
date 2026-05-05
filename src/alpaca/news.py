"""News fetcher — REST API for recent news, persisted with dedup by external_id.

Stream version is intentionally omitted — Alpaca free tier limits to 1 WS
connection (held by AI_trader), and news polling at 5-10 min cadence is
plenty for daily-recommendation latency.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest

from configs.settings import settings
from src.alpaca.client import with_retry
from src.db.connection import get_conn, transaction
from src.db.repos import NewsItem, NewsRepo, StocksRepo
from src.logger import logger

DEFAULT_POLL_INTERVAL = 600.0  # 10 minutes


def _client() -> NewsClient:
    return NewsClient(settings.alpaca_api_key, settings.alpaca_secret_key)


def load_default_symbols(limit: int = 100) -> list[str]:
    with get_conn() as conn:
        rows = StocksRepo(conn).list_recent(limit=limit)
    return [r["symbol"] for r in rows]


@with_retry(max_attempts=3)
def fetch_news(
    symbols: list[str] | None,
    since: datetime,
    until: datetime | None = None,
    limit: int = 50,
) -> list[NewsItem]:
    """Fetch news items from Alpaca News API.

    If symbols is None, returns market-wide news.
    """
    until = until or datetime.now(timezone.utc)
    req = NewsRequest(
        symbols=",".join(symbols) if symbols else None,
        start=since,
        end=until,
        limit=limit,
    )
    res = _client().get_news(req)
    raw_list = res.data.get("news", [])

    items: list[NewsItem] = []
    for n in raw_list:
        items.append(
            NewsItem(
                external_id=str(n.id) if n.id is not None else None,
                url=n.url,
                headline=n.headline or "",
                source=n.source,
                author=n.author,
                summary=n.summary,
                content=n.content,
                symbols=list(n.symbols) if n.symbols else [],
                ts=n.created_at.astimezone(timezone.utc).isoformat()
                if isinstance(n.created_at, datetime)
                else str(n.created_at),
            )
        )
    return items


def persist_news(items: list[NewsItem]) -> int:
    if not items:
        return 0
    inserted = 0
    with get_conn() as conn:
        with transaction(conn):
            repo = NewsRepo(conn)
            for it in items:
                if repo.insert(it) is not None:
                    inserted += 1
    return inserted


def fetch_and_persist(
    symbols: list[str] | None = None,
    hours_back: float = 24,
    limit: int = 50,
) -> dict[str, int]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    items = fetch_news(symbols, since=since, limit=limit)
    inserted = persist_news(items)
    counts = {"fetched": len(items), "inserted": inserted, "skipped_dupes": len(items) - inserted}
    logger.info(f"news fetch: {counts}")
    return counts


def run_news_poller(
    symbols: list[str] | None = None,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    max_cycles: int | None = None,
) -> None:
    """Long-running news poller. Re-fetches the trailing window each cycle;
    dedup happens at the DB layer via external_id UNIQUE constraint.
    """
    cursor_hours = max(2.0, poll_interval / 3600 * 2)  # 2× interval, min 2 hours
    cycles = 0
    logger.info(
        f"news poller started: symbols={'all' if symbols is None else len(symbols)}, "
        f"interval={poll_interval}s"
    )
    while True:
        try:
            fetch_and_persist(symbols=symbols, hours_back=cursor_hours, limit=100)
        except Exception:
            logger.exception("news poll cycle failed")
        cycles += 1
        if max_cycles and cycles >= max_cycles:
            logger.info(f"news poller stopped after {cycles} cycles")
            return
        time.sleep(poll_interval)
