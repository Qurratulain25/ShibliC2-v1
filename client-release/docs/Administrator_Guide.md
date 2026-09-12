# Administrator Guide

## First-run

A new installation has no users. The login screen asks you to create the first Administrator. Choose a strong unique password. SHIBLI stores only a password hash.

If users already exist, that screen does not appear. Existing accounts are kept across upgrades.

## Roles

- **Administrator** — users, cameras, settings, audit
- **Operator** — live video and allowed hardware controls
- **Viewer** — live video only

The server enforces permissions. Hiding a button in the window is not the security boundary.

## Cameras

Assign each camera:

- Name and type (Day or Thermal)
- Connection type: **LAN**, **IP / Online**, or **Unassigned**
- Host / IP, RTSP URL, ONVIF port
- Device username and password
- PTZ mapping when the camera shares a mover

Unassigned (legacy) cameras remain visible in both login modes until you classify them. SHIBLI does not infer LAN vs IP from the address.

## Persistent data

Windows: `C:\ProgramData\ShibliC2\`  
Ubuntu: `/var/lib/shiblic2/`

| Folder | Contents |
|---|---|
| `config/` | Runtime stream configuration |
| `data/` | Encrypted database and site `.env` |
| `logs/` | Application logs |
| `recordings/` | Recorded video |
| `snapshots/` | Snapshots |
| `exports/` | Exported files |
| `backups/` | Database backups |

Do not store site data under Program Files or `/opt/shiblic2/`.

## Backups

Automatic backups run only for a real database/schema change or when an administrator requests one. At most **5** automatic backups are kept.

## Logs

Application logs are written under the site `logs/` folder. They do not include password hashes or RTSP passwords.

## Upgrades

Install the newer package over the old one. Site data stays in place. See the Upgrade Guide.

## Uninstall

Windows: remove SHIBLI C2 from Installed Apps. Program Files is removed. `C:\ProgramData\ShibliC2\` is left for the site administrator.

Ubuntu: remove the `shibli-c2` package. `/var/lib/shiblic2/` is left unless an administrator deletes it.
