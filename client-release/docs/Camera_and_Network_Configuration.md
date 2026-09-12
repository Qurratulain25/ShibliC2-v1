# Camera and Network Configuration

## Connection modes

Operators select **LAN** or **IP / Online** at login. That choice filters which cameras appear.

An administrator classifies each camera. SHIBLI does **not** decide LAN vs IP from `192.168.x.x`, `10.x.x.x`, or a public address. Routed private networks and VPNs are valid.

## What to collect on site

For each camera:

- Display name
- Type: Day or Thermal
- Connection type: LAN or IP / Online
- Host name or IP the SHIBLI PC can reach
- RTSP URL (ask the camera vendor or site engineer)
- ONVIF port if PTZ/focus is used (often 80)
- Camera / ONVIF username and password
- PTZ mapping if Day and Thermal share one mover

Example placeholders only:

```text
Host: camera-day.site.local
RTSP: rtsp://USER:PASSWORD@camera-day.site.local:554/Streaming/Channels/101
ONVIF port: 80
```

Never put real site passwords in email or tickets if a safer channel exists.

## Day and Thermal

Add one record per optical channel. A shared PTZ head still uses two camera records with the same PTZ mapping.

## Status

A camera is online when SHIBLI can reach the configured stream/control endpoint. Offline means the path, credentials, or device is not responding — not a SHIBLI login failure.

## Remote / IP Online

Use the address the SHIBLI PC will use at that site (VPN host, public host, or routed LAN). Changing sites is a configuration change, not a new product install.
