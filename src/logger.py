import sys
from datetime import datetime

from loguru import logger

from configs.settings import settings


def setup_logger() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )

    settings.log_dir.mkdir(parents=True, exist_ok=True)
    log_file = settings.log_dir / f"radar_{datetime.now():%Y-%m-%d}.log"
    logger.add(
        log_file,
        level=settings.log_level,
        rotation="00:00",
        retention="30 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )


setup_logger()

__all__ = ["logger"]
