"""Long-running block-trade stream — entry point for launchd/cron-like keepers.

Usage:
    python -m scripts.run_trades_stream
    radar stream trades

Symbols come from the `stocks` table by default.
"""

import asyncio

from src.alpaca.trades_stream import load_default_symbols, run_block_stream
from src.logger import logger


def main() -> None:
    symbols = load_default_symbols()
    if not symbols:
        logger.error("no symbols in `stocks` table — run `radar screener run` first")
        return
    logger.info(f"starting block stream for {len(symbols)} symbols")
    asyncio.run(run_block_stream(symbols))


if __name__ == "__main__":
    main()
