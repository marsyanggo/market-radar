"""Engine v2 + signals + risk score tests."""

from datetime import date, timedelta

import pytest

from src.recommend.engine_v2 import classify
from src.recommend.risk_score import assess_risk
from src.recommend.signals import (
    SignalSnapshot,
    count_bullish_bearish,
    evaluate_signals,
    rsi_signal,
    technical_alignment_signal,
)


# ---------- signals ----------

def test_rsi_signal_oversold():
    snap = SignalSnapshot(rsi_14=25)
    s = rsi_signal(snap)
    assert s is not None and s < 40


def test_rsi_signal_sweet_spot():
    snap = SignalSnapshot(rsi_14=58)
    s = rsi_signal(snap)
    assert s is not None and s > 60


def test_rsi_signal_overbought():
    snap = SignalSnapshot(rsi_14=85)
    s = rsi_signal(snap)
    assert s is not None and s < 50


def test_technical_alignment_strong_uptrend():
    snap = SignalSnapshot(close=120, sma_20=115, sma_50=110, sma_200=100)
    s = technical_alignment_signal(snap)
    assert s == 100


def test_technical_alignment_strong_downtrend():
    snap = SignalSnapshot(close=90, sma_20=95, sma_50=100, sma_200=110)
    s = technical_alignment_signal(snap)
    assert s == 0


def test_evaluate_signals_skips_missing():
    snap = SignalSnapshot(rsi_14=60, close=100, sma_20=95, sma_50=90)
    scores = evaluate_signals(snap)
    assert "rsi" in scores
    assert "technical_alignment" in scores
    assert "smart_money" not in scores


def test_count_bullish_bearish():
    scores = {"a": 80, "b": 70, "c": 50, "d": 30, "e": 20}
    bull, bear, neut = count_bullish_bearish(scores)
    assert bull == 2 and bear == 2 and neut == 1


# ---------- risk ----------

def test_risk_overheated_veto():
    snap = SignalSnapshot(heat_score=95, rsi_14=85, close=100)
    risk = assess_risk(snap)
    assert risk.veto
    assert risk.score >= 50


def test_risk_earnings_veto():
    snap = SignalSnapshot(heat_score=70, rsi_14=60, close=100)
    today = date(2026, 5, 5)
    risk = assess_risk(snap, earnings_date=today + timedelta(days=2), today=today)
    assert risk.veto


def test_risk_low_liquidity():
    snap = SignalSnapshot(close=10, atr_14=0.3, sma_50=9)
    risk = assess_risk(snap, avg_volume=100_000)
    assert not risk.veto
    assert any("low liquidity" in r for r in risk.reasons)


def test_risk_penny_stock():
    snap = SignalSnapshot(close=2.0)
    risk = assess_risk(snap)
    assert any("price <" in r for r in risk.reasons)


# ---------- engine v2 ----------

def _bullish_snap() -> SignalSnapshot:
    return SignalSnapshot(
        heat_score=75,
        smart_money_score=70,
        rsi_14=58,
        close=100, sma_20=95, sma_50=90, sma_200=85,
        atr_14=2.0,
        volume_vs_adv=1.8,
        pct_from_high_52w=-3,
        put_call_ratio=0.7,
        iv_skew_25d=-0.02,
    )


def test_engine_v2_strong_long():
    rec = classify("STR", "2026-05-05", _bullish_snap())
    assert rec.category == "strong_long"
    assert rec.bullish_count >= 4
    assert rec.weighted_score >= 65


def test_engine_v2_avoid_overheat():
    snap = _bullish_snap()
    snap.heat_score = 95
    snap.rsi_14 = 85
    rec = classify("OVR", "2026-05-05", snap)
    assert rec.category == "avoid"


def test_engine_v2_watch_when_partial_resonance():
    snap = SignalSnapshot(
        heat_score=72,
        rsi_14=55,
        close=50, sma_20=48, sma_50=45,  # decent alignment
        volume_vs_adv=1.4,
        atr_14=1.0,
    )
    rec = classify("MID", "2026-05-05", snap)
    # Heat 72 → bullish, technical alignment bullish, volume neutral. RSI 55 score = 50 (neutral).
    # Bullish count >= 3 → watch
    assert rec.category in ("watch", "strong_long")


def test_engine_v2_none_when_weak():
    snap = SignalSnapshot(rsi_14=50, close=100, sma_20=100, sma_50=100)
    rec = classify("FLAT", "2026-05-05", snap)
    assert rec.category == "none"


def test_engine_v2_skips_avoid_when_low_heat_bearish():
    """Even if 3 bearish, if heat low, don't mark avoid (just none)."""
    snap = SignalSnapshot(
        heat_score=20,
        rsi_14=85,                # bearish
        close=80, sma_20=85, sma_50=90,  # bearish alignment
        volume_vs_adv=0.4,        # bearish volume
    )
    rec = classify("LOW", "2026-05-05", snap)
    assert rec.category != "avoid"
