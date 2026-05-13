from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Sequence

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlmodel import col

from app.agent.checkpoint import open_checkpointer
from app.agent.kb import build_kb
from app.agent.orchestrator import run_agent
from app.api.models import UserRow
from app.config import SETTINGS
from app.db import Base

_CLI_USER_EMAIL = "cli@finpaws.local"


def _bootstrap(use_local_sqlite: bool) -> tuple[sessionmaker[Session], str]:
    if use_local_sqlite:
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(SETTINGS.database_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with factory() as session:
        cli_user = session.execute(
            select(UserRow).where(col(UserRow.email) == _CLI_USER_EMAIL)
        ).scalar_one_or_none()
        if cli_user is None:
            cli_user = UserRow(
                id=str(uuid.uuid4()),
                email=_CLI_USER_EMAIL,
                password_hash="!cli-no-login",
                display_name="cli",
            )
            session.add(cli_user)
            session.commit()
            session.refresh(cli_user)
        return factory, cli_user.id


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="finpaws-chat")
    parser.add_argument("--ephemeral", action="store_true", help="Use in-memory SQLite (no persistence)")
    parser.add_argument("--thread", default=None, help="Conversation thread id")
    args = parser.parse_args(argv)

    factory, user_id = _bootstrap(args.ephemeral)
    kb = build_kb()

    print("FinPaws · Баксик слушает. Ctrl+C для выхода.")
    with open_checkpointer() as checkpointer:
        thread = args.thread or f"cli-{user_id}"
        while True:
            try:
                line = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not line:
                continue
            if line in {"/quit", "/exit"}:
                return 0
            response = run_agent(
                session_factory=factory,
                kb=kb,
                user_id=user_id,
                message=line,
                checkpointer=checkpointer,
                thread_id=thread,
            )
            print(response.answer)
            if response.tool_calls:
                sys.stderr.write(f"  [tools: {[call['name'] for call in response.tool_calls]}]\n")
            if response.injection_suspected:
                sys.stderr.write("  [⚠ возможна prompt-injection — Баксик игнорировал инструкции]\n")


if __name__ == "__main__":
    raise SystemExit(main())
