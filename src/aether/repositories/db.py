from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from aether.repositories.base import RepositoryError

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

_pool: ConnectionPool | None = None


def get_database_url() -> str:
    """Resolve DATABASE_URL from the environment (pooled Neon URL preferred)."""
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RepositoryError(
            "DATABASE_URL is not set. Add it to your .env (Neon pooled connection string)."
        )
    return url


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=get_database_url(),
            kwargs={"row_factory": dict_row},
            min_size=1,
            max_size=10,
            open=True,
        )
    return _pool


@contextmanager
def get_connection() -> Iterator[Connection]:
    with get_pool().connection() as conn:
        yield conn


def apply_schema(conn: Connection | None = None) -> None:
    """Apply repositories/schema.sql to the target database."""
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    if conn is not None:
        conn.execute(sql)
        conn.commit()
        return

    with get_connection() as owned:
        owned.execute(sql)
        owned.commit()


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
