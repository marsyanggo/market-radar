"""Simple linear migrations.

Each migration is (version_number, sql). They run in order, idempotently.
The base schema lives in schema.sql and is treated as version 1.
"""

from pathlib import Path

from src.db.connection import connect
from src.logger import logger

SCHEMA_FILE = Path(__file__).parent / "schema.sql"

# Future migrations: (version, sql_string). Version 1 is schema.sql.
MIGRATIONS: list[tuple[int, str]] = []


def current_version(conn) -> int:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    if cur.fetchone() is None:
        return 0
    cur = conn.execute("SELECT MAX(version) AS v FROM schema_version")
    row = cur.fetchone()
    return row["v"] or 0


def apply_base_schema(conn) -> None:
    sql = SCHEMA_FILE.read_text()
    conn.executescript(sql)
    conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (1)")


def apply_migrations(conn) -> None:
    for version, sql in MIGRATIONS:
        cur = conn.execute("SELECT 1 FROM schema_version WHERE version = ?", (version,))
        if cur.fetchone():
            continue
        logger.info(f"applying migration v{version}")
        conn.executescript(sql)
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))


def init_db(db_path: Path | None = None) -> int:
    """Bootstrap and migrate the DB. Returns the resulting version."""
    conn = connect(db_path)
    try:
        v = current_version(conn)
        if v == 0:
            logger.info("creating base schema (v1)")
            apply_base_schema(conn)
        apply_migrations(conn)
        return current_version(conn)
    finally:
        conn.close()
