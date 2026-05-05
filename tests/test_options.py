"""Options module tests — contract parsing, UOA classification, flow metrics, smart money."""

from datetime import date

import pytest

from src.options.contract_parser import OptionContract, otm_pct, parse_occ
from src.scoring.smart_money import (
    block_imbalance_score,
    compute_smart_money,
    iv_skew_score,
    pc_ratio_score,
    uoa_call_dominance_score,
)


def test_parse_occ_call():
    c = parse_occ("NVDA260522C00200000")
    assert c is not None
    assert c.underlying == "NVDA"
    assert c.expiration == date(2026, 5, 22)
    assert c.option_type == "call"
    assert c.strike == 200.0


def test_parse_occ_put():
    c = parse_occ("AAPL250117P00150500")
    assert c is not None
    assert c.option_type == "put"
    assert c.strike == 150.5


def test_parse_occ_invalid():
    assert parse_occ("INVALID") is None
    assert parse_occ("") is None


def test_otm_pct_call():
    c = OptionContract("X", "X", date(2026, 1, 1), "call", strike=110.0)
    assert otm_pct(c, 100.0) == pytest.approx(10.0)
    # ITM
    c2 = OptionContract("X", "X", date(2026, 1, 1), "call", strike=90.0)
    assert otm_pct(c2, 100.0) == pytest.approx(-10.0)


def test_otm_pct_put():
    c = OptionContract("X", "X", date(2026, 1, 1), "put", strike=90.0)
    assert otm_pct(c, 100.0) == pytest.approx(10.0)


def test_block_imbalance_score():
    assert block_imbalance_score(100, 0) == 100.0
    assert block_imbalance_score(0, 100) == 0.0
    assert block_imbalance_score(50, 50) == 50.0
    assert block_imbalance_score(0, 0) is None


def test_uoa_call_dominance_score():
    assert uoa_call_dominance_score(10, 0) == 100.0
    assert uoa_call_dominance_score(0, 10) == 0.0
    assert uoa_call_dominance_score(0, 0) is None


def test_pc_ratio_score():
    # 0.5 → very bullish (close to 100)
    assert pc_ratio_score(0.5) == 100.0
    # 1.0 → neutral
    assert pc_ratio_score(1.0) == pytest.approx(50.0)
    # 1.5 → very bearish (0)
    assert pc_ratio_score(1.5) == 0.0


def test_iv_skew_score():
    assert iv_skew_score(-0.05) == 100.0
    assert iv_skew_score(0.10) == 0.0
    assert iv_skew_score(None) is None


def test_compute_smart_money_full():
    sm = compute_smart_money(
        block_buy_size=1000,
        block_sell_size=0,
        uoa_call_buys=5,
        uoa_put_buys=0,
        pc_ratio=0.6,
        iv_skew=-0.02,
    )
    assert sm is not None
    assert 80 < sm <= 100  # all bullish signals


def test_compute_smart_money_no_signals():
    sm = compute_smart_money()
    assert sm is None


def test_compute_smart_money_partial():
    sm = compute_smart_money(pc_ratio=1.0)  # only one signal
    assert sm == pytest.approx(50.0)
