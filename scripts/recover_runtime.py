#!/usr/bin/env python3
"""Recover SHIBLI C2 camera/runtime state from older installs.

Default is dry-run. Never prints SHIBLI_DB_KEY, passwords, JWTs, or RTSP credentials.
Fingerprints keys as SHA-256 hex[:10] only.

  python3 scripts/recover_runtime.py
  python3 scripts/recover_runtime.py --apply
  python3 scripts/recover_runtime.py --write-controls-dir
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.bootstrap_env import bootstrap_environment  # noqa: E402
from app.core.paths import project_root  # noqa: E402
from app.core.runtime_recovery import (  # noqa: E402
    controls_candidates,
    env_candidates,
    env_has_name,
    import_cameras,
    key_fingerprint,
    open_sqlcipher,
    parse_env_file,
    summarize_db,
    try_open,
    upsert_env_value,
)


def _print(msg: str = "") -> None:
    print(msg, flush=True)


def _safe_env_flags(values: dict) -> str:
    flags = []
    for name in (
        "SHIBLI_DB_KEY",
        "SHIBLI_CONTROLS_DIR",
        "SHIBLI_CONTROLS_URL",
        "SHIBLI_JWT_SECRET",
    ):
        flags.append(f"{name}={'yes' if values.get(name, '').strip() else 'no'}")
    return ", ".join(flags)


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover SHIBLI C2 runtime/camera state")
    parser.add_argument("--apply", action="store_true", help="Import cameras from the matching backup into the current DB")
    parser.add_argument("--replace-cameras", action="store_true", help="Allow import even if the current DB already has cameras")
    parser.add_argument("--write-controls-dir", action="store_true", help="Set SHIBLI_CONTROLS_DIR in data/.env if missing")
    parser.add_argument("--backup", type=Path, default=None, help="Encrypted backup to probe (default: data/shibli_c2.db.verify_backup)")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Extra data/.env path to audit (repeatable). Example: --env /path/to/ShibliC2/data/.env",
    )
    args = parser.parse_args()

    bootstrap_environment(project_root())
    home = Path.home()
    data = ROOT / "data"
    current_env = data / ".env"
    current_db = data / "shibli_c2.db"
    backup = args.backup or data / "shibli_c2.db.verify_backup"
    safe = data / "shibli_c2.db.verify_backup.safe"
    probe_targets = [p for p in (backup, safe) if p.exists() and p.stat().st_size > 0]
    if backup.exists() and backup not in probe_targets:
        probe_targets.insert(0, backup)

    _print("=== SHIBLI C2 runtime recovery (secrets redacted) ===")
    _print(f"project: {ROOT}")
    _print(f"current db: {current_db} exists={current_db.exists()} size={current_db.stat().st_size if current_db.exists() else 0}")
    _print(f"backup: {backup} exists={backup.exists()} size={backup.stat().st_size if backup.exists() else 0}")
    _print(f"safe backup: {safe} exists={safe.exists()} size={safe.stat().st_size if safe.exists() else 0}")
    _print()

    extra_envs = [current_env] if current_env.exists() else []
    for raw in args.env:
        extra_envs.append(Path(raw).expanduser())
    candidates = env_candidates(home, extra=extra_envs)
    if current_env.exists() and current_env not in candidates:
        candidates.insert(0, current_env)

    _print(f"[env audit] {len(candidates)} candidate file(s)")
    matches = []
    for env_path in candidates:
        values = parse_env_file(env_path)
        key = values.get("SHIBLI_DB_KEY", "").strip()
        fp = key_fingerprint(key) if key else "none"
        controls_dir = values.get("SHIBLI_CONTROLS_DIR", "").strip()
        _print(f"  {env_path}")
        _print(f"    {_safe_env_flags(values)}")
        _print(f"    SHIBLI_DB_KEY fingerprint={fp}")
        if controls_dir:
            _print(f"    SHIBLI_CONTROLS_DIR={controls_dir}")
        if not key:
            _print("    result: SKIP (no DB key)")
            continue
        for target in probe_targets:
            ok, kind = try_open(target, key)
            if ok:
                _print(f"    result: MATCH against {target.name}")
                matches.append({"env": env_path, "key": key, "fingerprint": fp, "target": target})
            else:
                _print(f"    result: NO MATCH against {target.name} ({kind})")
        _print()

    if not matches:
        _print("No matching key found for the backup database on this machine.")
        _print("This environment cannot inspect another machine's local SHIBLI installation. Run this script on the target system.")
    else:
        unique_fps = {m["fingerprint"] for m in matches}
        if len(unique_fps) > 1:
            _print("Multiple distinct keys opened the backup. Copies of different .env files may share history;")
            _print("prefer the install that also has SHIBLI_CONTROLS_DIR and camera records.")
        elif len(matches) > 1:
            _print("Multiple .env files share the same matching key (duplicate installs / copied .env).")
        _print()
        chosen = matches[0]
        _print(f"[chosen MATCH] {chosen['env']}")
        _print(f"  fingerprint={chosen['fingerprint']}")
        _print(f"  backup={chosen['target']}")
        src = open_sqlcipher(chosen["target"], chosen["key"])
        summary = summarize_db(src)
        _print(f"  tables={summary['tables']}")
        _print(f"  camera_count={summary['camera_count']}")
        _print(f"  ptz_mapping_count={summary['ptz_mapping_count']}")
        _print(f"  user_count={summary['user_count']}")
        _print(f"  settings={summary['has_settings']}")
        _print(f"  local_cameras_columns={summary['local_cameras_columns']}")
        for cam in summary["cameras"]:
            _print(
                "  camera: "
                f"name={cam['name']!r} type={cam['camera_type']} enabled={cam['enabled']} "
                f"ptz={cam['ptz_mapping']} host={cam['host']} host_kind={cam['host_kind']} "
                f"onvif={cam['onvif_port']} rtsp={cam['rtsp_host']}:{cam['rtsp_port']}{cam['rtsp_path']}"
            )

        dest_summary = None
        current_key = parse_env_file(current_env).get("SHIBLI_DB_KEY", "").strip() if current_env.exists() else ""
        if current_db.exists() and current_db.stat().st_size > 0 and current_key:
            dest = open_sqlcipher(current_db, current_key)
            dest_summary = summarize_db(dest)
            _print()
            _print("[current DB]")
            _print(f"  fingerprint={key_fingerprint(current_key)}")
            _print(f"  tables={dest_summary['tables']}")
            _print(f"  camera_count={dest_summary['camera_count']}")
            _print(f"  user_count={dest_summary['user_count']}")
            src_cols = set(summary["local_cameras_columns"])
            dest_cols = set(dest_summary["local_cameras_columns"])
            if src_cols == dest_cols:
                _print("  schema: local_cameras columns MATCH current code")
            else:
                _print(f"  schema: only_in_backup={sorted(src_cols - dest_cols)} only_in_current={sorted(dest_cols - src_cols)}")
                _print("  recovery method: B (import camera rows; keep current users/auth schema)")

            method = "B"
            if src_cols != dest_cols:
                method = "B"
            _print(f"  selected method: {method} import cameras, do not replace users or SHIBLI_DB_KEY")

            if args.apply:
                if dest_summary["camera_count"] and not args.replace_cameras:
                    _print("APPLY skipped: current DB already has cameras. Re-run with --replace-cameras to overwrite.")
                else:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    snap = data / "recovery-snapshots" / ts
                    snap.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(current_db, snap / "shibli_c2.db")
                    if current_env.exists():
                        shutil.copy2(current_env, snap / ".env")
                    if dest_summary["camera_count"] and args.replace_cameras:
                        dest.execute("DELETE FROM local_cameras")
                        dest.commit()
                    copied = import_cameras(src, dest)
                    _print(f"APPLY: imported {copied} camera row(s). Snapshot: {snap}")
                    _print("Current SHIBLI_DB_KEY and users table were preserved.")
            else:
                _print("Dry-run only. Pass --apply to import camera rows into the current database.")
            dest.close()
        else:
            _print("Current DB is missing, empty, or unreadable with data/.env — not applying.")
        src.close()

    _print()
    _print("[SHIBLI-controls search]")
    found_controls = controls_candidates(home, ROOT)
    if found_controls:
        for path in found_controls:
            _print(f"  found: {path}")
        if args.write_controls_dir:
            if current_env.exists() and env_has_name(current_env, "SHIBLI_CONTROLS_DIR"):
                _print("  data/.env already has SHIBLI_CONTROLS_DIR — left unchanged")
            else:
                chosen_dir = found_controls[0]
                if current_env.exists():
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    shutil.copy2(current_env, data / f".env.controls-backup-{ts}")
                upsert_env_value(current_env, "SHIBLI_CONTROLS_DIR", str(chosen_dir))
                _print(f"  wrote SHIBLI_CONTROLS_DIR={chosen_dir}")
        else:
            _print("  Pass --write-controls-dir to set SHIBLI_CONTROLS_DIR in data/.env (if missing).")
    else:
        _print("  BLOCKER: no SHIBLI-controls/server.py found on this machine.")
        _print("  Set SHIBLI_CONTROLS_DIR in data/.env on the lab PC; do not invent a controls tree.")

    _print()
    _print("Recovery notes:")
    _print("  - LAN vs remote is the camera host/RTSP URL, not a separate codebase.")
    _print("  - After import, edit host to a LAN IP or hostname (e.g. camera.example.invalid) in Cameras.")
    _print("  - Then run ./scripts/start-all.sh so go2rtc is rendered from the DB.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
