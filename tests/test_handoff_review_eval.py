import json

import pytest

from scripts import handoff_review_eval as runner
from src.services.handoff_review import HandoffDecision
from tests.test_handoff_review import CATALOG


@pytest.mark.parametrize('uncertain', [False, True])
async def test_eval_reserves_before_call_and_stops_on_unknown(tmp_path, uncertain):
    selected = runner.cases()[:3]
    bundle = tmp_path / 'new-report'
    invocations = []
    async def review(messages, candidate, **kwargs):
        rows = [json.loads(line) for line in (bundle / 'evaluation.jsonl').read_text(encoding='utf-8').splitlines()]
        assert sum('started_call' in row for row in rows) == len(invocations) + 1
        invocations.append(True)
        return HandoffDecision(candidate, action=selected[len(invocations) - 1]['action'], reviewed=not uncertain)
    result = await runner.evaluate(CATALOG, selected, bundle, 2, review=review)
    assert len(invocations) == (1 if uncertain else 2)
    assert result['reserved_calls'] == len(invocations)
    with pytest.raises(FileExistsError):
        await runner.evaluate(CATALOG, selected, bundle, 2, review=review)
    assert len(invocations) == (1 if uncertain else 2)


@pytest.mark.parametrize('budget', [0, -1, 1, 20])
async def test_eval_rejects_budget_before_creating_report(tmp_path, budget):
    bundle = tmp_path / 'report'
    with pytest.raises(ValueError, match='Budget'):
        await runner.evaluate(CATALOG, runner.cases(), bundle, budget)
    assert not bundle.exists()


def test_all_cases_are_synthetic_and_only_19_need_review():
    description = runner.plan(CATALOG, runner.cases())
    assert description['cases'] == list(range(1, 22)) and description['calls_needed'] == 19
    content = runner.FIXTURE.read_text(encoding='utf-8')
    assert '@' not in content and 'instagram.com' not in content


async def test_eval_rejects_stale_catalog_before_any_calls(tmp_path):
    bundle = tmp_path / 'report'
    assert not runner.plan('=== ТУР: Старый каталог ===', runner.cases())['catalog_matches_fixture']
    with pytest.raises(ValueError, match='Catalog'):
        await runner.evaluate('=== ТУР: Старый каталог ===', runner.cases(), bundle, 19)
    assert not bundle.exists()


def test_candidates_include_real_primary_closing_and_keep_date_counterexample():
    from src.ai.prompts import _CLOSING_RULES

    footer = next(line.strip('«»') for line in _CLOSING_RULES.splitlines()
                  if line.startswith('«Наши менеджеры '))
    for case in runner.cases():
        proposal = runner.candidate(case)
        assert proposal['reply'].count(footer) == 1 and proposal['reply'].endswith(footer)
        assert 'Ваш запрос передан' not in proposal['reply']
        if case['id'] in {8, 18}:
            assert proposal['reply'].startswith('На Белосток нет свободных дат.')
