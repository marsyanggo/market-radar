"""REST polling fallback for block-trade detection.

Use this when the WebSocket connection slot is taken (e.g., AI_trader's
price_stream is running). Polls `get_stock_trades` for each symbol on an
interval, filters blocks, classifies side via latest quote, dedupes by
(symbol, ts, price, size, exchange), and persists.

Trade-offs vs. stream:
  + can run alongside another WebSocket consumer (Alpaca limits live WS to 1)
  + simpler operationally (no asyncio, no signals)
  - higher latency (~ poll_interval seconds)
  - more API calls (1 trades-call + 1 quote-call per symbol per cycle)
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from alpaca.data.requests import StockLatestQuoteRequest, StockTradesRequest

from src.alpaca.bars import _feed
from src.alpaca.client import get_stock_data_client, with_retry
from src.alpaca.trades_stream import QuoteSnapshot, classify_side
from src.db.connection import get_conn, transaction
from src.db.repos import BlockTrade, TradesRepo
from src.logger import logger

DEFAULT_POLL_INTERVAL = 60.0  # seconds


@with_retry(max_attempts=3)
def fetch_recent_trades(symbol: str, since: datetime, until: datetime) -> list[Any]:
    client = get_stock_data_client()
    res = client.get_stock_trades(
        StockTradesRequest(
            symbol_or_symbols=symbol,
            start=since,
            end=until,
            feed=_feed(),
        )
    )
    return list(res.data.get(symbol, []))


@with_retry(max_attempts=3)
def fetch_latest_quote(symbol: str) -> QuoteSnapshot | None:
    client = get_stock_data_client()
    res = client.get_stock_latest_quote(
        StockLatestQuoteRequest(symbol_or_symbols=symbol, feed=_feed())
    )
    q = res.get(symbol)
    if q is None or not q.bid_price or not q.ask_price:
        return None
    return QuoteSnapshot(bid=float(q.bid_price), ask=float(q.ask_price), ts=q.timestamp)


def poll_blocks_once(
    symbols: list[str],
    since: datetime,
    until: datetime,
    block_threshold: int = 10_000,
    seen: set[tuple] | None = None,
) -> tuple[int, set[tuple]]:
    """Poll each symbol once for trades in [since, until). Returns (n_persisted, updated_seen)."""
    seen = seen if seen is not None else set()
    new_blocks: list[BlockTrade] = []

    for sym in symbols:
        trades = fetch_recent_trades(sym, since, until)
        if not trades:
            continue

        snap = fetch_latest_quote(sym)
        for t in trades:
            size = int(t.size or 0)
            if size < block_threshold:
                continue
            ts_iso = (
                t.timestamp.astimezone(timezone.utc).isoformat()
                if isinstance(t.timestamp, datetime)
                else str(t.timestamp)
            )
            key = (sym, ts_iso, float(t.price), size, str(t.exchange) if t.exchange else None)
            if key in seen:
                continue
            seen.add(key)
            new_blocks.append(
                BlockTrade(
                    symbol=sym,
                    size=size,
                    price=float(t.price),
                    side=classify_side(float(t.price), snap),
                    exchange=str(t.exchange) if t.exchange else None,
                    ts=ts_iso,
                )
            )

    if new_blocks:
        with get_conn() as conn:
            with transaction(conn):
                TradesRepo(conn).insert_many(new_blocks)
        logger.info(f"polled {len(symbols)} symbols → persisted {len(new_blocks)} new blocks")
    return len(new_blocks), seen


def run_poller(
    symbols: list[str],
    block_threshold: int = 10_000,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    max_cycles: int | None = None,
) -> None:
    """Long-running poll loop. Set max_cycles for tests/smoke runs."""
    if not symbols:
        raise ValueError("symbols list is empty")

    cursor = datetime.now(timezone.utc) - timedelta(seconds=poll_interval)
    seen: set[tuple] = set()
    cycles = 0

    logger.info(
        f"poller started: {len(symbols)} symbols, threshold={block_threshold:,}, "
        f"interval={poll_interval}s"
    )
    while True:
        cycle_start = time.monotonic()
        until = datetime.now(timezone.utc)
        try:
            poll_blocks_once(symbols, since=cursor, until=until,
                             block_threshold=block_threshold, seen=seen)
        except Exception:
            logger.exception("poll cycle failed")

        cursor = until
        cycles += 1
        if max_cycles and cycles >= max_cycles:
            logger.info(f"poller stopped after {cycles} cycles")
            return

        elapsed = time.monotonic() - cycle_start
        sleep_for = max(1.0, poll_interval - elapsed)
        time.sleep(sleep_for)
