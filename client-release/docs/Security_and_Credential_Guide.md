# Security and Credential Guide

## Two kinds of credentials

**SHIBLI users** sign in to the application (Administrator, Operator, Viewer).

**Device credentials** belong to cameras and hardware (RTSP, ONVIF, PTZ, LRF, illuminator).

Changing a SHIBLI password never changes a camera password. Changing a camera password never changes a SHIBLI user.

## Passwords

- SHIBLI passwords are stored as bcrypt hashes. They are never shown.
- Do not use factory values such as `admin` / `password` on a client site.
- The first Administrator is created on the first run of a new install.

## Login errors

Failed sign-in always shows: **Invalid username or password**.

## What not to share

Do not send or publish:

- Password hashes
- Sign-in tokens
- RTSP URLs that contain passwords
- Device passwords
- Recovery codes
- The site `.env` file

## Recovery

Forgot-password works only when a site recovery code has been configured by an administrator. Treat that code as a secret.

## Database

The site database is encrypted. The key lives with the site data folder. Back up the folder as a whole.
