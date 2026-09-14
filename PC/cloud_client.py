"""Minimal Supabase REST/Auth client for BTS Manager.
Uses only Python standard library so the desktop app does not need another runtime dependency.
"""
import json, time, socket, urllib.request, urllib.error, urllib.parse
from pathlib import Path

class SupabaseClient:
    def __init__(self, config_path):
        self.config_path = Path(config_path)
        self.config = json.loads(self.config_path.read_text(encoding='utf-8'))
        self.url = self.config['project_url'].rstrip('/')
        self.publishable_key = self.config['publishable_key']
        self.access_token = None
        self.refresh_token = None
        self.user = None
        self.permissions = []
        self.permissions = []

    def _request(self, method, path, body=None, token=None, extra_headers=None, _retry_on_refresh=True):
        headers = {
            'apikey': self.publishable_key,
            'Content-Type': 'application/json',
        }
        if token:
            headers['Authorization'] = f'Bearer {token}'
        if extra_headers:
            headers.update(extra_headers)
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(self.url + path, data=data, headers=headers, method=method)

        # Supabase REST may need more than 15s when the project is waking up or
        # when a large table is being read. The old 15s timeout caused false
        # "Lỗi đồng bộ tạm thời" messages. Use a 60s socket timeout and retry
        # only idempotent requests. INSERT/POST is deliberately not retried here
        # because a timed-out response may mean the server already accepted it.
        request_timeout = 60
        retryable = method.upper() in {'GET', 'HEAD', 'PATCH', 'PUT', 'DELETE'}
        attempts = 3 if retryable else 1
        for attempt in range(attempts):
            request_started = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=request_timeout) as r:
                    raw = r.read().decode('utf-8')
                    return r.status, (json.loads(raw) if raw else None)
            except (TimeoutError, socket.timeout, urllib.error.URLError) as e:
                elapsed = time.monotonic() - request_started
                # Do not change retry semantics here. This diagnostic only makes
                # the exact HTTP method/path/attempt visible to CloudSyncManager.
                print(f'[SUPABASE REQUEST] {method.upper()} {path} attempt={attempt+1}/{attempts} elapsed={elapsed:.3f}s error={type(e).__name__}: {e}')
                if attempt + 1 < attempts:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
            except urllib.error.HTTPError as e:
                raw = e.read().decode('utf-8', errors='replace')
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = {'error': raw}

                # Supabase/PostgREST returns HTTP 401 with code PGRST303 when
                # the access JWT has expired. Refresh once, then retry the
                # original request with the new access token.
                code = str(payload.get('code', '')) if isinstance(payload, dict) else ''
                message = str(payload.get('message', '')) if isinstance(payload, dict) else str(payload)
                jwt_expired = (e.code == 401 and (code == 'PGRST303' or 'JWT expired' in message))
                if jwt_expired and _retry_on_refresh and token and token == self.access_token and self.refresh_token:
                    if self._refresh_session():
                        return self._request(method, path, body, token=self.access_token,
                                             extra_headers=extra_headers, _retry_on_refresh=False)
                return e.code, payload

    def _refresh_session(self):
        """Refresh the Supabase Auth session using the current refresh token."""
        if not self.refresh_token:
            return False
        try:
            status, payload = self._request(
                'POST', '/auth/v1/token?grant_type=refresh_token',
                {'refresh_token': self.refresh_token}, token=None,
                _retry_on_refresh=False)
            if status >= 400 or not isinstance(payload, dict):
                return False
            access = payload.get('access_token')
            if not access:
                return False
            self.access_token = access
            # Supabase can rotate refresh tokens; use the new one when present.
            self.refresh_token = payload.get('refresh_token') or self.refresh_token
            self.user = payload.get('user') or self.user
            return True
        except Exception:
            return False

    def sign_in(self, email, password):
        status, payload = self._request('POST', '/auth/v1/token?grant_type=password',
                                        {'email': email, 'password': password})
        if status >= 400:
            raise RuntimeError(payload.get('msg') or payload.get('message') or payload.get('error_description') or str(payload))
        self.access_token = payload.get('access_token')
        self.refresh_token = payload.get('refresh_token')
        self.user = payload.get('user')
        user = self.user or {}
        meta = user.get('app_metadata') or {}
        self.permissions = list(meta.get('permissions') or [])
        if str(user.get('email','')).strip().lower() == 'tntsang@gmail.com':
            self.permissions = ['*']
        return self.user

    def test(self):
        if not self.access_token:
            return False, 'Chưa đăng nhập Supabase.'
        tables = ['stations','contracts','equipment','transmission','power','batteries','auxiliary','maintenance','mll_events','kpi_targets','mll_bsc_summary','mll_analysis_summary','notifications']
        missing = []
        denied = []
        other = []
        for table in tables:
            status, payload = self._request('GET', f'/rest/v1/{table}?select=*&limit=1', token=self.access_token)
            if status < 400:
                continue
            code = str(payload.get('code','')) if isinstance(payload, dict) else ''
            msg = str(payload.get('message','')) if isinstance(payload, dict) else str(payload)
            if code == 'PGRST205' or 'Could not find the table' in msg:
                missing.append(table)
            elif status in (401,403):
                denied.append(table)
            else:
                other.append(f'{table} ({status}): {payload}')
        if missing:
            return False, ('Cloud chưa có đủ bảng dữ liệu: ' + ', '.join(missing) +
                           '. Đây là lỗi thiếu bảng/schema cache, không phải lỗi mật khẩu. '
                           "Hãy chạy SUPABASE_SCHEMA_V79_1.sql trong Supabase SQL Editor, sau đó chạy: NOTIFY pgrst, 'reload schema';")
        if denied:
            return False, 'Tài khoản đăng nhập được nhưng RLS/API đang từ chối đọc: ' + ', '.join(denied) + '.'
        if other:
            return False, 'Cloud/API kiểm tra thất bại: ' + ' | '.join(other)
        return True, f'Cloud OK • Auth OK • đọc đủ {len(tables)}/{len(tables)} bảng.'

    def _admin_function(self, action, body=None):
        """Call the server-side admin function; never exposes service-role key."""
        if not self.access_token:
            raise RuntimeError('Chưa đăng nhập Supabase.')
        payload = {'action': action}
        if body:
            payload.update(body)
        status, data = self._request('POST', '/functions/v1/admin-user-management', payload, token=self.access_token)
        if status == 404:
            # Backward compatibility with v35/v36 deployment name.
            status, data = self._request('POST', '/functions/v1/admin-create-user', payload, token=self.access_token)
        if status >= 400:
            msg = data.get('error') if isinstance(data, dict) else None
            if status == 404:
                msg = ('Không tìm thấy Edge Function. Hãy chạy DEPLOY_EDGE_FUNCTIONS.bat trong gói BTS Manager v39, '
                       'hoặc vào Supabase → Edge Functions và deploy admin-user-management.')
            raise RuntimeError(msg or str(data))
        return data or {}

    def reset_all_data_admin(self):
        """Admin-only server-side wipe of all shared BTS Manager data.

        The database RPC performs the authorization check server-side and
        preserves Supabase Auth users.
        """
        if not self.access_token:
            raise RuntimeError('Chưa đăng nhập Supabase.')
        status, payload = self._request(
            'POST', '/rest/v1/rpc/admin_wipe_all_data', {}, token=self.access_token,
            extra_headers={'Prefer': 'return=representation'}
        )
        if status >= 400:
            raise RuntimeError(
                f'RPC admin_wipe_all_data thất bại: {payload}. '
                'Hãy chạy migration V85.60.15 trong Supabase SQL Editor rồi reload schema.'
            )
        return payload or {'ok': True}

    def create_user(self, email, password, permissions=None):
        return self._admin_function('create', {'email': email, 'password': password, 'permissions': list(permissions or [])})

    def list_users(self):
        return self._admin_function('list').get('users', [])

    def admin_reset_password(self, user_id, password):
        return self._admin_function('reset_password', {'user_id': user_id, 'password': password})

    def update_user_permissions(self, user_id, permissions):
        return self._admin_function('update_permissions', {'user_id': user_id, 'permissions': list(permissions or [])})

    def delete_user(self, user_id):
        """Delete an Auth user as Admin, with an RPC fallback for older Edge Functions."""
        if not self.access_token:
            raise RuntimeError('Chưa đăng nhập Supabase.')
        try:
            return self._admin_function('delete', {'user_id': user_id})
        except Exception as edge_error:
            status, payload = self._request(
                'POST', '/rest/v1/rpc/admin_delete_user',
                {'target_user_id': user_id}, token=self.access_token,
                extra_headers={'Prefer': 'return=representation'})
            if status >= 400:
                raise RuntimeError(f'Edge Function xóa user không hỗ trợ và RPC cũng thất bại: {payload}. ' +
                                   'Hãy chạy SUPABASE_NOTIFICATION_PERMISSION_V85_60.sql để tạo RPC admin_delete_user.') from edge_error
            return payload or {'ok': True}

    def change_my_password(self, password):
        if not self.access_token:
            raise RuntimeError('Chưa đăng nhập Supabase.')
        status, payload = self._request('PUT', '/auth/v1/user', {'password': password}, token=self.access_token)
        if status >= 400:
            raise RuntimeError(payload.get('message') or payload.get('msg') or payload.get('error_description') or str(payload))
        return payload or {}

    def sign_out(self):
        # Tokens are kept only in memory; discard them on logout.
        self.access_token = None
        self.refresh_token = None
        self.user = None

    def select(self, table, query='select=*'):
        status, payload = self._request('GET', f'/rest/v1/{table}?{query}', token=self.access_token)
        if status >= 400: raise RuntimeError(str(payload))
        return payload or []

    def upsert(self, table, rows, on_conflict=None, return_representation=False):
        path = f'/rest/v1/{table}'
        if on_conflict: path += '?on_conflict=' + urllib.parse.quote(on_conflict)
        prefer = 'resolution=merge-duplicates,return=representation' if return_representation else 'resolution=merge-duplicates,return=minimal'
        status, payload = self._request('POST', path, rows, token=self.access_token,
                                        extra_headers={'Prefer': prefer})
        if status >= 400:
            text = str(payload)
            if table == 'mll_bsc_summary' and ('mll_bsc_summary.id does not exist' in text or 'column mll_bsc_summary.id does not exist' in text):
                raise RuntimeError(
                    'Cloud schema mll_bsc_summary đang thiếu cột id (audit trigger đang tham chiếu id). ' +
                    'Cần chạy REPAIR_MLL_BSC_SCHEMA_V85_46.sql một lần trong Supabase SQL Editor rồi reload schema.'
                )
            raise RuntimeError(text)
        return payload or []

    def insert(self, table, row, return_representation=True):
        path = f'/rest/v1/{table}'
        prefer = 'return=representation' if return_representation else 'return=minimal'
        status, payload = self._request('POST', path, row, token=self.access_token,
                                        extra_headers={'Prefer': prefer})
        if status < 400:
            return payload or []

        # Self-heal an old notifications identity sequence without requiring
        # the user to open Supabase SQL Editor.  Some older databases have an
        # out-of-sync notifications.id sequence.  The first insert then fails
        # with a duplicate primary key even though the client omitted id.
        # Allocate a safe explicit id above the current Cloud maximum and retry.
        if table == 'notifications' and self._is_duplicate_notification_id(payload):
            last_error = payload
            for _ in range(3):
                try:
                    rows = self.select('notifications', 'select=id&order=id.desc&limit=1')
                    max_id = int(rows[0].get('id') or 0) if rows else 0
                    retry_row = dict(row)
                    retry_row['id'] = max_id + 1
                    status2, payload2 = self._request('POST', path, retry_row, token=self.access_token,
                                                      extra_headers={'Prefer': prefer})
                    if status2 < 400:
                        return payload2 or []
                    last_error = payload2
                    if not self._is_duplicate_notification_id(payload2):
                        break
                except Exception as e:
                    last_error = {'error': str(e)}
            raise RuntimeError(str(last_error))

        raise RuntimeError(str(payload))

    @staticmethod
    def _is_duplicate_notification_id(payload):
        text = str(payload).lower()
        return ('notifications.id' in text or 'notifications_pkey' in text) and ('unique' in text or 'duplicate' in text)

    def delete_all(self, table):
        # Used only for PC-authoritative derived result tables.
        # IMPORTANT: mll_analysis_summary has range_key as its primary key and
        # does not have an id column. The previous generic id filter caused the
        # PC MLL sync to fail after mll_bsc_summary was written, leaving Mobile
        # without the authoritative range result.
        filters = {
            'mll_bsc_summary': 'dept=not.is.null',
            'mll_analysis_summary': 'range_key=not.is.null',
        }
        if table not in filters:
            raise ValueError(f'Không cho phép replace toàn bảng: {table}')
        path = f'/rest/v1/{table}?{filters[table]}'
        status, payload = self._request('DELETE', path, token=self.access_token)
        if status >= 400:
            raise RuntimeError(str(payload))
        return payload or []

    def replace_rows(self, table, rows):
        self.delete_all(table)
        if not rows:
            return []

        # mll_bsc_summary uses the generated `id` primary key plus UNIQUE(dept, month_no).
        # Keep the V85.60.23 working contract: never invent/use summary_key.
        if table == 'mll_bsc_summary':
            clean_rows = []
            for i, row in enumerate(rows):
                if not isinstance(row, dict):
                    raise RuntimeError(f'mll_bsc_summary payload[{i}] không phải object.')
                for k in ('dept', 'month_no', 'value', 'avg_6m'):
                    if k not in row:
                        raise RuntimeError(f'mll_bsc_summary payload[{i}] thiếu cột {k}.')
                clean_rows.append({
                    'dept': row.get('dept') or '',
                    'month_no': int(row['month_no']),
                    'value': row.get('value'),
                    'avg_6m': row.get('avg_6m'),
                })
            path = f'/rest/v1/{table}'
            status, payload = self._request(
                'POST', path, clean_rows, token=self.access_token,
                extra_headers={'Prefer': 'return=representation'}
            )
            if status >= 400:
                raise RuntimeError(str(payload))
            return payload or []

        # mll_analysis_summary is keyed by range_key rather than id.  Newer
        # PC builds publish additional authoritative JSON/insight columns, but
        # older V85.60 Supabase projects may still have only the original base
        # schema. Retry once with exactly those base columns so the PC result is
        # still published and Mobile can render it (top/longest tables have a
        # Mobile raw-event compatibility fallback).
        if table == 'mll_analysis_summary':
            try:
                return self.upsert(table, rows, return_representation=True)
            except Exception as first_error:
                text = str(first_error).lower()
                schema_mismatch = ('column' in text and ('does not exist' in text or 'schema cache' in text)) or 'pgrst204' in text
                if not schema_mismatch:
                    raise
                base_cols = ('range_key','from_month','to_month','cases','total_downtime',
                             'avg_per_event','stations','top_reason','monthly_json',
                             'reason_json','service_json')
                fallback_rows = [{k: r.get(k) for k in base_cols} for r in rows]
                return self.upsert(table, fallback_rows, return_representation=True)

        return self.upsert(table, rows, return_representation=True)

    def update_by_id(self, table, row_id, row):
        path = f'/rest/v1/{table}?id=eq.{urllib.parse.quote(str(row_id), safe="")}'
        status, payload = self._request('PATCH', path, row, token=self.access_token,
                                        extra_headers={'Prefer': 'return=representation'})
        if status >= 400:
            raise RuntimeError(str(payload))
        return payload or []

    def delete_by_id(self, table, row_id):
        path = f'/rest/v1/{table}?id=eq.{urllib.parse.quote(str(row_id), safe="")}';
        status, payload = self._request('DELETE', path, token=self.access_token,
                                        extra_headers={'Prefer': 'return=minimal'})
        if status >= 400:
            raise RuntimeError(str(payload))
        return payload or []

    def update_if_unchanged(self, table, key, key_value, expected_updated_at, row):
        # Optimistic concurrency: only update if the server row still has the
        # timestamp we fetched. This prevents PC-A from silently overwriting
        # a newer edit made by PC-B between read and write.
        q = f'{urllib.parse.quote(str(key))}=eq.{urllib.parse.quote(str(key_value), safe="")}&updated_at=eq.{urllib.parse.quote(str(expected_updated_at), safe="")}'
        path = f'/rest/v1/{table}?{q}'
        status, payload = self._request('PATCH', path, row, token=self.access_token,
                                        extra_headers={'Prefer': 'return=representation'})
        if status >= 400:
            raise RuntimeError(str(payload))
        return payload or []
