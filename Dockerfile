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
# Nothing here reads api/.env: see .dockerignore. On Cloud Run the settings
# arrive as environment variables and Secret Manager secrets, so no key is
# ever in a layer.

# uv's own Python image, which is Debian 13 (trixie) for every uv release
# since 0.9 -- there is no 0.11.x bookworm tag, and asking for one fails the
# build with "manifest unknown" before anything else happens. If this tag
# ever stops resolving, list what exists rather than guessing:
#
#     TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:astral-sh/uv:pull&service=ghcr.io" | jq -r .token)
#     curl -s -H "Authorization: Bearer $TOKEN" https://ghcr.io/v2/astral-sh/uv/tags/list | jq -r '.tags[]'
#
# One stage, not two. A second stage would leave uv out of the final image and
# save a few tens of megabytes, at the cost of copying a virtualenv between
# images whose interpreters have to agree exactly -- and that is a build
# failure you only see in Cloud Build's log. Layer caching, which is what
# actually costs time, comes from the order of the COPYs below.
FROM ghcr.io/astral-sh/uv:0.11.32-python3.12-trixie-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/srv/api/.venv/bin:$PATH" \
    PORT=8080

WORKDIR /srv/api

# The lockfile on its own first. A code change then rebuilds no dependency:
# this layer stands until pyproject.toml or uv.lock actually moves.
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY api/ ./
COPY data/samples/ /srv/data/samples/

# Nothing here needs root, and a container that cannot write to its own code
# is one less thing to reason about.
RUN useradd --create-home --uid 10001 billcheck && chown -R billcheck:billcheck /srv
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
