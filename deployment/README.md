# SHIBLI C2 v1.0 packaging

Build installers on a development machine that already has the SHIBLI runtime
dependencies. Client sites must not need `python`, `pip`, `npm`, `node`, or
`git` after install. Client sites must not download go2rtc or FFmpeg at runtime.

```text
deployment/
├── assets/logo/          # official SHIBLI artwork (do not replace with placeholders)
├── runtime/              # build-time sidecar binaries (not in Git)
├── windows/installer/    # Inno Setup script
├── ubuntu/installer/     # .desktop + Debian maintainer scripts
└── scripts/
    ├── generate-icons.py
    ├── build-ubuntu.sh
    └── build-windows.ps1
```

## Ubuntu (production)

The production `.deb` must be frozen inside Ubuntu 22.04 LTS, not on a newer development workstation.

```bash
./deployment/scripts/build-ubuntu-2204.sh
```

That script builds `deployment/ubuntu/Dockerfile.ubuntu2204` and packages inside `ubuntu:22.04`.

Produces `release/v1.0/shibli-c2_v1.0_amd64.deb`.

- Frozen onedir via PyInstaller (`ShibliC2.spec`)
- Bundled Linux go2rtc 1.9.14 + Ubuntu 22.04 FFmpeg
- SHIBLI-controls frozen from `deployment/runtime/controls`
- Persistent data: `/var/lib/shiblic2/`
- Application binaries: `/opt/shiblic2/`
- Debian `Depends`: `libc6` only

`./deployment/scripts/build-ubuntu.sh` is the older host-native builder. Do not use it for the production candidate on Ubuntu 25.10.

Clean-machine install steps: `deployment/ubuntu/CLEAN_VM_TEST.md`.

## Windows

Run on a Windows build PC with Inno Setup 6:

```powershell
.\deployment\scripts\build-windows.ps1
```

Produces `release\v1.0\ShibliC2-Setup-v1.0.exe`.

- Frozen onedir via PyInstaller
- Official `deployment/assets/logo/shibli.ico` for the executable, installer, and shortcuts
- Persistent data: `C:\ProgramData\ShibliC2\`
- Application binaries: `C:\Program Files\ShibliC2\`

This Ubuntu development host cannot produce the `.exe`. Do not invent one.

## Client data

Installers never include:

- live `data/shibli_c2.db`
- `go2rtc.yaml` with site streams
- `.env`
- recordings, snapshots, logs, or developer backups

Fresh install creates an empty database and the first-administrator screen.
Upgrades leave `/var/lib/shiblic2` and `C:\ProgramData\ShibliC2` untouched.
