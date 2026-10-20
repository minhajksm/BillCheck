"""How the app reaches a database that isn't on this machine.

None of this talks to a real database. What it checks is the decisions we
make before connecting -- TLS, prepared statements, which tables are locked
down -- because each of them is invisible until it has already gone wrong on
a hosted one.
"""

import importlib
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import make_url

import tables
from db import Base, engine_options

LOCAL = "postgresql+psycopg://billcheck:billcheck@localhost:5432/billcheck"
SESSION_POOLER = (
    "postgresql+psycopg://postgres.abcdefgh:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
)
TRANSACTION_POOLER = (
    "postgresql+psycopg://postgres.abcdefgh:pw@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
)
DIRECT = "postgresql+psycopg://postgres:pw@db.abcdefgh.supabase.co:5432/postgres"


def test_a_database_off_this_machine_is_reached_over_tls():
    """libpq's own default is "prefer", which drops to clear text without
    saying so. These rows are health data under DPDP; it is not the server's
    call whether they cross the internet encrypted."""
    for url in (SESSION_POOLER, TRANSACTION_POOLER, DIRECT):
        assert engine_options(url)["connect_args"]["sslmode"] == "require", url


def test_a_stricter_sslmode_in_the_url_is_left_alone():
    """verify-full checks the certificate's name as well. Someone who asked
    for it should not be quietly dropped back to require."""
    url = f"{DIRECT}?sslmode=verify-full"
    assert "sslmode" not in engine_options(url)["connect_args"]


def test_postgres_on_this_machine_is_not_forced_through_tls():
    """A local container has no certificate, so requiring one would mean the
    app only runs against a hosted database."""
    assert "sslmode" not in engine_options(LOCAL)["connect_args"]


def test_prepared_statements_are_off_through_a_transaction_pooler():
    """A transaction pooler hands each transaction whichever server connection
    is free, so a statement prepared on one isn't there on the next. psycopg
    prepares after the fifth use, so this breaks under load and not before."""
    assert engine_options(TRANSACTION_POOLER)["connect_args"]["prepare_threshold"] is None


def test_prepared_statements_stay_on_everywhere_else():
    """Session mode keeps one server connection per client, so there is
    nothing to work around and no reason to give up the speed."""
    for url in (LOCAL, SESSION_POOLER, DIRECT):
        assert "prepare_threshold" not in engine_options(url)["connect_args"], url


def test_a_connection_that_cannot_be_made_gives_up():
    """Without this, a wrong host holds a family's upload open until
    something further out times out."""
    assert engine_options(SESSION_POOLER)["connect_args"]["connect_timeout"] == 10


def test_a_stale_pooled_connection_is_not_handed_out():
    for url in (LOCAL, SESSION_POOLER):
        assert engine_options(url)["pool_pre_ping"] is True
        assert engine_options(url)["pool_recycle"] > 0


def test_sqlite_in_tests_gets_none_of_it():
    """All of the above is libpq's vocabulary, and tests run on SQLite."""
    assert engine_options("sqlite://") == {}


def locked_down_tables() -> set[str]:
    """Every table some migration turns row level security on for."""
    found: set[str] = set()
    for path in sorted(Path("migrations/versions").glob("*.py")):
        module = importlib.import_module(f"migrations.versions.{path.stem}")
        found |= set(getattr(module, "TABLES", ()))
    return found


def test_every_table_has_row_level_security_enabled():
    """The host serves the public schema over HTTP, and the key that reads it
    is published in client apps by design. A table no migration locks down is
    a family's bill readable by anyone who asks for it, so the list is
    checked against the models rather than kept by hand."""
    assert tables  # the models are what registered them on Base.metadata
    missing = set(Base.metadata.tables) - locked_down_tables()

    assert not missing, f"no migration enables row level security on {sorted(missing)}"


def test_a_password_is_read_whole_whatever_is_in_it():
    """Which characters in a Supabase password have to be escaped, and which
    do not. Only @ and % break the URL -- @ because the host starts after the
    last one, % because it begins an escape -- and the docs say so because
    this test says so. Everything else is read as itself, so telling someone
    to escape it would corrupt a working password."""
    for password in ("gAYr?w-tuc6XD84", "ab#cd", "ab/cd", "ab:cd", "p@ss%21"):
        url = make_url(f"postgresql+psycopg://postgres.ref:{quote(password, safe='')}@host:5432/postgres")
        assert url.password == password, password
        assert url.host == "host"
        assert url.database == "postgres"

    # Unescaped, these two are read as the URL's own punctuation.
    assert make_url("postgresql+psycopg://u:ab@cd@host:5432/db").password == "ab"
    assert make_url("postgresql+psycopg://u:ab%41cd@host:5432/db").password == "abAcd"
