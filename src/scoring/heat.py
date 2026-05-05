"""Heat Score — weighted blend of volume, block flow, UOA, and news.

    Heat = 0.30 × volume_vs_adv_norm
         + 0.25 × large_block_pct_norm
         + 0.25 × uoa_count_norm
         + 0.20 × news_density_norm

For MVP (Phase 3): UOA and news_density default to 0 until Phase 1.3+1.4+4 wire
them up. Heat then effectively measures volume + (any block info we have).
"""

from dataclasses import dataclass

import pandas as pd

from src.scoring.normalize import (
    norm_large_block_pct,
    norm_news_density,
    norm_uoa_count,
    norm_volume_vs_adv,
)

WEIGHT_VOLUME = 0.30
WEIGHT_BLOCK = 0.25
WEIGHT_UOA = 0.25
WEIGHT_NEWS = 0.20


@dataclass
class HeatBreakdown:
    symbol: str
    as_of: str
    volume_vs_adv: float | None
    large_block_pct: float | None
    options_uoa_count: int
    news_density: int
    heat_score: float

    @property
    def components(self) -> dict[str, float]:
        return {
            "volume": norm_volume_vs_adv(self.volume_vs_adv) * WEIGHT_VOLUME,
            "block": norm_large_block_pct(self.large_block_pct) * WEIGHT_BLOCK,
            "uoa": norm_uoa_count(self.options_uoa_count) * WEIGHT_UOA,
            "news": norm_news_density(self.news_density) * WEIGHT_NEWS,
        }


def volume_vs_adv_from_bars(df: pd.DataFrame, lookback: int = 30) -> float | None:
    """today_volume / avg_volume(last `lookback` days excluding today)."""
    if df is None or df.empty or len(df) < lookback + 1:
        return None
    today_vol = float(df["volume"].iloc[-1])
    avg_vol = float(df["volume"].iloc[-(lookback + 1) : -1].mean())
    if avg_vol <= 0:
        return None
    return today_vol / avg_vol


def compute_heat(
    symbol: str,
    as_of: str,
    df_bars: pd.DataFrame,
    large_block_pct: float | None = None,
    uoa_count: int = 0,
    news_count: int = 0,
) -> HeatBreakdown:
    vol_ratio = volume_vs_adv_from_bars(df_bars)

    score = (
        norm_volume_vs_adv(vol_ratio) * WEIGHT_VOLUME
        + norm_large_block_pct(large_block_pct) * WEIGHT_BLOCK
        + norm_uoa_count(uoa_count) * WEIGHT_UOA
        + norm_news_density(news_count) * WEIGHT_NEWS
    )

    return HeatBreakdown(
        symbol=symbol,
        as_of=as_of,
        volume_vs_adv=vol_ratio,
        large_block_pct=large_block_pct,
        options_uoa_count=uoa_count,
        news_density=news_count,
        heat_score=round(score, 2),
    )
