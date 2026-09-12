# Ubuntu production build baseline

The production `.deb` is built inside `ubuntu:22.04` via:

```bash
./deployment/scripts/build-ubuntu-2204.sh
```

Recorded from the successful 22.04 builder run:

| Field | Value |
|---|---|
| Build OS | Ubuntu 22.04 LTS (Jammy) |
| Architecture | amd64 / x86-64 |
| glibc | 2.35 (`ldd (Ubuntu GLIBC 2.35-0ubuntu3.14) 2.35`) |
| Python used to freeze | 3.10.12 |
| PyInstaller | 6.11.1 |
| FFmpeg | 4.4.2-0ubuntu0.22.04.1 |
| go2rtc | 1.9.14 (`32d616af226bd731678ffde328b94cfb94e30339bfefc469cfb76323144615a6`) |
| GUI | pywebview 5.4 + GTK / WebKit2GTK 4.0 from Ubuntu 22.04 |
| Minimum advertised Ubuntu | Ubuntu 22.04 LTS x86-64 |
| Later Ubuntu releases | list only after clean-machine tests pass |

Do not freeze the production package on Ubuntu 25.10. Do not copy Ubuntu 25.10 glibc or GTK/WebKit into the package. glibc itself is not bundled.

Actual versions are also in `deployment/runtime-manifest.json`.

Clean-machine install steps: `CLEAN_VM_TEST.md`.
