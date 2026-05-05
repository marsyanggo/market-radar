"""Daily Market Radar report — entry point for cron / launchd.

Usage:
    python -m scripts.daily_report
    radar report run
"""

from src.logger import logger
from src.recommend.daily_pipeline import run_daily_pipeline


def main() -> None:
    counts = run_daily_pipeline()
    logger.info(f"final: {counts}")


if __name__ == "__main__":
    main()
