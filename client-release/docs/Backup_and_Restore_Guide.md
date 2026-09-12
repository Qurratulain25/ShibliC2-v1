# Backup and Restore Guide

## Where data lives

Windows: `C:\ProgramData\ShibliC2\`  
Ubuntu: `/var/lib/shiblic2/`

The encrypted database is under `data/`. Recordings, snapshots, logs, and backups are sibling folders.

## Automatic backups

A backup is written only when:

1. A real schema or database migration is required
2. An upgrade must modify the database
3. An administrator requests a backup

SHIBLI does **not** back up on every start, login, or settings save.

At most **5** automatic backups are retained in `backups/`.

## Before an upgrade

Copy the entire persistent folder to safe storage:

- Windows: copy `C:\ProgramData\ShibliC2`
- Ubuntu: copy `/var/lib/shiblic2`

Keep that copy until the site has confirmed the upgrade.

## Restore

1. Close SHIBLI C2.
2. Replace the persistent folder (or only `data/` if you are restoring the database alone) from the copy.
3. Start SHIBLI C2.

Do not mix a database from one site with another site’s `.env`. The encryption key and the database belong together.
