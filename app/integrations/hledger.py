from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel

from app.config import SETTINGS


class HledgerError(Exception):
    pass


class HledgerPosting(BaseModel):
    account: str
    amount: Decimal
    currency: str = "RUB"


class HledgerEntry(BaseModel):
    occurred_on: date
    description: str
    postings: list[HledgerPosting]


def _journal_path() -> Path:
    return Path(SETTINGS.hledger_journal)


def _expense_account(category: str) -> str:
    safe = re.sub(r"\s+", "-", category.strip().lower()) or "other"
    return f"expenses:{safe}"


def _format_entry(entry: HledgerEntry) -> str:
    head = f"{entry.occurred_on.isoformat()} {entry.description}"
    lines = [head]
    for p in entry.postings:
        amount = f"{p.amount:.2f} {p.currency}"
        lines.append(f"    {p.account}    {amount}")
    return "\n".join(lines) + "\n\n"


def append_expense(
    amount: Decimal, currency: str, description: str, category: str, occurred_on: date
) -> bool:
    if not SETTINGS.hledger_mirror_enabled:
        return False
    entry = HledgerEntry(
        occurred_on=occurred_on,
        description=description,
        postings=[
            HledgerPosting(account=_expense_account(category), amount=amount, currency=currency),
            HledgerPosting(account="assets:cash", amount=-amount, currency=currency),
        ],
    )
    return _append(entry)


def append_income(amount: Decimal, currency: str, description: str, occurred_on: date) -> bool:
    if not SETTINGS.hledger_mirror_enabled:
        return False
    entry = HledgerEntry(
        occurred_on=occurred_on,
        description=description,
        postings=[
            HledgerPosting(account="assets:cash", amount=amount, currency=currency),
            HledgerPosting(account="income:salary", amount=-amount, currency=currency),
        ],
    )
    return _append(entry)


def _append(entry: HledgerEntry) -> bool:
    path = _journal_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(_format_entry(entry))
        return True
    except OSError:
        logger.bind(journal=str(path)).exception("hledger journal write failed")
        return False


def _run(args: list[str]) -> str:
    if shutil.which(SETTINGS.hledger_bin) is None:
        raise HledgerError(f"hledger binary not found: {SETTINGS.hledger_bin}")
    path = _journal_path()
    if not path.exists():
        return ""
    cmd = [SETTINGS.hledger_bin, "-f", str(path), *args]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=SETTINGS.hledger_timeout_seconds,
        )
    except subprocess.SubprocessError as exc:
        raise HledgerError(f"hledger subprocess failed: {exc}") from exc
    if proc.returncode != 0:
        raise HledgerError(f"hledger returned {proc.returncode}: {proc.stderr.strip()}")
    return proc.stdout


def balance(account_query: str | None = None) -> str:
    args = ["balance"]
    if account_query:
        args.append(account_query)
    return _run(args).strip()


def register(account_query: str | None = None, period: str | None = None) -> str:
    args = ["register"]
    if account_query:
        args.append(account_query)
    if period:
        args.extend(["--period", period])
    return _run(args).strip()


def stats_json() -> dict[str, Any]:
    out = _run(["balance", "-O", "json"])
    if not out:
        return {}
    try:
        data: Any = json.loads(out)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


_HEAD_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(.+)$")
_POSTING_RE = re.compile(r"^([\w:.\-]+)\s+(-?\d+(?:[.,]\d+)?)\s*([A-Z]{3})?$")


def import_journal(path: str | Path) -> list[HledgerEntry]:
    src = Path(path)
    if not src.exists():
        raise HledgerError(f"journal not found: {src}")
    entries: list[HledgerEntry] = []
    for block in re.split(r"\n\s*\n", src.read_text(encoding="utf-8")):
        stripped = block.strip()
        if not stripped or stripped.startswith(";"):
            continue
        head, *body = stripped.splitlines()
        head_match = _HEAD_RE.match(head.strip())
        if not head_match:
            continue
        when = date.fromisoformat(head_match.group(1))
        description = head_match.group(2).strip()
        postings: list[HledgerPosting] = []
        for raw_line in body:
            line = raw_line.strip()
            if not line or line.startswith(";"):
                continue
            match = _POSTING_RE.match(line)
            if not match:
                continue
            postings.append(
                HledgerPosting(
                    account=match.group(1),
                    amount=Decimal(match.group(2).replace(",", ".")),
                    currency=match.group(3) or "RUB",
                )
            )
        if postings:
            entries.append(HledgerEntry(occurred_on=when, description=description, postings=postings))
    return entries
