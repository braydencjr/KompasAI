-- Kompas: profiles, learning routes and finished steps.
-- Run this once in Supabase: SQL Editor > New query > paste > Run.
-- Sign-in itself (email, Google, passwords) is handled by Supabase Auth, so there is no table for it.

-- ---------- tables ----------

-- One row per person. Created automatically at sign-up (see the trigger below).
create table public.profiles (
  id           uuid primary key references auth.users (id) on delete cascade,
  display_name text not null default '',
  avatar_url   text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- One row per job a person is learning toward. Only one is active at a time.
create table public.learning_routes (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references auth.users (id) on delete cascade,
  role_isco           text not null,                      -- the job's code in Kompas, e.g. '3313'
  pace_hours_per_week numeric not null default 5 check (pace_hours_per_week > 0 and pace_hours_per_week <= 60),
  is_active           boolean not null default true,
  started_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  unique (id, user_id)                                    -- lets a step prove it belongs to the same person
);

create unique index one_active_route_per_user on public.learning_routes (user_id) where is_active;

-- One row per finished step of a route.
create table public.route_step_progress (
  route_id     uuid not null,
  user_id      uuid not null,
  skill_id     text not null,                             -- the step's skill in Kompas, e.g. 'financial-modelling'
  completed_at timestamptz not null default now(),
  best_score   numeric check (best_score between 0 and 1),
  primary key (route_id, skill_id),
  -- a step can only be filed under that same person's own route
  foreign key (route_id, user_id) references public.learning_routes (id, user_id) on delete cascade
);

create index route_step_progress_user on public.route_step_progress (user_id);

-- ---------- privacy: everyone sees and changes only their own rows ----------

alter table public.profiles            enable row level security;
alter table public.learning_routes     enable row level security;
alter table public.route_step_progress enable row level security;

create policy "own profile" on public.profiles
  for all to authenticated
  using (id = (select auth.uid())) with check (id = (select auth.uid()));

create policy "own routes" on public.learning_routes
  for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy "own steps" on public.route_step_progress
  for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- ---------- a profile is created at sign-up, filled in from Google when there is a name and picture ----------

create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name, avatar_url)
  values (
    new.id,
    coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name', split_part(new.email, '@', 1)),
    coalesce(new.raw_user_meta_data ->> 'avatar_url', new.raw_user_meta_data ->> 'picture')
  );
  return new;
end;
$$;

-- only the sign-up trigger runs it, never a visitor
revoke execute on function public.handle_new_user() from public, anon, authenticated;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------- keep updated_at honest ----------

create function public.touch_updated_at() returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger profiles_touch         before update on public.profiles        for each row execute function public.touch_updated_at();
create trigger learning_routes_touch  before update on public.learning_routes for each row execute function public.touch_updated_at();
