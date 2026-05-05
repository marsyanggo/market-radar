"""End-to-end daily pipeline: screener → indicators → heat → recommend → report.

Reads bars once per symbol (already cached by indicator step), then computes
heat scores using the same data. Wires into existing repos.
"""

from datetime import datetime, timezone
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
from src.output.markdown_report import write_report
from src.recommend.engine_v1 import classify
from src.scoring.heat import compute_heat


def run_daily_pipeline(
    refresh_universe: bool = True,
    most_actives_top: int = 50,
    movers_top: int = 25,
    batch_size: int = 50,
) -> dict:
    """Run the full daily pipeline. Returns counts + report path."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    logger.info(f"=== daily pipeline start (as_of {today}) ===")

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
                news_count = news_repo.count_for_symbol(sym, since_iso=yesterday_iso)
                uoa_count = uoa_repo.count_for_symbol(sym, since_iso=yesterday_iso)

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
                    rec = classify(
                        symbol=sym,
                        as_of=today,
                        heat_score=heat.heat_score,
                        rsi_14=snap.rsi_14,
                        close=snap.close,
                        sma_20=snap.sma_20,
                    )
                    if rec is not None:
                        rec_repo.upsert(
                            symbol=rec.symbol,
                            as_of=rec.as_of,
                            category=rec.category,
                            heat_score=rec.heat_score,
                            entry_price=rec.close,
                            reason=rec.reason,
                        )
                        rec_n += 1

    # 6. Report
    report_path: Path = write_report(today)
    logger.info(f"report written → {report_path}")

    counts = {
        "as_of": today,
        "universe": len(universe),
        "technicals": technicals_n,
        "heat_scores": heat_n,
        "recommendations": rec_n,
        "report_path": str(report_path),
    }
    logger.info(f"=== daily pipeline done: {counts} ===")
    return counts
