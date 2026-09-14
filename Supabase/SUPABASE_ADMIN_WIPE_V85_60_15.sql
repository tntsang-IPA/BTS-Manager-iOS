-- BTS Manager V85.60.15
-- Admin-only destructive reset. Auth users are preserved.
-- Run once in Supabase SQL Editor, then reload PostgREST schema.

create or replace function public.admin_wipe_all_data()
returns jsonb
language plpgsql
security definer
set search_path = public, auth
as $$
declare
  caller_email text := lower(coalesce(auth.jwt()->>'email',''));
begin
  if caller_email <> 'tntsang@gmail.com' then
    raise exception 'Chỉ Admin hệ thống mới có thể xóa toàn bộ dữ liệu.';
  end if;

  truncate table
    public.notifications,
    public.mll_analysis_summary,
    public.mll_bsc_summary,
    public.mll_events,
    public.maintenance,
    public.auxiliary,
    public.batteries,
    public.power,
    public.transmission,
    public.equipment,
    public.contracts,
    public.stations,
    public.kpi_targets,
    public.audit_log
  restart identity cascade;

  return jsonb_build_object(
    'ok', true,
    'action', 'wipe_all_data',
    'auth_users_preserved', true,
    'wiped_at', now()
  );
end;
$$;

revoke all on function public.admin_wipe_all_data() from public;
grant execute on function public.admin_wipe_all_data() to authenticated;

NOTIFY pgrst, 'reload schema';
