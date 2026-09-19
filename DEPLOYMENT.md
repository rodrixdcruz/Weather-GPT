# Deployment Runbook

How MausamBagha AI ships from Git to the live site, how to deploy by hand, and how to undo a bad deploy. Everything here reflects the production setup as of 2026-09-18 and uses commands that were actually run against it.

**Repository:** `https://github.com/rodrixdcruz/mausambagha-ai` (branch `main`)
**Live site:** https://weathergpt-web.onrender.com (frontend) → https://weather-gpt-1-ze0n.onrender.com (API)

---

## 1 · The two services

| | Frontend | Backend |
|---|---|---|
| Render service | `weathergpt-web` (static site) | `Weather-GPT-1` (web service) |
| Service ID | `srv-dalqcde1egvs73fgq2ag` | `srv-dal8s13l550s73ckmiug` |
| Repo rootDir | `frontend` | `backend/` |
| Build | `npm run build` → `dist` | Dockerfile (Python 3.11) |
| Auto-deploy | on (`commit` trigger) | on (`commit` trigger) — re-armed 2026-09-18; see §6 |
| Public port | 443 (Render-managed TLS) | Render-internal; only the frontend talks to it |

There are deliberately **no other MausamBagha AI services** — the old broken `weather-gpt-0eru` service was deleted. If you see a third URL somewhere, it is stale documentation.

All commands below authenticate with `RENDER_API_KEY` (already set as a user environment variable on this machine):

```bash
AUTH="Authorization: Bearer $RENDER_API_KEY"
API_BASE="https://api.render.com/v1"
FRONTEND=srv-dalqcde1egvs73fgq2ag
BACKEND=srv-dal8s13l550s73ckmiug
```

## 2 · How pushes deploy

1. **Push to `main`** → GitHub Actions CI runs first (backend pytest + frontend lint/build). Green CI is the gate; a red build means the deploy will fail too, so fix forward or roll back after.
2. **Render's GitHub App receives the push** and evaluates its `autoDeployTrigger: commit` setting **per service, filtered by that service's `rootDir`**:
   - Commits touching `frontend/` → the static site rebuilds (~1–2 min).
   - Commits touching `backend/` → the API rebuilds (Docker layer cache makes it fast, ~1 min).
   - A commit touching **both** deploys both services.
3. Deploy states progress `build_in_progress → update_in_progress → live`. Superseded deploys show as `deactivated` in history — that's normal, not an error.

**What does NOT trigger a deploy** (all verified the hard way):

- Empty commits (no changed paths → nothing inside the rootDir filter).
- A commit whose changes are entirely outside a service's rootDir (e.g. README-only edits never redeploy the backend).
- Amended/force-pushed commits are unreliable — the original SHA may have already been evaluated. Prefer new commits.

**Env-var changes on the Render dashboard/API redeploy the affected service automatically** — no push needed (this is how password rotation shipped).

## 3 · Trigger a deploy manually

Use when autoDeploy is off/broken, or when you want to deploy a specific older commit.

**Deploy the latest commit on `main`:**

```bash
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  "$API_BASE/services/$BACKEND/deploys" -d '{"clearCache":"do_not_clear"}'
```

(`clearCache: "clear"` forces a clean Docker build if you suspect poisoned layers.)

**Deploy a specific commit (pin the SHA):**

```bash
curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" \
  "$API_BASE/services/$BACKEND/deploys" -d '{"commitId":"<full-or-short-sha>"}'
```

**Watch it finish:**

```bash
DEP=<deploy-id-from-the-response>
curl -s -H "$AUTH" "$API_BASE/services/$BACKEND/deploys/$DEP" | grep -o '"status":"[a-z_]*"'
```

**Via dashboard:** Render → service → **Manual Deploy** → "Deploy latest commit" / "Deploy specific commit". Same machinery.

The frontend service works identically — swap `$FRONTEND` for `$BACKEND`.

## 4 · Roll back a bad deploy

Rollback = redeploy the last known-good commit, pinned. The deploys list tells you what was live before the bad one (the most recent `deactivated` entry that was `live`).

