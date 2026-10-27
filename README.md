# Sustain-X-Ray

A runnable campus sustainability MVP: React + TypeScript + Vite, Tailwind, Radix accessible dialogs, Recharts, FastAPI, Supabase Authentication and a Supabase PostgreSQL repository. Explicit SQLite local mode lets you evaluate without credentials. The initial dataset contains three source-backed university NPCL bills, **no fabricated water data or verified savings**.

## Run locally

Requires Node 22 and Python 3.11+ (tested here with Python 3.13).

```bash
# From the repository root
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.lock.txt
npm ci --prefix frontend
APP_MODE=local PYTHONPATH=backend python -m app.seed
APP_MODE=local PYTHONPATH=backend uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

In another terminal, from the repository root:

```bash
npm --prefix frontend run dev
```

Open http://127.0.0.1:5173. API documentation: http://127.0.0.1:8000/docs. Keep local mode bound to loopback: it deliberately bypasses login and grants a local admin role. Persistence is `data/local.sqlite` (ignored). The three historical bills can alternatively be loaded using Electricity → Load reviewed bills on an empty database. No source PDFs are publicly served.

## Checks

```bash
PYTHONPATH=backend python -m pytest backend/tests -q
npm --prefix frontend run test
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

Set `TEST_DATABASE_URL` to a disposable PostgreSQL database to also run the PostgreSQL adapter tests. Tests use isolated temporary SQLite databases and do not alter the working dataset.

## Working features

All nine pages connect to the API: overview, electricity entry/CSV/period comparisons/costs/demand; six-channel water entry/CSV/cumulative normalization/aligned RO balance; explainable configurable alerts; ticket assignment/status/findings/audit; evidence-backed estimated/verified/inconclusive outcomes; configurable score and hypothetical 2/5/10% scenarios; filtered reports and protected CSV exports; admin user roles, buildings/meters and rule/tariff settings. Import failures are atomic. CSV templates and opt-in synthetic examples are in `templates/` and served by the frontend.

Historical bills use original reading dates. **August correction:** active energy is 3,101,811.40 kWh; the blueprint's 3,135,321.59 is kVAh. Bill energy rate is INR/kVAh, distinct from effective total cost/kWh. Original sources and limitations: `docs/SOURCE_REVIEW.md`.

## Requires external configuration or validation

Supabase project, first admin profile, database credentials and Vercel/backend hosting; hardware commissioning and source-specific adapters; RO unit/interval/channel confirmation; separate Block 1/3 consumption evidence; contextual baselines and cost assumptions. No real-time data, cloud deployment or actual savings are claimed. No automated PDF OCR importer: supplied electricity figures were reviewed against originals; ongoing imports use validated CSV/manual entry.

See `docs/SUPABASE_AND_DEPLOYMENT.md`, `docs/SCHEMA.md`, `docs/HARDWARE.md`, `docs/IMPLEMENTATION_PLAN.md` and `docs/VALIDATION.md` for exact configuration, calculation rules and tested limits. `.env.example` files contain placeholders only; export backend variables or use your hosting environment (the backend does not automatically load `.env`).

## Structure

- `frontend/`: application, styles, Supabase Auth client, templates, frontend-only Vercel configuration.
- `api/index.py`, `vercel.json`, `requirements.txt`: single-project Vercel deployment (static frontend + Python API).
- `backend/app/`: models, analytics, repository adapters and PostgreSQL schema (`schema.sql`), API, authorization, hardware contract, seed utility.
- `backend/tests/`: calculation, validation, workflow, import and authorization tests.
- `data/`: source-backed bill JSON and source hashes; local database ignored.
- `docs/`: evidence review, schema, deployment, hardware, validation.

## MVP boundaries

Single campus, small data volumes; dashboard reads whole collections. Alerts calculate on dashboard load rather than scheduled notifications. Verification is evidence-backed operator review, not independent certification or weather-normalized modelling. Financial savings remain estimates, without unverified demand effects. Simultaneous overlapping imports and concurrent ticket updates require transaction/version hardening before multi-operator production use. See deployment notes. Sustainability snapshots are a reserved collection; historical score scheduling is not implemented.

## Live simulator

Open **Live simulator** to start/pause a synthetic electricity + RO + Blocks 1–3 stream. Switch between normal, electricity spike, RO imbalance and sensor dropout scenarios. Update interval, baseline load, RO flow and random seed are configurable; live charts refresh automatically. Demo CSV export is available. No real meters or credentials are needed in local mode. The stream is isolated from campus records and verified savings; use one backend worker. See `docs/SIMULATOR.md` for calculations, API and lifecycle.
