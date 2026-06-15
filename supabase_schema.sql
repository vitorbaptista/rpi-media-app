-- Schema for the external play log (see rpimedia/playlog.py).
-- Run once in the Supabase SQL editor.
--
-- Two row sources share this table:
--   kind='command'  — what this codebase launched (carries media_id, source)
--   kind='observed' — what dumpsys reported, logged change-only (catches
--                     playback started directly on the device)
--
-- Derivable facts (how long a state lasted, started/stopped/changed
-- transitions) are intentionally NOT stored — compute them at query time
-- from ts deltas between consecutive rows.

create table if not exists public.play_log (
    id        bigint generated always as identity primary key,
    ts        timestamptz not null default now(),
    kind      text not null,   -- 'command' | 'observed'
    -- command rows: the launch method (netflix/youtube/.../video for local).
    -- observed rows: the foregrounded app, or null when idle/launcher.
    app       text,
    state     text,            -- observed only: playing | paused | idle
    media_id  text,            -- command only: 'netflix:82836255' (joins to config)
    source    text             -- command only: 'b6' / cron origin
);

create index if not exists play_log_ts_idx on public.play_log (ts desc);

-- The device authenticates with the anon key. Grant it INSERT (to append)
-- and SELECT (the observed path reads the last row back for change
-- detection), but NOT update/delete — so a leaked key can add noise at
-- worst, never rewrite or wipe the history.
alter table public.play_log enable row level security;

create policy play_log_anon_insert on public.play_log
    for insert to anon with check (true);

create policy play_log_anon_select on public.play_log
    for select to anon using (true);
