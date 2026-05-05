"""Market Radar Dashboard API.

Read-only views over the SQLite DB. Run with:
    uvicorn dashboard.api.app:app --reload --port 8765
or:
    radar dashboard
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from src.db.connection import get_conn

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Market Radar Dashboard", version="0.1")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]


@app.get("/api/heat")
def heat(as_of: str | None = None, limit: int = 25) -> dict:
    as_of = as_of or _today()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT h.symbol, h.heat_score, h.volume_vs_adv, h.options_uoa_count, h.news_density,
                   t.close, t.rsi_14, t.sma_20, t.pct_from_high_52w,
                   f.put_call_ratio, f.iv_skew_25d, f.smart_money_score, f.uoa_count,
                   s.sentiment_score
            FROM heat_scores h
            LEFT JOIN technical_indicators t ON t.symbol = h.symbol AND t.as_of = h.as_of
            LEFT JOIN option_flow f          ON f.symbol = h.symbol AND f.as_of = h.as_of
            LEFT JOIN sentiment_daily s      ON s.symbol = h.symbol AND s.as_of = h.as_of
            WHERE h.as_of = ?
            ORDER BY h.heat_score DESC
            LIMIT ?
            """,
            (as_of, limit),
        ).fetchall()
    return {"as_of": as_of, "rows": _rows_to_dicts(rows)}


@app.get("/api/recommendations")
def recommendations(as_of: str | None = None) -> dict:
    as_of = as_of or _today()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT r.symbol, r.category, r.heat_score, r.smart_money_score,
                   r.entry_price, r.reason, t.rsi_14, t.close,
                   s.sentiment_score
            FROM recommendations r
            LEFT JOIN technical_indicators t ON t.symbol = r.symbol AND t.as_of = r.as_of
            LEFT JOIN sentiment_daily s      ON s.symbol = r.symbol AND s.as_of = r.as_of
            WHERE r.as_of = ?
            ORDER BY r.heat_score DESC
            """,
            (as_of,),
        ).fetchall()
    return {"as_of": as_of, "rows": _rows_to_dicts(rows)}


@app.get("/api/smart_money")
def smart_money(as_of: str | None = None, limit: int = 15) -> dict:
    as_of = as_of or _today()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT symbol, smart_money_score, uoa_count, put_call_ratio, iv_skew_25d,
                   call_count, put_count
            FROM option_flow
            WHERE as_of = ? AND smart_money_score IS NOT NULL
            ORDER BY smart_money_score DESC
            LIMIT ?
            """,
            (as_of, limit),
        ).fetchall()
    return {"as_of": as_of, "rows": _rows_to_dicts(rows)}


@app.get("/api/stock/{symbol}")
def stock_detail(symbol: str) -> dict:
    sym = symbol.upper()
    today = _today()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    with get_conn() as conn:
        stock = conn.execute("SELECT * FROM stocks WHERE symbol = ?", (sym,)).fetchone()
        if stock is None:
            raise HTTPException(404, f"unknown symbol: {sym}")

        tech = conn.execute(
            "SELECT * FROM technical_indicators WHERE symbol=? AND as_of=?", (sym, today),
        ).fetchone()
        heat_row = conn.execute(
            "SELECT * FROM heat_scores WHERE symbol=? AND as_of=?", (sym, today),
        ).fetchone()
        flow = conn.execute(
            "SELECT * FROM option_flow WHERE symbol=? AND as_of=?", (sym, today),
        ).fetchone()
        sent = conn.execute(
            "SELECT * FROM sentiment_daily WHERE symbol=? AND as_of=?", (sym, today),
        ).fetchone()

        recent_news = conn.execute(
            """
            SELECT headline, source, ts, sentiment_score, url
            FROM news
            WHERE symbols LIKE ? AND ts >= ?
            ORDER BY ts DESC LIMIT 12
            """,
            (f'%"{sym}"%', week_ago),
        ).fetchall()

        recent_blocks = conn.execute(
            """
            SELECT size, price, side, exchange, ts
            FROM trades_blocks
            WHERE symbol = ? AND ts >= ?
            ORDER BY ts DESC LIMIT 30
            """,
            (sym, week_ago),
        ).fetchall()

        recent_uoa = conn.execute(
            """
            SELECT contract_symbol, option_type, strike, expiration, side, size,
                   price, premium_total, otm_pct, ts
            FROM uoa
            WHERE symbol = ? AND ts >= ?
            ORDER BY ts DESC LIMIT 20
            """,
            (sym, week_ago),
        ).fetchall()

        recent_insider = conn.execute(
            """
            SELECT insider_name, insider_role, transaction_code, transaction_date,
                   shares, price_per_share, total_value
            FROM insider_trades
            WHERE symbol = ?
            ORDER BY transaction_date DESC LIMIT 20
            """,
            (sym,),
        ).fetchall()

    return {
        "symbol": sym,
        "stock": dict(stock),
        "today": today,
        "technical": dict(tech) if tech else None,
        "heat": dict(heat_row) if heat_row else None,
        "option_flow": dict(flow) if flow else None,
        "sentiment": dict(sent) if sent else None,
        "recent_news": _rows_to_dicts(recent_news),
        "recent_blocks": _rows_to_dicts(recent_blocks),
        "recent_uoa": _rows_to_dicts(recent_uoa),
        "recent_insider": _rows_to_dicts(recent_insider),
    }


@app.get("/api/health")
def health() -> dict:
    with get_conn() as conn:
        ver = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        n_stocks = conn.execute("SELECT COUNT(*) AS n FROM stocks").fetchone()
    return {"ok": True, "schema_version": ver["v"], "n_stocks": n_stocks["n"]}


# Static frontend — mount LAST so /api/* routes win.
# StaticFiles(html=True) auto-serves index.html for "/".
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
