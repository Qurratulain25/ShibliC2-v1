# SHIBLI logo assets

Official SHIBLI Electronics mark. Keep source artwork here only.

| File | Use |
| --- | --- |
| `shibli-official.jpg` | Master provided by SHIBLI |
| `shibli-mark.svg` / `shibli-logo.svg` | Vector mark for UI and Linux launchers |
| `shibli-256.png` | Ubuntu Applications icon |
| `shibli.ico` | Windows application / installer / shortcut |

Runtime copies used by the web UI:

* `static/branding/logo.png`
* `static/branding/logo.svg`

Regenerate derived sizes after replacing the official file:

```bash
python3 deployment/scripts/generate-icons.py
```

Preserve aspect ratio. Do not stretch.
