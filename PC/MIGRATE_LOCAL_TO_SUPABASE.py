"""Safe one-time migration: local BTS Manager SQLite -> Supabase.

Safety rules:
- creates a timestamped backup before doing anything
- validates all required local tables/columns
- signs in with Supabase Auth
- refuses to migrate if any target table already contains rows
- uploads in batches
- verifies row counts and deterministic content hashes after upload
- never deletes or modifies the local database
"""
import datetime as dt
import getpass
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from cloud_client import SupabaseClient

ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'BTS Manager'
DB = DATA_ROOT / 'bts_manager.db'
BACKUP_DIR = DATA_ROOT / 'migration_backups'
REPORT_DIR = DATA_ROOT / 'migration_reports'
TABLE_KEYS = {
    'stations': 'code', 'contracts': 'contract_id', 'equipment': 'equipment_id',
    'transmission': 'transmission_id', 'power': 'power_id', 'batteries': 'battery_id',
    'auxiliary': 'aux_id', 'maintenance': 'work_id', 'mll_events': 'id'
}
CLOUD_MANAGED = {'created_at', 'updated_at'}
BATCH = 200


def now_tag():
    return dt.datetime.now().strftime('%Y%m%d_%H%M%S')


def local_columns(con, table):
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()]


def local_rows(con, table):
    return [dict(r) for r in con.execute(f'SELECT * FROM "{table}"').fetchall()]


def canonical_rows(rows, columns, key):
    cols = [c for c in columns if c not in CLOUD_MANAGED]
    def norm(v):
        if isinstance(v, float) and v.is_integer():
            return int(v)
        return v
    normalized = []
    for row in rows:
        normalized.append({c: norm(row.get(c)) for c in cols})
    normalized.sort(key=lambda r: (str(r.get(key)), json.dumps(r, ensure_ascii=False, sort_keys=True, default=str)))
    return normalized


def digest(rows, columns, key):
    payload = json.dumps(canonical_rows(rows, columns, key), ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def check_required_schema(con):
    problems = []
    for table, key in TABLE_KEYS.items():
        cols = local_columns(con, table)
        if not cols:
            problems.append(f'Thiếu bảng local: {table}')
        if key not in cols:
            problems.append(f'Thiếu khóa {key} trong bảng {table}')
    if problems:
        raise RuntimeError('CSDL local không đúng cấu trúc BTS Manager hiện tại:\n- ' + '\n- '.join(problems))


def remote_rows(client, table, key):
    # Supabase REST defaults to a limited page size. Read in pages to verify large datasets.
    rows = []
    offset = 0
    while True:
        query = f'select=*&order={key}.asc&limit=1000&offset={offset}'
        page = client.select(table, query)
        rows.extend(page)
        if len(page) < 1000:
            return rows
        offset += 1000


def remote_count(client, table):
    return len(remote_rows(client, table, TABLE_KEYS[table]))


def write_report(report, tag):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f'migration_{tag}.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    return path


def main():
    print('=' * 72)
    print(' BTS Manager - SAFE LOCAL -> SUPABASE MIGRATION')
    print('=' * 72)
    print(f'Local DB: {DB}')
    if not DB.exists():
        raise SystemExit('Không tìm thấy bts_manager.db. Hãy chạy migration trên đúng máy đang có dữ liệu gốc.')

    tag = now_tag()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f'bts_manager_before_cloud_{tag}.db'
    shutil.copy2(DB, backup)
    print(f'Backup local: {backup}')

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        check_required_schema(con)
        local = {}
        for table, key in TABLE_KEYS.items():
            rows = local_rows(con, table)
            cols = local_columns(con, table)
            local[table] = {'rows': rows, 'columns': cols, 'key': key, 'count': len(rows), 'digest': digest(rows, cols, key)}
            print(f'LOCAL  {table:14s}: {len(rows):7d} rows  sha256={local[table]["digest"][:16]}...')
    finally:
        con.close()

    client = SupabaseClient(ROOT / 'supabase_config.json')
    email = input('\nSupabase email: ').strip()
    password = getpass.getpass('Supabase password: ')
    client.sign_in(email, password)
    ok, msg = client.test()
    if not ok:
        raise RuntimeError(msg)
    print('Cloud/Auth/RLS: OK')

    report = {'started_at': dt.datetime.now().isoformat(), 'database': str(DB), 'backup': str(backup), 'tables': {}}

    # Critical safety gate: migration is a clean initial load. Do not silently merge unknown Cloud data.
    print('\nChecking Cloud target tables...')
    occupied = []
    for table, meta in local.items():
        count = remote_count(client, table)
        report['tables'][table] = {'local_count': meta['count'], 'local_digest': meta['digest'], 'cloud_before': count}
        print(f'CLOUD  {table:14s}: {count:7d} rows')
        if count:
            occupied.append(f'{table}={count}')
    if occupied:
        report['status'] = 'ABORTED_CLOUD_NOT_EMPTY'
        report_path = write_report(report, tag)
        raise RuntimeError(
            'Migration dừng an toàn vì Cloud đã có dữ liệu: ' + ', '.join(occupied) +
            f'. Không có dữ liệu nào bị xóa/ghi đè. Report: {report_path}'
        )

    print('\nUploading...')
    for table, meta in local.items():
        rows = meta['rows']
        if not rows:
            print(f'UPLOAD {table:14s}: 0 rows')
            continue
        cols = [c for c in meta['columns'] if c not in CLOUD_MANAGED]
        clean = [{c: r.get(c) for c in cols} for r in rows]
        for i in range(0, len(clean), BATCH):
            client.upsert(table, clean[i:i+BATCH], on_conflict=meta['key'])
            done = min(i + BATCH, len(clean))
            print(f'  {table}: {done}/{len(clean)}')
        print(f'UPLOAD {table:14s}: {len(rows)} rows OK')

    print('\nVerifying Cloud...')
    failed = []
    for table, meta in local.items():
        cloud_rows = remote_rows(client, table, meta['key'])
        cc = len(cloud_rows)
        cd = digest(cloud_rows, meta['columns'], meta['key'])
        report['tables'][table].update({'cloud_after': cc, 'cloud_digest': cd, 'match': cc == meta['count'] and cd == meta['digest']})
        status = 'OK' if report['tables'][table]['match'] else 'MISMATCH'
        print(f'CHECK  {table:14s}: local={meta["count"]} cloud={cc} digest={status}')
        if status != 'OK':
            failed.append(table)

    report['finished_at'] = dt.datetime.now().isoformat()
    report['status'] = 'SUCCESS' if not failed else 'VERIFICATION_FAILED'
    report_path = write_report(report, tag)
    print('\n' + '=' * 72)
    if failed:
        print('MIGRATION FAILED VERIFICATION:', ', '.join(failed))
        print(f'Report: {report_path}')
        raise SystemExit(2)
    print('MIGRATION SUCCESS - 100% row count + content digest match.')
    print(f'Backup : {backup}')
    print(f'Report : {report_path}')
    print('Local database was NOT modified or deleted.')
    print('Bạn có thể mở BTS Manager và bấm "↻ Đồng bộ" để kiểm tra sau migration.')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nMigration cancelled. Local database remains untouched.')
        sys.exit(130)
    except Exception as e:
        print(f'\nMIGRATION STOPPED SAFELY: {e}')
        sys.exit(1)
