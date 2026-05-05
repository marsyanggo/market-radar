"""One-shot EOD technical indicators — entry point for cron / launchd.

Usage:
    python -m scripts.eod_indicators
    radar indicators run
"""

from src.indicators.eod import run_eod_indicators
from src.logger import logger


def main() -> None:
    logger.info("=== EOD indicators start ===")
    counts = run_eod_indicators()
    logger.info(f"=== EOD indicators done: {counts} ===")


if __name__ == "__main__":
    main()
