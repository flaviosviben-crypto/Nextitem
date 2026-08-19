# Deploying RevenueOS

GitHub → Render → a permanent public URL, updating on every push.

The whole deployment is described by [`render.yaml`](../render.yaml) at the repo
root. Nothing lives only in a dashboard, so this can be recreated from scratch
by pointing Render at the repository again.

---

## Why this architecture

`frontend/lib/api.ts` calls `/api` on **its own origin**. A server-side proxy
(`frontend/app/api/[...path]/route.ts`) forwards that to the API. Three things
follow, and they shape everything else:

- The browser never talks to the API directly, so production needs **no CORS**
  and **no API URL in the client bundle**.
- The frontend is the public product; the API is a dependency of it.
- The only wire between them is one environment variable, `BACKEND_HOST`, which
  Render fills in automatically from the API service. There is no URL to paste
  and no way to leave production pointing at localhost.

**Why Render rather than Vercel or Railway.** Vercel cannot host FastAPI, so it
would still need a second platform underneath — two dashboards for no gain.
Railway has no repo-level blueprint covering two services in one monorepo, so
its setup would live in a dashboard instead of in Git. Render's Blueprint
creates both services, wires them together and enables auto-deploy from one
file, which is the least ongoing manual work for this specific repository.

**How the two services are wired, and the trap in it.** Render's
`fromService` with `property: host` returns the service's **slug** — a name like
`revenueos-api-6bxb`, carrying the suffix Render adds when a name is already
taken. It is *not* a domain. Prefixing it with `https://` produces
`https://revenueos-api-6bxb`, which has no DNS record anywhere, and every
request fails to connect. That is how this deployment first broke.

The public address is that slug under `onrender.com` — the same relationship
the frontend shows, where slug `revenueos-web` is served at
`revenueos-web.onrender.com`. `lib/backend.ts` completes a dotless value
accordingly and leaves a real domain untouched, so `BACKEND_HOST` needs no
manual value. `frontend/scripts/resolve-backend.test.mjs` pins this, with the
exact production value as its first case.

If you ever need something else — an internal address such as
`http://revenueos-api-6bxb:10000` once both services are on a paid plan and can
use Render's private network — set `BACKEND_ORIGIN` in the frontend service. It
is used verbatim and outranks everything.

**Why a route handler instead of a `next.config` rewrite.** Next.js compiles
rewrite destinations into `routes-manifest.json` at *build* time. A build that
runs without the platform's variable set bakes in `localhost`, and no amount of
restarting or reconfiguring will fix it — only a rebuild. The route handler
reads the environment per request, so the deployed site always points where the
platform says.

---

## Services

| | Frontend | API |
|---|---|---|
| Render name | `revenueos-web` | `revenueos-api` |
| Runtime | Node 20 | Python 3.11 |
| Root directory | `revenueos/frontend` | `revenueos/backend` |
| Build | `npm ci && npm run build` | `pip install -r requirements.txt` |
| Start | `npm start` | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check | `/` | `/api/health` |
| Public? | Yes — this is the URL you share | Yes on the free plan, but nothing needs to call it directly |

Both bind to the `$PORT` Render assigns. A hardcoded port would make the health
check fail and the deploy roll back.

---

## First-time setup

1. Sign in at <https://dashboard.render.com> with GitHub.
2. **New → Blueprint**, pick this repository, branch
   `claude/startup-code-review-phxm28`.
3. Render reads `render.yaml` and shows both services. It will ask for the two
   values marked `sync: false` — both are optional, leave them blank:
   - `ANTHROPIC_API_KEY` — only enables the conversational analyst.
   - `CORS_ORIGINS` — only needed if something calls the API from another origin.
4. **Apply**. First build takes roughly 5–10 minutes.

You get two permanent URLs, `https://revenueos-web.onrender.com` and
`https://revenueos-api.onrender.com` (Render appends a suffix if a name is
taken; `BACKEND_HOST` resolves to the real one either way).

---

## Verifying a deployment

Do not trust a `200`. This app has already been broken once by a stale server
answering every health check happily while serving the previous build. Check
what comes back, not whether something comes back:

```bash
./revenueos/scripts/verify-deployment.sh https://revenueos-web.onrender.com
```

If a check fails with a 502, the body names the origin that was tried and which
variable it came from, so a wiring fault is readable without opening the logs.

Eleven assertions on content: opportunities are per-customer and every one names
a customer, a reason and an action; the Action Center exposes the five workflow
states; Performance keeps modelled figures labelled as modelled; no `undefined`
counts. Every check is issued against the **frontend** origin, so passing also
proves the proxy reaches the API.

Allow ~60s on the first run after idling — see cold starts below.

---

## Environment variables to maintain

| Variable | Service | Set by | Needed? |
|---|---|---|---|
| `BACKEND_HOST` | frontend | Render, automatically | Never touch it — it is a slug, and the proxy completes it |
| `BACKEND_ORIGIN` | frontend | You, only if overriding | Optional — a full origin, used verbatim |
| `PORT` | both | Render, automatically | Never touch it |
| `NODE_VERSION` / `PYTHON_VERSION` | frontend / API | `render.yaml` | Only to change runtime version |
| `SEED_DEMO_ON_EMPTY` | API | `render.yaml`, `true` | Set to `false` once real data is imported |
| `ANTHROPIC_API_KEY` | API | You, in the dashboard | Optional — only the AI Analyst needs it |
| `CORS_ORIGINS` | API | You, in the dashboard | Optional — the frontend does not need it |

Secrets are never committed: `.env` and `.env.local` are gitignored, and
`render.yaml` marks both secret-ish variables `sync: false` so their values live
only in Render.

---

## What happens when you push

Push to `claude/startup-code-review-phxm28` → Render receives the webhook →
rebuilds both services → runs the health checks → swaps traffic to the new
version. A service whose health check fails keeps serving the previous version
rather than going down.

To deploy from `main` instead, merge the branch and change both `branch:` lines
in `render.yaml`.

---

## Limits worth knowing

- **Cold starts.** Free services sleep after 15 minutes idle. The first request
  wakes the frontend, whose first API call wakes the API — up to ~90s for that
  one request, then normal. $7/month per service removes this.
- **The workspace resets on deploy.** The free plan has no persistent disk, so
  the snapshot in `backend/storage/` is lost on every restart. That is why
  `SEED_DEMO_ON_EMPTY=true` is set: the public URL always has the demo boutique
  rather than an empty shell. **Uploaded data does not survive a redeploy.** For
  real pilot data, add a Render persistent disk mounted at
  `revenueos/backend/storage` (paid) or move to Postgres — see the README's
  production next steps.
- **There is no authentication.** Anyone with the URL sees everything, and the
  API is publicly reachable on its own hostname. Fine for the synthetic demo;
  **do not upload a real customer list to this deployment** until auth is added.
- **Free plan quota:** 750 instance-hours/month across the account. Two sleeping
  services stay within it comfortably.
