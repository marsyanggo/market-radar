"""Recommendation engine v1 — rule classification tests."""

from src.recommend.engine_v1 import classify


def test_avoid_when_overheated():
    rec = classify("OVR", "2026-05-05", heat_score=95, rsi_14=85, close=100, sma_20=95)
    assert rec is not None
    assert rec.category == "avoid"


def test_strong_long_when_heat_and_breakout():
    rec = classify("STR", "2026-05-05", heat_score=85, rsi_14=60, close=100, sma_20=95)
    assert rec is not None
    assert rec.category == "strong_long"


def test_strong_long_blocked_by_below_sma20():
    rec = classify("WCH", "2026-05-05", heat_score=85, rsi_14=60, close=90, sma_20=95)
    assert rec is not None
    # below SMA20 → falls to watch (Heat>70 still passes)
    assert rec.category == "watch"


def test_watch_when_only_heat():
    rec = classify("HOT", "2026-05-05", heat_score=72, rsi_14=55, close=None, sma_20=None)
    assert rec is not None
    assert rec.category == "watch"


def test_no_recommendation_when_low_heat():
    rec = classify("LOW", "2026-05-05", heat_score=40, rsi_14=50, close=100, sma_20=99)
    assert rec is None


def test_strong_long_blocked_by_high_rsi():
    # Heat>80 but RSI>=70 → should fall through avoid check (not >90, not >80 rsi),
    # then strong_long requires rsi<70, fails → watch
    rec = classify("MID", "2026-05-05", heat_score=85, rsi_14=72, close=100, sma_20=95)
    # Heat 85 > 70, but rsi (72) is not < 70, so watch rule (rsi None or <70) fails too
    # → returns None
    assert rec is None
