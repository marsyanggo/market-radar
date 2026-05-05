"""Heat scoring + normalize tests."""

import numpy as np
import pandas as pd
import pytest

from src.scoring.heat import compute_heat, volume_vs_adv_from_bars
from src.scoring.normalize import (
    norm_large_block_pct,
    norm_news_density,
    norm_uoa_count,
    norm_volume_vs_adv,
)


def test_norm_volume_vs_adv():
    assert norm_volume_vs_adv(0.5) == 0.0
    assert norm_volume_vs_adv(3.0) == 100.0
    assert norm_volume_vs_adv(1.5) == 40.0  # (1.5-0.5)/(3.0-0.5)*100
    assert norm_volume_vs_adv(None) == 0.0


def test_norm_large_block_pct():
    assert norm_large_block_pct(0.0) == 0.0
    assert norm_large_block_pct(0.30) == 100.0
    assert norm_large_block_pct(0.15) == 50.0


def test_norm_uoa_news_clamp():
    assert norm_uoa_count(20) == 100.0  # clamped
    assert norm_uoa_count(0) == 0.0
    assert norm_news_density(8) == 100.0
    assert norm_news_density(20) == 100.0  # clamped


def _make_bars(volumes: list[int]) -> pd.DataFrame:
    n = len(volumes)
    return pd.DataFrame(
        {
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.0] * n,
            "volume": volumes,
        },
        index=pd.date_range("2025-01-01", periods=n, freq="B"),
    )


def test_volume_vs_adv_from_bars_basic():
    # 30 normal days at 1M, today at 3M → ratio 3.0
    bars = _make_bars([1_000_000] * 30 + [3_000_000])
    ratio = volume_vs_adv_from_bars(bars, lookback=30)
    assert ratio == pytest.approx(3.0)


def test_volume_vs_adv_insufficient_history():
    bars = _make_bars([1_000_000] * 5)
    assert volume_vs_adv_from_bars(bars, lookback=30) is None


def test_compute_heat_volume_dominates_when_others_zero():
    bars = _make_bars([1_000_000] * 30 + [3_000_000])
    h = compute_heat("X", "2026-05-05", df_bars=bars)
    assert h.symbol == "X"
    assert h.volume_vs_adv == pytest.approx(3.0)
    # volume saturated × 0.30 weight = 30
    assert h.heat_score == pytest.approx(30.0, abs=0.01)


def test_compute_heat_full_signals():
    # All four signals fully saturated → heat = 100
    bars = _make_bars([1_000_000] * 30 + [4_000_000])  # ratio 4.0 > 3.0 cap
    h = compute_heat(
        "Y",
        "2026-05-05",
        df_bars=bars,
        large_block_pct=0.40,
        uoa_count=15,
        news_count=10,
    )
    assert h.heat_score == pytest.approx(100.0, abs=0.5)
