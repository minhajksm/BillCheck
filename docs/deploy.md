# Deploying the API

```
Android app
   |  HTTPS, api.<your-domain>
   v
Cloud Run (billcheck-api)   the FastAPI container, scaled to zero when idle
   v
Supabase                    managed Postgres, session pooler
```

The app itself is not served here — Expo builds and ships that. This is the
API and nothing else.

**The domain points at Cloud Run itself, not at Firebase Hosting.** Hosting
answers `504` once the origin takes more than 60 seconds and will not be
configured otherwise. Reading a bill is one Claude call that writes thousands
of tokens: a one-page bill lands inside 60 seconds, a long multi-page one
does not, and the family would be told we couldn't read a bill that was read
perfectly well. Cloud Run's own timeout is ours to set, up to 60 minutes, so
the ceiling goes away by taking Hosting out of the path.

## Before you start

You need a Supabase account, a Google Cloud project with billing enabled, and
`uv` on your machine — migrations and the tests still run locally, and that is
the one thing hosting does not take away. Docker you do not need, here or
anywhere else.

Step 1 needs no gcloud. Everything after it does:

```sh
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com
```

### On Windows PowerShell

The commands on this page are written for a POSIX shell. `gcloud` itself is
the same everywhere; the shell around it is not. Three differences, and they
all bite silently:

- **Line continuation is a backtick,** `` ` ``, not `\`. A `\` at the end of a
  line in PowerShell does not continue it, so the rest of the command is lost
  and gcloud runs with whatever it got. Safest is to put long commands on one
  line.
- **`printf` does not exist, and piping a string adds a newline.** A
  `DATABASE_URL` secret with a trailing newline fails later with "database
  \"postgres\n\" does not exist", which reads like a Supabase problem and
  isn't. Write the value with `[IO.File]::WriteAllText`, which writes exactly
  the string and no byte-order mark on both PowerShell 5 and 7 — unlike `>`
  or `Set-Content -Encoding utf8`, which add one or the other.
- **`$(...)` and `for x in` are different.** Assign with `$NUMBER = gcloud ...`
  and loop with `foreach ($s in 'a','b') { ... }`.

Every command below that needs a different form has it.

### Which region

Use **`asia-southeast1`** (Singapore) for Cloud Run, and put the Supabase
project in Singapore too, so the API's queries don't cross a region.

Mumbai (`asia-south1`) is the tempting choice and is not in Cloud Run's list
of regions that custom domains can be mapped to. The 40-odd milliseconds
Singapore costs an Indian user is nothing beside the time the reader itself
takes.

## 1. The database

Supabase hosts it. Nothing below depends on Cloud Run, so this is worth doing
first and on its own: once `db_check.py` is happy, the API already runs
locally against the hosted database, and everything after this is only about
where the API itself runs.

1. **Create the project.** In Supabase, *New project*. **Singapore**, to match
   the Cloud Run region above. Save the database password it asks for.
2. **Copy the connection string.** *Connect*, in the top bar, → any of the
   **pooler** strings → then **make the port `5432`**.

   Go by the port, not by the label: Supabase renames these blocks, but the
   shared pooler has served session mode on **5432** and transaction mode on
   **6543** since it stopped offering session mode on 6543 in February 2025.
   Both are the same host and the same `postgres.<project-ref>` username, so
   if the dialog only offers you the transaction pooler, change the `:6543`
   to `:5432` and you have the session string. Avoid the **direct**
   connection (`db.<ref>.supabase.co`): it is IPv6-only on most projects, and
   Cloud Run calls out over IPv4.

   Transaction mode works too if you would rather not touch the port —
   `api/db.py` turns off prepared statements on 6543, so nothing breaks. You
   give up a little speed and some Postgres features. `api/README.md` compares
   the three.
3. **Put it in `api/.env`**, as `DATABASE_URL`, with two edits:
   - change the scheme from `postgresql://` to **`postgresql+psycopg://`**,
     which names the driver we use;
   - percent-encode the password if it contains `@ : / ? #` or `%`. Resetting
     it to something alphanumeric in *Database → Settings* is easier.

   ```sh
   cd api && cp .env.example .env     # if you haven't already
   ```

   You also want `ANTHROPIC_API_KEY` and `OCR_PROVIDER=claude` in there to read
   real bills; `OCR_PROVIDER` defaults to a stub that returns one fixed sample.

4. **Create the tables and check it.** Migrations run from your machine, not
   from the container: Cloud Run starts a web server, and a migration is not
   one.

   ```sh
   uv sync
   uv run alembic upgrade head
   uv run python scripts/db_check.py
   ```

   `db_check.py` writes nothing. It should say it reached Postgres, that the
   connection is encrypted, that migrations are up to date, and that row level
   security is on for all ten tables. **Row level security matters here**:
   Supabase also serves the `public` schema over HTTP with a key that client
   apps carry in the open, and the migration that turns it on is what keeps a
   family's bill from being readable by anyone who asks. `api/README.md` has
   the detail.

At this point `cd api && uv run uvicorn main:app --reload` works against
Supabase, with no Docker anywhere. The rest of this page moves that last
command off your machine.

