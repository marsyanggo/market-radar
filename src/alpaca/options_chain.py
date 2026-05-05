"""Fetch option chain snapshots from Alpaca."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, OptionTradesRequest

from configs.settings import settings
from src.alpaca.client import with_retry
from src.logger import logger
from src.options.contract_parser import OptionContract, otm_pct, parse_occ


@dataclass
class OptionSnap:
    contract: OptionContract
    iv: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    rho: float | None
    bid: float | None
    ask: float | None
    last_price: float | None
    last_size: int | None
    last_ts: str | None
    otm_pct_value: float | None


def _client() -> OptionHistoricalDataClient:
    return OptionHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_secret_key)


@with_retry(max_attempts=3)
def fetch_chain(underlying: str, underlying_price: float | None = None) -> list[OptionSnap]:
    """Fetch full option chain for an underlying.

    `underlying_price` is used to compute OTM distance. If None, OTM is null.
    """
    res = _client().get_option_chain(OptionChainRequest(underlying_symbol=underlying))
    out: list[OptionSnap] = []
    for contract_sym, snap in res.items():
        c = parse_occ(contract_sym)
        if c is None:
            continue

        greeks = snap.greeks
        lq = snap.latest_quote
        lt = snap.latest_trade

        out.append(
            OptionSnap(
                contract=c,
                iv=float(snap.implied_volatility) if snap.implied_volatility else None,
                delta=float(greeks.delta) if greeks else None,
                gamma=float(greeks.gamma) if greeks else None,
                theta=float(greeks.theta) if greeks else None,
                vega=float(greeks.vega) if greeks else None,
                rho=float(greeks.rho) if greeks else None,
                bid=float(lq.bid_price) if lq and lq.bid_price else None,
                ask=float(lq.ask_price) if lq and lq.ask_price else None,
                last_price=float(lt.price) if lt and lt.price else None,
                last_size=int(lt.size) if lt and lt.size else None,
                last_ts=lt.timestamp.astimezone(timezone.utc).isoformat() if lt and isinstance(lt.timestamp, datetime) else None,
                otm_pct_value=otm_pct(c, underlying_price) if underlying_price else None,
            )
        )
    logger.info(f"fetched {len(out)} option snapshots for {underlying}")
    return out


@with_retry(max_attempts=3)
def fetch_recent_trades(contract_symbol: str, since: datetime) -> list:
    """Raw recent trades for a single option contract."""
    req = OptionTradesRequest(symbol_or_symbols=contract_symbol, start=since)
    res = _client().get_option_trades(req)
    return list(res.data.get(contract_symbol, []))
