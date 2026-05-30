# Deploying Nightview

Production layout:

| Piece    | Where     | URL                                   |
|----------|-----------|---------------------------------------|
| Frontend | Vercel    | `https://nightview.aryanvalsa.me`     |
| Backend  | Fly.io    | `https://api.nightview.aryanvalsa.me` |
| Data     | baked into the Fly Docker image | — |
| Secrets  | Fly secret + Vercel project env | — |

Follow the steps in order. Each step has a "verify" line that should pass before moving on — most of the gotchas come from skipping verification.

## 0. Pre-deploy housekeeping

Rotate any Anthropic API key that's ever been pasted into chat / shared. Generate a fresh one at <https://console.anthropic.com/settings/keys>. This new key is what you'll set as a Fly secret in step 3.

Confirm nothing personal is committed:

```bash
git ls-files | grep -E 'AGENTS|BUILD_LOG|CONTEXT|SPEC|PORTFOLIO|Resume|\.env$'
# should return NOTHING
```

Confirm the data files the Fly image needs are NOT gitignored:

```bash
git check-ignore data/processed/trends.parquet data/raw/cities_seed.csv
# should print neither path
```

## 1. Push to GitHub

```bash
git init                                     # if not a repo yet
git add . && git commit -m "first commit"
gh repo create nightview --public --source=. --remote=origin --push
```

**Verify the push actually landed:**

```bash
git remote -v                                # should show origin
git log origin/main --oneline -1             # should show your commit
```

If `origin` is missing or `origin/main` doesn't resolve, the `--push` step failed silently. Fix manually:

```bash
git remote add origin https://github.com/<you>/nightview.git
git push -u origin main
```

Browse to `https://github.com/<you>/nightview` and confirm files appear. **This must be done before Vercel** — Vercel's directory picker silently shows only the repo root for ~minutes after a fresh push, and if the repo was empty when you first imported, it caches that empty view.

## 2. Backend → Fly.io (CLI)

```bash
brew install flyctl
fly auth login
```

From the repo root (where `fly.toml` and `Dockerfile` live):

```bash
fly launch --no-deploy --copy-config --name nightview-api --region iad --org personal --yes
```

`--yes` skips the interactive prompts about Postgres / Redis / Tigris. `--copy-config` keeps the existing `fly.toml`.

**Verify the app was created:**

```bash
fly apps list                                # nightview-api should appear
```

If the app didn't appear, the launch errored out — re-read its stderr. Common cause: the app name is already taken globally; pick a different `--name`.

## 3. Set the Anthropic secret

```bash
fly secrets set ANTHROPIC_API_KEY=<the-rotated-key>
```

The output says "staged for the first deployment" — that's expected.

## 4. Deploy the image

```bash
fly deploy --remote-only
```

`--remote-only` builds the image on Fly's builder rather than your laptop. ~2–3 minutes.

**Common failure: `COPY data/... not found`** — your `.dockerignore` is excluding files the Dockerfile copies. Whitelist them with `!` syntax:

```
data/raw/*
!data/raw/cities_seed.csv
data/processed/*
!data/processed/trends.parquet
```

Then re-run `fly deploy --remote-only`.

**Verify the deploy worked:**

```bash
curl https://nightview-api.fly.dev/api/health
# {"status":"ok","anthropic_key_configured":true,"data_source":{"real_data_loaded":true,...,"row_count":2894}}
```

If `anthropic_key_configured` is `false`, your secret didn't take — re-run step 3 and `fly deploy` again.

## 5. Attach the custom domain to Fly

```bash
fly certs add api.nightview.aryanvalsa.me
```

Fly prints the recommended DNS setup (CNAME → `nightview-api.fly.dev`, or A/AAAA records). Note this for step 7. You can check status with:

```bash
fly certs check api.nightview.aryanvalsa.me     # rerun until "Issued"
```

The cert can't fully validate until DNS is live (step 7), but adding the cert beforehand is fine — Fly retries automatically.

## 6. Frontend → Vercel (dashboard)

