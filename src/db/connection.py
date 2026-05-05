import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from configs.settings import settings
from src.logger import logger


def _resolve_db_path() -> Path:
    url = settings.database_url
    if url.startswith("sqlite:///"):
        return Path(url[len("sqlite:///") :])
    if url.startswith("sqlite://"):
        return Path(url[len("sqlite://") :])
    raise ValueError(f"unsupported database_url scheme: {url}")


DB_PATH = _resolve_db_path()


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a sqlite connection with sane defaults.

    - foreign_keys ON
    - WAL mode for concurrent readers
    - Row factory for dict-like access
    """
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def get_conn(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Context manager that closes the connection on exit."""
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Wrap a unit-of-work in BEGIN/COMMIT (rollback on exception)."""
    conn.execute("BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        logger.exception("transaction rolled back")
        raise
