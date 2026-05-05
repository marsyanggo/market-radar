"""Unusual Options Activity detector.

UOA criteria (snapshot-based, no OI feed available on free tier):
  - last_size >= MIN_SIZE (default 50 contracts)
  - aggressive: last_price >= ask  (buyer hit the ask)
                last_price <= bid  (seller hit the bid)
  - liquid quote (bid > 0, ask > 0)
  - reasonable distance from money (5% <= |otm| <= 25%)

Each qualifying snapshot becomes a row in `uoa`. Side is buy if hit-ask,
sell if hit-bid, otherwise unknown.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from src.alpaca.options_chain import OptionSnap
from src.db.connection import get_conn, transaction
from src.db.repos import UoaEvent, UoaRepo
from src.logger import logger

MIN_SIZE = 50
MIN_OTM = 5.0
MAX_OTM = 25.0


def is_unusual(snap: OptionSnap) -> bool:
    if snap.last_size is None or snap.last_size < MIN_SIZE:
        return False
    if snap.bid is None or snap.ask is None or snap.bid <= 0 or snap.ask <= 0:
        return False
    if snap.last_price is None:
        return False
    if snap.otm_pct_value is None:
        return False
    abs_otm = abs(snap.otm_pct_value)
    if abs_otm < MIN_OTM or abs_otm > MAX_OTM:
        return False
    return True


def classify_side(snap: OptionSnap) -> str:
    if snap.last_price >= snap.ask:
        return "buy"
    if snap.last_price <= snap.bid:
        return "sell"
    return "unknown"


def to_uoa_event(snap: OptionSnap) -> UoaEvent:
    side = classify_side(snap)
    aggressive = side in ("buy", "sell")
    premium_total = snap.last_price * snap.last_size * 100
    return UoaEvent(
        symbol=snap.contract.underlying,
        contract_symbol=snap.contract.contract_symbol,
        option_type=snap.contract.option_type,
        strike=snap.contract.strike,
        expiration=snap.contract.expiration.isoformat(),
        side=side,
        size=snap.last_size,
        price=snap.last_price,
        premium_total=premium_total,
        ts=snap.last_ts or datetime.now(timezone.utc).isoformat(),
        iv=snap.iv,
        aggressive=aggressive,
        otm_pct=snap.otm_pct_value,
    )


def detect_and_persist(snaps: list[OptionSnap]) -> int:
    """Filter snapshots for UOA candidates and insert into the uoa table.

    Note: current snapshot-based approach can't distinguish "today's events"
    from leftover quotes. Each call re-detects from latest snapshot — the
    same big trade could be re-recorded on multiple runs. dedup that later
    if needed.
    """
    candidates = [s for s in snaps if is_unusual(s)]
    if not candidates:
        return 0

    persisted = 0
    with get_conn() as conn:
        with transaction(conn):
            repo = UoaRepo(conn)
            for s in candidates:
                repo.insert(to_uoa_event(s))
                persisted += 1
    logger.info(f"UOA detected: {persisted} events from {len(snaps)} snapshots")
    return persisted
