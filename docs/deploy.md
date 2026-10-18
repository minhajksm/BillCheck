# Deploying the API

```
Android app
   |  HTTPS, api.<your-domain>
   v
Firebase Hosting            custom domain and TLS, rewrites everything to ->
   v
Cloud Run (billcheck-api)   the FastAPI container, scaled to zero when idle
   v
Supabase                    managed Postgres, session pooler
```

The app itself is not served here — Expo builds and ships that. This is the
API and nothing else.

> **Read [The sixty-second limit](#the-sixty-second-limit) before you point the
> app at the Hosting domain.** Firebase Hosting gives up on a request after 60
> seconds and cannot be configured otherwise, and reading a bill takes a large
> fraction of that.

## Before you start

```sh
# Google Cloud and Firebase are the same project; create it in either console.
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com

npm install -g firebase-tools && firebase login
```

### Which region

Use **`asia-southeast1`** (Singapore) for Cloud Run, and put the Supabase
project in Singapore too, so the API's queries don't cross a region.

Mumbai (`asia-south1`) is the tempting choice and does not work here: it is
absent from Firebase Hosting's list of regions it will rewrite to, and from
Cloud Run's custom-domain mapping regions. Singapore is in both, and the
40-odd milliseconds it costs an Indian user is nothing beside the time the
reader itself takes.

## 1. Secrets

They go in Secret Manager, never in `--set-env-vars` and never in the image.
`.dockerignore` keeps `api/.env` out of the build.

```sh
printf '%s' 'postgresql+psycopg://postgres.REF:PASSWORD@POOLER_HOST:5432/postgres' \
  | gcloud secrets create billcheck-database-url --data-file=-

python -c "import secrets; print(secrets.token_urlsafe(48), end='')" \
  | gcloud secrets create billcheck-secret-key --data-file=-

printf '%s' 'sk-ant-...' | gcloud secrets create billcheck-anthropic-key --data-file=-
```

Let the service read them:

```sh
NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format='value(projectNumber)')
for secret in billcheck-database-url billcheck-secret-key billcheck-anthropic-key; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:$NUMBER-compute@developer.gserviceaccount.com" \
    --role=roles/secretmanager.secretAccessor
done
```

## 2. Create the tables

Migrations run from your machine, not from the container: Cloud Run starts a
web server, and a migration is not one. `api/.env` already points at Supabase,
so this is the same command as always.

```sh
cd api && uv run alembic upgrade head && uv run python scripts/db_check.py
```

## 3. Deploy to Cloud Run

From the repository root, because the image needs `data/samples` as well as
`api/`:

```sh
gcloud run deploy billcheck-api \
  --source . \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --timeout 300 \
  --concurrency 20 \
  --max-instances 4 \
  --set-env-vars 'ENVIRONMENT=development,OCR_PROVIDER=claude,OTP_DELIVERY=console,REVIEW_KEEP_ALL=false' \
  --set-secrets 'DATABASE_URL=billcheck-database-url:latest,SECRET_KEY=billcheck-secret-key:latest,ANTHROPIC_API_KEY=billcheck-anthropic-key:latest'
```

`--allow-unauthenticated` is right here: the API does its own sign-in with
phone and OTP, and Cloud Run's IAM would be a second, unrelated door.

**`ENVIRONMENT=development` is deliberate.** `api/settings.py` refuses to start
in production while OTP codes are printed instead of sent, and real SMS needs
a DLT-approved MSG91 template, which takes weeks. See
[Going to actual production](#going-to-actual-production).

`--max-instances 4` with `--concurrency 20` caps what this can do to the
database: four instances, each with SQLAlchemy's pool of 5 plus 10 overflow,
is at most 60 client connections to Supabase's pooler. Raise them together,
and watch the pooler's own limits when you do.

Check it before putting a domain in front:

```sh
URL=$(gcloud run services describe billcheck-api --region asia-southeast1 --format='value(status.url)')
curl -s "$URL/health"     # {"status":"ok"}
```

## 4. Firebase Hosting and the custom domain

`firebase.json` is already in the repository: it rewrites every path to the
Cloud Run service and serves one static page at `/` so the bare domain isn't a
404.

```sh
firebase use --add                  # pick the same project
firebase deploy --only hosting
```

Then Firebase console → Hosting → **Add custom domain** →
`api.<your-domain>`, and add the DNS records it shows you. The certificate
takes a few minutes to an hour.

If you renamed the service or chose another region, change `serviceId` and
`region` in `firebase.json` to match.

## 5. Point the app at it

```sh
cd app
EXPO_PUBLIC_API_URL=https://api.your-domain.example npx expo run:android
```

For Expo web, the API has to allow the browser origin as well — redeploy with
`CORS_ORIGINS=["https://your-web-origin"]` in `--set-env-vars`. The Android
app doesn't need it.

## The sixty-second limit

Firebase Hosting answers `504` if the origin takes more than **60 seconds**,
and unlike Cloud Run's own timeout this is not configurable. Reading a bill is
one Claude call that writes thousands of tokens: a one-page bill lands well
inside 60 seconds, a long multi-page one will not, and when it goes over, the
family sees "we couldn't read this bill" for a bill that was read perfectly
well.

Nothing else the API does comes close — sign-in, cases and flags are all
milliseconds — so this is about `POST /bills` and `POST /cases/{id}/bills`
alone. Three ways out, in the order I'd try them:

1. **Give Cloud Run the domain instead of Hosting.** Map
   `api.<your-domain>` straight to the service (`gcloud beta run
   domain-mappings create`, or a global external load balancer, whose backend
   timeout you set yourself). Hosting keeps the project's static site, and the
   API stops having a 60-second ceiling. Cheapest fix, no code.
2. **Make the upload asynchronous.** `POST /bills` answers `202` with a job
   id and the app polls for the result. This is better regardless of hosting —
   the wait already has a screen of its own, and a poll survives the app being
   backgrounded, which an open request does not — but it changes the app and
   the API together, so it is a decision, not a patch.
3. **Leave it.** Short bills work; long ones fail with a misleading message.
   Fine for a demo, not for a family.

## Going to actual production

`ENVIRONMENT=production` makes `api/settings.py` refuse to start unless all of
these hold, and each one is deliberate:

| Setting | What production needs | Blocked on |
| --- | --- | --- |
| `SECRET_KEY` | 32+ random characters | nothing; the secret above is already one |
| `OTP_DELIVERY` | `msg91` | a DLT-approved template, one to two weeks |
| `OCR_PROVIDER` | `claude` | nothing |
| `REVIEW_KEEP_ALL` | `false` | nothing |

Two more things to settle before real families use this:

- **The price lists are illustrative.** `data/samples/reference-prices.json`
  is not the real NPPA and CGHS data, and it ships inside the image. Replace
  it before any flag is shown to anyone.
- **`/docs` is public.** FastAPI serves the whole schema at `/docs` and
  `/openapi.json`. Harmless while this is ours to look at; worth turning off
  (`FastAPI(docs_url=None, openapi_url=None)`) once it isn't.
