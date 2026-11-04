"""Inverse rollout proof on disposable files and SQLite, no server/network."""
import json
import sqlite3

import pytest

from scripts import tool_canary_release as release


@pytest.fixture
def package(tmp_path, monkeypatch):
    root, bundle = tmp_path / 'runtime', tmp_path / 'bundle'
    root.mkdir()
    bundle.mkdir()
    monkeypatch.setattr(release, 'ROOT', root)
    monkeypatch.setattr(release, 'BUNDLE', bundle)
    before, after = {}, {}
    for name in release.FILES:
        old, new = root / name, bundle / 'payload' / name
        old.parent.mkdir(parents=True, exist_ok=True)
        new.parent.mkdir(parents=True, exist_ok=True)
        old.write_text("VALUE = 'old'\n")
        new.write_text("VALUE = 'new'\n")
        before[name] = {'sha256': release.sha(old), 'bytes': old.stat().st_size}
        after[name] = {'sha256': release.sha(new), 'bytes': new.stat().st_size}
    (root / release.MANIFEST).parent.mkdir(parents=True)
    (root / release.MANIFEST).write_text(json.dumps(before))
    (bundle / 'baseline-runtime.json').write_text(json.dumps(before))
    (bundle / 'candidate.json').write_text(json.dumps(after))
    (root / '.env').write_text('INBOUND_RECOVERY_SCOPE=allowlist\nINBOUND_RECOVERY_CLIENT_IDS=123456\nINSTAGRAM_ACCESS_TOKEN=not-live\n')
    for name in ('start-bot.vbs', 'restart-bot.cmd', 'watchdog.cmd'):
        (root / name).write_text('unchanged')
    (root / 'data').mkdir()
    database = root / 'data/sessions.db'
    with sqlite3.connect(database) as conn:
        conn.execute('CREATE TABLE proof (value TEXT)')
        conn.execute("INSERT INTO proof VALUES ('unknown-before')")
    pid = [1]
    monkeypatch.setattr(release, 'process', lambda: {'pid': pid[0], 'start': str(pid[0])})
    monkeypatch.setattr(release, 'restart', lambda: pid.__setitem__(0, pid[0] + 1))
    monkeypatch.setattr(release, 'api', lambda url, headers=None:
        {'username': '_shelter_0'} if 'graph.facebook' in url else {'status': 'ok', 'model_tools': {
            'enabled': True, 'scope': 'allowlist', 'client_count': 1}})
    return root, bundle, database


def test_install_verify_rollback_preserves_new_receipts(package):
    root, bundle, database = package
    original_env = (root / '.env').read_bytes()
    release.prepare()
    release.apply()
    assert release.verify()['tool_clients'] == 1
    with sqlite3.connect(database) as conn:
        conn.execute("INSERT INTO proof VALUES ('new-receipt-after-install')")
    release.rollback()
    assert (root / '.env').read_bytes() == original_env
    release.runtime(release.read(bundle / 'baseline-runtime.json'))
    with sqlite3.connect(database) as conn:
        assert conn.execute('SELECT value FROM proof').fetchall() == [('unknown-before',), ('new-receipt-after-install',)]
    assert (root / 'watchdog.cmd').read_text() == 'unchanged'


def test_rollback_refuses_to_overwrite_unexpected_edit(package):
    root, _, _ = package
    release.prepare()
    release.apply()
    target = root / release.FILES[0]
    target.write_text('unrelated edit')
    with pytest.raises(AssertionError, match='Unexpected target'):
        release.rollback()
    assert target.read_text() == 'unrelated edit'


def test_half_install_automatically_restores_sources(package, monkeypatch):
    root, bundle, _ = package
    release.prepare()
    atomic = release.atomic
    failed = False
    def fail_once(path, data):
        nonlocal failed
        if path == root / release.FILES[1] and not failed:
            failed = True
            raise OSError('interrupted replacement')
        atomic(path, data)
    monkeypatch.setattr(release, 'atomic', fail_once)
    with pytest.raises(OSError):
        release.apply()
    release.runtime(release.read(bundle / 'baseline-runtime.json'))
    assert release.sha(root / '.env') == release.read(bundle / 'state.private.json')['backup']['.env']


def test_all_rollout_and_rollback_return_to_canary_without_old_database(package, monkeypatch):
    root, _, database = package
    (root / '.env').write_text((root / '.env').read_text() + 'DEEPSEEK_TOOL_CLIENT_IDS=123456\n')
    original = (root / '.env').read_bytes()
    monkeypatch.setattr(release, 'TARGET_SCOPE', 'all')
    monkeypatch.setattr(release, 'api', lambda url, headers=None: {'status': 'ok', 'model_tools':
        {'enabled': True, 'scope': 'all'} if 'DEEPSEEK_TOOL_SCOPE=all' in (root / '.env').read_text()
        else {'enabled': True, 'scope': 'allowlist', 'client_count': 1}})
    assert release.prepare()['scope'] == 'all'
    release.apply()
    assert release.verify()['scope'] == 'all'
    with sqlite3.connect(database) as conn:
        conn.execute("INSERT INTO proof VALUES ('new-global-receipt')")
    release.rollback()
    assert (root / '.env').read_bytes() == original
    with sqlite3.connect(database) as conn:
        assert conn.execute('SELECT value FROM proof').fetchall() == [('unknown-before',), ('new-global-receipt',)]
