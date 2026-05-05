"""One-shot daily screener — run pre-market to refresh the watchlist universe.

Usage:
    python -m scripts.daily_screener
    radar screener run
"""

from src.alpaca.screener import run_daily_screener
from src.logger import logger


def main() -> None:
    logger.info("=== daily screener start ===")
    counts = run_daily_screener()
    logger.info(f"=== daily screener done: {counts} ===")


if __name__ == "__main__":
    main()
