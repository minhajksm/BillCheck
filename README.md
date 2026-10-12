# BillCheck

A mobile app that helps Indian families check hospital bills during and after an admission. See [CLAUDE.md](CLAUDE.md) for scope and rules, and [docs/prototype.html](docs/prototype.html) for the clickable prototype.

| Folder | What's in it |
| --- | --- |
| `app/` | React Native app: Expo SDK 57, TypeScript, Expo Router. Android first. |
| `api/` | Python 3.12+ backend: FastAPI, managed with uv. |
| `data/` | Reference price lists and anonymized sample bills. `data/private/` is gitignored. |
| `docs/` | Prototype and design notes. |

## Run it

```sh
# App (development build; Expo Go doesn't support SDK 57)
cd app && npm install && npx expo run:android

# API, docs at http://localhost:8000/docs
cd api && uv sync && uv run uvicorn main:app --reload
```

From the Android emulator, the API is at `http://10.0.2.2:8000`.

## Checks

```sh
cd app && npm run lint && npm run typecheck && npm test
cd api && uv run ruff check . && uv run ruff format --check . && uv run pytest
```
