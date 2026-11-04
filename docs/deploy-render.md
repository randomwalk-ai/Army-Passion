# Deploying on Render + Supabase

A simpler alternative to `docs/deploy.md` (one DigitalOcean server), for a demo
with mock data:

```
Browser ──► army-passion-web  (Render, Next.js)
        └─► army-passion-api  (Render, FastAPI) ──► Supabase (PostgreSQL + PostGIS)
```

- **Open to anyone with the link** (no password). Mock data only — never load
  real family data on this setup.
- **Free plans sleep** after 15 minutes without visitors; the first page after
  that takes about a minute to wake up.
- **Uploaded documents are not kept**: Render's free plan has no permanent
  disk, so they disappear when the API restarts.
- Every chatbot question uses your Gemini key, so anyone with the link can
  spend a little of it.

Deploys come from the `feature/dashboard-and-cea` branch on GitHub.

---

## 1. Supabase: the database (once)

1. Go to <https://supabase.com> → **New project**.
   - Name: `army-passion`
   - Database password: make a strong one and **save it** — you need it below.
   - Region: **South Asia (Mumbai)**.
2. When it is ready: **Database → Extensions** → search **postgis** → turn it on.
3. **Connect** (top of the page) → **Session pooler** → copy the link. It looks like
   `postgresql://postgres.abcd1234:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres`
   Replace `[YOUR-PASSWORD]` with your password. This is your **DATABASE_URL**.
   (Use the *Session pooler* one: Render cannot reach the "Direct connection".)

## 2. Fill Supabase with the mock data (once, from your computer)

In a terminal:

```powershell
cd C:\army-passion\backend
$env:DATABASE_URL = "paste the Supabase link here"
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m seed.generate --reset
Remove-Item Env:DATABASE_URL
```

The last line makes your terminal use your local database again.
Check: in Supabase → **Table Editor**, the `families` table has 150 rows.

## 3. Render: the API and the screens (once)

1. Go to <https://render.com>, sign in with GitHub, and allow access to
   `randomwalk-ai/Army-Passion`.
2. **New → Blueprint** → pick the repo → branch **feature/dashboard-and-cea**.
   Render reads `render.yaml` and shows two services. It asks for:
   - **DATABASE_URL**: the Supabase link from step 1.
   - **LLM_API_KEY**: your Gemini key (the same one as in your `.env`).
   - **CORS_ORIGINS**: type `https://army-passion-web.onrender.com` for now.
   - **NEXT_PUBLIC_API_URL**: type `https://army-passion-api.onrender.com` for now.
3. Click **Apply**. The first build takes 5–10 minutes.
4. When both are **Live**, open each service and check its real address at the
   top of the page. If Render added letters to a name (for example
   `army-passion-api-x1y2.onrender.com`):
   - **army-passion-api → Environment**: set `CORS_ORIGINS` to the web address.
   - **army-passion-web → Environment**: set `NEXT_PUBLIC_API_URL` to the API
     address, then **Manual Deploy → Deploy latest commit** (this one is baked
     in when the screens are built, so it needs a rebuild).

## 4. Check it

- `https://<api address>/health` shows `{"status":"ok", ...}`.
- `https://<api address>/health/db` shows `"families": 150`.
- `https://<web address>` shows the dashboard with the numbers.

If the dashboard says *"The numbers could not be loaded"*, the usual cause is
`CORS_ORIGINS` (on the API) or `NEXT_PUBLIC_API_URL` (on the web) not matching
the real addresses exactly — no slash at the end.

## Updating

Push to `feature/dashboard-and-cea`; Render rebuilds both services by itself.
Database changes (new migrations) run automatically when the API starts.
