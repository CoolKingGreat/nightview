# Deploying Nightview

Production layout:

| Piece    | Where     | URL                                |
|----------|-----------|------------------------------------|
| Frontend | Vercel    | `https://nightview.aryanvalsa.me`     |
| Backend  | Fly.io    | `https://api.nightview.aryanvalsa.me` |
| Data     | baked into the Fly Docker image | — |
| Secrets  | Fly secrets + Vercel project env | — |

Follow the steps in order. Frontend depends on knowing the backend URL.

## 0. Before anything

Rotate any Anthropic API key that has ever been pasted into chat / shared. Generate a fresh one at <https://console.anthropic.com/settings/keys>. This new key is what you'll set as a Fly secret in step 2.

Confirm the repo is safe to publish:

```bash
git status
git ls-files | grep -E 'AGENTS|BUILD_LOG|CONTEXT|SPEC|PORTFOLIO|Resume|\.env$'
# ↑ should return NOTHING. If any of these appear, they slipped past .gitignore.
```

## 1. Push to GitHub

```bash
cd /Users/aryan/Documents/CodeProjects/geoproj
git init
git add .
git commit -m "Initial commit: Nightview"
gh repo create nightview --public --source=. --remote=origin --push
```

(If you don't use `gh`, create the repo on github.com first, then `git remote add origin … && git push -u origin main`.)

## 2. Backend → Fly.io

Install the CLI and sign in:

```bash
brew install flyctl
fly auth signup     # or `fly auth login` if you already have an account
```

Launch the app from the repo root (`fly.toml` is already there):

```bash
cd /Users/aryan/Documents/CodeProjects/geoproj
fly launch --no-deploy --copy-config --name nightview-api --region iad
```

When prompted, **say no** to creating Postgres / Redis / Tigris. Keep the existing `fly.toml`.

Set the secret(s):

```bash
fly secrets set ANTHROPIC_API_KEY=sk-ant-...your-fresh-key...
```

Deploy:

```bash
fly deploy
```

Smoke-test the default Fly URL it prints (e.g. `https://nightview-api.fly.dev/api/health`) — should return `{"status":"ok","anthropic_key_configured":true,"data_source":"..."}`.

Attach the custom domain:

```bash
fly certs add api.nightview.aryanvalsa.me
fly certs show api.nightview.aryanvalsa.me
```

The `certs show` output will give you the CNAME target to add at Namecheap (typically `nightview-api.fly.dev`). Note it for step 4.

## 3. Frontend → Vercel

Either via the dashboard (recommended for first deploy) or CLI.

**Dashboard:**
1. <https://vercel.com/new> → import the GitHub repo.
2. **Root directory:** `frontend`
3. Framework preset auto-detects as Vite. Leave build / output commands as defaults (`npm run build` / `dist`).
4. Add environment variables (Production):
   - `VITE_BACKEND_URL=https://api.nightview.aryanvalsa.me`
   - `VITE_CESIUM_ION_TOKEN=…` *(optional — only if you flipped `USE_BLACK_MARBLE_BASEMAP = true`)*
5. Deploy.
6. **Settings → Domains** → add `nightview.aryanvalsa.me`. Vercel will show you a CNAME target (typically `cname.vercel-dns.com`). Note it for step 4.

## 4. DNS at Namecheap

Namecheap dashboard → **Domain List** → `aryanvalsa.me` → **Manage** → **Advanced DNS**. Add two CNAME records:

| Type  | Host             | Value                          | TTL  |
|-------|------------------|--------------------------------|------|
| CNAME | `nightview`      | `cname.vercel-dns.com`         | Auto |
| CNAME | `api.nightview`  | *(value Fly's `certs show` printed)* | Auto |

Propagation usually takes 1–10 minutes. Verify:

```bash
dig +short nightview.aryanvalsa.me
dig +short api.nightview.aryanvalsa.me
```

Both should resolve. Then hit the URLs in a browser — Vercel and Fly will auto-provision SSL certs once DNS is live (give it a couple of minutes).

## 5. Post-deploy checks

- `https://api.nightview.aryanvalsa.me/api/health` → `{"status":"ok",...}`
- `https://nightview.aryanvalsa.me` loads the globe.
- Open devtools network tab, send a chat message, confirm `/api/chat` streams from the api subdomain (not from `fly.dev`).
- Watch Fly logs for the first real session: `fly logs`.

## When you regenerate the data

If `scripts/ingest_global.py` (or `ingest_gee.py`) regenerates `data/processed/trends.parquet`, commit the new parquet and `fly deploy` again — the Dockerfile bakes it into the image.

## Costs to watch

- **Fly:** the `shared-cpu-1x` + 512MB machine with `auto_stop = stop` and `min_machines_running = 0` should sit at ~$0/mo while idle. Cold starts add ~5 s to the first request after sleep. Flip `min_machines_running = 1` in `fly.toml` and redeploy if you want it always-warm (~$5/mo).
- **Anthropic:** `DAILY_USD_CAP=2.0` in `fly.toml` is the per-day spend ceiling enforced by `app/rate_limit.py`. Tune higher / lower as needed.
- **Vercel:** Hobby tier is free; bandwidth ceiling is 100 GB/mo (the bundle is ~2 MB so this is comfortable).