1. Go to <https://vercel.com/new> and click **Continue with GitHub** (first time only — connects the Vercel GitHub App).
2. In the repo list, click **Import** next to `nightview`. If the repo doesn't appear, it might not have access — at <https://github.com/settings/installations>, configure Vercel's repo access.
3. The form auto-detects. Override these:
   - **Application Preset**: if it shows "Services" (Vercel's experimental multi-service mode that wants to deploy the backend too), switch the dropdown to **Vite**.
   - **Project Name**: `nightview` (whatever you want; if a previous attempt stuck, you'll get an auto-suffix like `-fpz7` — delete the stub project at <https://vercel.com/coolkinggreats-projects> before retrying).
   - **Root Directory**: click **Edit**, pick `frontend` from the tree. If the tree only shows root with a "no entry" icon, your push from step 1 hasn't propagated yet — wait 30 seconds and re-import.
4. Expand **Environment Variables**, add:
   - Key: `VITE_BACKEND_URL`
   - Value: `https://api.nightview.aryanvalsa.me`
   - Environments: Production and Preview (default)
5. Click **Deploy**. Wait ~1 minute. The Deploy button greys out briefly then re-enables when done — watch the URL bar; success navigates you to the project overview.
6. Once Ready, go to **Settings → Domains**, click **Add Existing**, type `nightview.aryanvalsa.me`, Save.
7. The new domain shows **Invalid Configuration** with a CNAME target like `aa364e02cb42b0d2.vercel-dns-017.com.` — copy this for step 7.

## 7. DNS at Namecheap

Namecheap → **Domain List** → `aryanvalsa.me` → **Manage** → **Advanced DNS**. Add two CNAME records:

| Type  | Host             | Value                                                   | TTL  |
|-------|------------------|---------------------------------------------------------|------|
| CNAME | `nightview`      | *(CNAME target from Vercel step 6.7)*                   | Auto |
| CNAME | `api.nightview`  | `nightview-api.fly.dev`                                 | Auto |

Propagation usually takes 1–10 minutes. Verify:

```bash
dig +short nightview.aryanvalsa.me
dig +short api.nightview.aryanvalsa.me
```

Both should return CNAME targets (plus A records for the Vercel one once Vercel finishes provisioning).

## 8. Final verification

After DNS lands, both Vercel and Fly auto-provision Let's Encrypt certs in ~30–60s.

```bash
curl https://api.nightview.aryanvalsa.me/api/health    # JSON ok
fly certs check api.nightview.aryanvalsa.me            # Issued
curl -sI https://nightview.aryanvalsa.me | head -1     # 200 OK
```

Then load `https://nightview.aryanvalsa.me` in a browser. Globe should render, time scrubber and chat panel should appear, suggested prompts should respond.

In Vercel **Settings → Domains** the custom domain status should flip from "Invalid Configuration" to **Valid Configuration** within a couple of minutes.

## When you regenerate data

If `scripts/ingest_global.py` (or `ingest_gee.py`) regenerates `data/processed/trends.parquet`, commit the new parquet, push, then re-deploy Fly:

```bash
fly deploy --remote-only
```

Vercel auto-redeploys on push to `main`.

## When you change frontend env vars

After changing `VITE_BACKEND_URL` (or any `VITE_*`) in Vercel project settings, you need to **trigger a fresh build** — Vite bakes them into the bundle at build time, runtime changes don't propagate. Easiest: push an empty commit or click "Redeploy" on the latest deployment.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Vercel: "repository does not contain the requested branch or commit reference" | Local commit never made it to `origin/main` | `git remote -v`, `git push -u origin main` |
| Vercel directory picker shows only root with a "no entry" icon | Repo just pushed and Vercel cached the empty state, OR the GitHub App lacks repo access | Re-refresh `vercel.com/new`. If still empty, grant repo access at <https://github.com/settings/installations> |
| `fly deploy` fails on `COPY data/...` | `.dockerignore` excluded the file | Whitelist with `!path` syntax |
| Backend curl: `Could not resolve host: nightview-api.fly.dev` | The app doesn't exist (a previous `fly launch` failed silently) | `fly apps list` to confirm, re-run `fly launch ...` |
| `curl https://api...` fails but `dig` resolves | Cert still provisioning | Wait 30–60 s; `fly certs check` should say "Issued" |
| Chat replies are slow on the first message after idle | Fly machine cold-started from sleep | Normal — `auto_stop_machines = "stop"` in `fly.toml`. Set `min_machines_running = 1` to keep one warm (~$5/mo) |
| Frontend loads but chat 404s / blocked | `VITE_BACKEND_URL` missing or wrong, or CORS not allowing the prod origin | Check Vercel env var, check `fly secrets list` shows nothing for `ALLOWED_ORIGINS` (it's set in `fly.toml` `[env]`), redeploy Fly if you changed it |

## Costs

- **Fly:** `shared-cpu-1x` + 512 MB with `auto_stop = stop` and `min_machines_running = 0` idles at ~$0/mo. Cold starts add ~5 s to the first request after sleep. Without a payment method on file, Fly disables high availability automatically (only 1 machine instead of 2) — still works fine.
- **Anthropic:** `DAILY_USD_CAP=2.0` in `fly.toml` is the per-day spend ceiling enforced by `app/rate_limit.py`. Tune higher / lower as needed. **Important:** this cap is in your app code, not at Anthropic — if your key leaks, attackers can bypass it. Treat the key like any other prod credential.
- **Vercel:** Hobby tier is free; 100 GB/mo bandwidth (bundle is ~2 MB so this is comfortable).
