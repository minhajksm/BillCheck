# BillCheck API

FastAPI backend with PostgreSQL, managed with [uv](https://docs.astral.sh/uv/).

## First-time setup

```sh
# 1. Database (once). Afterwards, just: docker start billcheck-db
docker run -d --name billcheck-db -p 5432:5432 \
  -e POSTGRES_USER=billcheck -e POSTGRES_PASSWORD=billcheck -e POSTGRES_DB=billcheck \
  postgres:16

# 2. Settings
cp .env.example .env

# 3. Dependencies and tables
uv sync
uv run alembic upgrade head
```

## Run

```sh
uv run uvicorn main:app --reload   # http://localhost:8000/docs
```

From the Android emulator, the API is at `http://10.0.2.2:8000`.

**Sign-in codes during development:** with `OTP_DELIVERY=console`, codes aren't sent by SMS. They're printed in this terminal, like `OTP for +91******3210 is 482913`. Settings refuse console delivery when `ENVIRONMENT=production`.

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

Tests use an in-memory SQLite database, so they don't need Postgres running.

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
- `POST /bills` (signed in) takes one bill photo as multipart form field `file` (JPEG, PNG, WebP, or HEIC, up to 15 MB). It's a stub for now: it checks the file and returns an id with an empty `line_items` list. The image is not stored.

OTP codes and session tokens are stored only as hashes.

## Database changes

Edit `tables.py`, then:

```sh
uv run alembic revision --autogenerate -m "what changed"
uv run alembic upgrade head
```

Secrets (Claude API, OCR, SMS keys) go in `api/.env`, which is gitignored. `api/.env.example` lists every setting.
