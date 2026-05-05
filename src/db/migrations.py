"""Simple linear migrations.

Each migration is (version_number, sql). They run in order, idempotently.
The base schema lives in schema.sql and is treated as version 1.
"""

from pathlib import Path

from src.db.connection import connect
from src.logger import logger

SCHEMA_FILE = Path(__file__).parent / "schema.sql"

# Future migrations: (version, sql_string). Version 1 is schema.sql.
MIGRATIONS: list[tuple[int, str]] = [
    (
        2,
        # Daily snapshot of an option chain (one row per contract per day).
        # Used for derived metrics (P/C ratio, IV skew, near-the-money count).
        """
        CREATE TABLE IF NOT EXISTS option_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            contract_symbol TEXT NOT NULL,
            option_type TEXT NOT NULL CHECK(option_type IN ('call','put')),
            strike REAL NOT NULL,
            expiration TEXT NOT NULL,
            iv REAL,
            delta REAL,
            gamma REAL,
            theta REAL,
            vega REAL,
            rho REAL,
            bid REAL,
            ask REAL,
            last_price REAL,
            last_size INTEGER,
            otm_pct REAL,
            ts TEXT NOT NULL,
            as_of TEXT NOT NULL,
            ingested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            UNIQUE(contract_symbol, as_of)
        );
        CREATE INDEX IF NOT EXISTS idx_snap_symbol_as_of ON option_snapshots(symbol, as_of);
        CREATE INDEX IF NOT EXISTS idx_snap_otm ON option_snapshots(symbol, as_of, otm_pct);
        """,
    ),
    (
        3,
        # Per-day option flow summary (P/C ratio, IV skew, smart money score).
        """
        CREATE TABLE IF NOT EXISTS option_flow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            as_of TEXT NOT NULL,
            call_count INTEGER DEFAULT 0,
            put_count INTEGER DEFAULT 0,
            put_call_ratio REAL,
            iv_skew_25d REAL,
            uoa_count INTEGER DEFAULT 0,
            smart_money_score REAL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            UNIQUE(symbol, as_of)
        );
        CREATE INDEX IF NOT EXISTS idx_flow_as_of ON option_flow(as_of DESC);
        """,
    ),
    (
        4,
        # Per-day sentiment summary (combined LLM news + StockTwits + others).
        """
        CREATE TABLE IF NOT EXISTS sentiment_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            as_of TEXT NOT NULL,
            news_count INTEGER DEFAULT 0,
            news_avg_sentiment REAL,
            stocktwits_bullish INTEGER,
            stocktwits_bearish INTEGER,
            stocktwits_bullish_ratio REAL,
            sentiment_score REAL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            UNIQUE(symbol, as_of)
        );
        CREATE INDEX IF NOT EXISTS idx_sent_as_of ON sentiment_daily(as_of DESC);
        """,
    ),
    (
        5,
        # SEC EDGAR Form 4 — insider transactions (officers, directors, 10%+ owners).
        # Transaction codes: P=open-market purchase, S=open-market sale,
        # A=grant/award, M=option exercise, F=tax withholding, etc.
        """
        CREATE TABLE IF NOT EXISTS insider_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            cik INTEGER NOT NULL,
            accession TEXT NOT NULL,
            insider_name TEXT,
            insider_role TEXT,
            transaction_code TEXT,
            transaction_date TEXT NOT NULL,
            shares REAL NOT NULL,
            price_per_share REAL,
            total_value REAL,
            shares_owned_after REAL,
            filing_date TEXT NOT NULL,
            ingested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            UNIQUE(accession, transaction_code, transaction_date, shares, price_per_share, insider_name)
        );
        CREATE INDEX IF NOT EXISTS idx_insider_symbol_date ON insider_trades(symbol, transaction_date DESC);
        CREATE INDEX IF NOT EXISTS idx_insider_filing_date ON insider_trades(filing_date DESC);
        """,
    ),
]


def current_version(conn) -> int:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    if cur.fetchone() is None:
        return 0
    cur = conn.execute("SELECT MAX(version) AS v FROM schema_version")
    row = cur.fetchone()
    return row["v"] or 0


def apply_base_schema(conn) -> None:
    sql = SCHEMA_FILE.read_text()
    conn.executescript(sql)
    conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (1)")


def apply_migrations(conn) -> None:
    for version, sql in MIGRATIONS:
        cur = conn.execute("SELECT 1 FROM schema_version WHERE version = ?", (version,))
        if cur.fetchone():
            continue
        logger.info(f"applying migration v{version}")
        conn.executescript(sql)
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))


def init_db(db_path: Path | None = None) -> int:
    """Bootstrap and migrate the DB. Returns the resulting version."""
    conn = connect(db_path)
    try:
        v = current_version(conn)
        if v == 0:
            logger.info("creating base schema (v1)")
            apply_base_schema(conn)
        apply_migrations(conn)
        return current_version(conn)
    finally:
        conn.close()
