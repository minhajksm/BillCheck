# BillCheck API

FastAPI backend, managed with [uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run uvicorn main:app --reload   # http://localhost:8000/docs
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

From the Android emulator, the API is at `http://10.0.2.2:8000`.

## Endpoints

- `GET /health` returns `{"status": "ok"}`.
- `POST /bills` takes one bill photo as multipart form field `file` (JPEG, PNG, WebP, or HEIC, up to 15 MB). It's a stub for now: it checks the file and returns an id with an empty `line_items` list. The image is not stored.

Secrets (Claude API, OCR keys) go in `api/.env`, which is gitignored.
