"""Guarded five-file tool canary rollout; rollback never restores SQLite."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import urllib.request

from dotenv import dotenv_values

FILES = ('src/main.py', 'src/config.py', 'src/ai/prompts.py', 'src/services/llm.py', 'src/services/llm_response_log.py')
MANIFEST = '.kiro/specs/media-understanding/runtime-manifest.json'
KEY = 'DEEPSEEK_TOOL_CLIENT_IDS'
SCOPE_KEY = 'DEEPSEEK_TOOL_SCOPE'
TARGET_SCOPE = 'allowlist'
ROOT = Path('C:/travel-agent-bot')
BUNDLE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def atomic(path, data):
    resolved = path.resolve()
    assert resolved.is_relative_to(ROOT.resolve()) or resolved.is_relative_to(BUNDLE.resolve())
    assert not path.is_symlink()
    temp = path.with_name(path.name + '.tool-canary-tmp')
    created = False
    try:
        with temp.open('xb') as stream:
            created = True
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except Exception:
        if created:
            temp.unlink(missing_ok=True)
        raise


def save(state):
    atomic(BUNDLE / 'state.private.json', (json.dumps(state, indent=2) + '\n').encode())


def runtime(expected):
    for name, info in expected.items():
        path = ROOT / name
        assert path.resolve().is_relative_to(ROOT.resolve()) and not path.is_symlink()
        assert sha(path) == info['sha256'] and path.stat().st_size == info['bytes'], name


def package():
    assert not (BUNDLE / 'HOLD').exists()
    files = read(BUNDLE / 'candidate.json')
    assert set(files) == set(FILES)
    for name, info in files.items():
        path = BUNDLE / 'payload' / name
        assert path.resolve().is_relative_to((BUNDLE / 'payload').resolve())
        assert sha(path) == info['sha256'] and path.stat().st_size == info['bytes']
        ast.parse(path.read_text(encoding='utf-8'), filename=name)
    return files


def api(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=20) as response:
        return json.load(response)


def process():
    result = subprocess.run(['netstat.exe', '-ano', '-p', 'TCP'], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0
    owners = {int(a[-1]) for line in result.stdout.splitlines() if len(a := line.split()) == 5
              and a[0] == 'TCP' and a[1].endswith(':8000') and a[3] == 'LISTENING'}
    assert len(owners) == 1
    pid = owners.pop()
    command = f'$p=Get-Process -Id {pid}; @{{pid=$p.Id;start=$p.StartTime.ToUniversalTime().ToString("o")}} | ConvertTo-Json -Compress'
    result = subprocess.run([str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'),
                             '-NoProfile', '-NonInteractive', '-Command', command], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0
    return json.loads(result.stdout)


def restart():
    result = subprocess.run(['schtasks', '/run', '/tn', 'RestartTravelBot'], capture_output=True, timeout=20)
    assert result.returncode == 0


def protected():
    names = {'start-bot.vbs', 'restart-bot.cmd', 'watchdog.cmd'}
    names.update(str(p.relative_to(ROOT)).replace('\\', '/') for p in (ROOT / 'credentials').rglob('*') if p.is_file())
    return {name: sha(ROOT / name) for name in names}


def guard(state):
    assert all(sha(ROOT / name) == value for name, value in state['protected'].items())


def prepare():
    assert not (BUNDLE / 'state.private.json').exists() and not (BUNDLE / 'backup').exists()
    package()
    baseline = read(BUNDLE / 'baseline-runtime.json')
    assert read(ROOT / MANIFEST) == baseline
    runtime(baseline)
    env = dotenv_values(ROOT / '.env')
    assert TARGET_SCOPE in {'allowlist', 'all'}
    health = api('http://127.0.0.1:8000/health')
    assert health['status'] == 'ok'
    if TARGET_SCOPE == 'all':
        env_key, client = SCOPE_KEY, 'all'
        assert SCOPE_KEY not in env
        assert health.get('model_tools') == {'enabled': True, 'scope': 'allowlist', 'client_count': 1}
        assert env.get(KEY, '').isascii() and env.get(KEY, '').isdigit()
    else:
        env_key = KEY
        assert KEY not in env
        client = env.get('INBOUND_RECOVERY_CLIENT_IDS', '')
        assert client.isascii() and client.isdigit() and 0 < len(client) <= 128
        assert env.get('INBOUND_RECOVERY_SCOPE') == 'allowlist'
        identity = api('https://graph.facebook.com/v25.0/' + client + '?fields=username',
                       {'Authorization': 'Bearer ' + env['INSTAGRAM_ACCESS_TOKEN']})
        assert identity.get('username', '').lstrip('@') == '_shelter_0'
    before = process()
    backup = BUNDLE / 'backup'
    backup.mkdir()
    hashes = {}
    for name in (*FILES, MANIFEST, '.env'):
        target = backup / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        hashes[name] = sha(target)
        assert hashes[name] == sha(ROOT / name)
    database = ROOT / 'data/sessions.db'
    if database.is_file():
        with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as source:
            with sqlite3.connect(backup / 'sessions.db') as target:
                source.backup(target)
                assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    original = (ROOT / '.env').read_bytes()
    newline = b'\r\n' if b'\r\n' in original else b'\n'
    enabled = original + (b'' if original.endswith(b'\n') else newline) + env_key.encode() + b'=' + client.encode() + newline
    (BUNDLE / 'enabled.private.env').write_bytes(enabled)
    changed = dotenv_values(BUNDLE / 'enabled.private.env')
    assert {k: v for k, v in changed.items() if k != env_key} == dict(env)
    state = {'phase': 'prepared', 'before': before, 'protected': protected(), 'backup': hashes,
             'enabled_env_sha': sha(BUNDLE / 'enabled.private.env'), 'client': client,
             'target_scope': TARGET_SCOPE, 'env_key': env_key}
    save(state)
    return {'prepared': True, 'scope': TARGET_SCOPE, 'backup_verified': True, 'before': before}


def updated():
    return read(BUNDLE / 'baseline-runtime.json') | package()


def apply():
    state = read(BUNDLE / 'state.private.json')
    assert state['phase'] == 'prepared'
    runtime(read(BUNDLE / 'baseline-runtime.json'))
    package()
    guard(state)
    assert process() == state['before']
    assert all(sha(ROOT / n) == h and sha(BUNDLE / 'backup' / n) == h for n, h in state['backup'].items())
    assert sha(BUNDLE / 'enabled.private.env') == state['enabled_env_sha']
    state['phase'] = 'applying'
    save(state)
    try:
        for name in FILES:
            atomic(ROOT / name, (BUNDLE / 'payload' / name).read_bytes())
        atomic(ROOT / '.env', (BUNDLE / 'enabled.private.env').read_bytes())
        atomic(ROOT / MANIFEST, (json.dumps(updated(), indent=2) + '\n').encode())
        runtime(updated())
        guard(state)
    except Exception:
        rollback()
        raise
    state['phase'] = 'restart_requested'
    save(state)
    restart()
    return {'installed': True, 'restart_requested': True, 'scope': state['target_scope']}


def verify():
    state = read(BUNDLE / 'state.private.json')
    assert state['phase'] in {'restart_requested', 'verified'}
    runtime(updated())
    guard(state)
    assert sha(ROOT / '.env') == state['enabled_env_sha']
    current = process()
    assert current != state['before']
    health = api('http://127.0.0.1:8000/health')
    assert health['status'] == 'ok'
    scope = state['target_scope']
    expected = {'enabled': True, 'scope': 'all'} if scope == 'all' else {'enabled': True, 'scope': 'allowlist', 'client_count': 1}
    assert health.get('model_tools') == expected
    env = dotenv_values(ROOT / '.env')
    old = dotenv_values(BUNDLE / 'backup/.env')
    assert env[state['env_key']] == state['client']
    assert {k: v for k, v in env.items() if k != state['env_key']} == dict(old)
    state.update(phase='verified', after=current)
    save(state)
    return {'verified': True, 'health': health, 'process': current, 'runtime_count': len(updated()),
            'scope': scope, 'tool_clients': None if scope == 'all' else 1,
            'other_env_preserved': True, 'database_restored': False}


def rollback():
    state = read(BUNDLE / 'state.private.json')
    assert state['phase'] in {'applying', 'restart_requested', 'verified', 'rollback_requested'}
    guard(state)
    candidate = package()
    for name in (*FILES, MANIFEST, '.env'):
        assert sha(BUNDLE / 'backup' / name) == state['backup'][name]
        allowed = {state['backup'][name]}
        if name in candidate:
            allowed.add(candidate[name]['sha256'])
        elif name == '.env':
            allowed.add(state['enabled_env_sha'])
        else:
            allowed.add(hashlib.sha256((json.dumps(updated(), indent=2) + '\n').encode()).hexdigest())
        assert sha(ROOT / name) in allowed, 'Unexpected target changes; do not overwrite'
    for name in (*FILES, MANIFEST, '.env'):
        atomic(ROOT / name, (BUNDLE / 'backup' / name).read_bytes())
    runtime(read(BUNDLE / 'baseline-runtime.json'))
    assert sha(ROOT / '.env') == state['backup']['.env']
    state['phase'] = 'rollback_requested'
    save(state)
    restart()
    return {'rolled_back': True, 'database_restored': False, 'restart_requested': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'apply', 'verify', 'rollback'])
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--bundle', type=Path, default=BUNDLE)
    parser.add_argument('--scope', choices=['allowlist', 'all'], default=TARGET_SCOPE)
    args = parser.parse_args()
    ROOT, BUNDLE = args.root.resolve(), args.bundle.resolve()
    TARGET_SCOPE = args.scope
    try:
        print(json.dumps(globals()[args.action](), ensure_ascii=True))
    except Exception as error:
        print(json.dumps({'error': type(error).__name__, 'action': args.action}))
        sys.exit(1)
