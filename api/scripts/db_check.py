"""Say whether the database in DATABASE_URL is ready to be used.

The one command to run after pointing api/.env at a hosted Postgres. It
answers the four questions a hosted database raises and a local one in Docker
never does:

    uv run python scripts/db_check.py

  * Can we reach it at all, and as whom?
  * Is the connection encrypted? These rows are health data.
  * Are the tables there, at the migration this checkout expects?
  * Is row level security on? The host serves the public schema over HTTP
    with a key that is published in client apps, so a table without it is
    readable by anyone who asks.

It reads and counts rows; it writes nothing, and never prints the password.
Exits 0 when everything is in order, 1 when something needs doing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy import Connection, create_engine, func, inspect, make_url, select, text  # noqa: E402
from sqlalchemy.engine import URL  # noqa: E402

import tables  # noqa: E402, F401  (registers the tables on Base.metadata)
from db import ENCRYPTED_SSLMODES, Base, effective_sslmode, engine_options  # noqa: E402
from settings import get_settings  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
OK = "ok  "
BAD = "need"


def head_revision() -> str:
    """The migration this checkout expects the database to be at."""
    return ScriptDirectory.from_config(Config(str(HERE / "alembic.ini"))).get_current_head() or ""


def report_tls(connection: Connection, url: URL) -> int:
    """Says whether this connection is encrypted, and how we know.

    Two sources, and the order matters. Under sslmode=require and stricter,
    libpq will not connect to a server that refuses TLS at all, so a
    connection that exists is encrypted -- no question to ask. Only where we
    asked for nothing is the server worth consulting, and even then its answer
    is about its own end: through Supabase's pooler, `pg_stat_ssl` reports the
    pooler's link to Postgres, which is inside their network and not ours.
    Reading that as our connection says "NOT encrypted" about a connection
    that could not have been made in clear text.
    """
    mode = effective_sslmode(str(url))
    encrypted, cipher = connection.execute(
        text("SELECT ssl, COALESCE(cipher, '') FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
    ).one()

    if mode in ENCRYPTED_SSLMODES:
        print(f"{OK}  connection encrypted (sslmode={mode}, which libpq will not downgrade)")
        if not encrypted:
            print("      The server reports none on its side, which is what a pooler looks")
            print("      like: that is its own connection to Postgres, not ours to it.")
        return 0

    if encrypted:
        print(f"{OK}  connection encrypted ({cipher})")
        return 0

    # Nothing asked for and nothing in use. Fine on this machine, where
    # `engine_options` deliberately requires no TLS; not fine anywhere else.
    if mode is None and not host_is_remote(url):
        print(f"{OK}  not encrypted, which is fine for a database on this machine")
        return 0

    print(f"{BAD}  connection is NOT encrypted. These rows are health data under DPDP.")
    print("      Set sslmode=require in DATABASE_URL, or point it at a host that offers TLS.")
    return 1


def host_is_remote(url: URL) -> bool:
    """Whether this database is somewhere other than this machine."""
    return effective_sslmode(str(url.set(query={}))) is not None


def report(connection: Connection, url: URL) -> int:
    """Prints what is and isn't in order. Returns the number of problems."""
    problems = 0

    version, user = connection.execute(text("SELECT current_setting('server_version'), current_user")).one()
    print(f"{OK}  reached Postgres {version} as {user}")

    problems += report_tls(connection, url)

    # What the database thinks it is, against what this checkout expects. A
    # database behind the code is the usual reason a request dies on a column
    # that isn't there.
    inspector = inspect(connection)
    head = head_revision()
    at = ""
    if inspector.has_table("alembic_version"):
        at = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().first() or ""
    if at == head:
        print(f"{OK}  migrations up to date ({head})")
    else:
        print(f"{BAD}  database is at {at or 'nothing -- no tables yet'}, this checkout expects {head}.")
        print("      Run: uv run alembic upgrade head")
        return problems + 1

    secured = dict(
        connection.execute(
            text(
                "SELECT c.relname, c.relrowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = current_schema() AND c.relkind = 'r'"
            )
        ).all()
    )
    unprotected = sorted(name for name in Base.metadata.tables if not secured.get(name))
    if unprotected:
        print(f"{BAD}  row level security is off on: {', '.join(unprotected)}")
        print("      Run: uv run alembic upgrade head")
        problems += 1
    else:
        print(f"{OK}  row level security on all {len(Base.metadata.tables)} tables")

    for name, table in sorted(Base.metadata.tables.items()):
        count = connection.execute(select(func.count()).select_from(table)).scalar_one()
        print(f"      {name:<16} {count} rows")
    return problems


def main() -> int:
    url = make_url(get_settings().database_url)
    print(f"database  {url.render_as_string(hide_password=True)}")
    if url.get_backend_name() != "postgresql":
        print(f"{BAD}  DATABASE_URL is not Postgres. Point it at your database and try again.")
        return 1

    engine = create_engine(url, **engine_options(str(url)))
    try:
        with engine.connect() as connection:
            problems = report(connection, url)
    except Exception as error:  # any failure to use it is the answer
        print(f"{BAD}  could not use the database: {type(error).__name__}: {error}")
        print("      Check the host, port and password, and that your network allows the connection.")
        return 1
    finally:
        engine.dispose()

    print("\nready" if problems == 0 else f"\n{problems} thing(s) to fix, above")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
