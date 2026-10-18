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

import tables  # noqa: E402, F401  (registers the tables on Base.metadata)
from db import Base, engine_options  # noqa: E402
from settings import get_settings  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
OK = "ok  "
BAD = "need"


def head_revision() -> str:
    """The migration this checkout expects the database to be at."""
    return ScriptDirectory.from_config(Config(str(HERE / "alembic.ini"))).get_current_head() or ""


def report(connection: Connection) -> int:
    """Prints what is and isn't in order. Returns the number of problems."""
    problems = 0

    version, user = connection.execute(text("SELECT current_setting('server_version'), current_user")).one()
    print(f"{OK}  reached Postgres {version} as {user}")

    encrypted, cipher = connection.execute(
        text("SELECT ssl, COALESCE(cipher, '') FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
    ).one()
    if encrypted:
        print(f"{OK}  connection encrypted ({cipher})")
    else:
        print(f"{BAD}  connection is NOT encrypted. These rows are health data under DPDP.")
        problems += 1

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
            problems = report(connection)
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
