"""CRUD repositories — thin wrappers around sqlite for typed access.

Each repo takes a connection so callers control transactions.
"""

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ============================================================
# stocks
# ============================================================
@dataclass
class Stock:
    symbol: str
    name: str | None = None
    sector: str | None = None
    market_cap: float | None = None
    avg_volume: int | None = None
    last_seen_at: str = field(default_factory=_now)


class StocksRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, stock: Stock) -> None:
        self.conn.execute(
            """
            INSERT INTO stocks (symbol, name, sector, market_cap, avg_volume, last_seen_at)
            VALUES (:symbol, :name, :sector, :market_cap, :avg_volume, :last_seen_at)
            ON CONFLICT(symbol) DO UPDATE SET
                name=excluded.name,
                sector=excluded.sector,
                market_cap=excluded.market_cap,
                avg_volume=excluded.avg_volume,
                last_seen_at=excluded.last_seen_at,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            asdict(stock),
        )

    def upsert_many(self, stocks: list[Stock]) -> int:
        if not stocks:
            return 0
        self.conn.executemany(
            """
            INSERT INTO stocks (symbol, name, sector, market_cap, avg_volume, last_seen_at)
            VALUES (:symbol, :name, :sector, :market_cap, :avg_volume, :last_seen_at)
            ON CONFLICT(symbol) DO UPDATE SET
                name=excluded.name,
                sector=excluded.sector,
                market_cap=excluded.market_cap,
                avg_volume=excluded.avg_volume,
                last_seen_at=excluded.last_seen_at,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            [asdict(s) for s in stocks],
        )
        return len(stocks)

    def get(self, symbol: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM stocks WHERE symbol = ?", (symbol,)).fetchone()
        return dict(row) if row else None

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM stocks ORDER BY last_seen_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ============================================================
# trades_blocks
# ============================================================
@dataclass
class BlockTrade:
    symbol: str
    size: int
    price: float
    side: str  # 'buy' | 'sell' | 'unknown'
    ts: str
    exchange: str | None = None


class TradesRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def insert(self, trade: BlockTrade) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO trades_blocks (symbol, size, price, side, exchange, ts)
            VALUES (:symbol, :size, :price, :side, :exchange, :ts)
            """,
            asdict(trade),
        )
        return cur.lastrowid

    def insert_many(self, trades: list[BlockTrade]) -> int:
        if not trades:
            return 0
        self.conn.executemany(
            """
            INSERT INTO trades_blocks (symbol, size, price, side, exchange, ts)
            VALUES (:symbol, :size, :price, :side, :exchange, :ts)
            """,
            [asdict(t) for t in trades],
        )
        return len(trades)

    def list_for_symbol(self, symbol: str, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM trades_blocks WHERE symbol = ? ORDER BY ts DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def buy_sell_imbalance(self, symbol: str, since_iso: str) -> dict[str, int]:
        row = self.conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN side='buy'  THEN size ELSE 0 END), 0) AS buy_size,
                COALESCE(SUM(CASE WHEN side='sell' THEN size ELSE 0 END), 0) AS sell_size
            FROM trades_blocks
            WHERE symbol = ? AND ts >= ?
            """,
            (symbol, since_iso),
        ).fetchone()
        return {"buy_size": row["buy_size"], "sell_size": row["sell_size"]}


# ============================================================
# news
# ============================================================
@dataclass
class NewsItem:
    headline: str
    ts: str
    external_id: str | None = None
    url: str | None = None
    source: str | None = None
    author: str | None = None
    summary: str | None = None
    content: str | None = None
    symbols: list[str] = field(default_factory=list)
    sentiment_score: float | None = None


class NewsRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def insert(self, item: NewsItem) -> int | None:
        """Returns lastrowid on insert, None if duplicate (external_id conflict)."""
        try:
            cur = self.conn.execute(
                """
                INSERT INTO news
                  (external_id, url, headline, source, author, summary, content, symbols, sentiment_score, ts)
                VALUES
                  (:external_id, :url, :headline, :source, :author, :summary, :content, :symbols, :sentiment_score, :ts)
                """,
                {
                    **asdict(item),
                    "symbols": json.dumps(item.symbols),
                },
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def count_for_symbol(self, symbol: str, since_iso: str) -> int:
        # JSON match — simple LIKE filter; for higher volume migrate to news_symbols join table
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM news
            WHERE ts >= ?
              AND symbols LIKE ?
            """,
            (since_iso, f'%"{symbol}"%'),
        ).fetchone()
        return row["c"]


# ============================================================
# uoa
# ============================================================
@dataclass
class UoaEvent:
    symbol: str
    contract_symbol: str
    option_type: str  # 'call' | 'put'
    strike: float
    expiration: str  # YYYY-MM-DD
    side: str  # 'buy' | 'sell' | 'unknown'
    size: int
    price: float
    premium_total: float
    ts: str
    iv: float | None = None
    volume: int | None = None
    open_interest: int | None = None
    vol_oi_ratio: float | None = None
    aggressive: bool = False
    otm_pct: float | None = None


class UoaRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def insert(self, event: UoaEvent) -> int:
        d = asdict(event)
        d["aggressive"] = 1 if event.aggressive else 0
        cur = self.conn.execute(
            """
            INSERT INTO uoa
              (symbol, contract_symbol, option_type, strike, expiration, side, size, price,
               premium_total, iv, volume, open_interest, vol_oi_ratio, aggressive, otm_pct, ts)
            VALUES
              (:symbol, :contract_symbol, :option_type, :strike, :expiration, :side, :size, :price,
               :premium_total, :iv, :volume, :open_interest, :vol_oi_ratio, :aggressive, :otm_pct, :ts)
            """,
            d,
        )
        return cur.lastrowid

    def count_for_symbol(self, symbol: str, since_iso: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM uoa WHERE symbol = ? AND ts >= ?",
            (symbol, since_iso),
        ).fetchone()
        return row["c"]


# ============================================================
# technical_indicators
# ============================================================
class TechnicalsRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, snap) -> None:
        """Accepts a TechnicalSnapshot dataclass from src.indicators.technical."""
        self.conn.execute(
            """
            INSERT INTO technical_indicators
              (symbol, as_of, close, rsi_14, macd, macd_signal, macd_hist,
               sma_20, sma_50, sma_200, bb_upper, bb_middle, bb_lower, atr_14,
               high_52w, low_52w, pct_from_high_52w, pct_from_low_52w)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, as_of) DO UPDATE SET
              close=excluded.close,
              rsi_14=excluded.rsi_14,
              macd=excluded.macd,
              macd_signal=excluded.macd_signal,
              macd_hist=excluded.macd_hist,
              sma_20=excluded.sma_20,
              sma_50=excluded.sma_50,
              sma_200=excluded.sma_200,
              bb_upper=excluded.bb_upper,
              bb_middle=excluded.bb_middle,
              bb_lower=excluded.bb_lower,
              atr_14=excluded.atr_14,
              high_52w=excluded.high_52w,
              low_52w=excluded.low_52w,
              pct_from_high_52w=excluded.pct_from_high_52w,
              pct_from_low_52w=excluded.pct_from_low_52w
            """,
            (
                snap.symbol, snap.as_of, snap.close,
                snap.rsi_14, snap.macd, snap.macd_signal, snap.macd_hist,
                snap.sma_20, snap.sma_50, snap.sma_200,
                snap.bb_upper, snap.bb_middle, snap.bb_lower, snap.atr_14,
                snap.high_52w, snap.low_52w, snap.pct_from_high_52w, snap.pct_from_low_52w,
            ),
        )

    def get(self, symbol: str, as_of: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM technical_indicators WHERE symbol=? AND as_of=?",
            (symbol, as_of),
        ).fetchone()
        return dict(row) if row else None


# ============================================================
# heat_scores
# ============================================================
class HeatScoresRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(
        self,
        symbol: str,
        as_of: str,
        heat_score: float,
        volume_vs_adv: float | None = None,
        large_block_pct: float | None = None,
        options_uoa_count: int = 0,
        news_density: int | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO heat_scores
              (symbol, as_of, volume_vs_adv, large_block_pct, options_uoa_count, news_density, heat_score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, as_of) DO UPDATE SET
              volume_vs_adv=excluded.volume_vs_adv,
              large_block_pct=excluded.large_block_pct,
              options_uoa_count=excluded.options_uoa_count,
              news_density=excluded.news_density,
              heat_score=excluded.heat_score
            """,
            (symbol, as_of, volume_vs_adv, large_block_pct, options_uoa_count, news_density, heat_score),
        )

    def top(self, as_of: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM heat_scores WHERE as_of = ? ORDER BY heat_score DESC LIMIT ?",
            (as_of, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ============================================================
# recommendations
# ============================================================
class RecommendationsRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(
        self,
        symbol: str,
        as_of: str,
        category: str,
        heat_score: float | None = None,
        smart_money_score: float | None = None,
        sentiment_score: float | None = None,
        entry_price: float | None = None,
        stop_loss: float | None = None,
        target_price: float | None = None,
        reason: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO recommendations
              (symbol, as_of, category, heat_score, smart_money_score, sentiment_score,
               entry_price, stop_loss, target_price, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, as_of) DO UPDATE SET
              category=excluded.category,
              heat_score=excluded.heat_score,
              smart_money_score=excluded.smart_money_score,
              sentiment_score=excluded.sentiment_score,
              entry_price=excluded.entry_price,
              stop_loss=excluded.stop_loss,
              target_price=excluded.target_price,
              reason=excluded.reason
            """,
            (
                symbol, as_of, category, heat_score, smart_money_score, sentiment_score,
                entry_price, stop_loss, target_price,
                json.dumps(reason) if reason else None,
            ),
        )

    def list_for_date(self, as_of: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM recommendations WHERE as_of = ? ORDER BY heat_score DESC",
            (as_of,),
        ).fetchall()
        return [dict(r) for r in rows]
