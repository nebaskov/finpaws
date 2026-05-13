from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlmodel import col

from app.api.models import CurrencyRateRow
from app.config import SETTINGS
from app.domain.planning import round_money


class ConversionResult(BaseModel):
    amount: Decimal
    from_currency: str
    to_currency: str
    rate: Decimal
    converted: Decimal
    stale: bool
    fetched_at: datetime


class CurrencyError(Exception):
    pass


def _pair(base: str, quote: str) -> str:
    return f"{base.upper()}/{quote.upper()}"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _fetch_rate_remote(from_ccy: str, to_ccy: str) -> Decimal:
    params = {"from": from_ccy.upper(), "to": to_ccy.upper(), "amount": "1"}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(SETTINGS.currency_api_url, params=params)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        raise CurrencyError(f"http error: {exc}") from exc

    rate = data.get("result") or data.get("info", {}).get("rate") or data.get("rate")
    if rate is None:
        raise CurrencyError(f"unexpected response: {data}")
    return Decimal(str(rate))


def get_rate(session: Session, from_ccy: str, to_ccy: str) -> tuple[Decimal, datetime, bool]:
    """Return ``(rate, fetched_at, stale)`` for ``from_ccy -> to_ccy``.

    Uses a fresh cached value when available, fetches otherwise, and falls back to a
    stale cached value (``stale=True``) if the remote API is down.
    """
    if from_ccy.upper() == to_ccy.upper():
        return Decimal("1"), datetime.now(tz=UTC), False

    pair = _pair(from_ccy, to_ccy)
    cached: CurrencyRateRow | None = None
    try:
        cached = session.execute(
            select(CurrencyRateRow).where(col(CurrencyRateRow.pair) == pair)
        ).scalar_one_or_none()
    except SQLAlchemyError:
        logger.bind(pair=pair).exception("currency cache lookup failed")
        session.rollback()

    cached_at = _aware(cached.fetched_at) if cached is not None else None
    fresh_until = datetime.now(tz=UTC) - timedelta(seconds=SETTINGS.currency_cache_ttl_seconds)
    if cached is not None and cached_at is not None and cached_at >= fresh_until:
        return cached.rate, cached_at, False

    try:
        rate = _fetch_rate_remote(from_ccy, to_ccy)
    except CurrencyError:
        logger.bind(pair=pair).exception("currency api unavailable, using cache")
        if cached is not None and cached_at is not None:
            return cached.rate, cached_at, True
        raise

    now = datetime.now(tz=UTC)
    try:
        if cached is None:
            session.add(CurrencyRateRow(pair=pair, rate=rate, fetched_at=now))
        else:
            cached.rate = rate
            cached.fetched_at = now
        session.commit()
    except SQLAlchemyError:
        logger.bind(pair=pair).exception("currency cache write failed")
        session.rollback()

    return rate, now, False


def convert(session: Session, amount: Decimal, from_ccy: str, to_ccy: str) -> ConversionResult:
    rate, fetched_at, stale = get_rate(session, from_ccy, to_ccy)
    return ConversionResult(
        amount=amount,
        from_currency=from_ccy.upper(),
        to_currency=to_ccy.upper(),
        rate=rate,
        converted=round_money(amount * rate),
        stale=stale,
        fetched_at=fetched_at,
    )
