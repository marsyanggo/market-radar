"""Sentiment scoring tests — pure-function aggregation logic."""

import pytest

from src.scoring.sentiment_score import (
    compute_sentiment,
    news_score,
    stocktwits_score,
)


def test_news_score_extremes():
    assert news_score(-1.0) == 0.0
    assert news_score(0.0) == 50.0
    assert news_score(1.0) == 100.0
    assert news_score(None) is None


def test_stocktwits_score():
    assert stocktwits_score(0.0) == 0.0
    assert stocktwits_score(0.5) == 50.0
    assert stocktwits_score(1.0) == 100.0
    assert stocktwits_score(None) is None


def test_compute_sentiment_news_only():
    b = compute_sentiment("X", news_avg=0.5, news_count=4, stocktwits_ratio=None)
    assert b.score == 75.0  # news_score(0.5) = 75


def test_compute_sentiment_stocktwits_only():
    b = compute_sentiment("X", news_avg=None, news_count=0, stocktwits_ratio=0.8)
    assert b.score == 80.0


def test_compute_sentiment_both_blended():
    # news 0.0 → 50, stocktwits 1.0 → 100; weighted (50*0.6 + 100*0.4) = 70
    b = compute_sentiment("X", news_avg=0.0, news_count=2, stocktwits_ratio=1.0)
    assert b.score == pytest.approx(70.0, abs=0.01)


def test_compute_sentiment_no_signals():
    b = compute_sentiment("X", news_avg=None, news_count=0, stocktwits_ratio=None)
    assert b.score is None
