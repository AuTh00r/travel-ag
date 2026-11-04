"""Ten authorized direct API checks; never runs application handlers or deliveries."""
import argparse
import base64
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import sys
import time

try:
    from scripts import tool_call_probe as probe
except ModuleNotFoundError:
    import tool_call_probe as probe


def semantics(name, result):
    if result is None:
        return False
    reply = result['reply'].lower()
    manager = result['manager']
    if name == 'ad_vague':
        return not reply.strip() and manager is not None
    if not reply.strip():
        return False
    if name in ('problem', 'problem_repeat'):
        return manager is None
    if name == 'vdp':
        return manager is None and all(city in reply for city in ('варшав', 'дрезден', 'праг')) and 'https://docs.google.com/' in reply
    if name == 'manager':
        return manager is not None and 'эльбрус' in (reply + manager['context'].lower())
    if name == 'ad_clear':
        return manager is None and 'эльбрус' in reply and 'https://docs.google.com/' in reply
    if name == 'contact':
        return manager is not None and manager['type'] == 'контакт' and '1112233' not in ''.join(c for c in reply if c.isdigit())
    if name == 'limit':
        return manager is not None and 'лимит' in reply and ('не отправлен' in reply or 'не будет' in reply)
    if name == 'photo':
        return '220' in reply and ('€' in reply or 'евро' in reply)
    if name == 'video10':
        return all(city in reply for city in ('варшав', 'дрезден', 'праг'))
    raise ValueError('Unknown case')


def preflight(args):
    assert not (args.bundle / 'plan.private.json').exists()
    with probe.no_network():
        old = probe.load_bootstrap(args.bootstrap)
        _, main = old.boot()
        from src.ai.prompts import _RESPONSE_RULES, build_full_prompt
        from src.config import MINSK_TZ
        from src.services.llm import get_llm, get_vision_llm
        prior = json.loads(args.prior_inputs.read_text(encoding='utf-8'))
        assert all(probe.sha(args.root / name) == value for name, value in prior['runtime'].items())
        tours = json.loads((args.root / 'data/tours_snapshot.json').read_text(encoding='utf-8-sig'))['text']
        baseline = prior['cases'][0][1]
        cases = [(name, probe.tool_body(baseline, _RESPONSE_RULES, True), False)
                 for name in ('problem', 'problem_repeat')]
        now = datetime.now(MINSK_TZ)
        questions = [
            ('vdp', 'Виза есть! Пришлите программу тура ВДП', 0, '', []),
            ('manager', 'По Эльбрусу хочу поговорить с менеджером, уточнить свободные места', 0, '', []),
            ('ad_vague', 'Расскажите подробнее о вашем объявлении.', 0, 'Источник ADS. Содержимое объявления недоступно; тур неизвестен.', []),
            ('ad_clear', 'Эльбрус. Пришлите программу тура.', 0, 'Источник ADS. Содержимое объявления недоступно.', []),
            ('contact', 'Мой новый номер +375 29 444 55 66. Свяжитесь со мной по нему.', 0, '',
             [{'role': 'user', 'content': 'Мой старый номер +375 29 111 22 33.'},
              {'role': 'assistant', 'content': 'Записал ваш контакт.'}]),
            ('limit', 'Хочу связаться с менеджером по Эльбрусу.', 3, '', []),
            ('photo', 'Какая цена указана на изображении?', 0, '', []),
            ('video10', 'Какой маршрут показан в истории?', 0, '', [])]
        evidence = json.loads((args.media / 'video/evidence.json').read_text(encoding='utf-8'))
        assert evidence['images'] == 10 and evidence['detail'] == 'original' and evidence['audio'] is False
        photo = args.media / 'photo.jpg'
        assert probe.sha(photo) == '91b7bb01f236715919747629c059d513b5a297eb3d7fb2cb047c2a4d2cbf8bf2'
        def image(path, label):
            return {'label': label, 'url': 'data:image/jpeg;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')}
        frames = []
        for frame in evidence['frames']:
            path = args.media / 'video' / frame['file']
            assert probe.sha(path) == frame['sha256'] and path.stat().st_size == frame['bytes']
            frames.append(image(path, frame['label']))
        assert len(frames) == 10
        for name, text, count, ad, history in questions:
            images = [image(photo, 'Фото клиента')] if name == 'photo' else frames if name == 'video10' else None
            messages = build_full_prompt(tours, '', history, text, count,
                current_date=now.date(), current_time=now.strftime('%H:%M'),
                should_greet=False, is_first_message=False, media_images=images,
                media_kind='image' if name == 'photo' else 'story', ad_context=ad)
            body = (get_vision_llm() if images else get_llm())._get_request_payload(messages)
            cases.append((name, probe.tool_body(body, _RESPONSE_RULES, True), bool(ad)))
        assert len(cases) == 10 and len({c[0] for c in cases}) == 10
        for name, body, _ in cases:
            wire = {**body, **body.get('extra_body', {})}
            assert wire.get('max_tokens', wire.get('max_completion_tokens')) == 2048
            assert body.get('stream', False) is False and 'response_format' not in body
            images = [block for message in body['messages'] if isinstance(message['content'], list)
                      for block in message['content'] if block.get('type') == 'image_url']
            assert len(images) == (10 if name == 'video10' else 1 if name == 'photo' else 0)
            assert all(block['image_url']['detail'] == 'original' for block in images)
        assert main._validate_response('{"reply":"ok","manager":null}')[1] is None
    args.bundle.mkdir(parents=True, exist_ok=True)
    with (args.bundle / 'plan.private.json').open('x', encoding='utf-8') as stream:
        json.dump({'cases': cases, 'runtime': prior['runtime'], 'env_sha': probe.sha(args.root / '.env')}, stream, ensure_ascii=False)
    return {'preflight': True, 'external_calls': 0, 'planned_calls': 10, 'photo': 1, 'video_frames': 10, 'detail': 'original'}


