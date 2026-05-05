"""StockTwits public API — fetch recent symbol stream and count Bullish/Bearish tags.

Endpoint: https://api.stocktwits.com/api/2/streams/symbol/{SYMBOL}.json
No auth required for read-only public streams. Rate-limited (~200 req/hour);
poll modestly.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from src.logger import logger

API = "https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"


@dataclass
class StockTwitsSentiment:
    symbol: str
    bullish: int
    bearish: int
    neutral_or_untagged: int
    total_messages: int

    @property
    def bullish_ratio(self) -> float | None:
        tagged = self.bullish + self.bearish
        if tagged == 0:
            return None
        return self.bullish / tagged


def fetch_symbol_sentiment(symbol: str, timeout: float = 8.0) -> StockTwitsSentiment | None:
    """Fetch recent messages for a symbol and tally Bullish/Bearish tags.

    Returns None on HTTP / parse failure (logged, non-fatal).
    """
    url = API.format(symbol=symbol.upper())
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers={"User-Agent": "market-radar/0.1"})
        if resp.status_code == 404:
            return None
        if not resp.is_success:
            logger.warning(f"stocktwits {symbol}: HTTP {resp.status_code}")
            return None
        data = resp.json()
    except Exception:
        logger.exception(f"stocktwits {symbol} request failed")
        return None

    messages = data.get("messages") or []
    bullish = bearish = neutral = 0
    for m in messages:
        ent = m.get("entities") or {}
        sent = ent.get("sentiment")
        basic = (sent or {}).get("basic")
        if basic == "Bullish":
            bullish += 1
        elif basic == "Bearish":
            bearish += 1
        else:
            neutral += 1

    return StockTwitsSentiment(
        symbol=symbol.upper(),
        bullish=bullish,
        bearish=bearish,
        neutral_or_untagged=neutral,
        total_messages=len(messages),
    )


def fetch_many(symbols: list[str]) -> dict[str, StockTwitsSentiment]:
    out: dict[str, StockTwitsSentiment] = {}
    for sym in symbols:
        s = fetch_symbol_sentiment(sym)
        if s is not None:
            out[sym.upper()] = s
    logger.info(f"stocktwits fetched for {len(out)}/{len(symbols)} symbols")
    return out
