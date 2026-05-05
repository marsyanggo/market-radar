"""Technical indicator computation — sanity checks on synthetic data."""

import numpy as np
import pandas as pd
import pytest

from src.indicators.technical import compute_all


@pytest.fixture
def trending_up_df() -> pd.DataFrame:
    """250 days of monotonically rising prices (with noise)."""
    rng = np.random.default_rng(42)
    n = 250
    base = np.linspace(100, 200, n)
    noise = rng.normal(0, 1.0, n)
    close = base + noise
    high = close + np.abs(rng.normal(0, 0.5, n))
    low = close - np.abs(rng.normal(0, 0.5, n))
    open_ = close - rng.normal(0, 0.2, n)
    volume = rng.integers(1_000_000, 5_000_000, n)
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


@pytest.fixture
def short_df() -> pd.DataFrame:
    """Only 10 bars — should return None."""
    n = 10
    return pd.DataFrame(
        {
            "open": [100] * n,
            "high": [101] * n,
            "low": [99] * n,
            "close": [100] * n,
            "volume": [1_000_000] * n,
        },
        index=pd.date_range("2025-01-01", periods=n, freq="B"),
    )


def test_returns_none_for_short_df(short_df):
    snap = compute_all("TEST", short_df, as_of="2025-01-15")
    assert snap is None


def test_trending_up_indicators(trending_up_df):
    snap = compute_all("UP", trending_up_df, as_of="2025-12-31")
    assert snap is not None
    assert snap.symbol == "UP"
    assert snap.as_of == "2025-12-31"
    assert snap.close > 0

    # RSI on a strong uptrend should be relatively high
    assert snap.rsi_14 is not None
    assert 50 < snap.rsi_14 <= 100

    # MACD on uptrend should be positive (fast > slow)
    assert snap.macd is not None
    assert snap.macd > 0

    # SMA ordering on rising trend: 20 > 50 > 200
    assert snap.sma_20 is not None
    assert snap.sma_50 is not None
    assert snap.sma_200 is not None
    assert snap.sma_20 > snap.sma_50 > snap.sma_200

    # Bollinger bands sane: lower < middle < upper, middle ≈ sma_20
    assert snap.bb_lower < snap.bb_middle < snap.bb_upper
    assert abs(snap.bb_middle - snap.sma_20) < 0.01

    # ATR positive
    assert snap.atr_14 is not None
    assert snap.atr_14 > 0

    # 52w high should be ≥ close, low should be ≤ close
    assert snap.high_52w is not None
    assert snap.low_52w is not None
    assert snap.high_52w >= snap.close
    assert snap.low_52w <= snap.close

    # On rising trend, close should be near the high (small negative pct)
    assert snap.pct_from_high_52w is not None
    assert -10 < snap.pct_from_high_52w <= 0


def test_flat_prices_yield_neutral_rsi():
    n = 60
    flat = pd.DataFrame(
        {
            "open": [100.0] * n,
            "high": [100.5] * n,
            "low": [99.5] * n,
            "close": [100.0 + (i % 2) * 0.01 for i in range(n)],
            "volume": [1_000_000] * n,
        },
        index=pd.date_range("2025-01-01", periods=n, freq="B"),
    )
    snap = compute_all("FLAT", flat, as_of="2025-03-15")
    assert snap is not None
    # nearly flat, RSI should hover around 50 (within wide bounds)
    assert 30 < snap.rsi_14 < 70


def test_pct_from_high_low_consistency(trending_up_df):
    snap = compute_all("UP", trending_up_df, as_of="2025-12-31")
    # pct_from_high should always be ≤ 0
    assert snap.pct_from_high_52w <= 0
    # pct_from_low should always be ≥ 0
    assert snap.pct_from_low_52w >= 0
