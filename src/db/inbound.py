"""Durable inbound work and delivery receipts in the existing session database.

All methods are short, synchronous SQLite transactions. Never perform network
I/O while a transaction is open. Times are UTC epoch seconds, independent of
the Windows locale. The feature flag is checked by callers, not this store.
"""

import json
import math
import sqlite3
import time
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from src.db import sessions

TERMINAL = ("done", "cancelled", "failed_final", "blocked", "incomplete")


class StaleWork(Exception):
    """A manager, a new session revision, or a new source invalidated this work."""


def dumps(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), default=str)


def timestamp(value, default=None):
    try:
        if isinstance(value, (int, float)):
            return float(value) / 1000 if value > 100_000_000_000 else float(value)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp()
    except (ValueError, TypeError, AttributeError):
        return default


class InboundStore:
    def __init__(self, path=None, clock=time.time):
        self.path = path  # None follows sessions.DB_PATH, including isolated tests.
        self.clock = clock
        self._initialized_path = None
        self.merge = None
        self.allowed = lambda client: True

    @contextmanager
    def connection(self):
        path = self.path or sessions.DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.create_function("inbound_allowed", 1, lambda client: int(self.allowed(client)))
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            if self._initialized_path != str(path):
                self._schema(conn)
                self._initialized_path = str(path)
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _schema(conn):
        sessions.ensure_schema(conn)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS inbound_events (
                account TEXT NOT NULL, mid TEXT NOT NULL, client_id TEXT NOT NULL,
                event_time REAL NOT NULL, received_at REAL NOT NULL,
                payload TEXT NOT NULL, sources TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
                job_id TEXT, PRIMARY KEY(account,mid)
            );
            CREATE INDEX IF NOT EXISTS inbound_unassigned ON inbound_events(job_id,received_at);
            CREATE TABLE IF NOT EXISTS inbound_jobs (
                id TEXT PRIMARY KEY, account TEXT NOT NULL, client_id TEXT NOT NULL,
                payload TEXT NOT NULL, members TEXT NOT NULL, versions TEXT NOT NULL,
                state TEXT NOT NULL, outcome TEXT, reason TEXT, result TEXT,
                due REAL NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                technical_attempts INTEGER NOT NULL DEFAULT 0,
                semantic_used INTEGER NOT NULL DEFAULT 0, recovered INTEGER NOT NULL DEFAULT 0,
                claim TEXT, lease_until REAL, session_revision INTEGER,
                notification_counted INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS inbound_due ON inbound_jobs(state,due);
            CREATE TABLE IF NOT EXISTS inbound_deliveries (
                id TEXT PRIMARY KEY, job_id TEXT, client_id TEXT NOT NULL,
                channel TEXT NOT NULL, destination TEXT NOT NULL, part INTEGER NOT NULL,
                payload TEXT NOT NULL, state TEXT NOT NULL, due REAL NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, receipt TEXT, intent_at REAL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                UNIQUE(job_id,channel,destination,part)
            );
            CREATE INDEX IF NOT EXISTS inbound_receipts ON inbound_deliveries(channel,receipt);
            CREATE TABLE IF NOT EXISTS inbound_sync (key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS pending_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, recipient_id TEXT NOT NULL,
                text TEXT NOT NULL, created_at TEXT NOT NULL,retry_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0
            );
        """)
        columns = {r[1] for r in conn.execute("PRAGMA table_info(pending_messages)")}
        if "recovery_delivery_id" not in columns:
            conn.execute("ALTER TABLE pending_messages ADD COLUMN recovery_delivery_id TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS pending_recovery_delivery "
                     "ON pending_messages(recovery_delivery_id)")
        job_columns = {r[1] for r in conn.execute('PRAGMA table_info(inbound_jobs)')}
        if 'model_attempts' not in job_columns:
            conn.execute('ALTER TABLE inbound_jobs ADD COLUMN model_attempts INTEGER NOT NULL DEFAULT 0')
        if 'model_attempt_log' not in job_columns:
            conn.execute("ALTER TABLE inbound_jobs ADD COLUMN model_attempt_log TEXT NOT NULL DEFAULT '[]'")
        from src.db.manager_tasks import ensure_schema
        ensure_schema(conn)
        conn.commit()

    def get_sync(self, key, default=None):
        with self.connection() as conn:
            row = conn.execute("SELECT value FROM inbound_sync WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    @staticmethod
    def _set_sync(conn, key, value):
        conn.execute("INSERT INTO inbound_sync VALUES (?,?) ON CONFLICT(key) "
                     "DO UPDATE SET value=excluded.value", (key, dumps(value)))

    def set_sync(self, key, value):
        with self.connection() as conn:
            self._set_sync(conn, key, value)

    def initialize(self, account, clients=None):
        with self.connection() as conn:
            keys = (["baseline:" + account] if clients is None else
                    ["baseline:" + account + ":client:" + client for client in clients])
            for key in keys:
                if not conn.execute("SELECT 1 FROM inbound_sync WHERE key=?", (key,)).fetchone():
                    self._set_sync(conn, key, self.clock())
            scope = "all" if clients is None else sorted(clients)
            row = conn.execute("SELECT value FROM inbound_sync WHERE key=?", ("scope:"+account,)).fetchone()
            if not row or json.loads(row[0]) != scope:
                self._set_sync(conn, "scope:"+account, scope)
                for key in ("scan:", "complete_scan:", "next_scan:"):
                    conn.execute("DELETE FROM inbound_sync WHERE key=?", (key+account,))
            return self._baseline(conn, account, clients[0] if clients else None)

    def _baseline(self, conn, account, client):
        for key in (["baseline:"+account+":client:"+client] if client else []) + ["baseline:"+account]:
            row = conn.execute("SELECT value FROM inbound_sync WHERE key=?", (key,)).fetchone()
            if row:
                return json.loads(row[0])
        return self.clock()

    def baseline_for(self, account, client):
        with self.connection() as conn:
            return self._baseline(conn, account, client)

    def persist(self, account, events, source="webhook"):
        """Persist the whole webhook atomically. A duplicate may enrich its owner.

        API metadata never overwrites richer webhook values. Manager cancellation
        and the session pause are committed with the manager event, before ACK.
        """
        accepted = []
        with self.connection() as conn:
            for original in events:
                event = deepcopy(original)
                mid = event.get("mid")
                client = event.get("sender_id") or event.get("client_id")
                if not mid or not client or not self.allowed(client):
                    continue
                baseline = self._baseline(conn, account, client)
                when = timestamp(event.get("_event_time"), self.clock())
                row = conn.execute("SELECT * FROM inbound_events WHERE account=? AND mid=?",
                                   (account, mid)).fetchone()
                if row:
                    previous = json.loads(row["payload"])
                    sources = set(json.loads(row["sources"]))
                    richer = source == "webhook" and "webhook" not in sources
                    merged = deepcopy(event) if richer else previous
                    if richer:
                        merged.setdefault("_event_time", previous.get("_event_time"))
                        merged.pop("_context_incomplete", None)
                        merged.pop("_api_only", None)
                        merged.pop("_source_issues", None)
                    sources.add(source)
                    changed = richer and dumps(merged) != dumps(previous)
                    conn.execute("UPDATE inbound_events SET payload=?,sources=?,version=version+? "
                                 "WHERE account=? AND mid=?", (dumps(merged), dumps(sorted(sources)),
                                                              int(changed), account, mid))
                    if (changed and row["job_id"] == "ignored" and row["event_time"] >= baseline
                            and event.get("kind") not in ("ignored", "story_context", "own_echo", "manager", "ambiguous_echo")):
                        conn.execute("UPDATE inbound_events SET job_id=NULL WHERE account=? AND mid=?", (account, mid))
                    if changed and row["job_id"]:
                        job = conn.execute("SELECT * FROM inbound_jobs WHERE id=?", (row["job_id"],)).fetchone()
                        if job and job["state"] not in TERMINAL:
                            dispatched = conn.execute("SELECT 1 FROM inbound_deliveries WHERE job_id=? "
                                "AND state IN ('sending','sent','unknown')", (job["id"],)).fetchone()
                            if dispatched:
                                conn.execute("UPDATE inbound_jobs SET state='unknown',reason='source_changed_after_send' "
                                             "WHERE id=?", (job["id"],))
                                self._clear_projections(conn, job["id"])
                            else:
                                self._refresh_payload(conn, job)
                    continue
                old = when < baseline
                terminal = event.get("kind") in ("ignored", "own_echo", "story_context") or old
                conn.execute("INSERT INTO inbound_events(account,mid,client_id,event_time,received_at,"
                             "payload,sources,job_id) VALUES (?,?,?,?,?,?,?,?)",
                             (account, mid, client, when, self.clock(), dumps(event), dumps([source]),
                              "ignored" if terminal else None))
                accepted.append(event)
                if event.get("kind") == "manager" and not old:
                    self._cancel_client(conn, client, event.get("text", ""), when)
                    conn.execute("UPDATE inbound_events SET job_id='manager' WHERE account=? AND mid=?", (account, mid))
                elif event.get("kind") == "ambiguous_echo" and not old:
                    conn.execute("UPDATE inbound_jobs SET state='unknown',reason='ambiguous_outgoing',claim=NULL "
                                 "WHERE id IN (SELECT job_id FROM inbound_deliveries WHERE client_id=? AND state='sending') "
                                 "AND state NOT IN ('done','cancelled','failed_final')", (client,))
                    conn.execute("DELETE FROM pending_messages WHERE recovery_delivery_id IN "
                                 "(SELECT d.id FROM inbound_deliveries d JOIN inbound_jobs j ON j.id=d.job_id "
                                 "WHERE d.client_id=? AND j.state='unknown')", (client,))
                    conn.execute("UPDATE inbound_events SET job_id='ambiguous' WHERE account=? AND mid=?", (account, mid))
        return accepted

    def _refresh_payload(self, conn, job):
        # Rebuild the same owner: no client-wide budget inheritance or history duplicate.
        self._clear_projections(conn, job["id"])
        conn.execute("DELETE FROM inbound_deliveries WHERE job_id=?", (job["id"],))
        rows = conn.execute("SELECT * FROM inbound_events WHERE job_id=? ORDER BY event_time,mid", (job["id"],)).fetchall()
        active_rows = []
        for row in rows:
            if json.loads(row["payload"]).get("kind") in ("ignored", "story_context", "own_echo"):
                conn.execute("UPDATE inbound_events SET job_id='ignored' WHERE account=? AND mid=?", (row["account"], row["mid"]))
            else:
                active_rows.append(row)
        rows = active_rows
        if not rows:
            conn.execute("UPDATE inbound_jobs SET state='done',outcome='ignored',reason='source_reclassified_terminal',"
                         "claim=NULL,updated_at=? WHERE id=?", (self.clock(), job["id"]))
            state, revision = sessions.read_row(conn, job["client_id"])
            history = state.get("history", [])
            kept = [entry for entry in history if entry.get("_inbound_job") != job["id"]]
            if kept != history:
                state["history"] = kept
                self._write_own_session(conn, job["client_id"], state, revision)
            return
        events = [json.loads(row["payload"]) for row in rows]
        merged = self.merge(events) if self.merge else events
        if len(merged) != 1 or job["technical_attempts"] >= 2:
            conn.execute("UPDATE inbound_jobs SET state='incomplete',reason='source_changed_requires_review',claim=NULL WHERE id=?", (job["id"],))
            return
        payload = merged[0]
        previous_payload = json.loads(job["payload"])
        if (not payload.get("_ad_text_only") and previous_payload.get("_story_hint")
                and payload.get("text") == previous_payload.get("text")
                and payload.get("kind") == "user" and not any(key in payload for key in
                    ("story", "images", "shared_sources", "voice_parts", "visual_parts", "non_text", "phone_card"))):
            payload["story"] = previous_payload["story"]
            payload["_story_hint"] = True
        payload["_original_time"] = min(row["event_time"] for row in rows)
        payload["_context_incomplete"] = any(event.get("_context_incomplete") for event in events)
        payload["_source_issues"] = list(dict.fromkeys(issue for event in events for issue in event.get("_source_issues", [])))
        conn.execute("UPDATE inbound_jobs SET state='retry_wait',reason='source_enriched',claim=NULL,payload=?,versions=?,members=?,"
                     "result=NULL,technical_attempts=technical_attempts+1,due=?,updated_at=? WHERE id=?",
                     (dumps(payload), dumps({row["mid"]: row["version"] for row in rows}),
                      dumps([row["mid"] for row in rows]),
                      self.clock()+(120, 480)[job["technical_attempts"]], self.clock(), job["id"]))

    @staticmethod
    def _clear_projections(conn, job_id):
        conn.execute("DELETE FROM pending_messages WHERE recovery_delivery_id IN "
                     "(SELECT id FROM inbound_deliveries WHERE job_id=?)", (job_id,))

    @staticmethod
    def _write_own_session(conn, client, state, revision):
        if not sessions.write_row(conn, client, state, revision):
            return False
        # Another recovery job for the same client is a known writer, not an
        # unexplained manager/admin revision. Keep earlier saved answers alive.
        conn.execute("UPDATE inbound_jobs SET session_revision=? WHERE client_id=? AND session_revision=? "
                     "AND state='delivering'", (revision+1, client, revision))
        return True

    def _cancel_client(self, conn, client, manager_text="", when=None):
        from src.db.manager_tasks import close_client
        close_client(conn, client)
        conn.execute("DELETE FROM pending_messages WHERE recovery_delivery_id IN "
                     "(SELECT id FROM inbound_deliveries WHERE client_id=?)", (client,))
        conn.execute("UPDATE inbound_jobs SET state='cancelled',reason='manager_takeover',claim=NULL "
                     "WHERE client_id=? AND state NOT IN ('done','cancelled','failed_final')", (client,))
        conn.execute("UPDATE inbound_deliveries SET state='cancelled' WHERE client_id=? "
                     "AND state IN ('ready','retry_wait','blocked')", (client,))
        conn.execute("UPDATE inbound_events SET job_id='manager' WHERE client_id=? AND job_id IS NULL", (client,))
        state, revision = sessions.read_row(conn, client)
        manager_at = max(timestamp(state.get("manager_last_at"), 0), when or self.clock())
        state["manager_last_at"] = datetime.fromtimestamp(manager_at, timezone.utc).isoformat()
        if manager_text:
            state.setdefault("history", []).append({"role": "assistant", "content": manager_text})
        sessions.write_row(conn, client, state, revision)

    def pending_batches(self, wait=5):
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM inbound_events WHERE job_id IS NULL AND inbound_allowed(client_id) ORDER BY received_at,rowid").fetchall()
            batches = {}
            for row in rows:
                batches.setdefault(row["client_id"], []).append(dict(row))
            ready = []
            for rows in batches.values():
                group = [rows[0]]
                for row in rows[1:]:
                    if row["received_at"] > group[-1]["received_at"] + wait:
                        break  # A delayed worker must preserve an earlier quiet gap.
                    group.append(row)
                if group[-1]["received_at"] + wait <= self.clock():
                    ready.append(group)
            return ready

    def story_hint(self, client, before, ttl=600, mid=None):
        before = timestamp(before)
        if before is None or not math.isfinite(before):
            return None
        with self.connection() as conn:
            rows = conn.execute("SELECT mid,payload,event_time FROM inbound_events WHERE client_id=? "
                "AND event_time<=? AND event_time>? ORDER BY event_time,rowid",
                (client, before, before - ttl)).fetchall()
            hint = None
            for row in rows:
                if mid and row["mid"] == mid:
                    break
                event = json.loads(row["payload"])
                kind = event.get("kind")
                if kind == "story_context":
                    story = event.get("story", {})
                    hint = story if story.get("id") else None
                elif kind not in ("ignored", "own_echo"):
                    hint = None  # The next substantive message consumes the reaction.
            return hint

    def create_jobs(self, account, rows, merged):
        by_mid = {row["mid"]: row for row in rows}
        with self.connection() as conn:
            for event in merged:
                if not self.allowed(event.get("sender_id")):
                    continue
                mids = list(dict.fromkeys([event.get("mid"), *event.get("related_mids", [])]))
                mids = [mid for mid in mids if mid in by_mid]
                if not mids:
                    continue
                current = [conn.execute("SELECT * FROM inbound_events WHERE account=? AND mid=?", (account, mid)).fetchone()
                           for mid in mids]
                if any(row is None or row["job_id"] is not None for row in current):
                    continue
                job_id = uuid4().hex
                versions = {row["mid"]: row["version"] for row in current}
                event = deepcopy(event)
                event["_original_time"] = min(row["event_time"] for row in current)
                # Preserve incomplete context even when merge rebuilds the event.
                event["_context_incomplete"] = any(json.loads(row["payload"]).get("_context_incomplete") for row in current)
                event["_source_issues"] = list(dict.fromkeys(issue for row in current
                    for issue in json.loads(row["payload"]).get("_source_issues", [])))
                recovered = any("api" in json.loads(row["sources"]) for row in current)
                conn.execute("INSERT INTO inbound_jobs(id,account,client_id,payload,members,versions,state,due,created_at,"
                    "updated_at,recovered,technical_attempts,semantic_used) VALUES (?,?,?,?,?,?,'ready',?,?,?,?,?,?)",
                    (job_id, account, event["sender_id"], dumps(event), dumps(mids), dumps(versions), self.clock(),
                     self.clock(), self.clock(), int(recovered), 0, 0))
                for mid in mids:
                    conn.execute("UPDATE inbound_events SET job_id=? WHERE account=? AND mid=?", (job_id, account, mid))
            # Merged-away empty templates etc. have a deliberate, durable outcome.
            for mid in by_mid:
                conn.execute("UPDATE inbound_events SET job_id='ignored' WHERE account=? AND mid=? AND job_id IS NULL", (account, mid))

    def claim_due(self, lease=180):
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM inbound_jobs WHERE state IN ('ready','retry_wait','semantic_wait','failure_ready') "
                "AND due<=? AND inbound_allowed(client_id) ORDER BY created_at,rowid LIMIT 1", (self.clock(),)).fetchone()
            if not row:
                return None
            claim = uuid4().hex
            semantic = row["state"] == "semantic_wait"
            conn.execute("UPDATE inbound_jobs SET state='processing',claim=?,lease_until=?,semantic_used=MAX(semantic_used,?) "
                         "WHERE id=?", (claim, self.clock()+lease, int(semantic), row["id"]))
            result = dict(conn.execute("SELECT * FROM inbound_jobs WHERE id=?", (row["id"],)).fetchone())
            if semantic and not row['semantic_used']:
                conn.execute("UPDATE inbound_jobs SET model_attempts=0,model_attempt_log='[]' WHERE id=?", (row['id'],))
                result['model_attempts'] = 0
                result['model_attempt_log'] = '[]'
            result["launch"] = ("failure" if row["state"] == "failure_ready" else "semantic" if semantic else
                                "technical" if row["technical_attempts"] else "initial")
            return result

    def assert_claim(self, conn, job):
        row = conn.execute("SELECT * FROM inbound_jobs WHERE id=?", (job["id"],)).fetchone()
        if not row or row["claim"] != job["claim"] or row["state"] != "processing" or row["lease_until"] <= self.clock():
            raise StaleWork("claim_changed")
        versions = json.loads(row["versions"])
        for mid, version in versions.items():
            ev = conn.execute("SELECT version,job_id FROM inbound_events WHERE account=? AND mid=?", (row["account"], mid)).fetchone()
            if not ev or ev["version"] != version or ev["job_id"] != row["id"]:
                raise StaleWork("source_changed")
        return row

    def heartbeat(self, job, lease=180):
        with self.connection() as conn:
            self.assert_claim(conn, job)
            conn.execute("UPDATE inbound_jobs SET lease_until=? WHERE id=?", (self.clock()+lease, job["id"]))

    def read_session(self, client):
        with self.connection() as conn:
            return sessions.read_row(conn, client)

    def reserve_model_attempt(self, job, revision, request_id=None):
        """Reserve before network I/O; a crash cannot replenish the call budget."""
        from src.config import settings
        with self.connection() as conn:
            row = self.assert_claim(conn, job)
            state, current_revision = sessions.read_row(conn, job['client_id'])
            if (not self.allowed(job['client_id']) or current_revision != revision
                    or sessions.is_manager_active(state, settings.manager_takeover_ttl_minutes)):
                raise StaleWork('session_changed')
            if row['model_attempts'] >= 3:
                return None
            attempt = row['model_attempts'] + 1
            history = json.loads(row['model_attempt_log'])
            history.append(dict(attempt=attempt, stage='reservation', reason='call_reserved',
                                timeout=(120, 120, 240)[attempt - 1], request_id=request_id))
            conn.execute('UPDATE inbound_jobs SET model_attempts=?,model_attempt_log=? WHERE id=?',
                         (attempt, dumps(history[-3:]), job['id']))
            return attempt

    def record_model_attempt(self, job, details, request_id):
        with self.connection() as conn:
            row = self.assert_claim(conn, job)
            history = json.loads(row['model_attempt_log'])
            history = [{**details, 'request_id': request_id} if item['attempt'] == details['attempt'] else item
                       for item in history]
            conn.execute('UPDATE inbound_jobs SET model_attempt_log=? WHERE id=?', (dumps(history[-3:]), job['id']))

    def retry(self, job, reason, delays=(120, 480)):
        with self.connection() as conn:
            row = self.assert_claim(conn, job)
            used = row["technical_attempts"]
            if used >= len(delays):
                conn.execute("UPDATE inbound_jobs SET state='failed_final',reason=?,claim=NULL,updated_at=? WHERE id=?",
                             (reason, self.clock(), job["id"]))
                return False
            conn.execute("UPDATE inbound_jobs SET state='retry_wait',reason=?,technical_attempts=technical_attempts+1,"
                         "due=?,claim=NULL,updated_at=? WHERE id=?",
                         (reason, self.clock()+delays[used], self.clock(), job["id"]))
            return True

    def finish(self, job, state, reason):
        with self.connection() as conn:
            self.assert_claim(conn, job)
            conn.execute("UPDATE inbound_jobs SET state=?,reason=?,claim=NULL,updated_at=? WHERE id=?", (state, reason, self.clock(), job["id"]))

    def commit_result(self, job, state, revision, result, notifications):
        with self.connection() as conn:
            self.assert_claim(conn, job)
            if not self._write_own_session(conn, job["client_id"], state, revision):
                raise StaleWork("session_changed")
            conn.execute("UPDATE inbound_jobs SET result=?,outcome=?,state='delivering',session_revision=?,"
                         "claim=NULL,updated_at=? WHERE id=?",
                         (dumps(result), result["outcome"], revision+1, self.clock(), job["id"]))
            for notification in notifications:
                if isinstance(notification, dict):
                    from src.db.manager_tasks import plan
                    prefix = 'technical:' if notification['decision'].action == 'technical' else ''
                    plan(conn, client=job['client_id'], now=self.clock(), job_id=job['id'],
                         source_key=prefix + 'job:' + job['id'], **notification)
                else:
                    destination, text = notification
                    self._add_delivery(conn, job, "telegram", destination, 0, text)
            if conn.execute("SELECT 1 FROM inbound_deliveries WHERE job_id=? AND state='unknown'",
                            (job['id'],)).fetchone():
                conn.execute("UPDATE inbound_jobs SET state='unknown',reason='manager_delivery_unknown' WHERE id=?", (job['id'],))

    def _add_delivery(self, conn, job, channel, destination, part, text):
        conn.execute("INSERT OR IGNORE INTO inbound_deliveries(id,job_id,client_id,channel,destination,part,payload,"
                     "state,due,created_at,updated_at) VALUES (?,?,?,?,?,?,?,'ready',?,?,?)",
                     (uuid4().hex, job["id"], job["client_id"], channel, destination, part, text,
                      self.clock(), self.clock(), self.clock()))

    def get_job(self, job_id):
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM inbound_jobs WHERE id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def get_delivery(self, delivery_id):
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM inbound_deliveries WHERE id=?", (delivery_id,)).fetchone()
            return dict(row) if row else None

    def pending_delivery_id(self, pending_id):
        with self.connection() as conn:
            row = conn.execute("SELECT recovery_delivery_id FROM pending_messages WHERE id=?", (pending_id,)).fetchone()
            return row[0] if row else None

    def begin_legacy_send(self, client, text):
        with self.connection() as conn:
            delivery_id = uuid4().hex
            conn.execute("INSERT INTO inbound_deliveries(id,client_id,channel,destination,part,payload,state,due,intent_at,created_at,updated_at) "
                         "VALUES (?,?,'instagram',?,0,?,'sending',?,?,?,?)",
                         (delivery_id, client, client, text, self.clock(), self.clock(), self.clock(), self.clock()))
            return delivery_id

    def finish_legacy_failure(self, delivery_id, status):
        with self.connection() as conn:
            conn.execute("UPDATE inbound_deliveries SET state=?,updated_at=? WHERE id=? AND state='sending'",
                         (status, self.clock(), delivery_id))

    def record_legacy_receipt(self, client, text, mid, event=None, account=None, delivery_id=None):
        """Keep own-MID knowledge while the new recovery feature is disabled."""
        with self.connection() as conn:
            if delivery_id:
                conn.execute("UPDATE inbound_deliveries SET state='sent',receipt=?,updated_at=? WHERE id=?",
                             (mid, self.clock(), delivery_id))
            exists = conn.execute("SELECT 1 FROM inbound_deliveries WHERE channel='instagram' AND receipt=?", (mid,)).fetchone()
            if not exists:
                conn.execute("INSERT INTO inbound_deliveries(id,client_id,channel,destination,part,payload,state,due,receipt,created_at,updated_at) "
                             "VALUES (?,?,'instagram',?,0,?,'sent',?,?,?,?)",
                             (uuid4().hex, client, client, text, self.clock(), mid, self.clock(), self.clock()))
            if event and account:
                covered = set(filter(None, [event.get("mid"), *event.get("related_mids", [])]))
                for incoming_mid in covered:
                    previous = conn.execute("SELECT job_id FROM inbound_events WHERE account=? AND mid=?", (account, incoming_mid)).fetchone()
                    if previous and previous[0]:
                        job = conn.execute("SELECT * FROM inbound_jobs WHERE id=?", (previous[0],)).fetchone()
                        if job and set(json.loads(job["members"])).issubset(covered) and job["state"] != "unknown":
                            conn.execute("UPDATE inbound_jobs SET state='done',outcome='legacy_covered',claim=NULL,updated_at=? WHERE id=?", (self.clock(), job["id"]))
                            self._clear_projections(conn, job["id"])
                    elif not previous:
                        conn.execute("INSERT INTO inbound_events(account,mid,client_id,event_time,received_at,payload,sources,job_id) "
                                     "VALUES (?,?,?,?,?,'{}','[\"webhook\"]','legacy_answered')",
                                     (account, incoming_mid, client, timestamp(event.get("_event_time"), self.clock()), self.clock()))

    def mark_legacy_manager(self, client, text):
        with self.connection() as conn:
            self._cancel_client(conn, client, text)

    def deliveries(self, job_id):
        with self.connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM inbound_deliveries WHERE job_id=? "
                                                     "ORDER BY channel DESC,part,created_at,rowid", (job_id,))]

    def delivery_jobs(self):
        with self.connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM inbound_jobs WHERE state='delivering' AND due<=? AND inbound_allowed(client_id) ORDER BY created_at,rowid", (self.clock(),))]

    def defer_delivery(self, job, reason, delay):
        with self.connection() as conn:
            conn.execute("UPDATE inbound_jobs SET due=?,reason=? WHERE id=? AND state='delivering'", (self.clock()+delay, reason, job["id"]))

    def schedule_delivery(self, job):
        with self.connection() as conn:
            telegram = conn.execute("SELECT MIN(due) FROM inbound_deliveries WHERE job_id=? AND channel='telegram' "
                                   "AND state IN ('ready','retry_wait')", (job["id"],)).fetchone()[0]
            instagram = conn.execute("SELECT due FROM inbound_deliveries WHERE job_id=? AND channel='instagram' "
                                    "AND state IN ('ready','retry_wait') ORDER BY part LIMIT 1", (job["id"],)).fetchone()
            due = telegram if telegram is not None else instagram[0] if instagram else self.clock()
            conn.execute("UPDATE inbound_jobs SET due=? WHERE id=? AND state='delivering'", (due, job["id"]))

    def plan_instagram(self, job, parts):
        with self.connection() as conn:
            row = conn.execute("SELECT state FROM inbound_jobs WHERE id=?", (job["id"],)).fetchone()
            if not row or row[0] != "delivering":
                raise StaleWork("job_cancelled")
            for index, text in enumerate(parts):
                self._add_delivery(conn, job, "instagram", job["client_id"], index, text)
            self._project_ready(conn, job["id"])

    def _project_ready(self, conn, job_id):
        # Only final Instagram text with a proven safe-to-repeat state.
        rows = conn.execute("SELECT * FROM inbound_deliveries WHERE job_id=? AND channel='instagram' "
                            "AND state IN ('ready','retry_wait')", (job_id,)).fetchall()
        for row in rows:
            now = datetime.fromtimestamp(self.clock(), timezone.utc).isoformat()
            due = datetime.fromtimestamp(row["due"], timezone.utc).isoformat()
            conn.execute("INSERT OR IGNORE INTO pending_messages(recipient_id,text,created_at,retry_at,recovery_delivery_id) "
                         "VALUES (?,?,?,?,?)", (row["client_id"], row["payload"], now, due, row["id"]))

    def import_legacy_pending(self):
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM pending_messages WHERE recovery_delivery_id IS NULL AND inbound_allowed(recipient_id) ORDER BY id").fetchall()
            for row in rows:
                job_id = "legacy-"+str(row["id"])
                state, revision = sessions.read_row(conn, row["recipient_id"])
                when = timestamp(state.get("last_message_at"), timestamp(row["created_at"], self.clock()))
                conn.execute("INSERT OR IGNORE INTO inbound_jobs(id,account,client_id,payload,members,versions,state,result,"
                    "outcome,due,created_at,updated_at,session_revision,recovered) VALUES (?,?,?,?,'[]','{}','delivering',?,'legacy',?,?,?,?,1)",
                    (job_id, 'legacy', row["recipient_id"], dumps({"_original_time": when}),
                     dumps({"reply": "", "outcome": "legacy"}), timestamp(row["retry_at"], self.clock()),
                     self.clock(), self.clock(), revision))
                job = {"id": job_id, "client_id": row["recipient_id"]}
                self._add_delivery(conn, job, "instagram", row["recipient_id"], 0, row["text"])
                delivery = conn.execute("SELECT id FROM inbound_deliveries WHERE job_id=?", (job_id,)).fetchone()
                conn.execute("UPDATE inbound_deliveries SET attempts=?,due=? WHERE id=?",
                             (row["attempts"]+1, timestamp(row["retry_at"], self.clock()), delivery[0]))
                conn.execute("UPDATE pending_messages SET recovery_delivery_id=? WHERE id=?", (delivery[0], row["id"]))

    def start_delivery(self, job, delivery, manager_ttl):
        with self.connection() as conn:
            current = conn.execute("SELECT * FROM inbound_jobs WHERE id=?", (job["id"],)).fetchone()
            state, revision = sessions.read_row(conn, job["client_id"])
            if not current or current["state"] != "delivering":
                raise StaleWork("job_cancelled")
            from src.db.manager_tasks import can_start
            actual = conn.execute('SELECT * FROM inbound_deliveries WHERE id=?', (delivery['id'],)).fetchone()
            if not actual or actual['job_id'] != job['id'] or not can_start(conn, actual):
                if actual:
                    conn.execute("UPDATE inbound_deliveries SET state='cancelled' WHERE id=? AND state IN ('ready','retry_wait')", (actual['id'],))
                return False
            if revision != current["session_revision"] or sessions.is_manager_active(state, manager_ttl):
                conn.execute("UPDATE inbound_jobs SET state='cancelled',reason='session_changed' WHERE id=?", (job["id"],))
                self._clear_projections(conn, job["id"])
                return False
            blockers = conn.execute("SELECT 1 FROM inbound_deliveries WHERE job_id=? AND state IN ('sending','unknown')", (job["id"],)).fetchone()
            if blockers:
                return False
            cur = conn.execute("UPDATE inbound_deliveries SET state='sending',intent_at=?,updated_at=?,attempts=attempts+1 "
                               "WHERE id=? AND state IN ('ready','retry_wait') AND due<=?",
                               (self.clock(), self.clock(), delivery["id"], self.clock()))
            if cur.rowcount == 1:
                self._clear_projections(conn, job["id"])
            return cur.rowcount == 1

    def record_delivery(self, delivery, status, receipt=None, reason=None, delay=60):
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM inbound_deliveries WHERE id=?", (delivery["id"],)).fetchone()
            if not row or row["state"] != "sending":
                raise StaleWork("delivery_changed")
            if status == 'sent' and row['manager_task_id']:
                if (not isinstance(receipt, (str, int)) or isinstance(receipt, bool)
                        or not str(receipt).isdigit() or int(receipt) <= 0
                        or (row['operation'] == 'edit' and str(receipt) != row['target_message_id'])):
                    status, receipt, reason = 'unknown', None, 'invalid_manager_receipt'
            conn.execute("UPDATE inbound_deliveries SET state=?,receipt=?,due=?,updated_at=? WHERE id=?",
                         (status, receipt, self.clock()+delay, self.clock(), delivery["id"]))
            job = conn.execute("SELECT * FROM inbound_jobs WHERE id=?", (row["job_id"],)).fetchone()
            if status == "sent" and row["channel"] == "instagram" and job and job["state"] == "unknown" and job["reason"] == "ambiguous_outgoing":
                echo = conn.execute("SELECT payload FROM inbound_events WHERE account=? AND mid=?", (job["account"], receipt)).fetchone()
                if echo and json.loads(echo[0]).get("kind") == "ambiguous_echo":
                    event = json.loads(echo[0])
                    event["kind"] = "own_echo"
                    conn.execute("UPDATE inbound_events SET payload=?,job_id='ignored' WHERE account=? AND mid=?", (dumps(event), job["account"], receipt))
                    conn.execute("UPDATE inbound_jobs SET state='delivering',reason=NULL WHERE id=?", (job["id"],))
            if job and job["state"] == "cancelled" and status == "retry_wait":
                conn.execute("UPDATE inbound_deliveries SET state='cancelled' WHERE id=?", (row["id"],))
                self._clear_projections(conn, job["id"])
                return 'cancelled'
            if status == "unknown":
                conn.execute("UPDATE inbound_jobs SET state='unknown',reason=? WHERE id=?", (reason or 'delivery_unknown', row["job_id"]))
            elif status == "retry_wait" and row["channel"] == "instagram":
                self._project_ready(conn, row["job_id"])
            elif status == "blocked" and row["channel"] == "instagram":
                conn.execute("UPDATE inbound_jobs SET state='blocked',reason=? WHERE id=?", (reason or 'delivery_rejected', row["job_id"]))
                conn.execute("UPDATE inbound_deliveries SET state='blocked' WHERE job_id=? AND state IN ('ready','retry_wait')", (row["job_id"],))
                self._clear_projections(conn, row["job_id"])
            managed = bool(row['manager_task_id'])
            if status == 'sent' and (job or managed):
                state, revision = sessions.read_row(conn, row["client_id"])
                from src.db.manager_tasks import count_confirmed
                count_new = count_confirmed(conn, row) if managed else (
                    row['channel'] == 'telegram' and not job['notification_counted'])
                if count_new:
                    from src.config import settings
                    state["escalation_count"] = sessions.effective_escalation_count(state, settings.escalation_reset_hours) + 1
                    if job:
                        conn.execute("UPDATE inbound_jobs SET notification_counted=1 WHERE id=?", (job["id"],))
                elif row["channel"] == "instagram":
                    content = row["payload"]
                    result = json.loads(job["result"] or '{}')
                    if result.get("history_prefix"):
                        content = result["history_prefix"] + content
                    state.setdefault("history", []).append({"role": "assistant", "content": content,
                        "_inbound_job": job["id"], "_delivery": row["id"]})
                state["last_message_at"] = datetime.fromtimestamp(self.clock(), timezone.utc).isoformat()
                self._write_own_session(conn, row["client_id"], state, revision)
                # Do not bless a concurrent external writer as our revision.
                if job and revision == job["session_revision"]:
                    conn.execute("UPDATE inbound_jobs SET session_revision=? WHERE id=?", (revision+1, job["id"]))
        return status  # Returned only after transaction commit, for diagnostic confirmation.

    def complete_delivery(self, job, semantic_delay=120):
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM inbound_jobs WHERE id=?", (job["id"],)).fetchone()
            if not row or row["state"] != "delivering":
                return
            outstanding = conn.execute("SELECT 1 FROM inbound_deliveries WHERE job_id=? "
                "AND state IN ('ready','retry_wait','sending','unknown')", (job["id"],)).fetchone()
            if outstanding:
                return
            semantic = row["outcome"] == "silent_model_handoff" and not row["semantic_used"]
            conn.execute("UPDATE inbound_jobs SET state=?,due=?,updated_at=? WHERE id=?",
                ('semantic_wait' if semantic else 'failed_final' if row["outcome"] == 'failed_final' else 'done',
                 self.clock()+semantic_delay, self.clock(), row["id"]))

    def recover(self, startup=False, live_jobs=()):
        """Startup or expired lease. Sending is uncertain, never blindly retried."""
        with self.connection() as conn:
            sending = conn.execute("SELECT id,job_id FROM inbound_deliveries WHERE state='sending' AND inbound_allowed(client_id)").fetchall()
            for delivery in sending:
                if startup or delivery["job_id"] not in live_jobs:
                    conn.execute("UPDATE inbound_deliveries SET state='unknown' WHERE id=?", (delivery["id"],))
            conn.execute("UPDATE inbound_jobs SET state='unknown',reason='interrupted_send' WHERE id IN "
                         "(SELECT job_id FROM inbound_deliveries WHERE state='unknown' AND inbound_allowed(client_id)) AND inbound_allowed(client_id)")
            conn.execute("DELETE FROM pending_messages WHERE recovery_delivery_id IN (SELECT d.id FROM inbound_deliveries d "
                         "JOIN inbound_jobs j ON j.id=d.job_id WHERE j.state='unknown' AND inbound_allowed(j.client_id))")
            rows = conn.execute("SELECT * FROM inbound_jobs WHERE state='processing' AND lease_until<=? AND inbound_allowed(client_id)", (self.clock(),)).fetchall()
            for row in rows:
                if row["id"] in live_jobs:
                    continue
                used = row["technical_attempts"]
                conn.execute("UPDATE inbound_jobs SET state=?,technical_attempts=?,due=?,claim=NULL,recovered=1,"
                             "reason='interrupted_processing' WHERE id=?",
                             ('retry_wait' if used < 2 else 'failure_ready', min(used+1, 2),
                              self.clock()+((120, 480)[used] if used < 2 else 0), row["id"]))
            if startup:
                conn.execute("UPDATE inbound_jobs SET recovered=1 WHERE state IN ('ready','retry_wait','semantic_wait','delivering') AND inbound_allowed(client_id)")

    def own_mid(self, mid):
        with self.connection() as conn:
            return bool(conn.execute("SELECT 1 FROM inbound_deliveries WHERE channel='instagram' AND state='sent' AND receipt=?", (mid,)).fetchone())

    def unresolved_send(self, client):
        with self.connection() as conn:
            return bool(conn.execute("SELECT 1 FROM inbound_deliveries WHERE client_id=? AND channel='instagram' "
                "AND state IN ('sending','unknown')", (client,)).fetchone())

    def stats(self):
        with self.connection() as conn:
            counts = {row[0]: row[1] for row in conn.execute("SELECT state,COUNT(*) FROM inbound_jobs WHERE inbound_allowed(client_id) GROUP BY state")}
            oldest = conn.execute("SELECT MIN(created_at) FROM inbound_jobs WHERE state NOT IN ('done','cancelled','failed_final') AND inbound_allowed(client_id)").fetchone()[0]
            return {"jobs": counts, "oldest_age_seconds": max(0, self.clock()-oldest) if oldest else 0,
                    "unassigned": conn.execute("SELECT COUNT(*) FROM inbound_events WHERE job_id IS NULL AND inbound_allowed(client_id)").fetchone()[0],
                    "unlinked_unknown_deliveries": conn.execute("SELECT COUNT(*) FROM inbound_deliveries WHERE job_id IS NULL "
                        "AND state IN ('unknown','sending') AND inbound_allowed(client_id)").fetchone()[0]}

    def cleanup(self):
        with self.connection() as conn:
            cutoff = self.clock()-7*86400
            conn.execute("UPDATE inbound_jobs SET payload='{}',result=NULL WHERE state IN ('done','cancelled','failed_final') AND updated_at<? AND inbound_allowed(client_id)", (cutoff,))
            conn.execute("UPDATE inbound_events SET payload='{}' WHERE received_at<? AND job_id IN "
                         "(SELECT id FROM inbound_jobs WHERE state IN ('done','cancelled','failed_final')) AND inbound_allowed(client_id)", (cutoff,))
            conn.execute("UPDATE inbound_events SET payload='{}' WHERE received_at<? AND job_id IN ('ignored','manager') AND inbound_allowed(client_id)", (cutoff,))
            conn.execute("UPDATE inbound_deliveries SET payload='' WHERE job_id IN "
                         "(SELECT id FROM inbound_jobs WHERE state IN ('done','cancelled','failed_final') AND updated_at<?) AND inbound_allowed(client_id)", (cutoff,))
            cutoff = self.clock()-90*86400
            conn.execute("DELETE FROM inbound_events WHERE received_at<? AND (job_id IN ('ignored','manager','legacy_answered') OR job_id IN "
                         "(SELECT id FROM inbound_jobs WHERE state IN ('done','cancelled','failed_final'))) AND inbound_allowed(client_id)", (cutoff,))
            conn.execute("DELETE FROM inbound_deliveries WHERE updated_at<? AND state IN ('sent','cancelled','blocked') "
                         "AND job_id IN (SELECT id FROM inbound_jobs WHERE state IN ('done','cancelled','failed_final')) "
                         "AND NOT EXISTS (SELECT 1 FROM manager_tasks t WHERE t.id=manager_task_id AND t.status='open') "
                         "AND inbound_allowed(client_id)", (cutoff,))
            conn.execute("DELETE FROM inbound_jobs WHERE updated_at<? AND state IN ('done','cancelled','failed_final') AND inbound_allowed(client_id)", (cutoff,))
            conn.execute("DELETE FROM inbound_deliveries WHERE job_id IS NULL AND updated_at<? AND state='sent' "
                         "AND NOT EXISTS (SELECT 1 FROM manager_tasks t WHERE t.id=manager_task_id AND t.status='open') "
                         "AND inbound_allowed(client_id)", (cutoff,))
