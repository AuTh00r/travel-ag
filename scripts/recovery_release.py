"""Local release preparation and read-only preflight. Never deploys/restarts."""

import argparse
import ast
import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path

FILES = ("src/main.py", "src/config.py", "src/channels/instagram.py", "src/db/sessions.py",
         "src/db/pending_messages.py", "src/db/inbound.py", "src/exceptions.py",
         "src/services/inbound_recovery.py", "src/services/telegram_notify.py")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def verify(package):
    if (package / "HOLD").exists():
        raise ValueError("release_on_hold")
    files = json.loads((package / "manifest.json").read_text(encoding="utf-8"))["files"]
    if set(files) != set(FILES):
        raise ValueError("unexpected_release_files")
    for name, expected in files.items():
        source = package / "payload" / name
        if digest(source) != expected:
            raise ValueError("release_hash_mismatch")
        ast.parse(source.read_text(encoding="utf-8"), filename=name)


def build(root, package):
    package.mkdir(parents=True, exist_ok=False)
    files = {}
    for name in FILES:
        source, target = root / name, package / "payload" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        ast.parse(source.read_text(encoding="utf-8"), filename=name)
        shutil.copyfile(source, target)
        files[name] = digest(source)
    for source, name in ((Path(__file__), "recovery_release.py"),
                         (root / ".kiro/specs/inbound-recovery/rollout.md", "ROLLOUT.md")):
        shutil.copyfile(source, package / name)
    (package / "manifest.json").write_text(json.dumps({"files": files}, indent=2)+"\n", encoding="utf-8")
    (package / "disabled.env").write_text("INBOUND_RECOVERY_ENABLED=false\nINSTAGRAM_RECONCILE_ENABLED=false\n"
        "INBOUND_RECOVERY_SCOPE=allowlist\nINBOUND_RECOVERY_CLIENT_IDS=\n", encoding="utf-8")
    verify(package)


def preflight(root, package):
    from dotenv import dotenv_values
    verify(package)
    env = {**dotenv_values(root / ".env"), **os.environ}
    for key in ("INBOUND_RECOVERY_ENABLED", "INSTAGRAM_RECONCILE_ENABLED"):
        if str(env.get(key, "false")).lower() not in ("false", "0", "off", "no", ""):
            raise ValueError("flags_must_be_disabled")
    baseline = json.loads((package / "baseline.json").read_text(encoding="utf-8"))
    if set(baseline) != set(FILES) or any(digest(root / name) != sha for name, sha in baseline.items()):
        raise ValueError("target_changed_since_baseline")


def backup(root, destination):
    destination.mkdir(parents=True, exist_ok=False)
    manifest = {}
    for name in FILES:
        source, target = root / name, destination / name
        manifest[name] = digest(source)
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    (destination / "baseline.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    path = root / "data/sessions.db"
    if path.is_file():
        source = sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True)
        target = sqlite3.connect(destination / "sessions.db")
        try:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("backup_integrity_failed")
        finally:
            target.close()
            source.close()
    # Never restore an old DB automatically: keep newer delivery receipts.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "verify", "preflight", "backup"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == "build":
            build(args.root, args.package)
        elif args.action == "verify":
            verify(args.package)
        elif args.action == "preflight":
            preflight(args.root, args.package)
        else:
            backup(args.root, args.package)
    except (OSError, ValueError, sqlite3.Error, SyntaxError):
        raise SystemExit("Recovery release check failed; no deployment performed") from None
    print(json.dumps({"action": args.action, "ok": True, "runtime_files": len(FILES)}))


if __name__ == "__main__":
    main()
