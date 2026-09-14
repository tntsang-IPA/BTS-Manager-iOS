# BTS Manager V9.6.4 – Supabase Cloud

## 1. Supabase project
- Project URL is stored in `supabase_config.json`.
- The desktop app uses the Supabase **Publishable Key** only.
- Never put a database password, `service_role`, or `sb_secret_...` key in the desktop package.

## 2. Create the database schema
In Supabase Dashboard:
`SQL Editor` → `New query` → paste `SUPABASE_SCHEMA.sql` → `Run`.

The script only creates objects in `public`; it does not modify Supabase `auth.*` tables.

## 3. Create the first user
Go to:
`Authentication` → `Users` → `Add user`.

Create an email/password account for BTS Manager.

## 4. Start the desktop app
Use `INSTALL_BTS_MANAGER.bat` as Administrator.
Then open BTS Manager and press:
`☁ Đăng nhập`.

After login, the app can:
- Pull cloud data to the local cache.
- Push local records to Supabase.
- Automatically synchronize every 60 seconds while logged in.
- Keep the local SQLite database as a cache/offline safety copy.

## 5. First migration
Before using Cloud Sync for the first time, run `MIGRATE_LOCAL_TO_SUPABASE.py` on the computer containing the authoritative `bts_manager.db`, after the SQL schema and Auth user have been created.

The migration script does not delete the local database.

## Important
This first cloud release uses timestamp-based last-write-wins synchronization for normal BTS/asset tables. It is designed as a safe transition from local SQLite to shared PostgreSQL. Deletion synchronization and advanced conflict resolution are intentionally reserved for the next cloud phase.
