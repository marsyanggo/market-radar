"""News headline sentiment scorer using Claude Haiku 4.5.

Strategy:
  - Batch unscored headlines together (1 API call per ~50 headlines)
  - Use prompt caching on the system rubric (saves ~90% on input tokens after warmup)
  - Use structured outputs (output_config.format) to guarantee parseable JSON
  - Score range: -1.0 (very bearish) to +1.0 (very bullish), 0 neutral

Skipped gracefully when ANTHROPIC_API_KEY is empty.
"""

from __future__ import annotations

import json

import anthropic
from pydantic import BaseModel, Field

from configs.settings import settings
from src.db.connection import get_conn, transaction
from src.logger import logger


SYSTEM_RUBRIC = """You are a financial news sentiment scorer for a US-equities trading system.

For each headline, return a sentiment score from -1.0 to +1.0:
  +1.0 = strongly bullish for the named symbol(s) (positive earnings beat, FDA approval, M&A premium, breakthrough product)
  +0.5 = moderately bullish (analyst upgrade, decent guidance, partnership)
   0.0 = neutral / informational / unclear
  -0.5 = moderately bearish (analyst downgrade, weak guidance, lawsuit risk)
  -1.0 = strongly bearish (earnings miss, fraud allegation, major recall, FDA rejection, bankruptcy)

Important:
- Score from the perspective of the listed primary_symbol (first symbol in `symbols`)
- Macro / general-market news without a clear symbol-specific implication = 0
- Always return scores ONLY for the input ids; same length, same order
- Return JSON object {"scores": [{"id": ..., "sentiment_score": ...}, ...]}"""


class HeadlineInput(BaseModel):
    id: int
    headline: str
    primary_symbol: str | None = None


class NewsScore(BaseModel):
    id: int
    sentiment_score: float = Field(ge=-1.0, le=1.0)


class ScoresResponse(BaseModel):
    scores: list[NewsScore]


def _client() -> anthropic.Anthropic | None:
    if not settings.anthropic_api_key:
        return None
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def score_batch(headlines: list[HeadlineInput]) -> dict[int, float]:
    """Score a batch of headlines. Returns {news_id: sentiment_score}."""
    client = _client()
    if client is None:
        logger.warning("ANTHROPIC_API_KEY missing — skipping LLM sentiment")
        return {}
    if not headlines:
        return {}

    user_payload = json.dumps(
        [{"id": h.id, "headline": h.headline, "primary_symbol": h.primary_symbol}
         for h in headlines],
        ensure_ascii=False,
    )

    response = client.messages.parse(
        model=settings.anthropic_model,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_RUBRIC,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {"role": "user", "content": f"Score these headlines:\n{user_payload}"}
        ],
        output_format=ScoresResponse,
    )

    parsed = response.parsed_output
    out: dict[int, float] = {s.id: s.sentiment_score for s in parsed.scores}

    cached = response.usage.cache_read_input_tokens or 0
    written = response.usage.cache_creation_input_tokens or 0
    logger.info(
        f"LLM sentiment scored {len(out)}/{len(headlines)} headlines  "
        f"(cache: read={cached} write={written})"
    )
    return out


def score_recent_news(limit: int = 50) -> int:
    """Score the N most recent news rows that lack sentiment_score. Returns count updated."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, headline, symbols
            FROM news
            WHERE sentiment_score IS NULL
            ORDER BY ts DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    if not rows:
        logger.info("no unscored news")
        return 0

    headlines: list[HeadlineInput] = []
    for r in rows:
        symbols = json.loads(r["symbols"]) if r["symbols"] else []
        primary = symbols[0] if symbols else None
        headlines.append(HeadlineInput(id=r["id"], headline=r["headline"], primary_symbol=primary))

    scores = score_batch(headlines)
    if not scores:
        return 0

    with get_conn() as conn:
        with transaction(conn):
            for nid, s in scores.items():
                conn.execute(
                    "UPDATE news SET sentiment_score = ? WHERE id = ?",
                    (s, nid),
                )
    logger.info(f"persisted sentiment for {len(scores)} news rows")
    return len(scores)
