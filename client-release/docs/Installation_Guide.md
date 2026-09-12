# Installation Guide

SHIBLI C2 v1.0 is installed from a single file. Do not install Python, pip, Node, Git, go2rtc, or FFmpeg.

## Windows

1. Download `ShibliC2-Setup-v1.0.exe` from Releases.
2. Double-click the file.
3. Follow the SHIBLI C2 Setup Wizard.
4. Choose the installation folder if asked (default is Program Files).
5. Optionally create a Desktop shortcut.
6. Finish the wizard.
7. Launch **SHIBLI C2**.
8. On a fresh computer, create the first Administrator account.
9. Sign in and choose **LAN** or **IP / Online**.

Application files: `C:\Program Files\ShibliC2\`  
Site data: `C:\ProgramData\ShibliC2\`

## Ubuntu

Minimum Ubuntu: **Ubuntu 22.04 LTS x86-64**.

The production `.deb` is built against the Ubuntu 22.04 LTS ABI. Later Ubuntu x86-64 releases should be used only after they have been clean-machine tested with this same installer. 24.04 and 25.10 are not listed as tested until those tests pass.

1. Download `shibli-c2_v1.0_amd64.deb` from Releases.
2. Double-click the file to open the graphical installer.
3. Install.
4. Open **Applications** and launch **SHIBLI C2**.
5. On a fresh computer, create the first Administrator account.
6. Sign in and choose **LAN** or **IP / Online**.

If the graphical installer is not available, an administrator may run:

```bash
sudo dpkg -i shibli-c2_v1.0_amd64.deb
```

That command must not download extra packages. The `.deb` already contains the runtime.

Application files: `/opt/shiblic2/`  
Site data: `/var/lib/shiblic2/`

## After install

You can disconnect the internet. SHIBLI C2 does not download runtimes. A remote camera still needs a network path to that camera.
