"""End-to-end daily pipeline: screener → indicators → heat → recommend → report.

Reads bars once per symbol (already cached by indicator step), then computes
heat scores using the same data. Wires into existing repos.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.alpaca.bars import fetch_daily_bars_batch
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
from src.options.runner import run_options_pipeline
from src.sentiment.runner import run_sentiment_pipeline
from src.output.markdown_report import render_report, write_report
from src.output.telegram import send_daily_summary
from src.output.watchlist_writer import write_watchlists
from src.recommend.engine_v1 import classify as classify_v1
from src.recommend.engine_v2 import classify as classify_v2
from src.recommend.signals import SignalSnapshot
from src.scoring.heat import compute_heat


def run_daily_pipeline(
    refresh_universe: bool = True,
    most_actives_top: int = 50,
    movers_top: int = 25,
    batch_size: int = 50,
    send_telegram: bool = False,
    write_watchlists_files: bool = False,
    run_options: bool = False,
    options_top_n: int = 20,
    use_v2: bool = True,
    run_sentiment: bool = False,
) -> dict:
    """Run the full daily pipeline. Returns counts + report path."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    window_start_iso = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    logger.info(f"=== daily pipeline start (as_of {today}, window from {window_start_iso}) ===")

    # 1. Screener
    if refresh_universe:
        run_daily_screener(most_actives_top=most_actives_top, movers_top=movers_top)

    # 2. Pull universe
    with get_conn() as conn:
        universe = [r["symbol"] for r in StocksRepo(conn).list_recent(limit=500)]
    if not universe:
        logger.warning("empty universe, aborting")
        return {"error": "empty_universe"}
    logger.info(f"universe size: {len(universe)}")

    # 3. Fetch bars once (used for both technicals + heat volume_vs_adv)
    bars_by_symbol: dict = {}
    for i in range(0, len(universe), batch_size):
        chunk = universe[i : i + batch_size]
        bars_by_symbol.update(fetch_daily_bars_batch(chunk, days=260))

    # 3.5 Options pipeline (top-N by volume to bound API cost)
    options_summary = {}
    if run_options:
        # Pick top N by today's volume from bars
        ranked = sorted(
            ((sym, df["volume"].iloc[-1]) for sym, df in bars_by_symbol.items() if not df.empty),
            key=lambda x: -x[1],
        )
        opt_symbols = [s for s, _ in ranked[:options_top_n]]
        underlying_prices = {
            s: float(bars_by_symbol[s]["close"].iloc[-1])
            for s in opt_symbols if not bars_by_symbol[s].empty
        }
        options_summary = run_options_pipeline(
            opt_symbols, underlying_prices, today, window_start_iso
        )

    # 3.6 Sentiment pipeline (LLM news scoring + StockTwits)
    sentiment_summary = {}
    if run_sentiment:
        try:
            sentiment_summary = run_sentiment_pipeline(
                symbols=universe,
                as_of=today,
                window_start_iso=window_start_iso,
            )
        except Exception:
            logger.exception("sentiment pipeline failed (non-fatal)")

    # 4. Compute & persist technicals + heat scores
    technicals_n = 0
    heat_n = 0
    rec_n = 0

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

                # auxiliary signals (mostly 0 until later phases)
                news_count = news_repo.count_for_symbol(sym, since_iso=window_start_iso)
                uoa_count = uoa_repo.count_for_symbol(sym, since_iso=window_start_iso)

                heat = compute_heat(
                    symbol=sym,
                    as_of=today,
                    df_bars=df,
                    large_block_pct=None,  # Phase 1.4
                    uoa_count=uoa_count,
                    news_count=news_count,
                )
                heat_repo.upsert(
                    symbol=heat.symbol,
                    as_of=heat.as_of,
                    heat_score=heat.heat_score,
                    volume_vs_adv=heat.volume_vs_adv,
                    large_block_pct=heat.large_block_pct,
                    options_uoa_count=heat.options_uoa_count,
                    news_density=heat.news_density,
                )
                heat_n += 1

                # 5. Classify
                if snap is not None:
                    if use_v2:
                        # Pull options metrics if available
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
                            rsi_14=snap.rsi_14,
                            close=snap.close,
                            sma_20=snap.sma_20,
                            sma_50=snap.sma_50,
                            sma_200=snap.sma_200,
                            atr_14=snap.atr_14,
                            volume_vs_adv=heat.volume_vs_adv,
                            pct_from_high_52w=snap.pct_from_high_52w,
                            put_call_ratio=flow_row["put_call_ratio"] if flow_row else None,
                            iv_skew_25d=flow_row["iv_skew_25d"] if flow_row else None,
                            sentiment_score=sent_row["sentiment_score"] if sent_row else None,
                        )
                        rec = classify_v2(symbol=sym, as_of=today, snap=sig_snap)
                        if rec.category in ("strong_long", "watch", "avoid"):
                            rec_repo.upsert(
                                symbol=rec.symbol,
                                as_of=rec.as_of,
                                category=rec.category,
                                heat_score=heat.heat_score,
                                smart_money_score=sig_snap.smart_money_score,
                                entry_price=snap.close,
                                reason={
                                    "weighted_score": rec.weighted_score,
                                    "bullish_signals": rec.reason_signals,
                                    "bullish_count": rec.bullish_count,
                                    "bearish_count": rec.bearish_count,
                                    "risk_score": rec.risk.score if rec.risk else None,
                                    "risk_reasons": rec.risk.reasons if rec.risk else [],
                                },
                            )
                            rec_n += 1
                    else:
                        rec = classify_v1(
                            symbol=sym, as_of=today,
                            heat_score=heat.heat_score, rsi_14=snap.rsi_14,
                            close=snap.close, sma_20=snap.sma_20,
                        )
                        if rec is not None:
                            rec_repo.upsert(
                                symbol=rec.symbol, as_of=rec.as_of, category=rec.category,
                                heat_score=rec.heat_score, entry_price=rec.close, reason=rec.reason,
                            )
                            rec_n += 1

    # 6. Report
    report_path: Path = write_report(today)
    logger.info(f"report written → {report_path}")

    # 7. Watchlists for AI_trader
    watchlist_info = {}
    if write_watchlists_files:
        watchlist_info = write_watchlists(today)

    # 8. Telegram
    telegram_ok = False
    if send_telegram:
        telegram_ok = send_daily_summary(render_report(today), today)
        logger.info(f"telegram sent: {telegram_ok}")

    counts = {
        "as_of": today,
        "universe": len(universe),
        "technicals": technicals_n,
        "heat_scores": heat_n,
        "recommendations": rec_n,
        "report_path": str(report_path),
        "telegram": telegram_ok,
        **{k: v for k, v in watchlist_info.items() if k.endswith("_n")},
        **options_summary,
        **{f"sentiment_{k}": v for k, v in sentiment_summary.items()},
    }
    logger.info(f"=== daily pipeline done: {counts} ===")
    return counts
