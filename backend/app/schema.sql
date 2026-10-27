-- Sustain-X-Ray schema for PostgreSQL (Supabase). Idempotent: the backend applies it on
-- startup, and it can also be pasted into the Supabase SQL editor.
-- Row Level Security is enabled with no policies, so Supabase's public Data API cannot read
-- or write these tables. The backend connects as the table owner and enforces roles itself.

create table if not exists users (
  id text primary key,
  name text,
  role text check (role in ('viewer', 'operator', 'admin')),
  active boolean not null default true,
  created_at timestamptz,
  updated_at timestamptz,
  created_by text
);

create table if not exists buildings (
  id text primary key,
  name text not null,
  resource text not null,
  location text,
  source_ref text not null,
  connectivity text not null,
  notes text,
  created_at timestamptz,
  updated_at timestamptz,
  created_by text
);

create table if not exists meters (like buildings including all);

create table if not exists bills (
  id text primary key,
  account text not null,
  invoice text not null,
  meter_id text not null,
  period_start date not null,
  period_end date not null,
  kwh double precision not null,
  kvah double precision,
  total_inr double precision not null,
  demand_kva double precision,
  energy_rate double precision,
  energy_rate_unit text not null,
  demand_charges_inr double precision,
  source text not null check (source in ('manual', 'imported', 'actual', 'demo')),
  source_ref text not null,
  quality_flags jsonb not null default '[]',
  created_at timestamptz,
  updated_at timestamptz,
  created_by text
);

create table if not exists readings (
  id text primary key,
  meter_id text not null,
  category text not null check (category in ('ro_input', 'ro_product', 'ro_reject', 'block_1', 'block_2', 'block_3', 'electricity')),
  unit text not null check (unit in ('L', 'm3', 'kWh')),
  kind text not null check (kind in ('interval', 'cumulative')),
  value double precision not null,
  start timestamptz,
  "end" timestamptz not null,
  source text not null check (source in ('manual', 'imported', 'actual', 'demo')),
  source_ref text not null,
  quality_flags jsonb not null default '[]',
  created_at timestamptz,
  updated_at timestamptz,
  created_by text
);

create table if not exists alerts (
  id text primary key,
  status text not null,
  updated_at timestamptz,
  history jsonb not null default '[]'
);

create table if not exists maintenance_tickets (
  id text primary key,
  title text not null,
  alert_id text,
  owner text not null,
  priority text not null,
  status text not null,
  findings text,
  corrective_action text,
  post_start timestamptz,
  post_end timestamptz,
  history jsonb not null default '[]',
  created_at timestamptz,
  updated_at timestamptz,
  created_by text
);

create table if not exists action_verifications (
  id text primary key,
  ticket_id text not null,
  baseline_ids jsonb not null,
  post_ids jsonb not null,
  evidence_type text not null,
  requested_status text not null,
  context text not null,
  comparability_confirmed boolean not null,
  cost_rate double precision,
  cost_basis text,
  status text not null,
  unit text not null,
  reduction double precision not null,
  baseline_total double precision,
  post_total double precision,
  baseline_seconds double precision,
  post_seconds double precision,
  financial_estimate double precision,
  financial_status text,
  method text,
  reason text,
  evidence_snapshot jsonb,
  reviewed_by text,
  created_at timestamptz,
  updated_at timestamptz,
  created_by text
);

-- Reserved for scheduled score snapshots; nothing writes it yet.
create table if not exists sustainability_snapshots (
  id text primary key,
  data jsonb,
  created_at timestamptz
);

create table if not exists settings (
  id text primary key,
  increase_pct double precision not null,
  stale_days integer not null,
  water_balance_pct double precision not null,
  marginal_kwh_rate double precision,
  tariff_basis text,
  scenario_pcts jsonb not null,
  score_weights jsonb not null,
  created_at timestamptz,
  updated_at timestamptz,
  created_by text
);

alter table users enable row level security;
alter table buildings enable row level security;
alter table meters enable row level security;
alter table bills enable row level security;
alter table readings enable row level security;
alter table alerts enable row level security;
alter table maintenance_tickets enable row level security;
alter table action_verifications enable row level security;
alter table sustainability_snapshots enable row level security;
alter table settings enable row level security;
