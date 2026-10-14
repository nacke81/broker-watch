-- Broker Watch tables, living in the People CRM Supabase project (same sign-in, $0 extra; owner's call 2026-10-14).
-- Every row is owned by one login; row-level security is the whole privacy story (same pattern as public.people).
-- The weekly job writes with the secret key from this PC and stamps owner explicitly; the app never sends owner.
-- Applied with the Management API query endpoint (db/apply.py), not `supabase db push`: People CRM owns that history.

create table if not exists public.bw_profile (            -- what the weekly check searches for (My details)
  owner       uuid primary key default auth.uid() references auth.users(id) on delete cascade,
  names       text[] not null default '{}',
  addresses   text[] not null default '{}',
  city_state  text not null default '',
  phone       text not null default '',
  birth_year  int check (birth_year between 1900 and 2020),
  updated_at  timestamptz not null default now()
);

create table if not exists public.bw_runs (               -- one row per weekly run, written by the job
  id          uuid primary key default gen_random_uuid(),
  owner       uuid not null default auth.uid() references auth.users(id) on delete cascade,
  started_at  timestamptz not null default now(),
  finished_at timestamptz,
  status      text not null default 'running' check (status in ('running', 'ok', 'failed')),
  found       int not null default 0,
  not_found   int not null default 0,
  couldnt     int not null default 0,
  gone        int not null default 0,
  captchas    int not null default 0,
  error       text
);

create table if not exists public.bw_checks (             -- one row per site per run
  id          uuid primary key default gen_random_uuid(),
  owner       uuid not null default auth.uid() references auth.users(id) on delete cascade,
  run_id      uuid not null references public.bw_runs(id) on delete cascade,
  site        text not null,
  checked_on  date not null,
  result      text not null check (result in ('found', 'not_found', 'couldnt_check', 'gone')),
  step        int check (step between 1 and 7),
  tried       int[] not null default '{}',
  evidence    text,                                      -- listing | card
  gated       boolean not null default false,
  url         text,                                      -- the page that decided it (private to the owner)
  captcha     boolean not null default false,
  unique (run_id, site)
);

create table if not exists public.bw_optouts (            -- the owner marks "I sent the opt-out"
  owner       uuid not null default auth.uid() references auth.users(id) on delete cascade,
  site        text not null,
  sent_on     date not null,
  primary key (owner, site)
);

do $$
declare t text;
begin
  foreach t in array array['bw_profile', 'bw_runs', 'bw_checks', 'bw_optouts'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('alter table public.%I force row level security', t);
    execute format('revoke all on public.%I from anon', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);
    execute format('drop policy if exists "own rows: read" on public.%I', t);
    execute format('drop policy if exists "own rows: add" on public.%I', t);
    execute format('drop policy if exists "own rows: change" on public.%I', t);
    execute format('drop policy if exists "own rows: delete" on public.%I', t);
    execute format('create policy "own rows: read" on public.%I for select to authenticated using (owner = auth.uid())', t);
    execute format('create policy "own rows: add" on public.%I for insert to authenticated with check (owner = auth.uid())', t);
    execute format('create policy "own rows: change" on public.%I for update to authenticated using (owner = auth.uid()) with check (owner = auth.uid())', t);
    execute format('create policy "own rows: delete" on public.%I for delete to authenticated using (owner = auth.uid())', t);
  end loop;
end $$;

create index if not exists bw_checks_owner_site on public.bw_checks(owner, site, checked_on);
create index if not exists bw_runs_owner on public.bw_runs(owner, started_at);
