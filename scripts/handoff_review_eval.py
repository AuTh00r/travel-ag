"""Standalone synthetic N37 evaluation. Dry-run by default; never runs bot handlers.

Execution requires explicit --execute and a separately authorized --budget.
Each paid call is reserved/fsynced before invocation; an uncertain result stops
the run. Existing reports cannot be reused. No Instagram/Telegram or DB access.
"""
import argparse
import asyncio
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURE = ROOT / 'tests/fixtures/handoff_cases.json'
RUNTIME = ('src/ai/prompts.py', 'src/services/handoff_review.py', 'src/services/llm.py',
           'src/main.py', 'tests/fixtures/handoff_cases.json')


def cases():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def plan(catalog, selected):
    from src.services.llm_response_log import catalog_metadata
    metadata = catalog_metadata(catalog)
    belostok = next((tour for tour in metadata['tours'] if 'белосток' in tour['name'].lower()), {})
    catalog_ok = (not any(case['id'] in {8, 18} for case in selected)
                  or (belostok.get('available') is True and '08.12.2026' in belostok.get('dates', [])))
    return {'cases': [case['id'] for case in selected],
            'calls_needed': sum(case['action'] != 'contact' for case in selected),
            'catalog': metadata, 'catalog_matches_fixture': catalog_ok,
            'runtime': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in RUNTIME}}


def append(path, row):
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def candidate(case):
    from src.ai.prompts import _CLOSING_RULES

    footer = next(line.strip('«»') for line in _CLOSING_RULES.splitlines()
                  if line.startswith('«Наши менеджеры '))
    reply = 'На Белосток нет свободных дат.' if case['id'] in {8, 18} else case['reply']
    return {'reply': reply + '\n\n' + footer, 'manager': {
        'context': case['context'], 'type': 'консультация', 'name': ''}}


async def evaluate(catalog, selected, bundle, budget, *, review=None):
    from src.ai.prompts import build_full_prompt
    from src.config import MINSK_TZ, settings
    from src.main import _response_metadata, _validate_response
    from src.services import llm_response_log
    from src.services.handoff_review import review_manager_candidate

    description = plan(catalog, selected)
    if not 1 <= budget <= 19 or description['calls_needed'] > budget:
        raise ValueError('Budget must cover selected calls, with a maximum of 19')
    if not description['catalog_matches_fixture']:
        raise ValueError('Catalog does not match the Belostok date regressions; refresh catalog or fixtures before paying')
    bundle.mkdir(parents=True, exist_ok=False)
    (bundle / 'plan.json').write_text(json.dumps(description, ensure_ascii=False, indent=2), encoding='utf-8')
    journal = bundle / 'evaluation.jsonl'
    review = review or review_manager_candidate
    old_enabled, old_log = settings.manager_review_enabled, llm_response_log.LOG_PATH
    llm_response_log.close_response_log()
    settings.manager_review_enabled = True
    llm_response_log.LOG_PATH = bundle / 'model-responses.jsonl'
    calls, matches = 0, 0
    try:
        for case in selected:
            if case['action'] == 'contact':
                append(journal, {'case': case['id'], 'mandatory_bypass': True, 'calls': 0})
                continue
            if calls >= budget:
                raise ValueError('Budget exhausted')
            task_id = '1' * 32
            tasks = [{'id': task_id, 'revision': 1, 'summary': case['prior']}] if case.get('prior') else []
            history = ([{'role': 'assistant', 'content': 'Передан вопрос: ' + case['prior']}]
                       if case.get('prior') else [])
            now = datetime.now(MINSK_TZ)
            messages = build_full_prompt(catalog, '', history, case['question'], 3 if case.get('limit') else 0,
                current_date=now.date(), current_time=now.strftime('%H:%M'), should_greet=False,
                is_first_message=False, use_tools=True)
            proposal = candidate(case)
            request_id = uuid4().hex
            calls += 1
            append(journal, {'case': case['id'], 'started_call': calls, 'request_id': request_id})
            decision = await review(messages, proposal, tours_text=catalog, faq_context='', open_tasks=tasks,
                sender_id='synthetic-n37', request_id=request_id, catalog=description['catalog'],
                validate=_validate_response, metadata=_response_metadata)
            matched = (decision.reviewed and decision.action == case['action'] and
                       (case['action'] != 'update' or decision.task_id == task_id))
            matches += int(matched)
            append(journal, {'case': case['id'], 'reviewed': decision.reviewed, 'action': decision.action,
                             'expected': case['action'], 'matches': matched,
                             'reply': decision.response['reply'], 'manager': decision.response['manager']})
            if not decision.reviewed:
                append(journal, {'stopped': 'unconfirmed_review', 'reserved_calls': calls})
                break  # Includes timeout, provider errors and malformed function arguments.
    finally:
        llm_response_log.close_response_log()
        llm_response_log.LOG_PATH = old_log
        settings.manager_review_enabled = old_enabled
    return {'reserved_calls': calls, 'matches': matches, 'required_calls': description['calls_needed']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True, help='Plain text or a snapshot JSON with text')
    parser.add_argument('--case-ids', default='', help='Comma-separated IDs; default all 21')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--budget', type=int, default=0)
    parser.add_argument('--bundle', type=Path)
    args = parser.parse_args()
    catalog = args.catalog.read_text(encoding='utf-8-sig')
    if args.catalog.suffix == '.json':
        catalog = json.loads(catalog)['text']
    if not isinstance(catalog, str) or not 1 <= len(catalog) <= 250_000:
        parser.error('Invalid catalog')
    ids = {int(value) for value in args.case_ids.split(',')} if args.case_ids else set()
    selected = [case for case in cases() if not ids or case['id'] in ids]
    if not selected or (ids and ids != {case['id'] for case in selected}):
        parser.error('Unknown case ID')
    if not args.execute:
        print(json.dumps(plan(catalog, selected), ensure_ascii=False, indent=2))
        return
    if args.bundle is None:
        parser.error('--execute requires a new --bundle directory')
    result = asyncio.run(evaluate(catalog, selected, args.bundle, args.budget))
    print(json.dumps(result))
    if result['matches'] != result['required_calls']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
