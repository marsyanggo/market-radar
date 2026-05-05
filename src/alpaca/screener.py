"""Daily screener — fetch most actives + market movers and upsert into stocks."""

from dataclasses import dataclass
from datetime import datetime, timezone

from alpaca.data.requests import MarketMoversRequest, MostActivesRequest

from src.alpaca.client import get_screener_client, with_retry
from src.db.connection import get_conn, transaction
from src.db.repos import Stock, StocksRepo
from src.logger import logger


@dataclass
class ScreenerHit:
    symbol: str
    volume: float | None = None
    trade_count: float | None = None
    change_pct: float | None = None
    price: float | None = None


@with_retry(max_attempts=3)
def fetch_most_actives(top: int = 50) -> list[ScreenerHit]:
    """Top N most-actively-traded stocks today."""
    client = get_screener_client()
    res = client.get_most_actives(MostActivesRequest(top=top))
    hits = [
        ScreenerHit(symbol=a.symbol, volume=a.volume, trade_count=a.trade_count)
        for a in res.most_actives
    ]
    logger.info(f"fetched {len(hits)} most-actives")
    return hits


@with_retry(max_attempts=3)
def fetch_market_movers(top: int = 25) -> tuple[list[ScreenerHit], list[ScreenerHit]]:
    """Top N gainers and losers by % change. Returns (gainers, losers)."""
    client = get_screener_client()
    res = client.get_market_movers(MarketMoversRequest(top=top))
    gainers = [
        ScreenerHit(symbol=g.symbol, change_pct=g.percent_change, price=g.price)
        for g in res.gainers
    ]
    losers = [
        ScreenerHit(symbol=l.symbol, change_pct=l.percent_change, price=l.price)
        for l in res.losers
    ]
    logger.info(f"fetched {len(gainers)} gainers / {len(losers)} losers")
    return gainers, losers


def run_daily_screener(
    most_actives_top: int = 50,
    movers_top: int = 25,
) -> dict[str, int]:
    """Fetch screener data and upsert into `stocks`. Returns counts."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    actives = fetch_most_actives(most_actives_top)
    gainers, losers = fetch_market_movers(movers_top)

    seen: dict[str, Stock] = {}
    for hit in [*actives, *gainers, *losers]:
        if hit.symbol not in seen:
            seen[hit.symbol] = Stock(symbol=hit.symbol, last_seen_at=now_iso)

    with get_conn() as conn:
        with transaction(conn):
            n = StocksRepo(conn).upsert_many(list(seen.values()))

    counts = {
        "most_actives": len(actives),
        "gainers": len(gainers),
        "losers": len(losers),
        "unique_upserted": n,
    }
    logger.info(f"screener done: {counts}")
    return counts