**1. Find the last good commit:**

```bash
curl -s -H "$AUTH" "$API_BASE/services/$BACKEND/deploys?limit=10" \
  | node -e "let d='';process.stdin.on('data',c=>d+=c).on('end',()=>{JSON.parse(d).forEach(x=>{const dp=x.deploy; const c=typeof dp.commit==='string'?dp.commit:(dp.commit&&dp.commit.id)||'?'; console.log(dp.status.padEnd(12), c.slice(0,7), dp.createdAt)})})"
```

**2. Redeploy it (same command as §3 with that commitId).** Render rebuilds from that commit; layer caching makes it fast.

**3. Verify with the battery in §5.**

**4. Fix forward:** the rollback commit is now `live`, but `main` still contains the bad code — the next push of `backend/` files will deploy it again. Revert the bad commit (`git revert <sha>`) and push so Git and production agree.

**Dashboard path:** service → Deploys → find the good deploy → **Rollback to this deploy**.

**What rollback does NOT touch:** the database. Neon state (accounts, password hashes, sessions) is independent of deploys — startup only creates missing tables and seeds missing accounts, never resets existing ones. A bad deploy can't corrupt data, and rolling back can't un-rotate a password (that lives in Neon + the env vars).

## 5 · Post-deploy verification battery

Run after any deploy that matters (frontend deploys need only 1, 6, 7):

```bash
API=https://weather-gpt-1-ze0n.onrender.com
WEB=https://weathergpt-web.onrender.com
```

| # | Check | Command / expectation |
|---|---|---|
| 1 | Health | `curl -s $API/health` → `{"status":"ok","env":"production"}` |
| 2 | Old defaults dead | `curl -s -o /dev/null -w '%{http_code}' -X POST $API/api/v1/auth/login -H 'Content-Type: application/json' -d '{"username":"judge","password":"judge123"}'` → **401** (same for demo/demo123) |
| 3 | Real login works | Same with the rotated password from `.freebuff/credentials-rotated.txt` (never printed) → 200, `is_judge:true` |
| 4 | Weather live | `curl -s "$API/api/v1/weather/current?latitude=19.076&longitude=72.8777"` → `source` is a real provider (`met-norway`/`open-meteo`), never `mock_fixture` |
| 5 | Routing proxy | `curl -s -D - -o /dev/null "$API/api/v1/routing/route?from_lat=19.076&from_lon=72.8777&to_lat=19.0906&to_lon=72.8694&mode=driving"` → 200 + `Cache-Control: public, max-age=60` |
| 6 | Frontend + SPA | `curl -s -o /dev/null -w '%{http_code}' $WEB/` and `$WEB/login` → both 200 |
| 7 | Judge panel wired | Log in as judge in a browser → 🧑‍⚖️ Demo button present; scenarios flip the UI; 🌍 Live data restores |

## 6 · Known gotchas (read once, save an hour)

- **autoDeploy was flipped via API on 2026-09-18 but didn't fire until a manual deploy re-registered the service.** If pushes stop producing deploy rows again, do one Manual Deploy from the dashboard — that re-arms it. The next real `backend/` push after this runbook is the proof it stays armed.
- **`render.yaml` is partially stale.** Its `VITE_API_BASE_URL` names `weathergpt-api.onrender.com`, which does not exist; the deployed frontend bundle actually calls `weather-gpt-1-ze0n.onrender.com` (dashboard env wins over Blueprint values). If you ever re-sync the Blueprint, fix that value first or the frontend will point at a dead host.
- **Auth seeding gotcha:** `AUTH_*_PASSWORD` env vars only seed *new* account rows. If a row already exists (e.g. restored Neon dump), the stored hash wins — rotate by updating the row (see the 2026-09-18 rotation) or deleting the row and restarting.
- **Neon role password ≠ app passwords.** The `DATABASE_URL` credential is separate; if it's ever exposed, reset it in the Neon dashboard and update `DATABASE_URL` on Render (env change → auto redeploy).
- **Backend deploys pick up code only when `backend/` files change** — README/docs pushes intentionally don't redeploy it.
