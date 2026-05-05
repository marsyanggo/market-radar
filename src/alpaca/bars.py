"""Fetch OHLCV bars from Alpaca."""

from datetime import datetime, timedelta, timezone

import pandas as pd
from alpaca.data.enums import DataFeed
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from configs.settings import settings
from src.alpaca.client import get_stock_data_client, with_retry
from src.logger import logger


def _feed() -> DataFeed:
    """Map settings.alpaca_data_feed string to DataFeed enum."""
    feed_str = settings.alpaca_data_feed.lower()
    return {
        "iex": DataFeed.IEX,
        "sip": DataFeed.SIP,
        "otc": DataFeed.OTC,
    }.get(feed_str, DataFeed.IEX)


@with_retry(max_attempts=3)
def fetch_daily_bars(
    symbol: str,
    days: int = 260,
    end: datetime | None = None,
) -> pd.DataFrame:
    """Fetch daily OHLCV bars for a single symbol.

    Returns df indexed by timestamp (UTC) with columns:
      open, high, low, close, volume, trade_count, vwap
    """
    end = end or datetime.now(timezone.utc)
    start = end - timedelta(days=int(days * 1.5) + 30)  # buffer for weekends/holidays

    client = get_stock_data_client()
    res = client.get_stock_bars(
        StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            feed=_feed(),
        )
    )
    df = res.df
    if df.empty:
        logger.warning(f"no bars returned for {symbol}")
        return df

    # alpaca returns multi-index (symbol, timestamp); flatten to single index
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbol, level="symbol")

    df = df.tail(days)
    return df


@with_retry(max_attempts=3)
def fetch_daily_bars_batch(
    symbols: list[str],
    days: int = 260,
    end: datetime | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch daily bars for many symbols in one request."""
    if not symbols:
        return {}
    end = end or datetime.now(timezone.utc)
    start = end - timedelta(days=int(days * 1.5) + 30)

    client = get_stock_data_client()
    res = client.get_stock_bars(
        StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            feed=_feed(),
        )
    )
    df = res.df
    if df.empty:
        logger.warning(f"no bars returned for {len(symbols)} symbols")
        return {}

    out: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        if sym in df.index.get_level_values("symbol"):
            sub = df.xs(sym, level="symbol").tail(days)
            out[sym] = sub
    logger.info(f"fetched bars for {len(out)}/{len(symbols)} symbols")
    return out
