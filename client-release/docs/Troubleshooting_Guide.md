# Troubleshooting Guide

## The window does not open

- Confirm you launched **SHIBLI C2** from the Start Menu, Desktop, or Applications — not a web browser.
- On Ubuntu, confirm the package is installed and try Applications again.
- Check `logs/` under the persistent data folder.

## Invalid username or password

The username or password is wrong, or the account is inactive. SHIBLI does not say which. An Administrator can reset the password.

## No cameras after login

- Confirm you selected the same connection mode the cameras are classified for.
- Unassigned cameras appear in both modes until an Administrator sets LAN or IP / Online.
- Confirm the camera host is reachable from this PC.

## No live video

- Confirm the RTSP URL and device password on the Cameras page.
- Confirm the camera is powered and reachable.
- Recording and live video both need the bundled stream components; they start with the application.

## PTZ, LRF, or illuminator does nothing

- Confirm your role includes hardware control.
- Confirm ONVIF or USR devices are on the network the SHIBLI PC uses.
- Hardware that is not connected cannot be tested from software alone.

## Forgot password does not work

Forgot-password is disabled until an Administrator sets a site recovery code. It will not reveal whether a username exists.

## After uninstall, data is still there

That is intentional. Remove `C:\ProgramData\ShibliC2` or `/var/lib/shiblic2` only if the site administrator wants to erase the installation.
