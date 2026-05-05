"""Derived option flow metrics — P/C ratio, IV skew, simple smart-money score."""

from __future__ import annotations

from dataclasses import dataclass

from src.alpaca.options_chain import OptionSnap


@dataclass
class FlowMetrics:
    symbol: str
    call_count: int
    put_count: int
    put_call_ratio: float | None
    iv_skew_25d: float | None  # put IV(25d) − call IV(25d)


def _filter(snaps: list[OptionSnap], opt_type: str) -> list[OptionSnap]:
    return [s for s in snaps if s.contract.option_type == opt_type]


def _avg_iv_near_delta(snaps: list[OptionSnap], target_abs_delta: float = 0.25) -> float | None:
    """Pick contracts whose |delta| is within ±0.05 of target, avg their IV."""
    cands = [
        s for s in snaps
        if s.delta is not None and s.iv is not None
        and abs(abs(s.delta) - target_abs_delta) <= 0.05
    ]
    if not cands:
        return None
    return sum(s.iv for s in cands) / len(cands)


def compute_flow(symbol: str, snaps: list[OptionSnap]) -> FlowMetrics:
    calls = _filter(snaps, "call")
    puts = _filter(snaps, "put")

    pc_ratio = None
    if calls:
        pc_ratio = len(puts) / len(calls)

    call_iv = _avg_iv_near_delta(calls)
    put_iv = _avg_iv_near_delta(puts)
    skew = (put_iv - call_iv) if (call_iv is not None and put_iv is not None) else None

    return FlowMetrics(
        symbol=symbol,
        call_count=len(calls),
        put_count=len(puts),
        put_call_ratio=pc_ratio,
        iv_skew_25d=skew,
    )
