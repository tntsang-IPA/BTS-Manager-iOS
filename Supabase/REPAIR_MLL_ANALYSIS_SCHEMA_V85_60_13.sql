-- BTS Manager V85.60.13
-- Run once in Supabase SQL Editor if the project was created from an older V85.60 schema.
alter table if exists public.mll_analysis_summary add column if not exists total_bsc double precision;
alter table if exists public.mll_analysis_summary add column if not exists total_layer double precision;
alter table if exists public.mll_analysis_summary add column if not exists bsc_avg double precision;
alter table if exists public.mll_analysis_summary add column if not exists bsc_target double precision;
alter table if exists public.mll_analysis_summary add column if not exists top_station_json jsonb not null default '[]'::jsonb;
alter table if exists public.mll_analysis_summary add column if not exists longest_json jsonb not null default '[]'::jsonb;
alter table if exists public.mll_analysis_summary add column if not exists insight text;
