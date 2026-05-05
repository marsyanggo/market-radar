"""CRUD tests for db repositories.

Each test uses an in-memory SQLite via a tmp_path file (so connection sharing works).
"""

from pathlib import Path

import pytest

from src.db.connection import connect, transaction
from src.db.migrations import apply_base_schema
from src.db.repos import (
    BlockTrade,
    HeatScoresRepo,
    NewsItem,
    NewsRepo,
    RecommendationsRepo,
    Stock,
    StocksRepo,
    TradesRepo,
    UoaEvent,
    UoaRepo,
)


@pytest.fixture
def conn(tmp_path: Path):
    db_file = tmp_path / "test.db"
    c = connect(db_file)
    apply_base_schema(c)
    yield c
    c.close()


def test_schema_version_set(conn):
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    assert row["v"] == 1


def test_stocks_upsert_and_get(conn):
    repo = StocksRepo(conn)
    repo.upsert(Stock(symbol="NVDA", name="NVIDIA", sector="Tech", market_cap=3e12, avg_volume=50_000_000))
    got = repo.get("NVDA")
    assert got is not None
    assert got["symbol"] == "NVDA"
    assert got["sector"] == "Tech"

    # update path
    repo.upsert(Stock(symbol="NVDA", name="NVIDIA Corp", sector="Tech", market_cap=3.1e12, avg_volume=50_000_000))
    got = repo.get("NVDA")
    assert got["name"] == "NVIDIA Corp"


def test_stocks_upsert_many_and_list(conn):
    repo = StocksRepo(conn)
    n = repo.upsert_many(
        [
            Stock(symbol="AAPL", name="Apple"),
            Stock(symbol="TSLA", name="Tesla"),
            Stock(symbol="MSFT", name="Microsoft"),
        ]
    )
    assert n == 3
    rows = repo.list_recent(limit=10)
    assert len(rows) == 3
    assert {r["symbol"] for r in rows} == {"AAPL", "TSLA", "MSFT"}


def test_trades_blocks_insert_and_imbalance(conn):
    repo = TradesRepo(conn)
    repo.insert_many(
        [
            BlockTrade(symbol="NVDA", size=15000, price=500.0, side="buy", ts="2026-05-04T14:30:00Z"),
            BlockTrade(symbol="NVDA", size=20000, price=501.0, side="buy", ts="2026-05-04T14:31:00Z"),
            BlockTrade(symbol="NVDA", size=10000, price=499.5, side="sell", ts="2026-05-04T14:32:00Z"),
        ]
    )
    rows = repo.list_for_symbol("NVDA")
    assert len(rows) == 3

    imb = repo.buy_sell_imbalance("NVDA", since_iso="2026-05-04T00:00:00Z")
    assert imb["buy_size"] == 35000
    assert imb["sell_size"] == 10000


def test_news_dedup_by_external_id(conn):
    repo = NewsRepo(conn)
    item = NewsItem(
        external_id="alp-1",
        headline="NVDA beats earnings",
        ts="2026-05-04T20:00:00Z",
        source="Bloomberg",
        symbols=["NVDA"],
    )
    rid = repo.insert(item)
    assert rid is not None
    rid2 = repo.insert(item)  # duplicate
    assert rid2 is None


def test_news_count_for_symbol(conn):
    repo = NewsRepo(conn)
    repo.insert(NewsItem(external_id="a", headline="h1", ts="2026-05-04T10:00:00Z", symbols=["NVDA", "AMD"]))
    repo.insert(NewsItem(external_id="b", headline="h2", ts="2026-05-04T11:00:00Z", symbols=["NVDA"]))
    repo.insert(NewsItem(external_id="c", headline="h3", ts="2026-05-04T12:00:00Z", symbols=["TSLA"]))
    assert repo.count_for_symbol("NVDA", since_iso="2026-05-04T00:00:00Z") == 2
    assert repo.count_for_symbol("TSLA", since_iso="2026-05-04T00:00:00Z") == 1
    assert repo.count_for_symbol("AMD", since_iso="2026-05-04T00:00:00Z") == 1


def test_uoa_insert_and_count(conn):
    repo = UoaRepo(conn)
    repo.insert(
        UoaEvent(
            symbol="NVDA",
            contract_symbol="NVDA260516C00550000",
            option_type="call",
            strike=550.0,
            expiration="2026-05-16",
            side="buy",
            size=1000,
            price=12.5,
            premium_total=1_250_000,
            ts="2026-05-04T15:00:00Z",
            aggressive=True,
            otm_pct=10.0,
            vol_oi_ratio=3.2,
        )
    )
    assert repo.count_for_symbol("NVDA", since_iso="2026-05-04T00:00:00Z") == 1


def test_heat_scores_upsert_and_top(conn):
    repo = HeatScoresRepo(conn)
    repo.upsert("NVDA", "2026-05-04", heat_score=87.5, volume_vs_adv=2.3, news_density=12)
    repo.upsert("TSLA", "2026-05-04", heat_score=81.2, volume_vs_adv=1.9, news_density=15)
    repo.upsert("AAPL", "2026-05-04", heat_score=65.0, volume_vs_adv=1.8)

    top = repo.top("2026-05-04", limit=2)
    assert [r["symbol"] for r in top] == ["NVDA", "TSLA"]

    # upsert overrides
    repo.upsert("NVDA", "2026-05-04", heat_score=90.0)
    top = repo.top("2026-05-04", limit=1)
    assert top[0]["symbol"] == "NVDA"
    assert top[0]["heat_score"] == 90.0


def test_recommendations_upsert_and_list(conn):
    repo = RecommendationsRepo(conn)
    repo.upsert(
        "NVDA",
        "2026-05-04",
        category="strong_long",
        heat_score=87.5,
        smart_money_score=72.0,
        entry_price=500.0,
        stop_loss=490.0,
        target_price=520.0,
        reason={"signals": ["uoa", "ma_break", "rsi_ok"]},
    )
    repo.upsert("SOFI", "2026-05-04", category="avoid", heat_score=95.0)

    rows = repo.list_for_date("2026-05-04")
    assert len(rows) == 2
    cats = {r["symbol"]: r["category"] for r in rows}
    assert cats["NVDA"] == "strong_long"
    assert cats["SOFI"] == "avoid"


def test_transaction_rolls_back_on_error(conn):
    repo = StocksRepo(conn)
    with pytest.raises(ValueError):
        with transaction(conn):
            repo.upsert(Stock(symbol="GOOG", name="Google"))
            raise ValueError("boom")
    assert repo.get("GOOG") is None