## 2. Secrets

The deployed service gets the same settings from Secret Manager rather than
from `api/.env` — never from `--set-env-vars`, and never baked into the image.
`.dockerignore` keeps `api/.env` out of the build.

Use the **same `DATABASE_URL` you just put in `api/.env`**, the one
`db_check.py` approved:

```sh
printf '%s' 'postgresql+psycopg://postgres.REF:PASSWORD@POOLER_HOST:5432/postgres' \
  | gcloud secrets create billcheck-database-url --data-file=-

python -c "import secrets; print(secrets.token_urlsafe(48), end='')" \
  | gcloud secrets create billcheck-secret-key --data-file=-

printf '%s' 'sk-ant-...' | gcloud secrets create billcheck-anthropic-key --data-file=-
```

In PowerShell, through a temp file so no newline is appended:

```powershell
function New-Secret($name, $value) {
  $file = Join-Path $env:TEMP "$name.txt"
  [IO.File]::WriteAllText($file, $value)
  gcloud secrets create $name --data-file=$file
  Remove-Item $file
}

New-Secret billcheck-database-url 'postgresql+psycopg://postgres.REF:PASSWORD@POOLER_HOST:5432/postgres'
New-Secret billcheck-secret-key (uv run --directory api python -c "import secrets; print(secrets.token_urlsafe(48))")
New-Secret billcheck-anthropic-key 'sk-ant-...'
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

```powershell
$NUMBER = gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)"
foreach ($secret in 'billcheck-database-url','billcheck-secret-key','billcheck-anthropic-key') {
  gcloud secrets add-iam-policy-binding $secret --member="serviceAccount:$NUMBER-compute@developer.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
}
```

`$NUMBER-compute@developer.gserviceaccount.com` is the Compute Engine default
service account, which is what Cloud Run runs as unless told otherwise. If
the deploy later says it cannot find it, that account has been removed or
disabled on this project, and the service needs one of its own.

## 3. Deploy to Cloud Run

From the repository root, because the image needs `data/samples` as well as
`api/`:

```sh
gcloud run deploy billcheck-api \
  --source . \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --timeout 600 \
  --concurrency 20 \
  --max-instances 4 \
  --set-env-vars 'ENVIRONMENT=development,OCR_PROVIDER=claude,OTP_DELIVERY=console,REVIEW_KEEP_ALL=false' \
  --set-secrets 'DATABASE_URL=billcheck-database-url:latest,SECRET_KEY=billcheck-secret-key:latest,ANTHROPIC_API_KEY=billcheck-anthropic-key:latest'
```

In PowerShell, all on one line, since a stray `\` would silently drop
everything after it:

```powershell
gcloud run deploy billcheck-api --source . --region asia-southeast1 --allow-unauthenticated --memory 1Gi --timeout 600 --concurrency 20 --max-instances 4 --set-env-vars 'ENVIRONMENT=development,OCR_PROVIDER=claude,OTP_DELIVERY=console,REVIEW_KEEP_ALL=false' --set-secrets 'DATABASE_URL=billcheck-database-url:latest,SECRET_KEY=billcheck-secret-key:latest,ANTHROPIC_API_KEY=billcheck-anthropic-key:latest'
```

The first run asks to create an Artifact Registry repository to keep the image
in; answer yes. It then uploads the build context and builds on Cloud Build,
which takes a few minutes. Later deploys reuse the repository and the cached
layers.

`--allow-unauthenticated` is right here: the API does its own sign-in with
phone and OTP, and Cloud Run's IAM would be a second, unrelated door.

`--timeout 600` is the point of this whole arrangement — ten minutes, where
Hosting allowed one. It is an upper bound, not a target: a request that
actually took ten minutes would be a bug. Cloud Run's maximum is 3600.

**`ENVIRONMENT=development` is deliberate.** `api/settings.py` refuses to
start in production while OTP codes are printed instead of sent, and real SMS
needs a DLT-approved MSG91 template, which takes weeks. See
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

```powershell
$URL = gcloud run services describe billcheck-api --region asia-southeast1 --format="value(status.url)"
Invoke-RestMethod "$URL/health"     # status : ok
```

If it answers anything else, the logs say why —
`gcloud run services logs read billcheck-api --region asia-southeast1 --limit 50`.
A container that starts and immediately exits is almost always `settings.py`
refusing the configuration it was given, and it says which setting.

That `*.run.app` URL already works over HTTPS with no cap but Cloud Run's own.
Everything below is to put a name you own in front of it.

## 4. Point your domain at the service

Two ways. Start with the mapping, move to the load balancer before real
families use this — Google's own docs say the mapping is preview and
[not recommended for production](https://docs.cloud.google.com/run/docs/mapping-custom-domains).

### A. Domain mapping — free, about fifteen minutes

```sh
# Once per domain: prove you own it. Opens Search Console.
gcloud domains verify your-domain.example

gcloud beta run domain-mappings create \
  --service billcheck-api \
  --domain api.your-domain.example \
  --region asia-southeast1
