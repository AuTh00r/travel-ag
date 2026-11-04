"""Open manager questions and per-chat notification versions in the receipt journal.

The caller owns the transaction. No network I/O or model decisions here.
"""

from uuid import NAMESPACE_URL, uuid4, uuid5

from src.config import settings
from src.db import sessions


def ensure_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS manager_tasks (
            id TEXT PRIMARY KEY, client_id TEXT NOT NULL, summary TEXT NOT NULL,
            revision INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'open',
            counted INTEGER NOT NULL DEFAULT 0, manager_epoch TEXT NOT NULL,
            created_at REAL NOT NULL, updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS manager_tasks_client ON manager_tasks(client_id,status,updated_at);
        CREATE TABLE IF NOT EXISTS manager_task_changes (
            client_id TEXT NOT NULL, source_key TEXT NOT NULL, task_id TEXT NOT NULL,
            revision INTEGER NOT NULL, PRIMARY KEY(client_id,source_key)
        );
    """)
    task_columns = {row[1] for row in conn.execute('PRAGMA table_info(manager_tasks)')}
    if 'kind' not in task_columns:
        conn.execute("ALTER TABLE manager_tasks ADD COLUMN kind TEXT NOT NULL DEFAULT 'consultation'")
    columns = {row[1] for row in conn.execute('PRAGMA table_info(inbound_deliveries)')}
    for name, kind in [('manager_task_id', 'TEXT'), ('task_revision', 'INTEGER'),
                       ('operation', "TEXT NOT NULL DEFAULT 'send'"), ('target_message_id', 'TEXT')]:
        if name not in columns:
            conn.execute(f'ALTER TABLE inbound_deliveries ADD COLUMN {name} {kind}')
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS manager_task_delivery ON inbound_deliveries'
                 '(manager_task_id,task_revision,destination) WHERE manager_task_id IS NOT NULL')


def close_client(conn, client):
    """Manager takeover is permanent for these tasks, even if the pause is cleared."""
    conn.execute("UPDATE manager_tasks SET status='closed' WHERE client_id=? AND status='open'", (client,))
    conn.execute("UPDATE inbound_deliveries SET state='cancelled' WHERE client_id=? "
                 "AND manager_task_id IS NOT NULL AND state IN ('ready','retry_wait','blocked')", (client,))


def open_tasks(client, *, store=None):
    from src.db.inbound import InboundStore

    store = store or InboundStore()
    with store.connection() as conn:
        cutoff = store.clock() - settings.escalation_reset_hours * 3600
        return [dict(row) for row in conn.execute(
            "SELECT id,revision,summary FROM manager_tasks WHERE client_id=? AND status='open' AND kind='consultation' "
            'AND updated_at>=? ORDER BY updated_at DESC,rowid DESC LIMIT 8', (client, cutoff))]


def recover_legacy_intents():
    """Once at process start: an interrupted legacy HTTP call is uncertain."""
    from src.db.inbound import InboundStore

    if not sessions.DB_PATH.is_file():
        return
    with InboundStore().connection() as conn:
        conn.execute("UPDATE inbound_deliveries SET state='unknown' WHERE job_id IS NULL "
                     "AND manager_task_id IS NOT NULL AND state='sending'")


def due_legacy_operations(store):
    with store.connection() as conn:
        return [dict(row) for row in conn.execute(
            'SELECT d.* FROM inbound_deliveries d JOIN manager_tasks t ON t.id=d.manager_task_id '
            "WHERE d.job_id IS NULL AND d.channel='telegram' AND d.state IN ('ready','retry_wait') "
            "AND t.status='open' AND t.client_id=d.client_id AND t.revision=d.task_revision "
            'AND d.due<=? ORDER BY d.due,d.rowid LIMIT 32', (store.clock(),))]


def plan(conn, *, client, summary, decision, text, destinations, now, source_key, job_id=None):
    """CAS the semantic decision and write immutable HTTP intents atomically."""
    from src.db.inbound import StaleWork

    state, _ = sessions.read_row(conn, client)
    if sessions.is_manager_active(state, settings.manager_takeover_ttl_minutes):
        raise StaleWork('manager_takeover')
    previous = conn.execute('SELECT * FROM manager_task_changes WHERE client_id=? AND source_key=?',
                            (client, source_key)).fetchone()
    if previous:
        task = conn.execute("SELECT * FROM manager_tasks WHERE id=? AND status='open'",
                            (previous['task_id'],)).fetchone()
        if not task or task['revision'] != previous['revision']:
            raise StaleWork('manager_task_superseded')
        return task['id'], _deliveries(conn, task['id'], previous['revision'])

    epoch = state.get('manager_last_at') or ''
    if decision.action == 'update':
        task = conn.execute("SELECT * FROM manager_tasks WHERE id=? AND client_id=? AND status='open' AND kind='consultation'",
                            (decision.task_id, client)).fetchone()
        if (not task or task['revision'] != decision.task_revision or task['manager_epoch'] != epoch
                or task['updated_at'] < now - settings.escalation_reset_hours * 3600):
            raise StaleWork('manager_task_changed')
        if conn.execute("SELECT 1 FROM inbound_deliveries WHERE manager_task_id=? AND state='sending'",
                        (task['id'],)).fetchone():
            raise StaleWork('manager_task_inflight')
        task_id, revision = task['id'], task['revision'] + 1
        conn.execute('UPDATE manager_tasks SET summary=?,revision=?,updated_at=? WHERE id=?',
                     (summary, revision, now, task_id))
    elif decision.action in {'new', 'technical'}:
        if decision.action != 'technical' and sessions.effective_escalation_count(state, settings.escalation_reset_hours) >= 3:
            raise StaleWork('manager_limit')
        task_id = uuid5(NAMESPACE_URL, 'manager:' + client + ':' + source_key).hex
        revision = 1
        conn.execute('INSERT INTO manager_tasks(id,client_id,summary,revision,manager_epoch,created_at,updated_at,kind) '
                     'VALUES (?,?,?,?,?,?,?,?)', (task_id, client, summary, revision, epoch, now, now,
                     'technical' if decision.action == 'technical' else 'consultation'))
    else:
        raise StaleWork('invalid_manager_operation')

    conn.execute('INSERT INTO manager_task_changes VALUES (?,?,?,?)', (client, source_key, task_id, revision))
    for destination in dict.fromkeys(destinations):
        uncertain = conn.execute("SELECT 1 FROM inbound_deliveries WHERE manager_task_id=? AND destination=? "
                                 "AND state='unknown'", (task_id, destination)).fetchone()
        receipt = conn.execute("SELECT receipt FROM inbound_deliveries WHERE manager_task_id=? AND destination=? "
                               "AND state='sent' AND receipt IS NOT NULL ORDER BY task_revision DESC LIMIT 1",
                               (task_id, destination)).fetchone()
        target = receipt['receipt'] if receipt else None
        if target is not None and (not str(target).isdigit() or int(target) <= 0):
            raise StaleWork('invalid_manager_receipt')
        # A newer version may replace only operations proven not to have been sent.
        conn.execute("UPDATE inbound_deliveries SET state='cancelled' WHERE manager_task_id=? AND destination=? "
                     "AND state IN ('ready','retry_wait')", (task_id, destination))
        conn.execute('INSERT INTO inbound_deliveries(id,job_id,client_id,channel,destination,part,payload,state,'
                     'due,created_at,updated_at,manager_task_id,task_revision,operation,target_message_id) '
                     "VALUES (?,?,?,'telegram',?,?,?,?,?,?,?,?,?,?,?)",
                     (uuid4().hex, job_id, client, destination, int(decision.action == 'technical'), text, 'unknown' if uncertain else 'ready',
                      now, now, now, task_id, revision, 'edit' if target else 'send', target))
    return task_id, _deliveries(conn, task_id, revision)


def _deliveries(conn, task_id, revision):
    return [dict(row) for row in conn.execute('SELECT * FROM inbound_deliveries WHERE manager_task_id=? '
                                             'AND task_revision=? ORDER BY rowid', (task_id, revision))]


def can_start(conn, delivery):
    if not delivery['manager_task_id']:
        return True
    task = conn.execute('SELECT * FROM manager_tasks WHERE id=? AND client_id=?',
                        (delivery['manager_task_id'], delivery['client_id'])).fetchone()
    state, _ = sessions.read_row(conn, delivery['client_id'])
    return bool(task and task['status'] == 'open' and task['revision'] == delivery['task_revision']
                and task['manager_epoch'] == (state.get('manager_last_at') or '')
                and not sessions.is_manager_active(state, settings.manager_takeover_ttl_minutes))


def count_confirmed(conn, delivery):
    """Called with a confirmed receipt, including legacy operations with job_id=NULL."""
    if not delivery['manager_task_id']:
        return False
    return conn.execute("UPDATE manager_tasks SET counted=1 WHERE id=? AND client_id=? AND counted=0 AND kind='consultation'",
                        (delivery['manager_task_id'], delivery['client_id'])).rowcount == 1


def begin_legacy(store, delivery):
    from src.db.inbound import StaleWork

    with store.connection() as conn:
        row = conn.execute('SELECT * FROM inbound_deliveries WHERE id=?', (delivery['id'],)).fetchone()
        if not row or row['job_id'] is not None or not row['manager_task_id'] or not can_start(conn, row):
            raise StaleWork('manager_task_changed')
        return conn.execute("UPDATE inbound_deliveries SET state='sending',intent_at=?,updated_at=?,"
                            "attempts=attempts+1 WHERE id=? AND state IN ('ready','retry_wait') AND due<=?",
                            (store.clock(), store.clock(), row['id'], store.clock())).rowcount == 1
