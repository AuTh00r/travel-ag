from datetime import date

import pytest

from src.services import tour_sync as sync
from src.services.tour_loader import _extract_tour_section, _split_tours

URL = 'https://sundita.by/tur/example/'
DOC = 'https://docs.google.com/document/d/source'
BODY = 'Куда: Минск — Прага\nКогда: 12.12.2027 - 17.12.2027\n'


@pytest.mark.parametrize('label', ['Ссылка на бронирование', 'ссылка на бронь',
    'ССЫЛКА НА ТУР НА САЙТЕ', 'Ссылка на тур', 'ссылка', 'Тур на сайте',
    'ссылка на сайт', 'Бронирование на сайте', 'ссылка\u00a0на\u00a0тур на сайте'])
@pytest.mark.parametrize('separator', [' ', ': ', ' —\n'])
def test_booking_labels_reach_catalog_prompt_and_bootstrap(label, separator):
    text = BODY + label + separator + URL
    snapshot, skipped = sync.build_snapshot({'source': {'name': 'Тур', 'text': text}}, {}, today=date(2026, 11, 1))
    assert not skipped and snapshot['tours'][0]['booking_url'] == URL
    assert 'Ссылка на бронирование: ' + URL in snapshot['text']
    assert 'Ссылка на тур: ' + DOC in snapshot['text']
    assert sync.seed_bookings_from_text('=== ТУР: Тур ===\n' + text) == {'Тур': URL}


@pytest.mark.parametrize('url', [DOC, 'https://drive.google.com/file/d/source/view',
    'HTTPS://DOCS.GOOGLE.COM/document/d/source'])
def test_program_links_are_not_booking_links(url):
    snapshot, _ = sync.build_snapshot({'source': {'name': 'Тур', 'text': BODY + 'ссылка на тур: ' + url}}, {})
    assert snapshot['tours'][0]['booking_url'] == ''
    assert 'Ссылка на бронирование:' not in snapshot['text']


def test_explicit_booking_beats_generic_link_in_all_paths():
    text = BODY + 'ссылка: https://sundita.by/\nССЫЛКА НА БРОНИРОВАНИЕ: ' + URL
    snapshot, _ = sync.build_snapshot({'source': {'name': 'Тур', 'text': text}}, {})
    assert snapshot['tours'][0]['booking_url'] == URL
    assert 'Ссылка на бронирование: ' + URL in snapshot['text']
    assert sync.seed_bookings_from_text('=== ТУР: Тур ===\n' + text) == {'Тур': URL}


def test_unlabelled_or_unrelated_link_does_not_replace_carried_booking():
    for line in ['Подробности https://example.org/', 'Ссылка на Instagram: https://instagram.com/test/']:
        snapshot, _ = sync.build_snapshot({'source': {'name': 'Тур', 'text': BODY + line}}, {'source': URL})
        assert snapshot['tours'][0]['booking_url'] == URL


def test_loader_preserves_program_and_booking_roles():
    text = _extract_tour_section('Тур', [BODY, 'ссылка на тур на сайте ' + URL,
        'Ссылка на тур - ' + DOC], today=date(2026, 11, 1))
    assert 'Ссылка на тур: ' + DOC in text
    assert 'Ссылка на бронирование: ' + URL in text


def test_generic_references_do_not_split_before_explicit_booking():
    paragraphs = ['Куда: Тур A', 'Ссылка: https://sundita.by/', 'Описание A',
        'ССЫЛКА НА БРОНИРОВАНИЕ: ' + URL, 'Куда: Тур B', 'ссылка на тур https://sundita.by/tur/b/',
        'Описание B', 'Ссылка на бронирование: https://sundita.by/tur/b-booking/']
    blocks = _split_tours(paragraphs)
    assert len(blocks) == 2
    assert blocks[0] == paragraphs[:4] and blocks[1] == paragraphs[4:]
