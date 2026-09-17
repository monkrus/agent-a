# Deploying Agent-A Readiness Scanner

## Platform recommendation: Railway

Railway is the best fit for this app:
- Nixpacks auto-detects Python + `requirements.txt` (zero Dockerfile)
- Persistent disk available ($0.25/GB/mo) for `.scans/` JSON store
- Env var UI for secrets (ANTHROPIC_API_KEY, STRIPE keys, etc.)
- Free trial tier, then usage-based ($5/mo hobby plan covers this)
- Custom domains + automatic HTTPS
- One-click deploys from GitHub

Alternatives considered:
- **Render**: works, but free tier sleeps after 15 min (scan timeouts)
- **Fly.io**: requires Dockerfile + fly.toml, volume setup more manual
- **Vercel/Netlify**: not suited for long-running Python + Pillow

## Prerequisites

1. A Railway account (https://railway.com — sign in with GitHub)
2. The `monkrus/agent-a` repo connected to Railway
3. These env vars set in Railway dashboard:

| Variable | Required | Notes |
|----------|----------|-------|
| `ANTHROPIC_API_KEY` | Yes | For real Claude extraction |
| `SHOPPER` | Yes | Set to `anthropic` for production |
| `STRIPE_SECRET_KEY` | For paid reports | Stripe dashboard |
| `STRIPE_PRICE_ID` | For paid reports | Stripe dashboard |
| `FLASK_SECRET_KEY` | Yes | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DEV_MODE` | No | Set `true` only for demo/testing |
| `PORT` | Auto | Railway sets this automatically |

## Files already prepared

- `Procfile` — gunicorn start command
- `railway.json` — Railway-specific build + deploy config
- `requirements.txt` — all Python dependencies

## Deployment steps (you run these)

### 1. Create the Railway project

```bash
# Install Railway CLI (if not already)
npm install -g @railway/cli

# Login
railway login

# Link to your repo
cd agent-a
railway init
# Or: create project in Railway dashboard, connect GitHub repo
```

### 2. Add persistent storage for scans

Scans are stored as JSON files in `readiness/.scans/`. By default this
is ephemeral (lost on redeploy). To persist:

**Option A — Railway Volume (recommended):**
```
# In Railway dashboard: Service > Settings > Volumes
# Mount path: /app/readiness/.scans
# Size: 1 GB is plenty
```

**Option B — No volume (acceptable for now):**
Scans regenerate on demand. Existing permalinks break on redeploy,
but new scans work immediately. Fine for launch; add volume later.

### 3. Set environment variables

```bash
# In Railway dashboard: Service > Variables
# Or via CLI:
railway variables set ANTHROPIC_API_KEY=sk-ant-...
railway variables set SHOPPER=anthropic
railway variables set FLASK_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
# Add Stripe keys when ready
```

### 4. Deploy

```bash
# Push to main triggers auto-deploy if GitHub is connected
git push origin main

# Or manual deploy:
railway up
```

### 5. Custom domain (optional)

```
# Railway dashboard: Service > Settings > Domains
# Add your custom domain, point DNS CNAME to the provided target
```

### 6. Verify

```
# Railway gives you a URL like: agent-a-production.up.railway.app
curl https://YOUR-DOMAIN/
curl https://YOUR-DOMAIN/r/SOME_SCAN_ID
```

## Estimated setup effort

- Railway account + project creation: 5 minutes
- Env vars: 2 minutes
- First deploy (auto from GitHub push): 2-3 minutes build
- Volume for persistence: 2 minutes in dashboard
- Custom domain + DNS: 5 minutes + propagation

**Total: ~15 minutes hands-on.**

## Private fix recipes

Full fix recipes (`_fixes_private.py`) live in the `agent-a-private` repo,
not in the public scanner. To make them available at deploy time:

**Option A — FIXES_MODULE env var (recommended):**

1. In `agent-a-private/`, create a pip-installable package containing the
   private recipes module.
2. Add a Railway build command that installs it:
   ```
   pip install -r requirements.txt && pip install git+https://<PAT>@github.com/monkrus/agent-a-private.git
   ```
3. Set `FIXES_MODULE=agent_a_private.fixes` (or whatever the module path is)
   in Railway env vars.

**Option B — Copy the file at build time:**

1. Add the file to a Railway volume or build step:
   ```
   cp /mnt/private/_fixes_private.py readiness/_fixes_private.py
   ```
2. `fixes.py` auto-discovers the co-located file — no env var needed.

**Option C — Git submodule (not recommended):**
Submodules add complexity to deploys. Prefer Option A.

## Production notes

- gunicorn runs with `--workers 2 --threads 4 --worker-class gthread`.
  This prevents a single slow scan from blocking all other requests.
  Railway hobby gives 1 vCPU — 2 workers × 4 threads handles concurrent
  scans comfortably. Each worker forks the app, so:
  - **Rate limits and scan counts** are sqlite-backed (cross-worker safe).
  - **Fetch cache** (`_fetch_cache`) is per-process — acceptable, each worker
    builds its own short-lived cache.
  - **`FLASK_SECRET_KEY`** must be set in production — without it, each
    worker generates its own random key and sessions break across workers.
  - Playwright browser instances are per-thread — budget ~150 MB per
    concurrent browser check. With 2 workers × 4 threads, worst case is
    8 concurrent browser instances (~1.2 GB). Tune `--threads` down if
    memory-constrained.
- Pillow works out of the box with Nixpacks (system libs included).
- No database migration needed — scan store is flat JSON files.
- The app binds to `0.0.0.0:$PORT` (Railway sets PORT automatically).
