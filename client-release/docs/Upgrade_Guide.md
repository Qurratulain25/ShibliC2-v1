# Upgrade Guide

Future versions follow this client flow:

1. Download the newer installer from Releases.
2. Close SHIBLI C2.
3. Run the new Windows wizard or Ubuntu package.
4. Application files are replaced.
5. Site data stays in `ProgramData\ShibliC2` or `/var/lib/shiblic2`.
6. If the new version needs a database change, SHIBLI migrates it and may write one backup.
7. Launch SHIBLI C2 and sign in with existing users.

You do not replace source code. You do not run pip or Git.

## What is preserved

- Users and roles
- Cameras, RTSP, and PTZ mappings
- LAN / IP classification
- Recordings, snapshots, logs, audit history
- Existing backups

## If something fails

Restore the persistent-data copy taken before the upgrade. See the Backup and Restore Guide.
