"""Per-day options pipeline:
  fetch chain → persist snapshots → detect UOA → compute flow + smart money.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.alpaca.options_chain import fetch_chain
from src.db.connection import get_conn, transaction
from src.db.repos import OptionFlowRepo, OptionSnapshotsRepo, TradesRepo, UoaRepo
from src.logger import logger
from src.options.flow_metrics import compute_flow
from src.options.uoa_detector import detect_and_persist
from src.scoring.smart_money import compute_smart_money


def _snap_to_row(s, symbol: str, as_of: str) -> dict:
    return {
        "symbol": symbol,
        "contract_symbol": s.contract.contract_symbol,
        "option_type": s.contract.option_type,
        "strike": s.contract.strike,
        "expiration": s.contract.expiration.isoformat(),
        "iv": s.iv,
        "delta": s.delta,
        "gamma": s.gamma,
        "theta": s.theta,
        "vega": s.vega,
        "rho": s.rho,
        "bid": s.bid,
        "ask": s.ask,
        "last_price": s.last_price,
        "last_size": s.last_size,
        "otm_pct": s.otm_pct_value,
        "ts": s.last_ts or datetime.now(timezone.utc).isoformat(),
        "as_of": as_of,
    }


def run_for_symbol(
    symbol: str,
    underlying_price: float | None,
    as_of: str,
    window_start_iso: str,
) -> dict:
    """Fetch chain, persist snapshots + UOA, compute flow + smart money for one symbol."""
    snaps = fetch_chain(symbol, underlying_price=underlying_price)
    if not snaps:
        return {"symbol": symbol, "snaps": 0}

    # 1. Snapshots
    rows = [_snap_to_row(s, symbol, as_of) for s in snaps]
    with get_conn() as conn:
        with transaction(conn):
            OptionSnapshotsRepo(conn).upsert_many(rows)

    # 2. UOA
    uoa_n = detect_and_persist(snaps)

    # 3. Flow metrics
    metrics = compute_flow(symbol, snaps)

    # 4. UOA call/put buy split (recent window)
    with get_conn() as conn:
        urepo = UoaRepo(conn)
        call_buys = conn.execute(
            "SELECT COUNT(*) AS c FROM uoa WHERE symbol=? AND ts>=? AND option_type='call' AND side='buy'",
            (symbol, window_start_iso),
        ).fetchone()["c"]
        put_buys = conn.execute(
            "SELECT COUNT(*) AS c FROM uoa WHERE symbol=? AND ts>=? AND option_type='put' AND side='buy'",
            (symbol, window_start_iso),
        ).fetchone()["c"]
        total_uoa = urepo.count_for_symbol(symbol, since_iso=window_start_iso)

        # 5. Block imbalance
        imb = TradesRepo(conn).buy_sell_imbalance(symbol, since_iso=window_start_iso)

    sm = compute_smart_money(
        block_buy_size=imb["buy_size"],
        block_sell_size=imb["sell_size"],
        uoa_call_buys=call_buys,
        uoa_put_buys=put_buys,
        pc_ratio=metrics.put_call_ratio,
        iv_skew=metrics.iv_skew_25d,
    )

    # 6. Persist flow row
    with get_conn() as conn:
        with transaction(conn):
            OptionFlowRepo(conn).upsert(
                symbol=symbol,
                as_of=as_of,
                call_count=metrics.call_count,
                put_count=metrics.put_count,
                put_call_ratio=metrics.put_call_ratio,
                iv_skew_25d=metrics.iv_skew_25d,
                uoa_count=total_uoa,
                smart_money_score=sm,
            )

    return {
        "symbol": symbol,
        "snaps": len(snaps),
        "uoa_new": uoa_n,
        "uoa_total_window": total_uoa,
        "pc_ratio": metrics.put_call_ratio,
        "iv_skew": metrics.iv_skew_25d,
        "smart_money": sm,
    }


def run_options_pipeline(
    symbols: list[str],
    underlying_prices: dict[str, float],
    as_of: str,
    window_start_iso: str,
) -> dict:
    """Run option pipeline for a batch of symbols."""
    results = []
    for sym in symbols:
        try:
            r = run_for_symbol(
                sym,
                underlying_price=underlying_prices.get(sym),
                as_of=as_of,
                window_start_iso=window_start_iso,
            )
            results.append(r)
        except Exception:
            logger.exception(f"options pipeline failed for {sym}")

    summary = {
        "symbols_processed": len(results),
        "total_snaps": sum(r.get("snaps", 0) for r in results),
        "total_uoa_new": sum(r.get("uoa_new", 0) for r in results),
    }
    logger.info(f"options pipeline: {summary}")
    return summary
