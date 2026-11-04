from unittest.mock import Mock

import pytest

from src.db import faq_db


@pytest.mark.parametrize('directory_exists', [False, True])
def test_loading_without_faq_sources_does_not_open_stale_index(tmp_path, monkeypatch, directory_exists):
    sources = tmp_path / 'faq'
    if directory_exists:
        sources.mkdir()
        (sources / 'README.md').write_text('No verified FAQ yet.', encoding='utf-8')
    monkeypatch.setattr(faq_db, 'FAQ_DIR', sources)
    open_index = Mock(side_effect=AssertionError('Stale index must not be read'))
    monkeypatch.setattr(faq_db, 'get_collection', open_index)

    assert faq_db.load_faq_to_chroma() == 0
    open_index.assert_not_called()


@pytest.mark.parametrize('directory_exists', [False, True])
async def test_search_without_faq_sources_does_not_read_stale_index(tmp_path, monkeypatch, directory_exists):
    sources = tmp_path / 'faq'
    if directory_exists:
        sources.mkdir()
    monkeypatch.setattr(faq_db, 'FAQ_DIR', sources)
    open_index = Mock(side_effect=AssertionError('Stale index must not be read'))
    monkeypatch.setattr(faq_db, 'get_collection', open_index)

    assert await faq_db.search_faq('Как происходит оплата?') == []
    open_index.assert_not_called()


def test_verified_source_can_still_be_loaded(tmp_path, monkeypatch):
    (tmp_path / 'verified.txt').write_text('Q: Verified question\nA: Verified answer', encoding='utf-8')
    monkeypatch.setattr(faq_db, 'FAQ_DIR', tmp_path)
    collection = Mock()
    collection.count.return_value = 0
    monkeypatch.setattr(faq_db, 'get_collection', lambda: collection)

    assert faq_db.load_faq_to_chroma() == 1
    assert collection.add.call_args.kwargs['documents'] == ['Вопрос: Verified question\nОтвет: Verified answer']
    assert collection.add.call_args.kwargs['metadatas'][0]['source'] == 'verified.txt'


async def test_verified_source_keeps_existing_search_working(tmp_path, monkeypatch):
    (tmp_path / 'verified.txt').write_text('Q: Verified question\nA: Verified answer', encoding='utf-8')
    monkeypatch.setattr(faq_db, 'FAQ_DIR', tmp_path)
    collection = Mock()
    collection.count.return_value = 1
    collection.query.return_value = {
        'ids': [['verified_0']], 'documents': [['Verified answer']],
        'metadatas': [[{'source': 'verified.txt'}]], 'distances': [[0.1]],
    }
    monkeypatch.setattr(faq_db, 'get_collection', lambda: collection)

    assert (await faq_db.search_faq('Verified question'))[0]['document'] == 'Verified answer'
    collection.query.assert_called_once_with(query_texts=['Verified question'], n_results=1)
