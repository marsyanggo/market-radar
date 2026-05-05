"""SEC EDGAR API client.

Public API (no key needed) — but User-Agent header is required by SEC's
fair-access policy. Rate limit: 10 req/sec.

Endpoints used:
  - https://www.sec.gov/files/company_tickers.json     ticker → CIK map
  - https://data.sec.gov/submissions/CIK{cik:010d}.json filings index
  - https://www.sec.gov/Archives/edgar/data/{cik}/...   filing files
"""

from __future__ import annotations

import time
from threading import Lock

import httpx

from src.logger import logger

USER_AGENT = "Market Radar marsyanggo@gmail.com"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

_RATE_LIMIT_RPS = 8.0  # SEC allows 10/s; leave headroom
_last_request_at = 0.0
_lock = Lock()


def _throttle() -> None:
    """Block until ≥ 1/RPS since the last call."""
    global _last_request_at
    with _lock:
        delay = 1.0 / _RATE_LIMIT_RPS - (time.monotonic() - _last_request_at)
        if delay > 0:
            time.sleep(delay)
        _last_request_at = time.monotonic()


def _get(url: str, timeout: float = 15.0) -> dict:
    _throttle()
    with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
        resp = client.get(url)
    resp.raise_for_status()
    return resp.json()


_ticker_cache: dict[str, int] | None = None


def load_ticker_cik_map(force_refresh: bool = False) -> dict[str, int]:
    """Load and cache the ticker → CIK mapping from SEC."""
    global _ticker_cache
    if _ticker_cache is not None and not force_refresh:
        return _ticker_cache

    data = _get(TICKERS_URL)
    # Format: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    out: dict[str, int] = {}
    for entry in data.values():
        ticker = entry.get("ticker", "").upper()
        cik = entry.get("cik_str")
        if ticker and isinstance(cik, int):
            out[ticker] = cik
    _ticker_cache = out
    logger.info(f"loaded {len(out)} ticker → CIK mappings from SEC")
    return out


def cik_for(symbol: str) -> int | None:
    return load_ticker_cik_map().get(symbol.upper())


def fetch_submissions(cik: int) -> dict:
    """Fetch the filings index for one CIK. Contains recent + historical filings."""
    return _get(SUBMISSIONS_URL.format(cik=cik))


def filing_url(cik: int, accession: str, primary_doc: str) -> str:
    """Construct the URL to a primary filing document."""
    accession_nodash = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{primary_doc}"


def fetch_filing_doc(cik: int, accession: str, primary_doc: str, timeout: float = 15.0) -> bytes:
    """Fetch raw filing document bytes."""
    url = filing_url(cik, accession, primary_doc)
    _throttle()
    with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
        resp = client.get(url)
    resp.raise_for_status()
    return resp.content


def fetch_filing_index(cik: int, accession: str, timeout: float = 15.0) -> dict:
    """List all files in a filing's directory."""
    accession_nodash = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/index.json"
    _throttle()
    with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
        resp = client.get(url)
    resp.raise_for_status()
    return resp.json()


def find_form4_xml_doc(cik: int, accession: str) -> str | None:
    """Locate the actual Form 4 XML file in a filing (it's not always primary_doc).

    Form 4 directories contain something like primary_doc.xml + a rendered .htm.
    We scan for any .xml file that isn't a tax/footnote stub.
    """
    try:
        idx = fetch_filing_index(cik, accession)
    except Exception:
        return None
    for item in idx.get("directory", {}).get("item", []):
        name = item.get("name", "")
        if name.endswith(".xml") and "form4" in name.lower():
            return name
    # fallback: any .xml that's not a primary_doc.xml stub
    for item in idx.get("directory", {}).get("item", []):
        name = item.get("name", "")
        if name.endswith(".xml") and name != "primary_doc.xml":
            return name
    # last resort
    for item in idx.get("directory", {}).get("item", []):
        if item.get("name", "").endswith(".xml"):
            return item["name"]
    return None
