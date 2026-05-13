from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.config import SETTINGS

#: SQLModel's shared metadata/registry. Aliased as ``Base`` so callers keep the
#: familiar ``Base.metadata.create_all(...)`` entry point.
Base = SQLModel

engine = create_engine(SETTINGS.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
