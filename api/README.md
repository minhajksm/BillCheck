# BillCheck API

FastAPI backend with PostgreSQL, managed with [uv](https://docs.astral.sh/uv/).

## First-time setup

The database is hosted on Supabase, so there is nothing to install or start
for it.

1. **Make the project.** In Supabase, *New project*. **Mumbai
   (`ap-south-1`)**, closest to the families, and the same region the API is
   deployed to. Save the database password it asks for. Supabase cannot move
   a project to another region afterwards, so this one is worth not getting
   wrong — see [Which region](../docs/deploy.md#which-region) for what it
   decides.
2. **Get the connection string.** *Connect*, in the top bar, → one of the
   **pooler** strings → then make sure the port reads **`5432`**. Go by the
   port rather than the label, which Supabase has renamed more than once:
   session mode is 5432, transaction mode is 6543, same host and username
   either way. See [Where the database lives](#where-the-database-lives).
3. **Put it in `.env`:**

   ```sh
   cp .env.example .env
   ```

   Paste the URI as `DATABASE_URL` and change its scheme from
   `postgresql://` to `postgresql+psycopg://` — that is the driver we use.
   A password containing `@` or `%` needs them written `%40` and `%25`;
   those two are the only ones that break the URL, and `?`, `#`, `/` and `:`
   are read literally.
4. **Create the tables and check it:**

   ```sh
   uv sync
   uv run alembic upgrade head
   uv run python scripts/db_check.py
   ```

   `db_check.py` is the "did that work?" command. It says who it connected
   as, whether the connection is encrypted, which migration the database is
   at, and whether row level security is on. It writes nothing.

   Through the pooler it reports encryption as `sslmode=require, which libpq
   will not downgrade`, and may add that the server reports none on its side.
   That is the expected answer, not a warning: `pg_stat_ssl` describes the
   pooler's own connection to Postgres, inside Supabase's network, while ours
   is the one to the pooler — and under `require` libpq would have refused to
   open it at all in clear text.

## Run

```sh
uv run uvicorn main:app --reload   # http://localhost:8000/docs
```

From the Android emulator, the API is at `http://10.0.2.2:8000`.

To run it somewhere other than this machine, see
[docs/deploy.md](../docs/deploy.md): a container on Cloud Run with your domain
mapped to it, talking to the same Supabase database.

**Sign-in codes during development:** with `OTP_DELIVERY=console`, codes aren't sent by SMS. They're printed in this terminal, like `OTP for +91******3210 is 482913`. Settings refuse console delivery when `ENVIRONMENT=production`.

## Where the database lives

Supabase offers the same database at three addresses, and the difference
matters:

| How to connect | Host and port | Use it |
| --- | --- | --- |
| **Session pooler** | the pooler host, **5432** | **This API.** One server connection per client, IPv4, prepared statements work. |
| Transaction pooler | the same pooler host, **6543** | Serverless, where connections are many and short. Works here too: `db.py` turns off prepared statements on this port, because a pooled transaction may land on a different server connection than the one that prepared the statement. |
| Direct connection | `db.<ref>.supabase.co`, 5432 | IPv6-only unless the project has the IPv4 add-on, so it usually can't be reached from a home network, and not from Cloud Run. |

The two pooler rows are one endpoint with two ports, so the dashboard's
labels don't matter much: whatever pooler string it gives you, `:5432` is
session mode and `:6543` is transaction mode. Session mode used to be offered
on 6543 as well and was withdrawn in February 2025, which is why older
write-ups disagree.

A project on Supabase's free plan **pauses after a week with no queries** and
has to be restored from the dashboard; `db_check.py` will say it can't be
reached. The free plan is also capped at 500 MB, which is a great many bills
given that the photographs are never stored.

`db.py` also requires TLS for any host that isn't this machine. libpq's own
default, `sslmode=prefer`, falls back to clear text without saying so, and
these rows are health data. Set `sslmode` in the URL yourself to ask for
something stricter, e.g. `?sslmode=verify-full`.

### Row level security

Supabase does not only serve Postgres. It also publishes every table in the
`public` schema over HTTP, read with a key that client apps are meant to carry
in the open. BillCheck does not use that API at all — the app talks to this
service — so migration `c1d4a7f20b63` turns row level security on for all ten
tables and writes no policies. The role that owns the tables is outside row
level security, so this API reads and writes as before; a request arriving over
HTTP with the anon key gets no rows. `db_check.py` reports it, and
`tests/test_db_connection.py` fails if a new table is added without it.

### Running Postgres locally instead

For working offline, or to keep a throwaway database for experiments:

```sh
docker run -d --name billcheck-db -p 5432:5432 \
  -e POSTGRES_USER=billcheck -e POSTGRES_PASSWORD=billcheck -e POSTGRES_DB=billcheck \
  postgres:16                       # afterwards: docker start billcheck-db
```

Then point `DATABASE_URL` at
`postgresql+psycopg://billcheck:billcheck@localhost:5432/billcheck` and run
`uv run alembic upgrade head` again. The commented line in `.env.example` is
this one.

### Moving an existing local database to Supabase

Only worth doing if there is something in the local one you want to keep.
Bill photographs are never stored, so this is cases, line items and flags.

```sh
docker exec billcheck-db pg_dump -U billcheck --data-only --no-owner \
  --no-privileges billcheck > /tmp/billcheck-data.sql

# With DATABASE_URL already pointing at Supabase:
uv run alembic upgrade head            # tables first
psql "$SUPABASE_URI" -f /tmp/billcheck-data.sql   # then the rows
rm /tmp/billcheck-data.sql
```

`$SUPABASE_URI` is the connection string **without** the `+psycopg`, which
only SQLAlchemy understands. Delete the dump afterwards: even test data in
this shape is the shape of a patient's bill.

## Three ways to test sign-in

| `OTP_DELIVERY` | What happens | Use it for |
| --- | --- | --- |
| `console` (default) | The code is printed in the API's terminal. No provider, no account needed. | Day-to-day development. |
| `msg91` + `MSG91_URL=http://localhost:8091/` | The API builds a real MSG91 request; `scripts/fake_msg91.py` answers it and prints the code. | Checking the SMS path works before DLT approval comes through. |
| `msg91` | A real SMS through MSG91. | Staging and production. |

### Testing the SMS path without sending an SMS

Sending through MSG91 needs a DLT-approved template, which takes weeks. Until
then, run the stand-in provider in a second terminal:

```sh
uv run python scripts/fake_msg91.py            # accepts, prints the code
uv run python scripts/fake_msg91.py --refuse   # refuses, so you can see the
                                               # app's "couldn't send" message
```

and point the API at it:

```sh
OTP_DELIVERY=msg91 MSG91_AUTH_KEY=fake-key MSG91_TEMPLATE_ID=fake-template \
  MSG91_URL=http://localhost:8091/ uv run uvicorn main:app --reload
```

The API sends exactly the request it would send to MSG91, so this catches
everything except MSG91's own answer.

### Sending real SMS

1. **Register on DLT.** TRAI requires every transactional SMS in India to match
   a template registered against your entity. MSG91's dashboard walks through
   it; approval usually takes one to two weeks.
2. Register a template whose variable is named `otp`, e.g.
   `Your BillCheck code is ##otp##. It expires in 5 minutes.`
3. Put the auth key, template id, and sender id in `api/.env` and set
   `OTP_DELIVERY=msg91`.

The code is never written to the logs on this path, only the masked number.
If MSG91 refuses or can't be reached, `POST /auth/otp/request` answers `502`
with code `sms_failed` and drops the challenge, so the resend cooldown doesn't
hold the user back for a failure that was ours.

## Checks

```sh
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Tests use an in-memory SQLite database, so they need no database at all:
not Supabase, not Docker.

## Endpoints

- `GET /health` returns `{"status": "ok"}`.
- **Sign-in, phone number + OTP** (`auth.py`):
  - `POST /auth/otp/request` with `{"phone": "9876543210"}` sends a 6-digit code. It responds the same way whether or not the number has an account. Codes expire after 5 minutes. You can ask again after 30 seconds, up to 5 codes an hour.
  - `POST /auth/otp/verify` with `{"phone", "code"}` checks the latest code. Five wrong tries lock it.
    - An existing account gets `{"status": "logged_in", "token", "user"}`.
    - A new number gets `{"status": "signup_required", "signup_token"}`, valid for 15 minutes.
  - `POST /auth/signup` with `{"signup_token", "name", "consent": true}` creates the account and returns `logged_in`. It records the consent version and time for DPDP.
  - `GET /auth/me` returns the signed-in user. `POST /auth/logout` revokes the session.
  - Send the token as `Authorization: Bearer <token>`. Sessions last 30 days.
  - Errors look like `{"detail": {"code": "otp_invalid", "message": "..."}}`. The app turns `code` into translated copy. `sms_failed` (502) means the SMS provider refused or couldn't be reached.
- **Cases** (`cases.py`), all signed in. A case is one admission, shared with family.
  - `POST /cases` opens one. Whoever opens it is its first member.
  - `GET /cases` lists the ones you follow; `GET /cases/{id}` reads one. A case you don't follow answers 404, not 403, so an id can't be used to confirm that someone is in hospital.
  - `POST /cases/{id}/invites` makes an invite code (members only). It's shown once, stored only as a hash, and expires after 7 days. `GET /cases/{id}/invites` lists the live ones and `POST /cases/{id}/invites/{invite_id}/revoke` withdraws one.
  - `POST /cases/join` with `{"code"}` joins. The code goes in the body so it never lands in access logs. An unknown, expired or withdrawn code all answer `404 invite_invalid`. The case id alone can't be used to join.
  - `POST /cases/{id}/members/{user_id}/remove`: anyone can leave; only whoever started the case can remove someone else, and they can't leave it.
  - `POST /cases/{id}/close` marks the stay over. Reports stay readable.
- **Bills and flags** (`bills.py`), all signed in.
  - `POST /cases/{id}/bills` takes the photographed pages as multipart `pages` (JPEG, PNG, WebP or HEIC, up to 15 MB each, 12 pages). It reads them into line items, runs the audit, and returns the bill with its flags. **The photos are never stored** — read in memory, then dropped. Each person can send `BILL_UPLOADS_PER_DAY` bills (default 20) in 24 hours, counting reads that fail, since each is a paid call; past that it answers `429 upload_limit`.
  - `GET /bills/{id}` reads a bill back with its line items and flags.
  - `PATCH /flags/{id}` with `{"status": "corrected" | "explained" | "open"}` records what the hospital said. A corrected flag's difference counts as recovered.

### What the audit checks

`audit.py` runs three checks against the price lists in `data/`:

| Check | Level | Raised when |
| --- | --- | --- |
| Above MRP | red | A medicine is billed above its printed MRP, or above its NPPA ceiling price where one applies. |
| Duplicate | red | The same charge appears twice with the same printed detail. |
| Unusual quantity | amber | Far more of something than a ward stay usually uses. |

A flag stores facts, never sentences: what was billed, what it was checked
against, and the difference. The app turns those into copy in the family's own
language, which is why nothing user-facing is stored here.

**The lists in `data/samples/` are illustrative, not the real NPPA and CGHS
rates.** Replace them before any flag is shown to a real family.

### Reading the bill

`OCR_PROVIDER` picks how a photo becomes line items, the same shape as SMS:

| Value | What happens |
| --- | --- |
| `stub` (default) | Returns one fixed sample bill. No key needed, so the whole loop runs in development and tests without a real bill leaving the machine. |
| `claude` | Reads the real pages with Claude's vision input and structured outputs. Needs `ANTHROPIC_API_KEY`. |

Settings refuse `stub` in production. A HEIC photo is accepted on upload but
the Claude provider can't read it yet — it needs converting first.

OTP codes and session tokens are stored only as hashes.

## Database changes

Edit `tables.py`, then:

```sh
uv run alembic revision --autogenerate -m "what changed"
uv run alembic upgrade head
```

Autogenerate does not know about row level security, so a **new table needs it
turned on by hand** in the generated migration:

```python
op.execute('ALTER TABLE "your_table" ENABLE ROW LEVEL SECURITY')
```

and its name added to a `TABLES` tuple in that migration, which is how
`tests/test_db_connection.py` finds it. Until then that test fails, which is
the point: an unprotected table in `public` is readable by anyone holding the
project's anon key.

Secrets (Claude API, OCR, SMS keys) go in `api/.env`, which is gitignored. `api/.env.example` lists every setting.
