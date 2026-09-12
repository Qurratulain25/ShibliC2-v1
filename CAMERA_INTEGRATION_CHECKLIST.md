# SHIBLI C2 — Camera Integration Checklist (Phase 1)

Use this form **before** connecting physical cameras tomorrow. Complete each section on-site with the client/network team.

---

## Site / Network

| Field | Value |
|-------|-------|
| Site name | |
| C2 PC IP address | |
| Camera subnet (e.g. 192.168.1.0/24) | |
| Default gateway | |
| DNS | |
| NVR / switch model | |
| VLAN (if any) | |
| Firewall rules for RTSP/ONVIF | |

---

## Day Camera (EO)

| Field | Value |
|-------|-------|
| Camera name (in SHIBLI) | |
| IP address | |
| RTSP URL | |
| ONVIF port (default 80) | |
| Username | |
| Password | |
| PTZ system mapping | PTZ System 1 |
| Type | Day |
| Same device as thermal? | Yes / No |

---

## Thermal Camera (IR)

| Field | Value |
|-------|-------|
| Camera name (in SHIBLI) | |
| IP address | |
| RTSP URL | |
| ONVIF port | |
| Username | |
| Password | |
| PTZ system mapping | PTZ System 2 |
| Type | Thermal |
| Same device as day? | Yes / No |

---

## PTZ / Protocol

| Field | Value |
|-------|-------|
| PTZ protocol | ONVIF / ISAPI / Pelco / SDK / Other |
| Controls service URL | http://127.0.0.1:8001 |
| Camera ID format for Controls | `IP:ONVIF_PORT` |

---

## Auxiliary Hardware (if applicable)

| Device | IP | Port | Protocol / Notes |
|--------|-----|------|------------------|
| LRF | | | |
| Illuminator | | | |
| Wiper | | | Method: |
| Heater | | | Method: |
| NUC | | | Phase 2+ |
| AGC | | | Phase 2+ |

---

## Pre-Connection Tests (Windows)

Run on the C2 workstation **before** adding cameras in SHIBLI:

```powershell
ipconfig
ping <day-camera-ip>
ping <thermal-camera-ip>
Test-NetConnection <camera-ip> -Port 554
Test-NetConnection <camera-ip> -Port 80
Test-NetConnection <camera-ip> -Port 8000
```

**VLC RTSP test** (recommended before SHIBLI):

1. Open VLC → Media → Open Network Stream  
2. Paste RTSP URL  
3. Confirm live video appears  

---

## Common RTSP URL Patterns

```
rtsp://username:password@<camera-ip>:554/Streaming/Channels/101
rtsp://username:password@<camera-ip>:554/Streaming/Channels/102
rtsp://username:password@<camera-ip>:554/live
rtsp://username:password@<camera-ip>:554/live?channel=0&subtype=0
```

---

## SHIBLI C2 In-App Steps (Day 1)

1. Start: `.\scripts\restart-shibli.ps1`  
2. Login: `<administrator username>` / `<administrator password>`  
3. **Cameras** → Add Camera (Day, then Thermal)  
4. **Test Connection** on each — expect: *Camera connected successfully* or specific error  
5. **Sync Core → Controls** when Core + Controls Docker stacks are running  
6. **Operations Dashboard** → verify streams, PTZ, recording mode  
7. Check **Audit Logs** for `camera_test`, `camera_create`, PTZ actions  

---

## Expected Test Connection Messages

| Message | Meaning |
|---------|---------|
| Camera connected successfully | Reachability OK |
| Camera unreachable | Ping/TCP to camera IP failed |
| Authentication failed | ONVIF credentials wrong |
| RTSP URL missing | No URL in form |
| RTSP stream unavailable | Port 554 not reachable |
| ONVIF not reachable | ONVIF HTTP service not responding |

---

## Sign-off

| Role | Name | Date | Notes |
|------|------|------|-------|
| Integrator | | | |
| Client | | | |
