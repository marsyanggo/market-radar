"""Backtest engine v2 against historical bars.

We don't yet have historical option_flow / news / heat — only daily bars.
So this backtest exercises only the technical/volume signals. As we accumulate
real option_flow/news rows day-over-day, future runs can replay those too.

Approach:
  1. For each symbol with bars:
     For each candidate day D (last N days, leaving room for 20-day forward window):
       a. Compute technicals from bars[:D]
       b. Build minimal SignalSnapshot (no heat/SM/skew available historically)
       c. classify() → category
       d. If category in {watch, strong_long}:
          entry  = next_day_open
          exit5  = close[D+5]
          exit20 = close[D+20]
          record return5d, return20d
  3. Aggregate: hit rate (return > 0), avg return, vol, sharpe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from src.alpaca.bars import fetch_daily_bars_batch
from src.db.connection import get_conn
from src.db.repos import StocksRepo
from src.indicators.technical import compute_all
from src.logger import logger
from src.recommend.engine_v2 import classify
from src.recommend.signals import SignalSnapshot
from src.scoring.heat import volume_vs_adv_from_bars
from src.scoring.normalize import norm_volume_vs_adv


@dataclass
class TradeResult:
    symbol: str
    entry_date: str
    category: str
    weighted_score: float
    bullish_count: int
    entry_price: float
    return_5d: float | None
    return_20d: float | None


@dataclass
class BacktestSummary:
    n_trades: int
    by_category: dict[str, int]
    win_rate_5d: dict[str, float]
    win_rate_20d: dict[str, float]
    avg_return_5d: dict[str, float]
    avg_return_20d: dict[str, float]
    sharpe_5d: dict[str, float]
    trades: list[TradeResult] = field(default_factory=list)


def _build_snapshot_from_bars(df_slice: pd.DataFrame, symbol: str, as_of: str) -> SignalSnapshot | None:
    """Compute minimal historical snapshot (no SM / news / options data)."""
    snap_t = compute_all(symbol, df_slice, as_of)
    if snap_t is None:
        return None

    vol_ratio = volume_vs_adv_from_bars(df_slice)
    # Approximate heat using only volume_vs_adv (the only signal we have historically)
    heat = norm_volume_vs_adv(vol_ratio) * 0.30 if vol_ratio is not None else None

    return SignalSnapshot(
        heat_score=heat,
        smart_money_score=None,
        rsi_14=snap_t.rsi_14,
        close=snap_t.close,
        sma_20=snap_t.sma_20,
        sma_50=snap_t.sma_50,
        sma_200=snap_t.sma_200,
        atr_14=snap_t.atr_14,
        volume_vs_adv=vol_ratio,
        pct_from_high_52w=snap_t.pct_from_high_52w,
        put_call_ratio=None,
        iv_skew_25d=None,
    )


def backtest_symbol(
    symbol: str,
    df: pd.DataFrame,
    lookback_days: int = 60,
    holding_5d: int = 5,
    holding_20d: int = 20,
) -> list[TradeResult]:
    if df is None or len(df) < 200 + lookback_days + holding_20d:
        return []

    results: list[TradeResult] = []
    end_idx = len(df) - max(holding_5d, holding_20d) - 1
    start_idx = max(200, end_idx - lookback_days)

    for d in range(start_idx, end_idx):
        slice_df = df.iloc[: d + 1]
        as_of = slice_df.index[-1].strftime("%Y-%m-%d")

        snap = _build_snapshot_from_bars(slice_df, symbol, as_of)
        if snap is None:
            continue

        rec = classify(symbol, as_of, snap)
        if rec.category not in ("strong_long", "watch"):
            continue

        if d + 1 >= len(df):
            continue
        entry_price = float(df["open"].iloc[d + 1])
        if entry_price <= 0:
            continue

        return_5d = None
        if d + holding_5d < len(df):
            return_5d = (float(df["close"].iloc[d + holding_5d]) - entry_price) / entry_price * 100
        return_20d = None
        if d + holding_20d < len(df):
            return_20d = (float(df["close"].iloc[d + holding_20d]) - entry_price) / entry_price * 100

        results.append(
            TradeResult(
                symbol=symbol,
                entry_date=df.index[d + 1].strftime("%Y-%m-%d"),
                category=rec.category,
                weighted_score=rec.weighted_score,
                bullish_count=rec.bullish_count,
                entry_price=entry_price,
                return_5d=return_5d,
                return_20d=return_20d,
            )
        )

    return results


def _agg(values: list[float]) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    n = len(values)
    mean = sum(values) / n
    if n == 1:
        return (mean, 0.0)
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    return (mean, math.sqrt(var))


def summarize(trades: list[TradeResult]) -> BacktestSummary:
    if not trades:
        return BacktestSummary(0, {}, {}, {}, {}, {}, {}, [])

    by_cat: dict[str, list[TradeResult]] = {}
    for t in trades:
        by_cat.setdefault(t.category, []).append(t)

    win_5d, win_20d = {}, {}
    avg_5d, avg_20d = {}, {}
    sharpe_5d = {}

    for cat, items in by_cat.items():
        rets5 = [t.return_5d for t in items if t.return_5d is not None]
        rets20 = [t.return_20d for t in items if t.return_20d is not None]
        win_5d[cat] = sum(1 for r in rets5 if r > 0) / len(rets5) * 100 if rets5 else 0.0
        win_20d[cat] = sum(1 for r in rets20 if r > 0) / len(rets20) * 100 if rets20 else 0.0
        avg_5d[cat], std5 = _agg(rets5)
        avg_20d[cat], _ = _agg(rets20)
        sharpe_5d[cat] = (avg_5d[cat] / std5) if std5 > 0 else 0.0

    return BacktestSummary(
        n_trades=len(trades),
        by_category={k: len(v) for k, v in by_cat.items()},
        win_rate_5d=win_5d,
        win_rate_20d=win_20d,
        avg_return_5d=avg_5d,
        avg_return_20d=avg_20d,
        sharpe_5d=sharpe_5d,
        trades=trades,
    )


def run_backtest(
    symbols: list[str] | None = None,
    lookback_days: int = 60,
    bar_history_days: int = 280,
    batch_size: int = 50,
) -> BacktestSummary:
    if symbols is None:
        with get_conn() as conn:
            symbols = [r["symbol"] for r in StocksRepo(conn).list_recent(limit=200)]

    logger.info(f"backtest: {len(symbols)} symbols, lookback={lookback_days}d")

    all_trades: list[TradeResult] = []
    for i in range(0, len(symbols), batch_size):
        chunk = symbols[i : i + batch_size]
        bars = fetch_daily_bars_batch(chunk, days=bar_history_days)
        for sym, df in bars.items():
            all_trades.extend(backtest_symbol(sym, df, lookback_days=lookback_days))

    summary = summarize(all_trades)
    logger.info(
        f"backtest done: trades={summary.n_trades}  by_cat={summary.by_category}  "
        f"5d_win={ {k: round(v,1) for k,v in summary.win_rate_5d.items()} }"
    )
    return summary


def render_report(summary: BacktestSummary) -> str:
    lines = ["# Backtest Report\n"]
    lines.append(f"_generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_\n")
    lines.append(f"Total trades: **{summary.n_trades}**\n")
    if summary.n_trades == 0:
        lines.append("\n_no trades recorded._\n")
        return "\n".join(lines)

    lines.append("| Category | N | Win 5d | Avg 5d | Sharpe 5d | Win 20d | Avg 20d |")
    lines.append("|----------|---|--------|--------|-----------|---------|---------|")
    for cat in ("strong_long", "watch"):
        if cat not in summary.by_category:
            continue
        n = summary.by_category[cat]
        w5 = summary.win_rate_5d.get(cat, 0)
        a5 = summary.avg_return_5d.get(cat, 0)
        s5 = summary.sharpe_5d.get(cat, 0)
        w20 = summary.win_rate_20d.get(cat, 0)
        a20 = summary.avg_return_20d.get(cat, 0)
        lines.append(
            f"| {cat} | {n} | {w5:.1f}% | {a5:+.2f}% | {s5:.2f} | {w20:.1f}% | {a20:+.2f}% |"
        )
    return "\n".join(lines)
