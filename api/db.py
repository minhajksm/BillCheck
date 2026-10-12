from collections.abc import Iterator
from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy import DateTime, Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from settings import get_settings


class UTCDateTime(TypeDecorator[datetime]):
    """Stores datetimes as UTC and always returns them timezone-aware, so
    comparisons behave the same on Postgres and on SQLite in tests."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime; use datetime.now(UTC).")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one database session per request."""
    with _session_factory()() as session:
        yield session


def utcnow() -> datetime:
    return datetime.now(UTC)
