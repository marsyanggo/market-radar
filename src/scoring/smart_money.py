"""Smart Money Score — blend of block flow + options flow + UOA.

For Phase 4 we have:
  - block trade buy/sell imbalance      (from trades_blocks)
  - aggressive UOA count + side mix     (from uoa)
  - put/call ratio                      (from option_flow)
  - IV skew (25d)                       (from option_flow)

For now: simple weighted blend, all components mapped to 0-100.
Smart_money 0-100 — higher = bullish smart money flow.
"""

from __future__ import annotations

from src.scoring.normalize import clamp, linear


def block_imbalance_score(buy_size: int, sell_size: int) -> float | None:
    total = buy_size + sell_size
    if total == 0:
        return None
    imb = (buy_size - sell_size) / total  # -1..+1
    return linear(imb, -1.0, 1.0)


def uoa_call_dominance_score(call_buys: int, put_buys: int) -> float | None:
    total = call_buys + put_buys
    if total == 0:
        return None
    dom = (call_buys - put_buys) / total  # -1..+1
    return linear(dom, -1.0, 1.0)


def pc_ratio_score(pc_ratio: float | None) -> float | None:
    """Lower P/C is more bullish.
    P/C 0.5 → 100 (very bullish), 1.0 → 50, 1.5 → 0 (very bearish).
    """
    if pc_ratio is None:
        return None
    return clamp(linear(1.5 - pc_ratio, 0.0, 1.0), 0, 100)


def iv_skew_score(skew: float | None) -> float | None:
    """Lower skew (puts not paying premium) → bullish.
    skew −0.05 → 100, 0.0 → 50, 0.10 → 0.
    """
    if skew is None:
        return None
    return clamp(linear(0.10 - skew, 0.0, 0.15), 0, 100)


def compute_smart_money(
    block_buy_size: int = 0,
    block_sell_size: int = 0,
    uoa_call_buys: int = 0,
    uoa_put_buys: int = 0,
    pc_ratio: float | None = None,
    iv_skew: float | None = None,
) -> float | None:
    """Weighted blend. Returns None if no signal at all (all components None)."""
    components = [
        (block_imbalance_score(block_buy_size, block_sell_size), 0.30),
        (uoa_call_dominance_score(uoa_call_buys, uoa_put_buys), 0.30),
        (pc_ratio_score(pc_ratio), 0.20),
        (iv_skew_score(iv_skew), 0.20),
    ]
    weighted = [(s, w) for s, w in components if s is not None]
    if not weighted:
        return None
    total_w = sum(w for _, w in weighted)
    return round(sum(s * w for s, w in weighted) / total_w, 2)
