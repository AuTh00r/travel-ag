"""Release preparation must not overwrite targets or accept changed artifacts."""

import json
import sqlite3

import pytest

from scripts.recovery_release import FILES, backup, build, digest, preflight, verify


def source_tree(tmp_path):
    root = tmp_path / "source"
    for name in FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("VALUE = 1\n", encoding="utf-8")
    doc = root / ".kiro/specs/inbound-recovery/rollout.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("Reviewed rollout", encoding="utf-8")
    return root


def test_release_rejects_tampering_and_target_drift(tmp_path, monkeypatch):
    root, package = source_tree(tmp_path), tmp_path / "package"
    for key in ("INBOUND_RECOVERY_ENABLED", "INSTAGRAM_RECONCILE_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    build(root, package)
    (package / "baseline.json").write_text(json.dumps({name: digest(root / name) for name in FILES}))
    preflight(root, package)
    (package / "HOLD").write_text("Awaiting complete media coverage")
    with pytest.raises(ValueError, match="release_on_hold"):
        verify(package)
    (package / "HOLD").unlink()
    (root / FILES[0]).write_text("VALUE = 2\n")
    with pytest.raises(ValueError, match="target_changed"):
        preflight(root, package)
    (package / "payload" / FILES[0]).write_text("VALUE = 3\n")
    with pytest.raises(ValueError, match="hash_mismatch"):
        verify(package)
    with pytest.raises(FileExistsError):
        build(root, package)


def test_preflight_refuses_enabled_recovery(tmp_path, monkeypatch):
    root, package = source_tree(tmp_path), tmp_path / "package"
    build(root, package)
    monkeypatch.setenv("INBOUND_RECOVERY_ENABLED", "true")
    with pytest.raises(ValueError, match="flags_must_be_disabled"):
        preflight(root, package)


def test_online_backup_keeps_committed_wal_and_never_restores(tmp_path):
    root = source_tree(tmp_path)
    path = root / "data/sessions.db"
    path.parent.mkdir()
    live = sqlite3.connect(path)
    try:
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("CREATE TABLE receipts (mid TEXT, state TEXT)")
        live.execute("INSERT INTO receipts VALUES ('first','unknown')")
        live.commit()
        destination = tmp_path / "backup"
        backup(root, destination)
        live.execute("INSERT INTO receipts VALUES ('second','sent')")
        live.commit()
        snapshot = sqlite3.connect(destination / "sessions.db")
        try:
            assert snapshot.execute("SELECT * FROM receipts").fetchall() == [("first", "unknown")]
        finally:
            snapshot.close()
        assert live.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 2
        with pytest.raises(FileExistsError):
            backup(root, destination)
    finally:
        live.close()
