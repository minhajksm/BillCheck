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

**Where a command appears twice below — once as `sh`, once as `powershell` —
those are the same command in two shells. Run one of them, not both.** Each
pair is labelled.

### Which region

**`asia-south1`** (Mumbai), for Cloud Run and for Supabase both. Closest to
the families, and the API's queries then stay inside one region — Supabase
cannot be moved later, so this is the decision to get right first.

It costs one thing, and only one: **Cloud Run cannot map a custom domain to a
service in Mumbai.** That feature exists in ten regions —
`asia-east1`, `asia-northeast1`, `asia-southeast1`, `europe-north1`,
`europe-west1`, `europe-west4`, `us-central1`, `us-east1`, `us-east4`,
`us-west1` — and Mumbai is not among them. The service's own
`*.run.app` address works regardless, and a load balancer can put your own
name in front of it from any region; see
[step 4](#4-point-your-domain-at-the-service). Nothing else about the deploy
changes.

Singapore (`asia-southeast1`) is the alternative: it can map a domain
directly, at the cost of every database round trip leaving the region. For an
API whose slowest call waits on Claude for most of a minute, the domain is
worth less than the proximity, which is why Mumbai is the recommendation here.

## 1. The database

Supabase hosts it. Nothing below depends on Cloud Run, so this is worth doing
first and on its own: once `db_check.py` is happy, the API already runs
locally against the hosted database, and everything after this is only about
where the API itself runs.

1. **Create the project.** In Supabase, *New project*. **Mumbai
   (`ap-south-1`)**, to match the Cloud Run region above. Save the database
   password it asks for — and note that Supabase cannot change a project's
   region afterwards, so this one is worth not getting wrong.
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
   - escape the password if it contains `@` or `%`, as `%40` and `%25`. Those
     are the only two that break it: `?`, `#`, `/` and `:` are read
     literally, whatever a URL does elsewhere. Resetting the password to
     something alphanumeric in *Database → Settings* avoids the question.

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

These can also be created by hand in the console, which on Windows is the
easier path — no quoting, and no shell appending a newline to a value that
then fails hours later. See
[deploying from GitHub](#or-deploy-from-github-with-no-local-commands-at-all),
which does the whole of steps 2 and 3 without a shell.

They live in the Google Cloud project, not on your machine and not in this
repository: `gcloud secrets list`, or
`console.cloud.google.com/security/secret-manager?project=<id>`. Your
`api/.env` keeps its own copies for running locally, which is why the same
`DATABASE_URL` is in both. Each secret is a container of versions, and the
deploy below asks for `:latest`, so a new version needs a redeploy before the
service sees it.

Use the **same `DATABASE_URL` you just put in `api/.env`**, the one
`db_check.py` approved.

*bash — macOS, Linux, WSL, Git Bash:*

```sh
printf '%s' 'postgresql+psycopg://postgres.REF:PASSWORD@POOLER_HOST:5432/postgres' \
  | gcloud secrets create billcheck-database-url --data-file=-

python -c "import secrets; print(secrets.token_urlsafe(48), end='')" \
  | gcloud secrets create billcheck-secret-key --data-file=-

printf '%s' 'sk-ant-...' | gcloud secrets create billcheck-anthropic-key --data-file=-
```

*PowerShell — the same three secrets, through a temp file so that nothing
appends a newline to them. Run this instead of the block above; it does not
matter which directory you are in:*

```powershell
function New-Secret($name, $value) {
  # A secret made from the output of a command that failed is the one error
  # worth refusing: gcloud takes an empty payload without complaint, and an
  # empty SECRET_KEY is what signs the OTP hashes.
  if ([string]::IsNullOrWhiteSpace($value)) { throw "$name would be empty. Nothing created." }
  $file = Join-Path $env:TEMP "$name.txt"
  [IO.File]::WriteAllText($file, $value)
  gcloud secrets create $name --data-file=$file
  Remove-Item $file
}

New-Secret billcheck-database-url 'postgresql+psycopg://postgres.REF:PASSWORD@POOLER_HOST:5432/postgres'
New-Secret billcheck-anthropic-key 'sk-ant-...'

# 48 random bytes, base64, which is 64 characters. PowerShell's own generator
# rather than Python's, so this works from any directory and needs no uv.
$bytes = New-Object byte[] 48
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
New-Secret billcheck-secret-key ([Convert]::ToBase64String($bytes))
```

Check each one arrived whole — this prints the length, not the value:

```powershell
foreach ($secret in 'billcheck-database-url','billcheck-secret-key','billcheck-anthropic-key') {
  "$secret : " + (gcloud secrets versions access latest --secret=$secret).Length
}
```

`billcheck-secret-key` should read 64. A secret that reads 0, or errors, was
created empty; give it a real value with `gcloud secrets versions add <name>
--data-file=<file>` rather than deleting and starting again, since the
service always reads `:latest`.

Let the service read them. *bash:*

```sh
NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format='value(projectNumber)')
for secret in billcheck-database-url billcheck-secret-key billcheck-anthropic-key; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:$NUMBER-compute@developer.gserviceaccount.com" \
    --role=roles/secretmanager.secretAccessor
done
```

*PowerShell, instead of the above:*

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
`api/`. *bash:*

```sh
gcloud run deploy billcheck-api \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --timeout 600 \
  --concurrency 20 \
  --max-instances 4 \
  --set-env-vars 'ENVIRONMENT=development,OCR_PROVIDER=claude,OTP_DELIVERY=console,REVIEW_KEEP_ALL=false' \
  --set-secrets 'DATABASE_URL=billcheck-database-url:latest,SECRET_KEY=billcheck-secret-key:latest,ANTHROPIC_API_KEY=billcheck-anthropic-key:latest'
```

*PowerShell — the same deploy, instead of the above, all on one line, since
a stray `\` would silently drop everything after it:*

```powershell
gcloud run deploy billcheck-api --source . --region asia-south1 --allow-unauthenticated --memory 1Gi --timeout 600 --concurrency 20 --max-instances 4 --set-env-vars 'ENVIRONMENT=development,OCR_PROVIDER=claude,OTP_DELIVERY=console,REVIEW_KEEP_ALL=false' --set-secrets 'DATABASE_URL=billcheck-database-url:latest,SECRET_KEY=billcheck-secret-key:latest,ANTHROPIC_API_KEY=billcheck-anthropic-key:latest'
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

### Or deploy from GitHub, with no local commands at all

Cloud Run can watch the repository and build on every push, and the secrets
and settings can be filled in from the console, so the only thing you run
locally is `git push`. Same image, same Dockerfile — Cloud Run runs container
images and nothing else, so something has to build one; this only moves the
build off your machine and onto a push.

**1. The three secrets, in the console.** *Security → Secret Manager →
Create secret*, three times: `billcheck-database-url`,
`billcheck-secret-key`, `billcheck-anthropic-key`. Paste each value into the
*Secret value* box. This is worth preferring over the command line on
Windows: there is no quoting to get wrong, and no shell appending a newline
to a value that then fails hours later.

For `billcheck-secret-key`, paste 40-odd random characters. Any password
generator will do; nothing reads it but the API.

**2. Create the service.** *Cloud Run → Deploy container → Service*, then:

| Field | Value |
| --- | --- |
| Source | **Continuously deploy from a repository** → *Set up with Cloud Build* |
| Repository provider | GitHub, then authorise and pick this repository |
| Branch | one you merge into deliberately — not a branch you are working on, since every push to it deploys |
| Build type | **Dockerfile**, location `/Dockerfile` |
| Region | `asia-south1`, or whichever matches your Supabase project |
| Authentication | allow unauthenticated invocations — the API does its own sign-in, and Cloud Run's IAM would be a second, unrelated door |

The Dockerfile's location is also the build context, and `/Dockerfile` makes
that the repository root, which this image needs: it copies `data/samples` as
well as `api/`.

**3. Under *Containers → Settings*:** memory 1 GiB, request timeout **600**,
maximum concurrent requests 20. Under *Revision autoscaling*, maximum
instances 4. (Why those numbers: see the notes under the command above.)

**4. Under *Containers → Variables & Secrets*:** four plain variables —
`ENVIRONMENT=development`, `OCR_PROVIDER=claude`, `OTP_DELIVERY=console`,
`REVIEW_KEEP_ALL=false` — then *Reference a secret* three times, each exposed
**as an environment variable**:

| Variable | Secret | Version |
| --- | --- | --- |
| `DATABASE_URL` | `billcheck-database-url` | latest |
| `SECRET_KEY` | `billcheck-secret-key` | latest |
| `ANTHROPIC_API_KEY` | `billcheck-anthropic-key` | latest |

The console offers to grant the service account access to each secret as you
add it. Accept, and step 2's IAM commands are unnecessary.

**5. Create.** The first build takes a few minutes; the service page tracks
it, and *Build history* has the log if it fails.

Afterwards, a push to that branch builds and deploys on its own. The
environment variables and secrets live on the service, not in the trigger, so
they survive every later deploy and are only edited when you mean to.

What this does **not** remove: the migration in step 1 still runs from your
machine, because Cloud Run starts a web server and a migration is not one.

### If the build or the deploy fails

Two failures are worth recognising on sight, because neither is a problem with
the code.

**`manifest unknown`, on the Dockerfile's first line.** That image tag does
not exist, and nothing was built:

```
Step 1/N : FROM ghcr.io/astral-sh/uv:...
manifest unknown
```

uv's versioned Python images moved to Debian 13 (trixie) at uv 0.9, so a
`bookworm` tag for a current uv is not there to be pulled. The Dockerfile has
the command for listing what does exist.

**`Permission denied on secret: ... for Revision service account`.** The image
built and the service was created; the revision could not start because the
account Cloud Run runs as may not read the secrets. This is the IAM grant from
[step 2](#2-secrets), skipped or not yet applied — the console grants it for
you as you add each secret reference, `gcloud` does not.

The message names only the first secret it tried. All three need it:

```powershell
$NUMBER = gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)"
foreach ($secret in 'billcheck-database-url','billcheck-secret-key','billcheck-anthropic-key') {
  gcloud secrets add-iam-policy-binding $secret --member="serviceAccount:$NUMBER-compute@developer.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
}
```

Then deploy again; nothing rebuilds, since the image is already there. Check
it took with `gcloud secrets get-iam-policy billcheck-database-url`.

`--max-instances 4` with `--concurrency 20` caps what this can do to the
database: four instances, each with SQLAlchemy's pool of 5 plus 10 overflow,
is at most 60 client connections to Supabase's pooler. Raise them together,
and watch the pooler's own limits when you do.

Check it before putting a domain in front. *bash:*

```sh
URL=$(gcloud run services describe billcheck-api --region asia-south1 --format='value(status.url)')
curl -s "$URL/health"     # {"status":"ok"}
```

*PowerShell, instead of the above:*

```powershell
$URL = gcloud run services describe billcheck-api --region asia-south1 --format="value(status.url)"
Invoke-RestMethod "$URL/health"     # status : ok
```

If it answers anything else, the logs say why —
`gcloud run services logs read billcheck-api --region asia-south1 --limit 50`.
A container that starts and immediately exits is almost always `settings.py`
refusing the configuration it was given, and it says which setting.

That `*.run.app` URL already works over HTTPS with no cap but Cloud Run's own.
Everything below is to put a name you own in front of it.

## 4. Point your domain at the service

**You probably do not need this yet.** The service's own
`https://billcheck-api-<hash>.a.run.app` is real HTTPS with a certificate
Google manages, and nothing but Cloud Run's own `--timeout` caps a request on
it. Point the app at that, get the loop working end to end, and come back here
when you want a name of your own.

When you do, in Mumbai there is **one** way: a load balancer. Cloud Run's own
`domain-mappings` — a `CNAME` to `ghs.googlehosted.com`, free, fifteen
minutes — exists only in `asia-east1`, `asia-northeast1`,
`asia-southeast1`, `europe-north1`, `europe-west1`, `europe-west4`,
`us-central1`, `us-east1`, `us-east4` and `us-west1`. Not `asia-south1`.

That is less of a loss than it sounds. Google's own docs call the mapping a
preview feature, [not recommended for production](https://docs.cloud.google.com/run/docs/mapping-custom-domains)
on latency grounds, and it cannot refuse TLS 1.0 and 1.1 or take a
certificate of your own. The load balancer was always the answer for real
users; being in Mumbai just removes the shortcut.

### Global external Application Load Balancer

This is what Google recommends, and with a serverless NEG backend the
timeout is 60 minutes and not configurable, so Cloud Run's own `--timeout`
stays the only limit. It also brings Cloud CDN, Cloud Armor and your own
certificate. It costs: a global forwarding rule is billed by the hour whether
or not anyone uses it, so this is the step that turns a free deployment into a
monthly bill.

```sh
gcloud compute network-endpoint-groups create billcheck-neg \
  --region=asia-south1 --network-endpoint-type=serverless \
  --cloud-run-service=billcheck-api

gcloud compute backend-services create billcheck-backend \
  --global --load-balancing-scheme=EXTERNAL_MANAGED

gcloud compute backend-services add-backend billcheck-backend --global \
  --network-endpoint-group=billcheck-neg \
  --network-endpoint-group-region=asia-south1

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

Load balancer flags move around more than most, and I have not run these
against a Mumbai project. If gcloud refuses one, follow
[Serverless network endpoint groups](https://docs.cloud.google.com/load-balancing/docs/negs/serverless-neg-concepts)
rather than arguing with it.

## 5. Point the app at it

```sh
cd app
EXPO_PUBLIC_API_URL=https://api.your-domain.example npx expo run:android
```

For Expo web, the API has to allow the browser origin as well. The default is
`["http://localhost:8081"]`, which is where Expo's web dev server runs — so
running the app locally against the deployed API works without changing
anything, **until port 8081 is busy**. Expo then takes 8082, the origin no
longer matches, and the browser refuses the request before it is sent: a CORS
error in the console and a plain network error in the app, neither of which
mentions the port.

The fix is to free 8081, or to add the other origin. `CORS_ORIGINS` holds a
JSON list, and gcloud splits `--update-env-vars` on commas, so the console's
*Variables & Secrets* tab is the easier place to set it. The Android app needs
none of this: CORS is a browser rule.

### How long the app itself will wait

Nothing in the app sets a timeout: `apiFetch` uses `fetch` with none, and the
upload's `XMLHttpRequest` leaves `timeout` at its default of 0, which means
never. So the wait is whatever the platform's own socket timeout allows —
effectively unbounded on Android, which is what this is built for first. iOS
defaults to 60 seconds per request, so a long bill will need
`request.timeout` and an `ontimeout` handler before there is an iOS build. As
it stands a platform timeout would arrive as `onerror`, which the app shows
as a network error — the right message, at least.

## Shipping a change

Four things ship separately, and only two of them are "deploys". The order
below is the order to do them in when a change touches more than one.

### 1. The database

Schema lives in `api/tables.py`; the history of changes to it lives in
`api/migrations/versions/`. Cloud Run never touches either — its only command
is `uvicorn`, and a web server has no business altering a schema. Four
instances booting at once would each try.

So this always runs from your machine, and always **before** the API code
that needs it:

```sh
cd api
uv run alembic revision --autogenerate -m "what changed"
# read the generated file. Autogenerate guesses, and a rename reads to it as
# a drop and an add, which would take the column's data with it.
uv run alembic upgrade head
uv run python scripts/db_check.py
```

A **new table** needs two more things in that generated migration, or it is
served to anyone holding the project's publishable key:

```python
op.execute('ALTER TABLE "your_table" ENABLE ROW LEVEL SECURITY')
```

and its name added to a `TABLES` tuple in the same file.
`tests/test_db_connection.py` fails until both are done, which is the point.

**Deploy first, migrate first — but not both.** A migration that only adds
things (a nullable column, a new table) is safe to apply before the code
ships, and that is the order to prefer: the old code ignores what it doesn't
know about. A migration that removes or renames something is not, because the
running API still expects it; add the new shape, ship the code, then remove
the old shape in a second migration.

**Rolling back:** `uv run alembic downgrade -1`. Check the migration's
`downgrade()` first — it is generated too, and a dropped column's data is
gone either way.

### 2. The FastAPI service

```sh
# From the repository root. Or, with the GitHub trigger set up, just push.
gcloud run deploy billcheck-api --source . --region asia-south1
```

The flags from step 3 stick to the service; repeat only one you are changing.
Settings alone, without a rebuild, are `gcloud run services update
billcheck-api --region ... --timeout 900` or the console's *Edit & deploy new
revision*.

**Rolling back** is the one genuinely easy rollback here. Every deploy makes a
revision, and the old one is still there: *Cloud Run → the service →
Revisions → Manage traffic*, and send 100% back. Nothing rebuilds, and it
takes seconds. It does not roll back the database.

**Watching it:**

```sh
gcloud run services logs read billcheck-api --region asia-south1 --limit 50
```

A container that starts and exits immediately is nearly always `settings.py`
refusing its configuration, and it names the setting.

### 3. The app

Not deployed by any of the above, and **not currently set up to ship at all**:
there is no `eas.json`, and `app.json` has no `updates` block. Today the only
way to run it is a development build on a machine with the Android toolchain:

```sh
cd app
EXPO_PUBLIC_API_URL=https://... npx expo run:android
```

To put it on someone else's phone, Expo Application Services has to be
configured first — roughly `npm i -g eas-cli`, `eas login`, `eas build:configure`,
then `eas build -p android --profile preview` for a shareable build or
`--profile production` for a Play Store AAB. That is a piece of work in its
own right and has not been started.

Two things to know when it is:

- **`EXPO_PUBLIC_API_URL` is baked into the bundle at build time.** Pointing
  the app at a different API means a new build, or an over-the-air update once
  `expo-updates` is configured.
- **An over-the-air update only carries JavaScript.** Changed copy in
  `app/src/i18n/locales/`, a changed screen, a changed flag sentence: all
  shippable that way. A new native dependency is not.

### 4. The things that are neither

| What changed | What to do | Notes |
| --- | --- | --- |
| `data/samples/reference-prices.json` — including replacing the illustrative lists with the real NPPA and CGHS rates | Deploy the API | Baked into the image. No migration, no app build. |
| `api/analysis_prompt.py`, `api/audit.py`, `api/review.py` — what gets flagged and why | Deploy the API | Flags are computed server-side; the app only renders them. |
| `app/src/i18n/locales/*.json`, `app/src/data/flag-copy.ts` — the words a family reads | Ship the app | The API sends numbers and a reference, never a sentence. |
| The Supabase password, or the Anthropic key | New secret **version**, then deploy the API | The service reads `:latest` at startup, so a new version does nothing until it restarts. |
| `SECRET_KEY` | New version, then deploy | It signs the OTP code hashes only. Rotating it invalidates codes already sent — a five-minute window — and leaves signed-in sessions alone, since those are plain hashes of the token. |
| `CORS_ORIGINS`, `BILL_UPLOADS_PER_DAY`, `OCR_MODEL`, `OCR_EFFORT` | `gcloud run services update --update-env-vars ...` | Settings, not code. No rebuild. **`--update-env-vars`, not `--set-env-vars`:** the latter replaces the whole set, so it would drop `ENVIRONMENT` and the rest and the service would come back up configured as production. A value containing commas, which `CORS_ORIGINS` does, is easier set in the console than escaped for gcloud. |
| Going to real SMS | `OTP_DELIVERY=msg91` plus the MSG91 secrets, then deploy | Needs the DLT template first. See below. |
| The custom domain | Once, per step 4 | Nothing to repeat. |
| Supabase itself | Nothing | Managed. A free project does pause after a week idle and needs restoring from the dashboard. |

## Going to actual production

`ENVIRONMENT=production` makes `api/settings.py` refuse to start unless all of
these hold, and each one is deliberate:

| Setting | What production needs | Blocked on |
| --- | --- | --- |
| `SECRET_KEY` | 32+ random characters | nothing; the secret above is already one |
| `OTP_DELIVERY` | `msg91` | a DLT-approved template, one to two weeks |
| `OCR_PROVIDER` | `claude` | nothing |
| `REVIEW_KEEP_ALL` | `false` | nothing |

Four more things to settle before real families use this:

- **The app has no way to reach a phone.** No `eas.json`, no `expo-updates`:
  today it runs only as a development build on a machine with the Android
  toolchain. Everything else here is moot until that is set up.
- **Put a load balancer in front** (step 4), which is the supported path, the
  only one available in Mumbai, and the only one that can refuse TLS 1.0 and
  1.1.
- **The price lists are illustrative.** `data/samples/reference-prices.json`
  is not the real NPPA and CGHS data, and it ships inside the image. Replace
  it before any flag is shown to anyone.
- **`/docs` is public.** FastAPI serves the whole schema at `/docs` and
  `/openapi.json`. Harmless while this is ours to look at; worth turning off
  (`FastAPI(docs_url=None, openapi_url=None)`) once it isn't.
