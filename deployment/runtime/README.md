# Bundled sidecar binaries

This folder is populated at **build time** on the packaging machine.

```text
deployment/runtime/
  linux/go2rtc
  linux/ffmpeg
  windows/go2rtc.exe
  windows/ffmpeg.exe
```

These files are not stored in Git. The Ubuntu and Windows build scripts copy
or download them before packaging. Client installs never download them.
