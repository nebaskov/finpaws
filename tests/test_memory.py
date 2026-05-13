from __future__ import annotations

from app.agent import memory as prefs
from app.api.models import UserRow
from app.db import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _factory():
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    return sessionmaker(bind=eng, autoflush=False, autocommit=False)


def test_pref_crud() -> None:
    factory = _factory()
    with factory() as s:
        s.add(UserRow(id="u1", email="u1@x.io", password_hash="!"))
        s.commit()

    with factory() as s:
        assert prefs.get_preference(s, "u1", "k") is None
        assert prefs.set_preference(s, "u1", "k", "v1") is True
        assert prefs.get_preference(s, "u1", "k") == "v1"
        assert prefs.set_preference(s, "u1", "k", "v2") is True
        assert prefs.get_preference(s, "u1", "k") == "v2"
        assert prefs.list_preferences(s, "u1") == {"k": "v2"}
        assert prefs.delete_preference(s, "u1", "k") is True
        assert prefs.delete_preference(s, "u1", "k") is False


def test_pref_swallows_db_errors() -> None:
    # An engine without create_all → every query hits a missing table and is handled.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as s:
        assert prefs.get_preference(s, "u", "k") is None
        assert prefs.set_preference(s, "u", "k", "v") is False
        assert prefs.list_preferences(s, "u") == {}
        assert prefs.delete_preference(s, "u", "k") is False
