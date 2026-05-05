"""Form 4 — insider transaction filings.

Each Form 4 is an XML file with one or more transaction rows. We pull the
filings index for the company, filter for type=4, fetch the primary XML,
and parse the relevant fields.

Transaction codes:
  P = open-market purchase  (bullish)
  S = open-market sale      (bearish)
  A = grant/award            (neutral — comp)
  M = option exercise        (neutral)
  F = tax withholding        (neutral)
  D = disposition to issuer  (mostly neutral)
  G = gift                   (neutral)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.db.connection import get_conn, transaction
from src.edgar.client import (
    cik_for,
    fetch_filing_doc,
    fetch_submissions,
    find_form4_xml_doc,
)
from src.logger import logger


@dataclass
class InsiderTrade:
    symbol: str
    cik: int
    accession: str
    insider_name: str | None
    insider_role: str | None
    transaction_code: str | None
    transaction_date: str
    shares: float
    price_per_share: float | None
    total_value: float | None
    shares_owned_after: float | None
    filing_date: str


def _findtext(elem: ET.Element | None, path: str) -> str | None:
    if elem is None:
        return None
    found = elem.find(path)
    if found is None or found.text is None:
        return None
    return found.text.strip() or None


def _findfloat(elem: ET.Element | None, path: str) -> float | None:
    txt = _findtext(elem, path)
    try:
        return float(txt) if txt is not None else None
    except ValueError:
        return None


def _extract_role(reporter: ET.Element | None) -> str:
    """Combine relationship flags into a human-readable role."""
    if reporter is None:
        return ""
    rel = reporter.find("reportingOwnerRelationship")
    if rel is None:
        return ""
    parts: list[str] = []
    if (rel.findtext("isDirector") or "0").strip() == "1":
        parts.append("Director")
    if (rel.findtext("isOfficer") or "0").strip() == "1":
        title = rel.findtext("officerTitle") or "Officer"
        parts.append(f"Officer ({title.strip()})")
    if (rel.findtext("isTenPercentOwner") or "0").strip() == "1":
        parts.append("10% Owner")
    if (rel.findtext("isOther") or "0").strip() == "1":
        text = rel.findtext("otherText") or "Other"
        parts.append(f"Other ({text.strip()})")
    return ", ".join(parts)


def parse_form4_xml(xml_bytes: bytes, symbol: str, cik: int, accession: str) -> list[InsiderTrade]:
    """Parse a Form 4 XML body. Returns one InsiderTrade per non-derivative transaction row."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        logger.warning(f"form4 parse error for {accession}: {e}")
        return []

    filing_date = _findtext(root, "periodOfReport") or ""
    reporter = root.find("reportingOwner")
    insider_name = _findtext(reporter, "reportingOwnerId/rptOwnerName")
    role = _extract_role(reporter)

    out: list[InsiderTrade] = []
    txn_table = root.find("nonDerivativeTable")
    if txn_table is None:
        return out

    for txn in txn_table.findall("nonDerivativeTransaction"):
        date = _findtext(txn, "transactionDate/value")
        coding = txn.find("transactionCoding")
        code = _findtext(coding, "transactionCode")
        amounts = txn.find("transactionAmounts")
        shares = _findfloat(amounts, "transactionShares/value")
        price = _findfloat(amounts, "transactionPricePerShare/value")
        ad = _findtext(amounts, "transactionAcquiredDisposedCode/value")
        sign = 1 if ad == "A" else (-1 if ad == "D" else 1)

        post = _findfloat(txn, "postTransactionAmounts/sharesOwnedFollowingTransaction/value")

        if shares is None or date is None:
            continue

        total_value = (sign * shares * price) if price is not None else None

        out.append(
            InsiderTrade(
                symbol=symbol,
                cik=cik,
                accession=accession,
                insider_name=insider_name,
                insider_role=role or None,
                transaction_code=code,
                transaction_date=date,
                shares=sign * shares,
                price_per_share=price,
                total_value=total_value,
                shares_owned_after=post,
                filing_date=filing_date or date,
            )
        )
    return out


def fetch_recent_form4(symbol: str, days_back: int = 30, limit: int = 30) -> list[InsiderTrade]:
    """Fetch and parse the last `limit` Form 4 filings within `days_back` days for a ticker."""
    cik = cik_for(symbol)
    if cik is None:
        logger.warning(f"no CIK for {symbol}")
        return []

    submissions = fetch_submissions(cik)
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    filing_dates = recent.get("filingDate", [])

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

    trades: list[InsiderTrade] = []
    fetched = 0
    for form, accession, primary_doc, fdate in zip(forms, accessions, primary_docs, filing_dates):
        if fetched >= limit:
            break
        if form != "4":
            continue
        if fdate < cutoff:
            break  # filings are sorted newest first

        try:
            # primary_doc is often the rendered HTML wrapper; find the real XML
            xml_doc = find_form4_xml_doc(cik, accession) or primary_doc
            if not xml_doc.endswith(".xml"):
                continue
            xml = fetch_filing_doc(cik, accession, xml_doc)
            trades.extend(parse_form4_xml(xml, symbol, cik, accession))
            fetched += 1
        except Exception:
            logger.exception(f"form4 fetch failed for {symbol} {accession}")

    logger.info(f"{symbol}: parsed {len(trades)} insider txns from {fetched} filings")
    return trades


def persist_trades(trades: list[InsiderTrade]) -> int:
    if not trades:
        return 0
    inserted = 0
    with get_conn() as conn:
        with transaction(conn):
            for t in trades:
                try:
                    conn.execute(
                        """
                        INSERT INTO insider_trades
                          (symbol, cik, accession, insider_name, insider_role,
                           transaction_code, transaction_date, shares,
                           price_per_share, total_value, shares_owned_after, filing_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            t.symbol, t.cik, t.accession, t.insider_name, t.insider_role,
                            t.transaction_code, t.transaction_date, t.shares,
                            t.price_per_share, t.total_value, t.shares_owned_after, t.filing_date,
                        ),
                    )
                    inserted += 1
                except Exception:
                    pass  # UNIQUE constraint conflict — already have it
    return inserted


def fetch_and_persist(symbols: list[str], days_back: int = 30) -> dict[str, int]:
    counts = {"symbols": 0, "trades": 0}
    for sym in symbols:
        try:
            trades = fetch_recent_form4(sym, days_back=days_back)
            n = persist_trades(trades)
            if n > 0:
                counts["symbols"] += 1
                counts["trades"] += n
        except Exception:
            logger.exception(f"form4 pipeline failed for {sym}")
    logger.info(f"form4 fetch_and_persist: {counts}")
    return counts
