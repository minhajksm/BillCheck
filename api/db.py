from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from sqlalchemy import DateTime, Engine, create_engine, make_url
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


# Where a database can live and still be reached in clear text: this machine.
_LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1"})

# Supabase serves Supavisor's transaction mode on this port, session mode on
# the usual 5432. The difference matters to us; see `engine_options`.
_TRANSACTION_POOLER_PORT = 6543


def effective_sslmode(database_url: str) -> str | None:
    """The sslmode this connection will actually use, or None where we ask
    for nothing and libpq's own default stands.

    Worth being able to read back, because it is the whole proof that a
    connection is encrypted: libpq refuses to connect at all under "require"
    if the server will not do TLS, so a connection that exists under it is a
    connection that is encrypted. Asking the server afterwards is the thing
    that cannot be trusted -- through a pooler, `pg_stat_ssl` describes the
    pooler's own link to Postgres rather than ours to the pooler.
    """
    url = make_url(database_url)
    in_url = url.query.get("sslmode")
    if in_url:
        return str(in_url)
    chosen = engine_options(database_url).get("connect_args", {})
    mode = chosen.get("sslmode") if isinstance(chosen, dict) else None
    return str(mode) if mode else None


# The modes under which libpq will not fall back to clear text.
ENCRYPTED_SSLMODES = frozenset({"require", "verify-ca", "verify-full"})


def engine_options(database_url: str) -> dict[str, Any]:
    """How to connect, given where the database is.

    A hosted database is not a local one with a longer address. The
    connection crosses the internet, it is handed to us by a pooler that
    shares server connections between everybody, and either end may close it
    while we still believe it is open. Each of those needs saying out loud,
    and none of it applies to SQLite in the tests.
    """
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        return {}

    connect_args: dict[str, Any] = {
        # Names us in the host's own connection list, so a connection left
        # open is traceable to this service rather than anonymous.
        "application_name": "billcheck-api",
        # A database that cannot be reached should say so rather than hold a
        # family's upload open until something else times out.
        "connect_timeout": 10,
    }
    if (url.host or "").lower() not in _LOCAL_HOSTS and "sslmode" not in url.query:
        # Health data crosses the internet on this connection. libpq's own
        # default is "prefer", which falls back to clear text without
        # mentioning it, and DPDP does not leave that to the server's mood.
        connect_args["sslmode"] = "require"
    if url.port == _TRANSACTION_POOLER_PORT:
        # A transaction pooler gives each transaction whichever server
        # connection is free, so a statement prepared on one is not there on
        # the next. psycopg prepares a statement after its fifth use, which
        # makes this fail only once the app is busy.
        connect_args["prepare_threshold"] = None

    return {
        "pool_pre_ping": True,
        # A pooler drops connections it thinks are idle, and so does any NAT
        # between here and it. Both leave a socket that looks open.
        "pool_recycle": 240,
        "connect_args": connect_args,
    }


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    return create_engine(url, **engine_options(url))


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one database session per request."""
    with _session_factory()() as session:
        yield session


def utcnow() -> datetime:
    return datetime.now(UTC)


# India Standard Time. India has no daylight saving, so a fixed offset is
# exact, and unlike a zoneinfo name it needs no tz database (Windows has none).
INDIA = timezone(timedelta(hours=5, minutes=30), "IST")


def india_today() -> date:
    """Today's date where the families are. A bill photographed at 1:30 am on
    12 October in Mumbai is 11 October in UTC, which would put it on the wrong
    day of the stay."""
    return utcnow().astimezone(INDIA).date()
