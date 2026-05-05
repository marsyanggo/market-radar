"""Live block-trade detector — subscribes to trades + quotes via WebSocket
and persists trades whose size meets the block threshold.

Side determination uses the latest NBBO quote in memory (Lee-Ready style):
  trade.price >= ask     → buy
  trade.price <= bid     → sell
  trade > midpoint       → buy
  trade < midpoint       → sell
  no quote yet           → unknown
"""

from __future__ import annotations

import asyncio
import signal
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from alpaca.data.live.stock import StockDataStream
from alpaca.data.models import Quote, Trade

from configs.settings import settings
from src.alpaca.bars import _feed
from src.db.connection import get_conn, transaction
from src.db.repos import BlockTrade, StocksRepo, TradesRepo
from src.logger import logger


def load_default_symbols(limit: int = 50) -> list[str]:
    with get_conn() as conn:
        rows = StocksRepo(conn).list_recent(limit=limit)
    return [r["symbol"] for r in rows]

DEFAULT_BLOCK_THRESHOLD = 10_000  # shares
DEFAULT_FLUSH_INTERVAL = 5.0       # seconds


@dataclass
class QuoteSnapshot:
    bid: float
    ask: float
    ts: datetime


def classify_side(price: float, quote: QuoteSnapshot | None) -> str:
    """Return 'buy', 'sell', or 'unknown' based on price relative to NBBO."""
    if quote is None or quote.bid <= 0 or quote.ask <= 0 or quote.ask < quote.bid:
        return "unknown"
    if price >= quote.ask:
        return "buy"
    if price <= quote.bid:
        return "sell"
    mid = (quote.bid + quote.ask) / 2
    if price > mid:
        return "buy"
    if price < mid:
        return "sell"
    return "unknown"


class BlockTradeCollector:
    """Buffer block trades in memory; flush to SQLite on a timer."""

    def __init__(
        self,
        symbols: list[str],
        block_threshold: int = DEFAULT_BLOCK_THRESHOLD,
        flush_interval: float = DEFAULT_FLUSH_INTERVAL,
    ) -> None:
        self.symbols = symbols
        self.block_threshold = block_threshold
        self.flush_interval = flush_interval
        self.latest_quotes: dict[str, QuoteSnapshot] = {}
        self.buffer: list[BlockTrade] = []
        self.stats = defaultdict(int)
        self._stop = asyncio.Event()

    async def on_quote(self, quote: Quote) -> None:
        if quote.bid_price and quote.ask_price:
            self.latest_quotes[quote.symbol] = QuoteSnapshot(
                bid=float(quote.bid_price),
                ask=float(quote.ask_price),
                ts=quote.timestamp,
            )

    async def on_trade(self, trade: Trade) -> None:
        self.stats["trades_seen"] += 1
        size = int(trade.size or 0)
        if size < self.block_threshold:
            return

        snap = self.latest_quotes.get(trade.symbol)
        side = classify_side(float(trade.price), snap)
        self.stats[f"side_{side}"] += 1

        ts = (
            trade.timestamp.astimezone(timezone.utc).isoformat()
            if isinstance(trade.timestamp, datetime)
            else str(trade.timestamp)
        )

        self.buffer.append(
            BlockTrade(
                symbol=trade.symbol,
                size=size,
                price=float(trade.price),
                side=side,
                exchange=str(trade.exchange) if trade.exchange else None,
                ts=ts,
            )
        )
        logger.debug(f"block: {trade.symbol} {size:,}@{trade.price} {side}")

    async def flush_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.flush_interval)
            except asyncio.TimeoutError:
                pass
            await self._flush()

    async def _flush(self) -> None:
        if not self.buffer:
            return
        batch, self.buffer = self.buffer, []
        with get_conn() as conn:
            with transaction(conn):
                n = TradesRepo(conn).insert_many(batch)
        self.stats["blocks_persisted"] += n
        logger.info(
            f"flushed {n} block trades  (seen={self.stats['trades_seen']}, "
            f"buy={self.stats['side_buy']}, sell={self.stats['side_sell']}, "
            f"unknown={self.stats['side_unknown']})"
        )

    def stop(self) -> None:
        self._stop.set()


async def run_block_stream(
    symbols: list[str],
    block_threshold: int = DEFAULT_BLOCK_THRESHOLD,
    flush_interval: float = DEFAULT_FLUSH_INTERVAL,
) -> None:
    if not symbols:
        raise ValueError("symbols list is empty")

    stream = StockDataStream(
        settings.alpaca_api_key,
        settings.alpaca_secret_key,
        feed=_feed(),
    )
    collector = BlockTradeCollector(symbols, block_threshold, flush_interval)

    stream.subscribe_trades(collector.on_trade, *symbols)
    stream.subscribe_quotes(collector.on_quote, *symbols)

    logger.info(
        f"block stream subscribed to {len(symbols)} symbols "
        f"(threshold={block_threshold:,} shares, flush={flush_interval}s)"
    )

    loop = asyncio.get_running_loop()

    def _handle_signal() -> None:
        logger.info("shutdown signal received")
        collector.stop()
        asyncio.create_task(stream.stop_ws())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            pass

    flusher = asyncio.create_task(collector.flush_loop())
    try:
        await stream._run_forever()
    finally:
        collector.stop()
        await collector._flush()
        flusher.cancel()
