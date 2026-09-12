# SHIBLI C2

Current Release: **v1.0**

SHIBLI C2 is a desktop command-and-control application for Day and Thermal cameras, PTZ, recording, and related hardware.

## Supported Platforms

- Windows 10/11 64-bit — when `ShibliC2-Setup-v1.0.exe` is published
- Ubuntu 22.04 LTS x86-64 and later tested compatible Ubuntu x86-64 releases

Ubuntu 24.04 and 25.10 are not listed as tested until a clean-machine install of the same `.deb` has passed on those versions. Compatibility is not claimed for Ubuntu releases that have not been tested.

Only installers listed in Releases are supported. A Git checkout is not required and is not provided to clients.

## Connection Modes

- **LAN** — use cameras classified for the local site
- **IP / Online** — use cameras classified for remote/online operation

The operator chooses the mode on the login screen. SHIBLI does not guess the mode from an IP address.

## Downloads

Use the **Releases** section of this repository.

- Windows: `ShibliC2-Setup-v1.0.exe`
- Ubuntu: `shibli-c2_v1.0_amd64.deb`

Each installer is self-contained. After you download it you can disconnect from the internet and install.

## Documentation

- [Installation Guide](docs/Installation_Guide.md)
- [User Manual](docs/User_Manual.md)
- [Administrator Guide](docs/Administrator_Guide.md)
- [Camera and Network Configuration](docs/Camera_and_Network_Configuration.md)
- [Backup and Restore Guide](docs/Backup_and_Restore_Guide.md)
- [Upgrade Guide](docs/Upgrade_Guide.md)
- [Troubleshooting Guide](docs/Troubleshooting_Guide.md)
- [Security and Credential Guide](docs/Security_and_Credential_Guide.md)

## What you receive

One installer per platform. You do **not** install Python, Node, go2rtc, FFmpeg, or any other development tool.