def run(args):
    plan = json.loads((args.bundle / 'plan.private.json').read_text(encoding='utf-8'))
    assert len(plan['cases']) == 10
    def preserved():
        return all(probe.sha(args.root / n) == h for n, h in plan['runtime'].items()) and probe.sha(args.root / '.env') == plan['env_sha']
    assert preserved()
    with probe.no_network():
        settings, main = probe.load_bootstrap(args.bootstrap).boot()
        from src.services.llm_response_log import _redact
    rows = []
    with (args.bundle / 'responses.private.jsonl').open('x', encoding='utf-8') as stream:
        for index, (name, body, silent) in enumerate(plan['cases'], 1):
            stream.write(json.dumps({'started_call': index, 'case': name}) + '\n')
            stream.flush()
            started = time.monotonic()
            try:
                status, data = probe.send(deepcopy(body), settings.deepseek_api_key, True)
            except Exception as error:
                stream.write(json.dumps({'call': index, 'case': name, 'transport_error': type(error).__name__}) + '\n')
                stream.flush()
                raise RuntimeError('Transport uncertain; inspect report, do not rerun') from None
            result, reason = probe.extract_tool_result(data, main._validate_response, allow_silent=silent) if status == 200 else (None, 'http_' + str(status))
            row = {'call': index, 'case': name, 'status': status, 'seconds': round(time.monotonic() - started, 2),
                   'valid': result is not None, 'reason': reason, 'semantic_ok': semantics(name, result),
                   'reply_chars': len(result['reply']) if result else None,
                   'has_manager': result['manager'] is not None if result else None,
                   'usage': data.get('usage') if isinstance(data, dict) else None,
                   'model': data.get('model') if isinstance(data, dict) else None}
            stream.write(json.dumps({**row, 'raw_response': _redact(json.dumps(data, ensure_ascii=False))}, ensure_ascii=False) + '\n')
            stream.flush()
            rows.append(row)
            print(json.dumps(row), flush=True)
            if status in (401, 403, 429) or status >= 500:
                raise RuntimeError('Provider unavailable; stop remaining calls')
    assert preserved()
    proof = {'calls': len(rows), 'valid': sum(r['valid'] for r in rows), 'semantic_ok': sum(r['semantic_ok'] for r in rows),
             'runtime_config_preserved': True, 'customer_or_manager_sends': 0, 'rows': rows}
    with (args.bundle / 'proof.json').open('x', encoding='utf-8') as stream:
        json.dump(proof, stream, ensure_ascii=False, indent=2)
    return {k: v for k, v in proof.items() if k != 'rows'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preflight', 'run'])
    for flag in ('root', 'bundle', 'bootstrap', 'prior-inputs', 'media'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(preflight(args) if args.action == 'preflight' else run(args)))
    except Exception as error:
        print(json.dumps({'error': type(error).__name__, 'action': args.action}))
        sys.exit(1)
