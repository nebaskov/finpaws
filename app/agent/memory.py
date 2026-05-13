"""Long-term user preferences (key/value) backed by the database."""

from __future__ import annotations

from loguru import logger
from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlmodel import col

from app.api.models import UserPreferenceRow


def _select_pref(user_id: str, key: str) -> Select[tuple[UserPreferenceRow]]:
    return select(UserPreferenceRow).where(
        col(UserPreferenceRow.user_id) == user_id,
        col(UserPreferenceRow.key) == key,
    )


def get_preference(session: Session, user_id: str, key: str) -> str | None:
    try:
        row = session.execute(_select_pref(user_id, key)).scalar_one_or_none()
    except SQLAlchemyError:
        logger.bind(user_id=user_id, key=key).exception("get_preference failed")
        session.rollback()
        return None
    return row.value if row else None


def set_preference(session: Session, user_id: str, key: str, value: str) -> bool:
    try:
        row = session.execute(_select_pref(user_id, key)).scalar_one_or_none()
        if row is None:
            session.add(UserPreferenceRow(user_id=user_id, key=key, value=value))
        else:
            row.value = value
        session.commit()
    except SQLAlchemyError:
        logger.bind(user_id=user_id, key=key).exception("set_preference failed")
        session.rollback()
        return False
    return True


def list_preferences(session: Session, user_id: str) -> dict[str, str]:
    try:
        rows = (
            session.execute(select(UserPreferenceRow).where(col(UserPreferenceRow.user_id) == user_id))
            .scalars()
            .all()
        )
    except SQLAlchemyError:
        logger.bind(user_id=user_id).exception("list_preferences failed")
        session.rollback()
        return {}
    return {row.key: row.value for row in rows}


def delete_preference(session: Session, user_id: str, key: str) -> bool:
    try:
        row = session.execute(_select_pref(user_id, key)).scalar_one_or_none()
        if row is None:
            return False
        session.delete(row)
        session.commit()
    except SQLAlchemyError:
        logger.bind(user_id=user_id, key=key).exception("delete_preference failed")
        session.rollback()
        return False
    return True