```

It prints the DNS record to add — a `CNAME` to `ghs.googlehosted.com` for a
subdomain. Add it at your registrar. Google issues and renews the certificate
itself; it usually takes about fifteen minutes and can take up to 24 hours.

What you are accepting with it:

- It is a **preview** feature, which Google says is not production-ready,
  because of latency: a known issue reports very high latency from some
  locations for services reached this way.
- **TLS 1.0 and 1.1 cannot be turned off.** A load balancer or Hosting is the
  only way to refuse them.
- No wildcard certificates, and you cannot supply your own.

### B. Global external Application Load Balancer — the production answer

This is what Google recommends, and with a serverless NEG backend the
timeout is 60 minutes and not configurable, so Cloud Run's own `--timeout`
stays the only limit. It also brings Cloud CDN, Cloud Armor and your own
certificate. It costs: a global forwarding rule is billed by the hour whether
or not anyone uses it, so this is the step that turns a free deployment into a
monthly bill.

```sh
gcloud compute network-endpoint-groups create billcheck-neg \
  --region=asia-southeast1 --network-endpoint-type=serverless \
  --cloud-run-service=billcheck-api

gcloud compute backend-services create billcheck-backend \
  --global --load-balancing-scheme=EXTERNAL_MANAGED

gcloud compute backend-services add-backend billcheck-backend --global \
  --network-endpoint-group=billcheck-neg \
  --network-endpoint-group-region=asia-southeast1

gcloud compute url-maps create billcheck-lb --default-service billcheck-backend

gcloud compute ssl-certificates create billcheck-cert \
  --domains=api.your-domain.example --global

gcloud compute target-https-proxies create billcheck-https-proxy \
  --ssl-certificates=billcheck-cert --url-map=billcheck-lb

gcloud compute addresses create billcheck-ip --global
gcloud compute forwarding-rules create billcheck-fr --global \
  --target-https-proxy=billcheck-https-proxy --ports=443 --address=billcheck-ip
```

Then point an `A` record at the address `gcloud compute addresses describe
billcheck-ip --global --format='value(address)'` prints. Do not set
`timeoutSec` on the backend service: with a serverless NEG the API rejects it.

Load balancer flags move around more than most. If gcloud refuses one, follow
[Serverless network endpoint groups](https://docs.cloud.google.com/load-balancing/docs/negs/serverless-neg-concepts)
rather than arguing with it.

## 5. Point the app at it

```sh
cd app
EXPO_PUBLIC_API_URL=https://api.your-domain.example npx expo run:android
```

For Expo web, the API has to allow the browser origin as well — redeploy with
`CORS_ORIGINS=["https://your-web-origin"]` in `--set-env-vars`. The Android
app doesn't need it.

### How long the app itself will wait

Nothing in the app sets a timeout: `apiFetch` uses `fetch` with none, and the
upload's `XMLHttpRequest` leaves `timeout` at its default of 0, which means
never. So the wait is whatever the platform's own socket timeout allows —
effectively unbounded on Android, which is what this is built for first. iOS
defaults to 60 seconds per request, so a long bill will need
`request.timeout` and an `ontimeout` handler before there is an iOS build. As
it stands a platform timeout would arrive as `onerror`, which the app shows
as a network error — the right message, at least.

## When you change something

| What changed | What to run |
| --- | --- |
| API code | `gcloud run deploy billcheck-api --source . --region asia-southeast1` from the repository root. The flags from step 3 stick to the service; you only repeat one you are changing. |
| `api/tables.py` | `cd api && uv run alembic revision --autogenerate -m "..."` then `uv run alembic upgrade head`, from your machine, **before** deploying the code that needs the new column. A new table also needs row level security turned on by hand; `api/README.md` says how. |
| A secret | `printf '%s' 'new value' \| gcloud secrets versions add billcheck-database-url --data-file=-`, then redeploy so the service picks up `:latest`. |
| The price lists in `data/samples/` | Redeploy. They are baked into the image. |
| App code | Nothing here — Expo builds and ships the app. |

## Going to actual production

`ENVIRONMENT=production` makes `api/settings.py` refuse to start unless all of
these hold, and each one is deliberate:

| Setting | What production needs | Blocked on |
| --- | --- | --- |
| `SECRET_KEY` | 32+ random characters | nothing; the secret above is already one |
| `OTP_DELIVERY` | `msg91` | a DLT-approved template, one to two weeks |
| `OCR_PROVIDER` | `claude` | nothing |
| `REVIEW_KEEP_ALL` | `false` | nothing |

Three more things to settle before real families use this:

- **Move to the load balancer** (B above), which is the supported path and the
  only one that can refuse TLS 1.0 and 1.1.
- **The price lists are illustrative.** `data/samples/reference-prices.json`
  is not the real NPPA and CGHS data, and it ships inside the image. Replace
  it before any flag is shown to anyone.
- **`/docs` is public.** FastAPI serves the whole schema at `/docs` and
  `/openapi.json`. Harmless while this is ours to look at; worth turning off
  (`FastAPI(docs_url=None, openapi_url=None)`) once it isn't.
