"""Lite intraday pipeline — fast hourly heat refresh.

Skips: options chain (heavy + low intra-hour value), LLM news scoring (slow,
already done daily), watchlists (no need every hour).

Includes: screener refresh (some symbols rotate), news fetch (last 2h),
bars + technicals, heat + sentiment_daily lookup, engine_v2 classify, telegram.

Target latency: ~10 seconds per cycle.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.alpaca.bars import fetch_daily_bars_batch
from src.alpaca.news import fetch_and_persist
from src.alpaca.screener import run_daily_screener
from src.db.connection import get_conn, transaction
from src.db.repos import (
    HeatScoresRepo,
    NewsRepo,
    RecommendationsRepo,
    StocksRepo,
    TechnicalsRepo,
    UoaRepo,
)
from src.indicators.technical import compute_all
from src.logger import logger
from src.output.markdown_report import render_intraday_report, write_intraday_report
from src.output.telegram import send_message
from src.recommend.engine_v2 import classify as classify_v2
from src.recommend.signals import SignalSnapshot
from src.scoring.heat import compute_heat


def run_intraday_pipeline(
    refresh_universe: bool = True,
    most_actives_top: int = 50,
    movers_top: int = 25,
    batch_size: int = 50,
    send_telegram: bool = True,
    news_hours: float = 2.0,
) -> dict:
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    slot = now.strftime("%H:%M")
    window_start_iso = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")

    logger.info(f"=== intraday pipeline start (slot {slot} UTC) ===")

    # 1. Light screener
    if refresh_universe:
        run_daily_screener(most_actives_top=most_actives_top, movers_top=movers_top)

    # 2. Recent news
    fetch_and_persist(symbols=None, hours_back=news_hours, limit=100)

    # 3. Universe + bars
    with get_conn() as conn:
        universe = [r["symbol"] for r in StocksRepo(conn).list_recent(limit=200)]
    if not universe:
        return {"error": "empty_universe"}

    bars_by_symbol: dict = {}
    for i in range(0, len(universe), batch_size):
        chunk = universe[i : i + batch_size]
        bars_by_symbol.update(fetch_daily_bars_batch(chunk, days=260))

    # 4. Recompute heat + classify (reuse latest options + sentiment from DB)
    technicals_n = heat_n = rec_n = 0

    with get_conn() as conn:
        with transaction(conn):
            tech_repo = TechnicalsRepo(conn)
            heat_repo = HeatScoresRepo(conn)
            news_repo = NewsRepo(conn)
            uoa_repo = UoaRepo(conn)
            rec_repo = RecommendationsRepo(conn)

            for sym in universe:
                df = bars_by_symbol.get(sym)
                if df is None or df.empty:
                    continue

                snap = compute_all(sym, df, today)
                if snap is not None:
                    tech_repo.upsert(snap)
                    technicals_n += 1

                news_count = news_repo.count_for_symbol(sym, since_iso=window_start_iso)
                uoa_count = uoa_repo.count_for_symbol(sym, since_iso=window_start_iso)

                heat = compute_heat(
                    symbol=sym, as_of=today, df_bars=df,
                    large_block_pct=None, uoa_count=uoa_count, news_count=news_count,
                )
                heat_repo.upsert(
                    symbol=heat.symbol, as_of=heat.as_of,
                    heat_score=heat.heat_score, volume_vs_adv=heat.volume_vs_adv,
                    large_block_pct=heat.large_block_pct,
                    options_uoa_count=heat.options_uoa_count,
                    news_density=heat.news_density,
                )
                heat_n += 1

                if snap is None:
                    continue

                # Pull pre-existing options + sentiment (from this morning's daily run)
                flow_row = conn.execute(
                    "SELECT put_call_ratio, iv_skew_25d, smart_money_score FROM option_flow WHERE symbol=? AND as_of=?",
                    (sym, today),
                ).fetchone()
                sent_row = conn.execute(
                    "SELECT sentiment_score FROM sentiment_daily WHERE symbol=? AND as_of=?",
                    (sym, today),
                ).fetchone()
                sig_snap = SignalSnapshot(
                    heat_score=heat.heat_score,
                    smart_money_score=flow_row["smart_money_score"] if flow_row else None,
                    rsi_14=snap.rsi_14, close=snap.close,
                    sma_20=snap.sma_20, sma_50=snap.sma_50, sma_200=snap.sma_200,
                    atr_14=snap.atr_14, volume_vs_adv=heat.volume_vs_adv,
                    pct_from_high_52w=snap.pct_from_high_52w,
                    put_call_ratio=flow_row["put_call_ratio"] if flow_row else None,
                    iv_skew_25d=flow_row["iv_skew_25d"] if flow_row else None,
                    sentiment_score=sent_row["sentiment_score"] if sent_row else None,
                )
                rec = classify_v2(symbol=sym, as_of=today, snap=sig_snap)
                if rec.category in ("strong_long", "watch", "avoid"):
                    rec_repo.upsert(
                        symbol=rec.symbol, as_of=rec.as_of, category=rec.category,
                        heat_score=heat.heat_score,
                        smart_money_score=sig_snap.smart_money_score,
                        entry_price=snap.close,
                        reason={
                            "weighted_score": rec.weighted_score,
                            "bullish_signals": rec.reason_signals,
                            "bullish_count": rec.bullish_count,
                            "bearish_count": rec.bearish_count,
                            "intraday_slot": slot,
                        },
                    )
                    rec_n += 1

    # 5. Render + persist + push
    report_path = write_intraday_report(today, slot)
    logger.info(f"intraday report → {report_path}")

    telegram_ok = False
    if send_telegram:
        et_slot = (now - timedelta(hours=4)).strftime("%H:%M")  # PT → ET conversion approx (DST may shift)
        header = f"📡 *Market Radar — Intraday {et_slot} ET*\n"
        body = render_intraday_report(today, slot)
        telegram_ok = send_message(header + body, silent=True)  # silent so it doesn't ping every hour

    counts = {
        "as_of": today, "slot": slot,
        "universe": len(universe), "technicals": technicals_n,
        "heat_scores": heat_n, "recommendations": rec_n,
        "telegram": telegram_ok,
    }
    logger.info(f"=== intraday pipeline done: {counts} ===")
    return counts
