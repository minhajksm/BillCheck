# BillCheck

A mobile app that helps Indian families check hospital bills during and after an admission. See [CLAUDE.md](CLAUDE.md) for scope and rules, and [docs/prototype.html](docs/prototype.html) for the clickable prototype.

| Folder | What's in it |
| --- | --- |
| `app/` | React Native app: Expo SDK 57, TypeScript, Expo Router. Android first. |
| `api/` | Python 3.12+ backend: FastAPI, managed with uv. |
| `data/` | Reference price lists and anonymized sample bills. `data/private/` is gitignored. |
| `docs/` | Prototype and design notes. |

## Run it

The app needs the API running so you can sign in. See [api/README.md](api/README.md) for the one-time database setup.

```sh
# API, docs at http://localhost:8000/docs
cd api && docker start billcheck-db && uv run uvicorn main:app --reload

# App, in a second terminal (development build; Expo Go doesn't support SDK 57)
cd app && npm install && npx expo run:android
# ...or in a browser
cd app && npx expo start --web
```

To sign in while developing, use any Indian mobile number. The 6-digit code is printed in the API's terminal instead of being sent by SMS.

The app calls the API at `http://10.0.2.2:8000` on the Android emulator and `http://localhost:8000` on web. On a real phone, set `EXPO_PUBLIC_API_URL` to your computer's address on the same Wi-Fi, e.g. `EXPO_PUBLIC_API_URL=http://192.168.1.20:8000 npx expo run:android`.

## Checks

```sh
cd app && npm run lint && npm run typecheck && npm test
cd api && uv run ruff check . && uv run ruff format --check . && uv run pytest
```
