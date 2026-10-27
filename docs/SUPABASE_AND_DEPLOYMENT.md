# Supabase and deployment

## Supabase
1. Create a Supabase project. Keep `regions` in `vercel.json` on the Vercel region closest to it (this deployment: Supabase Seoul `ap-northeast-2`, Vercel `icn1`), because every dashboard load makes several database queries.
2. Copy the **Transaction pooler** connection string (Connect → Transaction pooler, port 6543) and replace `[YOUR-PASSWORD]` with the database password; URL-encode special characters such as `@`, `#` or `/`. Vercel cannot reach Supabase's IPv6-only direct connection, so use the pooler.
3. Copy the Project URL and the publishable (or legacy anon) key from Project Settings → API Keys. Both are public by design.
4. Authentication → Sign In / Providers: keep Email enabled. Optionally turn off "Allow new users to sign up"; the app has no sign-up form and new accounts get no access without a profile anyway.
5. The backend creates the tables from `backend/app/schema.sql` on startup (idempotent). You can also paste that file into the SQL editor. Row Level Security is enabled with no policies, so Supabase's public Data API cannot read or write the tables; the backend connects as the table owner and enforces roles itself.
6. Create the first administrator: Authentication → Users → Add user (tick "Auto Confirm User"). Once the tables exist, run in the SQL editor:

   ```sql
   insert into users (id, name, role, active, created_at, updated_at, created_by)
   select id::text, 'Admin', 'admin', true, now(), now(), 'bootstrap'
   from auth.users where email = 'admin@example.com';
   ```

   Later users are created the same way in Authentication, then given a role from Administration → Campus registry → users, using their Supabase user ID.
7. Import the historical bills with the admin Electricity page's "Load reviewed June–August bills" button, or `DATABASE_URL=... PYTHONPATH=backend python -m app.seed`.

Login uses Supabase email/password. The frontend sends the access token to FastAPI, which asks Supabase Auth to validate it on every request, then reads the active role from the `users` table. Viewer: read; operator: data/workflow writes; admin: settings, registry, user provisioning and source seed. Do not deploy local mode.

## Vercel (frontend + API in one project)
Import this repository into Vercel and leave Root Directory empty (repository root). The root `vercel.json` builds `frontend/` into static files and serves the FastAPI backend from `api/index.py` as a Python function at `/api/*` on the same domain, so `VITE_API_URL` must be left unset. Python dependencies come from the root `requirements.txt`. Set these environment variables, then redeploy (Vite values are compiled in at build time):

- `DATABASE_URL`: the transaction pooler connection string.
- `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`: used by the frontend, and by the backend to validate sign-ins.

`APP_MODE` defaults to `production`. The live simulator keeps its buffer in function memory, so it can reset on cold starts or when requests reach different instances.

### Frontend only
Alternatively set the Vercel project root to `frontend` (`frontend/vercel.json` supplies the SPA fallback), host the backend elsewhere (below), set `VITE_API_URL` to its HTTPS origin (without `/api`), and add the Vercel domain to the backend's `CORS_ORIGINS`. The Vite development proxy only applies locally.

## Python backend
Use Cloud Run, Render, Fly.io or another Python container service. Build from repo root: `docker build -f backend/Dockerfile -t sustain-x-ray-api .`. Supply `DATABASE_URL`, `SUPABASE_URL` and `SUPABASE_ANON_KEY`; route HTTPS to container port 8000. Health route `/api/health`; API docs `/docs`. Configure concurrency, rate limits and request-body limits at the edge. Use a secrets manager. PostgreSQL provides durable storage; the SQLite adapter is only for explicit local development (`APP_MODE=local` without `DATABASE_URL`). Set `TEST_DATABASE_URL` to a disposable database to run `backend/tests/test_postgres.py`; it drops the app tables.

## Operational limits
This is an MVP for one campus with low-volume imports (200 rows / 1 MB per CSV). Dashboard computations currently load whole tables; add paginated queries, summary snapshots, transactional overlap checks and scheduled analysis before high-volume telemetry. Imports are atomic and exact identities are unique, but interval overlap checking is an application preflight; simultaneous distinct-ID overlapping submissions need transactional range locking before concurrent production ingestion. Ticket history updates similarly require transaction/version checks for concurrent operators. Alerts are evaluated when the dashboard is read; there is no background email/SMS delivery. No external messages are sent.

Before production: check roles using separate accounts, verify Supabase backups/retention, assess campus data sharing, configure hosting/network controls, and commission real sources. Existing local SQLite data is not automatically migrated into PostgreSQL.
