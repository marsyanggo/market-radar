"""Parse OCC option contract symbols.

Format: {ROOT}{YY}{MM}{DD}{C|P}{STRIKE_8DIGITS}
Example: NVDA260522P00180000
  → underlying=NVDA, expiration=2026-05-22, type=put, strike=180.000
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

OCC_RE = re.compile(r"^(?P<root>[A-Z0-9]{1,6})(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})(?P<cp>[CP])(?P<strike>\d{8})$")


@dataclass
class OptionContract:
    contract_symbol: str
    underlying: str
    expiration: date
    option_type: str  # 'call' | 'put'
    strike: float


def parse_occ(symbol: str) -> OptionContract | None:
    m = OCC_RE.match(symbol)
    if not m:
        return None
    yy = int(m["yy"])
    year = 2000 + yy if yy < 70 else 1900 + yy
    return OptionContract(
        contract_symbol=symbol,
        underlying=m["root"],
        expiration=date(year, int(m["mm"]), int(m["dd"])),
        option_type="call" if m["cp"] == "C" else "put",
        strike=int(m["strike"]) / 1000.0,
    )


def otm_pct(contract: OptionContract, underlying_price: float) -> float | None:
    """Return distance from spot to strike as +% OTM (positive = OTM, negative = ITM)."""
    if not underlying_price or underlying_price <= 0:
        return None
    if contract.option_type == "call":
        return (contract.strike - underlying_price) / underlying_price * 100
    else:  # put
        return (underlying_price - contract.strike) / underlying_price * 100
