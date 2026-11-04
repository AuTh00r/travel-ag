"""Offline accounting and semantic checks for the ten-call diagnostic."""
import json
from types import SimpleNamespace

import pytest

from scripts import tool_call_matrix as matrix
from scripts import tool_call_probe as probe
from src.main import _validate_response
from tests.test_tool_call_probe import response


@pytest.mark.parametrize('name,reply,manager,expected', [
    ('problem', 'Ответ', None, True),
    ('problem', 'Ответ', {'context': 'Не нужен', 'type': 'консультация', 'name': ''}, False),
    ('vdp', 'Варшава Дрезден Прага https://docs.google.com/document/d/example', None, True),
    ('vdp', 'Варшава Берлин Познань https://docs.google.com/document/d/example', None, False),
    ('vdp', 'Какой тур?', None, False),
    ('ad_vague', '', {'context': 'Нет контекста', 'type': 'консультация', 'name': ''}, True),
    ('ad_vague', 'Какое объявление?', None, False),
    ('photo', 'На фото 220 €.', None, True),
    ('photo', 'На фото 999 евро.', None, False),
    ('video10', 'Варшава — Дрезден — Прага.', None, True),
    ('video10', 'Варшава — Берлин — Познань.', None, False),
])
def test_semantic_expectations(name, reply, manager, expected):
    assert matrix.semantics(name, {'reply': reply, 'manager': manager}) is expected


@pytest.mark.parametrize('uncertain', [False, True])
def test_runner_reserves_before_send_and_never_repeats(tmp_path, monkeypatch, uncertain):
    root, bundle = tmp_path / 'root', tmp_path / 'private'
    root.mkdir()
    bundle.mkdir()
    (root / 'runtime.py').write_text('original')
    (root / '.env').write_text('original')
    plan = {'cases': [('problem', {}, False)] * 10,
            'runtime': {'runtime.py': probe.sha(root / 'runtime.py')},
            'env_sha': probe.sha(root / '.env')}
    (bundle / 'plan.private.json').write_text(json.dumps(plan))
    fake = SimpleNamespace(boot=lambda: (SimpleNamespace(deepseek_api_key='not-real'),
                                       SimpleNamespace(_validate_response=_validate_response)))
    monkeypatch.setattr(probe, 'load_bootstrap', lambda _: fake)
    report = bundle / 'responses.private.jsonl'
    calls = []
    def send(body, key, strict):
        reserved = [json.loads(line) for line in report.read_text().splitlines() if 'started_call' in line]
        assert len(reserved) == len(calls) + 1 and strict is True
        calls.append(True)
        if uncertain:
            raise TimeoutError('unknown result')
        return 200, response()
    monkeypatch.setattr(probe, 'send', send)
    args = SimpleNamespace(root=root, bundle=bundle, bootstrap=tmp_path / 'unused')
    if uncertain:
        with pytest.raises(RuntimeError, match='Transport uncertain'):
            matrix.run(args)
        assert len(calls) == 1
    else:
        assert matrix.run(args)['calls'] == 10
        assert len(calls) == 10
    with pytest.raises(FileExistsError):
        matrix.run(args)
    assert len(calls) == (1 if uncertain else 10)
    assert (root / 'runtime.py').read_text() == 'original'
    assert (root / '.env').read_text() == 'original'
