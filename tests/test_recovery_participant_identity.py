import pytest

from tests.test_recovery_scan_budget import scanner as scanner
from tests.test_inbound_recovery import clock as clock


@pytest.mark.parametrize('participants', [None, [], 'bad', {}, {'data': None},
    {'data': {}}, {'data': [None]}, {'data': [{}]}, {'data': [{'id': None}]},
    {'data': [{'id': True}]}, {'data': [{'id': ''}]}, {'data': [{'id': 'None'}]},
    {'data': [{'id': 0}]}, {'data': [{'id': -2}]}, {'data': [{'id': '１００１'}]},
    {'data': [{'id': '1001'}, {'id': None}]},
    {'data': [{'id': 'account'}, {'id': None}]},
    {'data': [{'id': 'account'}]}])
async def test_incomplete_identity_never_counts_as_scanned_or_reads_messages(scanner, participants):
    scanner.channel.list_conversations.return_value = {'data': [
        {'id': 'incomplete', 'participants': participants}], 'after': None}
    await scanner.reconcile_tick()
    scanner.channel.list_conversation_messages.assert_not_awaited()
    assert scanner.store.get_sync('complete_scan:account') is None
    assert scanner.store.get_sync('dialog_gap:incomplete')['reason'] == 'incomplete_identity'


async def test_duplicate_valid_participant_is_resolved_once(scanner):
    await scanner.sync_dialog({'id': 'target', 'participants': {'data': [
        {'id': 'account'}, {'id': '1001'}, {'id': '1001'}]}})
    scanner.channel.list_conversation_messages.assert_awaited_once_with('target')


async def test_known_foreign_identity_is_excluded_without_reading(scanner):
    assert await scanner.sync_dialog({'id': 'foreign', 'participants': {'data': [
        {'id': 'account'}, {'id': '2002'}]}})
    scanner.channel.list_conversation_messages.assert_not_awaited()
