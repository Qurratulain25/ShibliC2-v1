# SHIBLI C2 v1.0 — Ubuntu clean-machine test

Use the **same** file on every machine:

`release/v1.0/shibli-c2_v1.0_amd64.deb`

These steps are the required validation. Extracting the `.deb` on the build host is not an install PASS.

## Machines

Prepare one clean VM for each target:

- Ubuntu 22.04 LTS x86-64 (required)
- Ubuntu 24.04 LTS x86-64 (required)
- Ubuntu 25.10 x86-64 (optional / currently available)

Each VM must start with:

- no SHIBLI source repository
- no SHIBLI `.venv`
- no developer Python install created for SHIBLI
- no separately installed go2rtc, FFmpeg, or SHIBLI-controls
- a normal desktop session (Applications menu)

## Procedure (repeat on each VM)

1. Copy **only** `shibli-c2_v1.0_amd64.deb` onto the VM.
2. Disconnect the internet (disable NIC or unplug).
3. Double-click the `.deb` and install. If a graphical installer is not available:

   ```bash
   sudo dpkg -i shibli-c2_v1.0_amd64.deb
   ```

4. Confirm `dpkg` does **not** download extra packages (`apt` must stay unused).
5. Confirm `/opt/shiblic2/` exists and contains the frozen application.
6. Confirm `/var/lib/shiblic2/` has `config data logs recordings snapshots exports backups`.
7. Confirm **Applications → SHIBLI C2** is present with the official icon.
8. Launch **SHIBLI C2**. Confirm a desktop window (not Firefox/Chrome/Edge).
9. Confirm official logo, **SHIBLI C2**, **v1.0**, **LAN**, **IP / Online**. Confirm there is no Phase 1 wording.
10. Create the first Administrator. Confirm a later login works.
11. Log out. Restart the application. Confirm the account persists.
12. Reboot the operating system. Confirm SHIBLI C2 still launches.
13. Confirm the development repository and `.venv` are not required.
14. Reinstall the same `.deb`. Confirm the user and configuration persist.

Do not classify a sudo-password limitation on the development workstation as an application FAIL.

Record each row as `PASS`, `FAIL`, or `NOT TESTED — environment unavailable`.
