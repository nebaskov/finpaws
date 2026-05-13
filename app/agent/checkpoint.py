from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from loguru import logger

from app.config import SETTINGS


def _to_psycopg_url(sa_url: str) -> str:
    if sa_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + sa_url.split("://", 1)[1]
    return sa_url


@contextmanager
def open_checkpointer() -> Iterator[Any]:
    """Yield a LangGraph checkpointer: a PostgresSaver if the DB URL is Postgres, else an in-memory one."""
    url = _to_psycopg_url(SETTINGS.database_url)
    if not url.startswith("postgresql"):
        from langgraph.checkpoint.memory import MemorySaver

        yield MemorySaver()
        return
    try:
        from langgraph.checkpoint.postgres import PostgresSaver

        with PostgresSaver.from_conn_string(url) as saver:
            try:
                saver.setup()
            except Exception:  # noqa: BLE001 - setup races/perms: usable without it
                logger.exception("postgres checkpointer setup failed")
            yield saver
    except Exception as exc:  # noqa: BLE001 - no Postgres: fall back to in-memory history
        # An expected degradation when running offline / without a DB — log briefly, don't dump a traceback.
        logger.warning("postgres checkpointer unavailable ({}), falling back to in-memory", exc)
        from langgraph.checkpoint.memory import MemorySaver

        yield MemorySaver()
