"""Normalization helpers — map raw signal values to a 0–100 scale."""


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def linear(x: float, x_min: float, x_max: float) -> float:
    """Linear map [x_min, x_max] → [0, 100], clamped at the edges."""
    if x_max == x_min:
        return 0.0
    return clamp((x - x_min) / (x_max - x_min) * 100)


def norm_volume_vs_adv(ratio: float) -> float:
    """today_vol / avg_vol_30d.
    1.0 = baseline (50), 3.0+ = saturated (100), 0.5 or below = 0.
    """
    if ratio is None:
        return 0.0
    return linear(ratio, 0.5, 3.0)


def norm_large_block_pct(pct: float) -> float:
    """Block volume / total volume. 0 → 0, 0.30 → 100."""
    if pct is None:
        return 0.0
    return linear(pct, 0.0, 0.30)


def norm_uoa_count(count: int) -> float:
    """Number of UOA events in 24h. 0 → 0, 10 → 100."""
    if count is None:
        return 0.0
    return linear(count, 0.0, 10.0)


def norm_news_density(count: int) -> float:
    """News count in 24h. 0 → 0, 8 → 100."""
    if count is None:
        return 0.0
    return linear(count, 0.0, 8.0)
