"""End-of-day indicator runner — fetch bars + compute + persist."""

from datetime import datetime, timezone

from src.alpaca.bars import fetch_daily_bars_batch
from src.db.connection import get_conn, transaction
from src.db.repos import StocksRepo, TechnicalsRepo
from src.indicators.technical import compute_all
from src.logger import logger


def run_eod_indicators(symbols: list[str] | None = None, batch_size: int = 50) -> dict[str, int]:
    """Compute & persist technical indicators.

    If symbols is None, uses all stocks from the `stocks` table.
    """
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if symbols is None:
        with get_conn() as conn:
            rows = StocksRepo(conn).list_recent(limit=500)
            symbols = [r["symbol"] for r in rows]

    if not symbols:
        logger.warning("no symbols to process")
        return {"processed": 0, "skipped": 0}

    logger.info(f"computing indicators for {len(symbols)} symbols (as_of {as_of})")

    processed = 0
    skipped = 0

    for i in range(0, len(symbols), batch_size):
        chunk = symbols[i : i + batch_size]
        bars_by_symbol = fetch_daily_bars_batch(chunk, days=260)

        with get_conn() as conn:
            with transaction(conn):
                repo = TechnicalsRepo(conn)
                for sym in chunk:
                    df = bars_by_symbol.get(sym)
                    if df is None or df.empty:
                        skipped += 1
                        continue
                    snap = compute_all(sym, df, as_of)
                    if snap is None:
                        skipped += 1
                        continue
                    repo.upsert(snap)
                    processed += 1

    counts = {"processed": processed, "skipped": skipped}
    logger.info(f"eod indicators done: {counts}")
    return counts
