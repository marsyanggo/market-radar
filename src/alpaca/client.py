"""Alpaca client factories.

Centralize client construction so we can swap creds, add retry, or fake in tests.
"""

import time
from functools import wraps
from typing import Callable, TypeVar

from alpaca.data.historical.screener import ScreenerClient
from alpaca.data.historical.stock import StockHistoricalDataClient

from configs.settings import settings
from src.logger import logger

T = TypeVar("T")


def _check_credentials() -> None:
    if not settings.alpaca_api_key or not settings.alpaca_secret_key:
        raise RuntimeError(
            "Alpaca credentials missing — set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env"
        )


def get_screener_client() -> ScreenerClient:
    _check_credentials()
    return ScreenerClient(settings.alpaca_api_key, settings.alpaca_secret_key)


def get_stock_data_client() -> StockHistoricalDataClient:
    _check_credentials()
    return StockHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_secret_key)


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    backoff: float = 2.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry wrapper for transient API errors with exponential backoff."""

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            attempt = 0
            while True:
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        logger.error(f"{fn.__name__} failed after {attempt} attempts: {e}")
                        raise
                    delay = base_delay * (backoff ** (attempt - 1))
                    logger.warning(
                        f"{fn.__name__} attempt {attempt} failed: {e} — retrying in {delay:.1f}s"
                    )
                    time.sleep(delay)

        return wrapper

    return decorator
