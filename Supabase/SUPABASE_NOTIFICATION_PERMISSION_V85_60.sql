-- BTS Manager V85.60 - notification recipient isolation and employee self-create
-- Run once in Supabase SQL Editor BEFORE testing V85.58.

-- 1) Station manager email imported from sheet TRẠM BTS.
alter table public.stations add column if not exists email text;
create index if not exists idx_stations_email on public.stations (lower(trim(email)));

-- 2) Notification recipient identity.
alter table public.notifications add column if not exists target_email text;
alter table public.notifications add column if not exists created_by_email text;
create index if not exists idx_notifications_target_email on public.notifications (lower(trim(target_email)));
create index if not exists idx_notifications_creator_email on public.notifications (lower(trim(created_by_email)));

-- Backfill automatic notifications from the station manager email.
update public.notifications n
set target_email = lower(trim(s.email))
from public.stations s
where n.target_email is null
  and nullif(trim(n.station_code), '') is not null
  and upper(trim(n.station_code)) = upper(trim(s.code))
  and nullif(trim(s.email), '') is not null;

-- Legacy manual rows with a creator email remain private to that creator.
update public.notifications
set target_email = lower(trim(created_by_email))
where nullif(trim(target_email), '') is null
  and nullif(trim(created_by_email), '') is not null;

-- All authenticated users may create a private/manual notification for themselves.
-- target_email and created_by_email must both equal the logged-in email.
-- Admin remains unrestricted.

-- 3) Server-side enforcement. This is the important security boundary:
-- Mobile/PC filtering alone is NOT considered sufficient.
alter table public.notifications enable row level security;

-- Remove existing notification policies so an old permissive SELECT policy
-- cannot accidentally expose every notification after this migration.
do $$
declare
  p record;
begin
  for p in select policyname from pg_policies where schemaname='public' and tablename='notifications' loop
    execute format('drop policy if exists %I on public.notifications', p.policyname);
  end loop;
end $$;

create policy "bts_notifications_select_recipient_or_admin"
on public.notifications for select to authenticated
using (
  lower(coalesce(auth.jwt()->>'email','')) = 'tntsang@gmail.com'
  or lower(trim(coalesce(target_email,''))) = lower(coalesce(auth.jwt()->>'email',''))
  or lower(trim(coalesce(created_by_email,''))) = lower(coalesce(auth.jwt()->>'email',''))
  or (
    nullif(trim(coalesce(auto_alert_key,'')), '') is not null
    and exists (
      select 1 from public.stations s
      where upper(trim(coalesce(s.code,''))) = upper(trim(coalesce(public.notifications.station_code,'')))
        and lower(trim(coalesce(s.email,''))) = lower(coalesce(auth.jwt()->>'email',''))
    )
  )
);

create policy "bts_notifications_insert_recipient_or_admin"
on public.notifications for insert to authenticated
with check (
  lower(coalesce(auth.jwt()->>'email','')) = 'tntsang@gmail.com'
  or (
    lower(trim(coalesce(target_email,''))) = lower(coalesce(auth.jwt()->>'email',''))
    and lower(trim(coalesce(created_by_email,''))) = lower(coalesce(auth.jwt()->>'email',''))
  )
);

create policy "bts_notifications_update_recipient_or_admin"
on public.notifications for update to authenticated
using (
  lower(coalesce(auth.jwt()->>'email','')) = 'tntsang@gmail.com'
  or lower(trim(coalesce(target_email,''))) = lower(coalesce(auth.jwt()->>'email',''))
  or lower(trim(coalesce(created_by_email,''))) = lower(coalesce(auth.jwt()->>'email',''))
)
with check (
  lower(coalesce(auth.jwt()->>'email','')) = 'tntsang@gmail.com'
  or lower(trim(coalesce(target_email,''))) = lower(coalesce(auth.jwt()->>'email',''))
  or lower(trim(coalesce(created_by_email,''))) = lower(coalesce(auth.jwt()->>'email',''))
);

create policy "bts_notifications_delete_recipient_or_admin"
on public.notifications for delete to authenticated
using (
  lower(coalesce(auth.jwt()->>'email','')) = 'tntsang@gmail.com'
  or lower(trim(coalesce(target_email,''))) = lower(coalesce(auth.jwt()->>'email',''))
  or lower(trim(coalesce(created_by_email,''))) = lower(coalesce(auth.jwt()->>'email',''))
);

-- Stations remain readable by authenticated users under the existing BTS policy.
-- The email is used by PC when creating automatic notifications; it is not used
-- by Mobile to decide visibility. For automatic alerts, stations.email is the authoritative
-- recipient field.


-- V85.59: automatic alerts follow the current station manager email dynamically.
-- If an imported TRẠM BTS row changes Email, the next Mobile query immediately
-- follows the new assignment even before PC rewrites target_email.
-- Manual notifications remain private to created_by_email/target_email.

-- V85.60.10: Admin-only Auth user deletion.
-- Used by PC's "Xóa" action in Quản lý người dùng.
-- The function cannot delete the currently logged-in Admin account.
create or replace function public.admin_delete_user(target_user_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public, auth
as $$
declare
  caller_email text := lower(coalesce(auth.jwt()->>'email',''));
begin
  if caller_email <> 'tntsang@gmail.com' then
    raise exception 'Chỉ Admin hệ thống mới có thể xóa user.';
  end if;
  if target_user_id is null then
    raise exception 'Thiếu user_id cần xóa.';
  end if;
  if target_user_id = auth.uid() then
    raise exception 'Không thể tự xóa tài khoản Admin đang đăng nhập.';
  end if;

  delete from auth.users where id = target_user_id;
  if not found then
    raise exception 'Không tìm thấy user cần xóa.';
  end if;

  return jsonb_build_object('ok', true, 'user_id', target_user_id::text);
end;
$$;

revoke all on function public.admin_delete_user(uuid) from public;
grant execute on function public.admin_delete_user(uuid) to authenticated;
