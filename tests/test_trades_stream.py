"""Block-trade side-classification tests (Lee-Ready style)."""

from datetime import datetime, timezone

import pytest

from src.alpaca.trades_stream import QuoteSnapshot, classify_side


def _q(bid: float, ask: float) -> QuoteSnapshot:
    return QuoteSnapshot(bid=bid, ask=ask, ts=datetime.now(timezone.utc))


def test_at_or_above_ask_is_buy():
    q = _q(99.95, 100.00)
    assert classify_side(100.00, q) == "buy"
    assert classify_side(100.05, q) == "buy"


def test_at_or_below_bid_is_sell():
    q = _q(99.95, 100.00)
    assert classify_side(99.95, q) == "sell"
    assert classify_side(99.90, q) == "sell"


def test_above_midpoint_inside_spread_is_buy():
    q = _q(100.00, 100.20)
    assert classify_side(100.15, q) == "buy"


def test_below_midpoint_inside_spread_is_sell():
    q = _q(100.00, 100.20)
    assert classify_side(100.05, q) == "sell"


def test_exact_midpoint_is_unknown():
    q = _q(100.00, 100.20)
    assert classify_side(100.10, q) == "unknown"


def test_no_quote_is_unknown():
    assert classify_side(100.00, None) == "unknown"


def test_invalid_quote_is_unknown():
    # crossed quote
    q = _q(100.20, 100.00)
    assert classify_side(100.10, q) == "unknown"
    # zero bid
    q2 = _q(0.0, 100.00)
    assert classify_side(100.10, q2) == "unknown"
