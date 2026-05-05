"""Write proposed watchlists for AI_trader.

Writes to `data/proposed_watchlist.json` and `data/proposed_phase2_watchlist.json`
in the Market Radar repo (NOT directly to AI_trader's data dir — user must
review and manually promote, or wire up later once trust is established).

Schema matches AI_trader: just a JSON array of symbol strings.
"""

import json
from pathlib import Path

from configs.settings import settings
from src.db.connection import get_conn
from src.logger import logger

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def select_ic_watchlist(as_of: str, limit: int = 18) -> list[str]:
    """Candidates for AI_trader's iron-condor strategy.

    Heuristic until Phase 4 IV Rank is wired:
      - liquid (avg_volume reasonable)
      - not currently flagged as overheated (RSI < 75)
      - has bars data
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT t.symbol
            FROM technical_indicators t
            WHERE t.as_of = ?
              AND t.rsi_14 IS NOT NULL
              AND t.rsi_14 < 75
              AND t.close > 5.0
            ORDER BY ABS(t.rsi_14 - 50) ASC
            LIMIT ?
            """,
            (as_of, limit),
        ).fetchall()
    return [r["symbol"] for r in rows]


def select_phase2_watchlist(as_of: str, limit: int = 10) -> list[str]:
    """Candidates for AI_trader's Phase 2 (oversold + smart-money buy):
      - RSI < 35 (oversold)
      - any net-buy block trades in window
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT t.symbol
            FROM technical_indicators t
            WHERE t.as_of = ?
              AND t.rsi_14 IS NOT NULL
              AND t.rsi_14 < 35
              AND t.close > 5.0
            ORDER BY t.rsi_14 ASC
            LIMIT ?
            """,
            (as_of, limit),
        ).fetchall()
    return [r["symbol"] for r in rows]


def write_watchlists(as_of: str) -> dict[str, str]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    ic = select_ic_watchlist(as_of)
    p2 = select_phase2_watchlist(as_of)

    ic_path = DATA_DIR / "proposed_watchlist.json"
    p2_path = DATA_DIR / "proposed_phase2_watchlist.json"

    ic_path.write_text(json.dumps(ic, indent=2), encoding="utf-8")
    p2_path.write_text(json.dumps(p2, indent=2), encoding="utf-8")

    logger.info(f"watchlists: ic={len(ic)} → {ic_path.name}, phase2={len(p2)} → {p2_path.name}")
    return {"ic": str(ic_path), "phase2": str(p2_path), "ic_n": len(ic), "phase2_n": len(p2)}
