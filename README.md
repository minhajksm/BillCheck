# BillCheck

A mobile app that helps Indian families check hospital bills during and after an admission. See [CLAUDE.md](CLAUDE.md) for scope and rules, and [docs/prototype.html](docs/prototype.html) for the clickable prototype.

| Folder | What's in it |
| --- | --- |
| `app/` | React Native app: Expo SDK 57, TypeScript, Expo Router. Android first. |
| `api/` | Python 3.12+ backend: FastAPI, managed with uv. |
| `data/` | Reference price lists and anonymized sample bills. `data/private/` is gitignored. |
| `docs/` | Prototype, design notes, and [how the API is deployed](docs/deploy.md). |

## Run it

The app needs the API running so you can sign in. The database is hosted on
Supabase; see [api/README.md](api/README.md) for the one-time setup, which is
a connection string in `api/.env`.

```sh
# API, docs at http://localhost:8000/docs
cd api && uv run uvicorn main:app --reload

# App, in a second terminal (development build; Expo Go doesn't support SDK 57)
cd app && npm install && npx expo run:android
# ...or in a browser
cd app && npx expo start --web
```

To sign in while developing, use any Indian mobile number. The 6-digit code is printed in the API's terminal instead of being sent by SMS.

The app calls the API at `http://10.0.2.2:8000` on the Android emulator and `http://localhost:8000` on web. On a real phone, set `EXPO_PUBLIC_API_URL` to your computer's address on the same Wi-Fi, e.g. `EXPO_PUBLIC_API_URL=http://192.168.1.20:8000 npx expo run:android`.

### Local API or the deployed one

`EXPO_PUBLIC_API_URL` is the whole switch: set, the app talks to the deployed
API; unset, it talks to `uvicorn` on this machine. It is read when the bundle
is built, so changing it means restarting the dev server, not reloading the
page — and in PowerShell it lives for the whole session, so clearing it takes
`$env:EXPO_PUBLIC_API_URL = $null`.

Which database the local API uses is whatever `DATABASE_URL` in `api/.env`
says, and that is probably the same Supabase project Cloud Run reads: local
testing then writes rows the deployed app can see, and a migration run locally
changes the schema it is serving. Fine while nothing real is in there. Before
that stops being true, make a second Supabase project for development and keep
its URL in `api/.env`, leaving the deployed service's own copy in Secret
Manager. The free plan allows two.

## Deploying

The API runs on Cloud Run, with the domain mapped straight to the service,
against the same Supabase database. The `Dockerfile` is in the repository and
[docs/deploy.md](docs/deploy.md) is the runbook.

## Checks

```sh
cd app && npm run lint && npm run typecheck && npm test
cd api && uv run ruff check . && uv run ruff format --check . && uv run pytest
```
