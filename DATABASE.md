# SHIBLI C2 Database (SQLCipher)

Phase 1 stores users, settings, recordings metadata, cameras, and audit logs in **one encrypted SQLite file**. There is no plain-SQLite fallback.

## Location

| Mode | Path |
|------|------|
| Dev (source) | `<project>/data/shibli_c2.db` |
| Windows exe | `%LOCALAPPDATA%\ShibliC2\shibli_c2.db` (or project `data/` when that folder is writable) |
| Linux binary | `~/.local/share/ShibliC2/shibli_c2.db` |

Override: `SHIBLI_DATA_DIR`.

## Encryption (required)

| Requirement | Detail |
|-------------|--------|
| Package | `sqlcipher3` (see `requirements.txt`) |
| Key | `SHIBLI_DB_KEY` in `data/.env` |
| Startup | App refuses to start if sqlcipher3 or the key is missing |
| Verification | `scripts/verify-phase1.ps1` / `scripts/verify_phase1.py` or `GET /api/db/verify` (admin) |

```env
SHIBLI_DB_KEY=change-this-in-production
```

Plain SQLite **cannot** open the file (`file is not a database`). Encrypted files do not start with the `SQLite format 3` header.

## Schema (v2)

| Table | Purpose |
|-------|---------|
| `users` | Login, roles, permissions, full_name, active |
| `app_settings` | Theme, recording path, keyboard map, PTZ labels |
| `recordings` | Local recording metadata |
| `layouts` | Layout definitions |
| `audit_log` | Security audit trail |
| `local_cameras` | Cameras configured in C2 |
| `user_cameras` | Optional per-user camera assignment |
| `schema_meta` | Version, encryption flag |

## Migration

On startup the app:

1. Requires sqlcipher3 + `SHIBLI_DB_KEY`
2. Encrypts any legacy plain DB in place (backup first)
3. Migrates copies from the project root / AppData into `data/shibli_c2.db`
4. Backs up a stale AppData DB without using it as the active file

## Reset database

On a fresh database, SHIBLI C2 requires initial Administrator setup. No default Administrator password is shipped.

## Verify

```bash
python scripts/verify_phase1.py
```

Expected: `"encrypted": true`, `"verificationOk": true`, `"plainSqliteReadable": false`.
