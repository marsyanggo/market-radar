"""Technical indicators — compute EOD values from a daily OHLCV DataFrame.

Input df must have columns: open, high, low, close, volume.
Output is a flat dict of latest values, one row per symbol, ready to upsert.
"""

from dataclasses import dataclass

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands


@dataclass
class TechnicalSnapshot:
    symbol: str
    as_of: str
    close: float
    rsi_14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    atr_14: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    pct_from_high_52w: float | None = None
    pct_from_low_52w: float | None = None


def _last(series: pd.Series) -> float | None:
    if series is None or series.empty:
        return None
    val = series.iloc[-1]
    if pd.isna(val):
        return None
    return float(val)


def compute_all(symbol: str, df: pd.DataFrame, as_of: str) -> TechnicalSnapshot | None:
    """Compute the full indicator set for one symbol.

    Returns None if df doesn't have enough rows (need 200 bars for sma_200).
    """
    if df.empty or len(df) < 20:
        return None

    close = df["close"]
    high = df["high"]
    low = df["low"]

    snap = TechnicalSnapshot(
        symbol=symbol,
        as_of=as_of,
        close=float(close.iloc[-1]),
    )

    if len(close) >= 14:
        snap.rsi_14 = _last(RSIIndicator(close=close, window=14).rsi())
        snap.atr_14 = _last(AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range())

    if len(close) >= 26:
        macd_calc = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
        snap.macd = _last(macd_calc.macd())
        snap.macd_signal = _last(macd_calc.macd_signal())
        snap.macd_hist = _last(macd_calc.macd_diff())

    if len(close) >= 20:
        snap.sma_20 = _last(SMAIndicator(close=close, window=20).sma_indicator())
        bb = BollingerBands(close=close, window=20, window_dev=2)
        snap.bb_upper = _last(bb.bollinger_hband())
        snap.bb_middle = _last(bb.bollinger_mavg())
        snap.bb_lower = _last(bb.bollinger_lband())

    if len(close) >= 50:
        snap.sma_50 = _last(SMAIndicator(close=close, window=50).sma_indicator())
    if len(close) >= 200:
        snap.sma_200 = _last(SMAIndicator(close=close, window=200).sma_indicator())

    # 52w high/low — use up to last 252 bars
    window_52w = close.tail(252)
    high_52w = window_52w.max()
    low_52w = window_52w.min()
    if not pd.isna(high_52w):
        snap.high_52w = float(high_52w)
        snap.pct_from_high_52w = float((snap.close - high_52w) / high_52w * 100)
    if not pd.isna(low_52w):
        snap.low_52w = float(low_52w)
        snap.pct_from_low_52w = float((snap.close - low_52w) / low_52w * 100)

    return snap
