# syntax=docker/dockerfile:1

# The BillCheck API, as Cloud Run runs it.
#
# At the repository root rather than in api/ for two reasons: the price lists
# the audit checks against live in data/samples, so the build context has to
# be the whole repository; and `gcloud run deploy --source .` only looks for a
# Dockerfile here. The app in app/ is built and shipped by Expo instead.
#
#     docker build -t billcheck-api .
#
# The image keeps the repository's own shape -- /srv/api beside /srv/data --
# so REFERENCE_DATA_PATH's default, "../data/samples/reference-prices.json",
# resolves without being set.
#
# Two stages, so what runs holds no build tools and no uv. Nothing reads
# api/.env: see .dockerignore. On Cloud Run the settings arrive as environment
# variables and Secret Manager secrets, so no key is ever in a layer.

FROM ghcr.io/astral-sh/uv:0.11.32-python3.12-bookworm-slim AS build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /srv/api

# The lockfile on its own first. A code change then rebuilds no dependency:
# this layer stands until pyproject.toml or uv.lock actually moves.
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Both stages are python:3.12-slim-bookworm underneath -- the uv image is
# built on it -- which is what lets the virtualenv be copied across. Change
# the Python version in one stage and you must change it in the other.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/srv/api/.venv/bin:$PATH" \
    PORT=8080

# Nothing here needs root, and a container that cannot write to its own code
# is one less thing to reason about.
RUN useradd --create-home --uid 10001 billcheck

WORKDIR /srv/api
COPY --from=build --chown=billcheck:billcheck /srv/api/.venv ./.venv
COPY --chown=billcheck:billcheck api/ ./
COPY --chown=billcheck:billcheck data/samples/ /srv/data/samples/

USER billcheck
EXPOSE 8080

# Cloud Run names the port in $PORT and terminates TLS at its own front end,
# so uvicorn is told to trust X-Forwarded-*: without it every URL the API
# builds for itself, the OpenAPI docs included, comes out as http. Trusting
# any peer is safe here because the only peer is Cloud Run's front end.
#
# One worker. Cloud Run adds instances to scale; a second worker inside this
# one would only double this instance's connections to Supabase.
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 1 \
    --proxy-headers --forwarded-allow-ips='*'
