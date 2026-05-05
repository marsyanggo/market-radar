-- Market Radar SQLite schema
-- Version: 1
--
-- Conventions:
--   - all timestamps stored as ISO-8601 UTC strings (TEXT)
--   - all date columns stored as 'YYYY-MM-DD' (TEXT)
--   - prices stored as REAL (sqlite has no DECIMAL); aggregate carefully
--   - foreign keys enabled at connection time (PRAGMA foreign_keys=ON)

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- ============================================================
-- 1. stocks — master watchlist (universe Market Radar tracks)
-- ============================================================
CREATE TABLE IF NOT EXISTS stocks (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    sector TEXT,
    market_cap REAL,            -- in dollars
    avg_volume INTEGER,         -- 30d average daily volume (shares)
    last_seen_at TEXT NOT NULL, -- last time it appeared in screener
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_stocks_last_seen ON stocks(last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_stocks_sector ON stocks(sector);

-- ============================================================
-- 2. trades_blocks — block trades (size >= 10K shares)
-- ============================================================
CREATE TABLE IF NOT EXISTS trades_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    size INTEGER NOT NULL,      -- shares
    price REAL NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('buy','sell','unknown')),
    exchange TEXT,
    ts TEXT NOT NULL,           -- trade timestamp (ISO-8601 UTC)
    ingested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_trades_blocks_symbol_ts ON trades_blocks(symbol, ts DESC);
CREATE INDEX IF NOT EXISTS idx_trades_blocks_ts ON trades_blocks(ts DESC);

-- ============================================================
-- 3. news — news items from Alpaca News Stream
-- ============================================================
CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE,    -- alpaca news id (dedup key)
    url TEXT,
    headline TEXT NOT NULL,
    source TEXT,
    author TEXT,
    summary TEXT,
    content TEXT,
    symbols TEXT,               -- JSON array of related symbols
    sentiment_score REAL,       -- filled in Phase 5 by LLM (-1..+1)
    ts TEXT NOT NULL,           -- published timestamp
    ingested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_news_ts ON news(ts DESC);

-- ============================================================
-- 4. uoa — unusual options activity
-- ============================================================
CREATE TABLE IF NOT EXISTS uoa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    contract_symbol TEXT NOT NULL,    -- e.g., NVDA250516C00500000 (OCC)
    option_type TEXT NOT NULL CHECK(option_type IN ('call','put')),
    strike REAL NOT NULL,
    expiration TEXT NOT NULL,         -- YYYY-MM-DD
    side TEXT NOT NULL CHECK(side IN ('buy','sell','unknown')),
    size INTEGER NOT NULL,            -- contracts
    price REAL NOT NULL,              -- per contract
    premium_total REAL NOT NULL,      -- size * price * 100
    iv REAL,
    volume INTEGER,
    open_interest INTEGER,
    vol_oi_ratio REAL,
    aggressive INTEGER NOT NULL DEFAULT 0,  -- bool: hit ask side
    otm_pct REAL,                     -- distance OTM as %
    ts TEXT NOT NULL,
    ingested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_uoa_symbol_ts ON uoa(symbol, ts DESC);

-- ============================================================
-- 5. heat_scores — daily heat score snapshot
-- ============================================================
CREATE TABLE IF NOT EXISTS heat_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    as_of TEXT NOT NULL,              -- YYYY-MM-DD
    volume_vs_adv REAL,               -- today_vol / 30d_avg
    large_block_pct REAL,             -- block volume / total volume
    options_uoa_count INTEGER DEFAULT 0,
    news_density INTEGER,             -- 24h news count
    heat_score REAL NOT NULL,         -- 0-100
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(symbol, as_of)
);

CREATE INDEX IF NOT EXISTS idx_heat_scores_as_of ON heat_scores(as_of DESC, heat_score DESC);

-- ============================================================
-- 6. technical_indicators — daily snapshot of EOD technicals
-- ============================================================
CREATE TABLE IF NOT EXISTS technical_indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    as_of TEXT NOT NULL,              -- YYYY-MM-DD
    close REAL NOT NULL,
    rsi_14 REAL,
    macd REAL,
    macd_signal REAL,
    macd_hist REAL,
    sma_20 REAL,
    sma_50 REAL,
    sma_200 REAL,
    bb_upper REAL,
    bb_middle REAL,
    bb_lower REAL,
    atr_14 REAL,
    high_52w REAL,
    low_52w REAL,
    pct_from_high_52w REAL,
    pct_from_low_52w REAL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(symbol, as_of)
);

CREATE INDEX IF NOT EXISTS idx_tech_as_of ON technical_indicators(as_of DESC);

-- ============================================================
-- 7. recommendations — daily recommendation list
-- ============================================================
CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    as_of TEXT NOT NULL,              -- YYYY-MM-DD
    category TEXT NOT NULL CHECK(category IN ('strong_long','watch','avoid')),
    heat_score REAL,
    smart_money_score REAL,
    sentiment_score REAL,
    entry_price REAL,
    stop_loss REAL,
    target_price REAL,
    reason TEXT,                      -- JSON: {signals: [...], notes: ...}
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(symbol, as_of)
);

CREATE INDEX IF NOT EXISTS idx_recs_as_of ON recommendations(as_of DESC);
