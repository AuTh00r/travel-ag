"""Date formatting must never manufacture a sold-out tour."""
from datetime import date

import pytest

from src.services.llm_response_log import catalog_metadata
from src.services.tour_loader import _extract_tour_section, _parse_date_range
from src.services.tour_sync import build_snapshot

TODAY = date(2026, 11, 2)


def section(*lines):
    return _extract_tour_section('Тест', list(lines), today=TODAY)


@pytest.mark.parametrize('label', ['Когда:', 'КОГДА:', 'когда:', 'Даты:', 'ДАТЫ:',
                                  'Дата выезда:', 'Даты выезда:', 'ДАТЫ ВЫЕЗДА —'])
def test_labels_shared_with_drive(label):
    text = f'{label} 08.12.2026 - 10.12.2026'
    direct = section(text)
    snapshot, skipped = build_snapshot({'id': {'name': 'Тест', 'text': text}}, {}, today=TODAY)
    assert not skipped
    for result in (direct, snapshot['text']):
        assert 'Когда (ближайшие свободные даты): 08.12.2026 - 10.12.2026' in result
        assert 'Свободных дат нет' not in result


@pytest.mark.parametrize('text', ['Когда: 08.12.2026', 'Даты: 08.12.2026 (мало мест)',
                                  'Когда: 08 . 12 . 2026 ‑ 10 . 12 . 2026',
                                  'Когда:\n08.12.2026 - 10.12.2026',
                                  'Даты:\u00a008.12.2026\u202f−\u00a010.12.2026'])
def test_single_spacing_and_heading(text):
    result = section(*text.splitlines())
    assert 'Когда (ближайшие свободные даты): 08.12.2026' in result
    assert 'Даты требуют уточнения' not in result


@pytest.mark.parametrize('lines', [[], ['Когда:'], ['Когда: декабрь'], ['Когда: 08.12'],
                                  ['08.12 - 10.12'], ['Когда: 31.02.2027 - 05.03.2027'],
                                  ['Когда: 08.12.2026 - 40.12.2026'],
                                  ['Когда: 10.12.2026 - 08.12.2026'],
                                  ['Когда: 08.12.2026 (мест нет)', 'Даты: уточняются'],
                                  ['Когда: 01.01.2026 - 03.01.2026', '08/12/2026']])
def test_unknown_is_not_sold_out(lines):
    result = section(*lines, 'Программа: музей и прогулка')
    assert 'Даты требуют уточнения' in result
    assert 'Свободных дат нет' not in result
    assert 'Программа: музей и прогулка' in result
    assert catalog_metadata(result)['tours'][0]['available'] is None


def test_mixed_unknown_keeps_confirmed_dates():
    result = section('Когда: 08.12.2026 - 10.12.2026', 'Даты: уточняются')
    assert 'Когда (ближайшие свободные даты): 08.12.2026 - 10.12.2026' in result
    assert 'Даты требуют уточнения' in result
    assert catalog_metadata(result)['tours'][0]['available'] is True


def test_known_closed_and_past_still_closed():
    result = section('Когда: 08.12.2026 (мест нет)', '01.01.2026 - 03.01.2026')
    assert 'Свободных дат нет' in result
    assert 'Даты требуют уточнения' not in result
    assert catalog_metadata(result)['tours'][0]['available'] is False


@pytest.mark.parametrize('line', ['08.12.2026 посещение музея', '10 день: прогулка',
                                  'Музей работает 08.12.2026 - 10.12.2026'])
def test_description_is_not_a_departure(line):
    result = section('Когда: 15.12.2026 - 17.12.2026', line)
    dates = next(x for x in result.splitlines() if x.startswith('Когда ('))
    assert dates.endswith('15.12.2026 - 17.12.2026')
    assert 'Даты требуют уточнения' not in result
    assert line in result


def test_single_date_after_description_stays_description():
    result = section('Когда: 15.12.2026 - 17.12.2026', 'Программа музея', '08.12.2026')
    assert 'Даты требуют уточнения' not in result
    assert result.endswith('Программа музея\n08.12.2026')


@pytest.mark.parametrize('tail', [[], ['Программа: музей'], ['Виза - НУЖНА']])
def test_unfinished_heading_after_closed_date_is_unknown(tail):
    result = section('Когда: 01.01.2026', 'Даты:', *tail)
    assert 'Даты требуют уточнения' in result
    assert 'Свободных дат нет' not in result


def test_text_month_continuation_is_unknown():
    result = section('Когда: 01.01.2026', '08 декабря 2026')
    assert 'Даты требуют уточнения' in result
    assert 'Свободных дат нет' not in result


@pytest.mark.parametrize('boundary', ['Программа: музей', 'Виза - НУЖНА'])
@pytest.mark.parametrize('body_date', ['31.12.2026', '12.12.2026 - 13.12.2026'])
def test_date_block_ends_at_other_fields(boundary, body_date):
    result = section('Когда: 08.12.2026', boundary, body_date)
    dates = next(line for line in result.splitlines() if line.startswith('Когда ('))
    assert dates.endswith('08.12.2026')
    assert result.endswith(body_date)


def test_program_standalone_range_not_a_departure():
    result = section('Когда: 08.12.2026', 'Программа: музей', '12.12.2026 - 13.12.2026')
    dates = next(line for line in result.splitlines() if line.startswith('Когда ('))
    assert dates.endswith('08.12.2026')
    assert result.endswith('12.12.2026 - 13.12.2026')


@pytest.mark.parametrize('line', ['08.12.2026 - 40.12.2026', '10.12.2026 - 08.12.2026',
                                  '08.12', '08.12 - 10.12'])
def test_invalid_or_yearless_records(line):
    assert _parse_date_range(line) is None


@pytest.mark.parametrize('tools', [False, True])
def test_unknown_date_rule_is_shared_by_response_modes(tools):
    from src.ai.prompts import build_full_prompt
    messages = build_full_prompt(section('Даты: уточняются'), '', [], 'Пришлите программу', 0,
                                 current_date=TODAY, use_tools=tools)
    system = messages[0].content
    assert 'просьба программы сама по себе не требует manager' in system
    assert 'Даты требуют уточнения' in system
    assert 'при частичных данных не называй список исчерпывающим' in system
