"""Telegram notifier — share the bot with AI_trader (same TELEGRAM_BOT_TOKEN
+ TELEGRAM_CHAT_ID in .env)."""

from __future__ import annotations

import httpx

from configs.settings import settings
from src.logger import logger

TELEGRAM_API = "https://api.telegram.org"
MAX_LEN = 4096  # Telegram per-message limit


def _enabled() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def send_message(text: str, parse_mode: str = "Markdown", silent: bool = False) -> bool:
    """Send a single message; auto-splits at 4096 char boundary."""
    if not _enabled():
        logger.warning("telegram not configured; skipping send")
        return False

    url = f"{TELEGRAM_API}/bot{settings.telegram_bot_token}/sendMessage"
    chunks = [text[i : i + MAX_LEN] for i in range(0, len(text), MAX_LEN)] or [text]

    ok_all = True
    with httpx.Client(timeout=10.0) as client:
        for chunk in chunks:
            try:
                resp = client.post(
                    url,
                    json={
                        "chat_id": settings.telegram_chat_id,
                        "text": chunk,
                        "parse_mode": parse_mode,
                        "disable_notification": silent,
                    },
                )
                if not resp.is_success:
                    logger.error(f"telegram send failed: {resp.status_code} {resp.text[:200]}")
                    ok_all = False
            except Exception:
                logger.exception("telegram send raised")
                ok_all = False
    return ok_all


def send_daily_summary(report_md: str, as_of: str) -> bool:
    """Send the daily report. Trims long markdown tables for chat-friendly view."""
    header = f"📡 *Market Radar Daily — {as_of}*\n"
    # Telegram Markdown is finicky around | and _; strip table separators
    safe = header + report_md.replace("---", "─" * 8)
    return send_message(safe)
