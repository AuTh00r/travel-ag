"""Run a narrowly scoped Meta review demonstration on the existing Windows server.

status and watch are read-only. subscribe explicitly re-applies the messages
subscription, preserving every existing field. No tokens or raw logs are printed.
"""

import argparse
import base64
import json
from pathlib import Path
import subprocess


REMOTE = r'''
import base64
from collections import deque
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
logging.disable(logging.CRITICAL)
ROOT = Path("C:/travel-agent-bot")
APP = "1133220645701291"
PAGE = "100373865233538"
IG = "17841402218805629"

def show(label, value):
    print(label + ": " + json.dumps(value, ensure_ascii=False), flush=True)

class LogTail:
    """Close between polls: an open Windows reader prevents log rotation."""
    def __init__(self, path):
        self.path = path
        stat = path.stat()
        self.identity = (stat.st_dev, stat.st_ino)
        self.offset = stat.st_size
        self.partial = b""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def readlines(self):
        try:
            with self.path.open("rb") as stream:
                stat = os.fstat(stream.fileno())
                identity = (stat.st_dev, stat.st_ino)
                if identity != self.identity or stat.st_size < self.offset:
                    self.identity = identity
                    self.offset = 0
                    self.partial = b""
                stream.seek(self.offset)
                data = stream.read()
                self.offset = stream.tell()
        except FileNotFoundError:
            return []  # The writer may be between rename and creation.
        parts = (self.partial + data).split(b"\n")
        self.partial = parts.pop()
        return [part.decode("utf-8", errors="replace") for part in parts]

def graph_demo(action):
    import httpx
    from dotenv import dotenv_values
    cfg = dotenv_values(ROOT / ".env")
    assert cfg.get("INSTAGRAM_APP_ID") == APP, "Unexpected configured app"
    token = cfg.get("INSTAGRAM_ACCESS_TOKEN")
    assert token, "Missing token"
    with httpx.Client(base_url="https://graph.facebook.com/v25.0/",
                      headers={"Authorization": "Bearer " + token}, timeout=30) as client:
        def request(method, path, **kwargs):
            result = client.request(method, path, **kwargs)
            data = result.json()
            show(method + " /" + path, {"http_status": result.status_code})
            if result.is_error or "error" in data:
                error = data.get("error", {})
                show("Meta error", {"code": error.get("code"),
                                    "subcode": error.get("error_subcode")})
                raise RuntimeError("Meta request failed; no credentials printed")
            return data
        identity = request("GET", "me", params={
            "fields": "id,name,instagram_business_account{id,username}"})
        assert identity.get("id") == PAGE, "Unexpected Page"
        ig = identity.get("instagram_business_account", {})
        assert ig.get("id") == IG, "Unexpected Instagram account"
        show("CONNECTED ASSETS", {"configured_app_id": APP, "page_id": PAGE,
                                  "page_name": identity.get("name"),
                                  "instagram_id": IG, "instagram_username": ig.get("username")})
        subscriptions = request("GET", PAGE + "/subscribed_apps")
        matches = [row for row in subscriptions.get("data", []) if row.get("id") == APP]
        if not matches:
            raise RuntimeError("Expected app subscription missing; stop and inspect setup")
        fields = set(matches[0].get("subscribed_fields", []))
        show("CURRENT APP SUBSCRIPTION", {"app_id": APP, "fields": sorted(fields)})
        if action == "subscribe":
            fields.add("messages")
            show("ACTION", "Apply messages subscription; preserve existing fields")
            result = request("POST", PAGE + "/subscribed_apps",
                             data={"subscribed_fields": ",".join(sorted(fields))})
            if result.get("success") is not True:
                raise RuntimeError("Subscription success not confirmed")
            subscriptions = request("GET", PAGE + "/subscribed_apps")
            matches = [row for row in subscriptions.get("data", []) if row.get("id") == APP]
            assert matches and fields.issubset(matches[0].get("subscribed_fields", []))
            show("VERIFIED SUBSCRIPTION", {"app_id": APP,
                 "page_id": PAGE, "fields": matches[0]["subscribed_fields"]})

def select_demo(history, marker):
    for index, entry in enumerate(history):
        if entry.get("role") == "user" and marker in str(entry.get("content", "")):
            reply = None
            if index + 1 < len(history) and history[index + 1].get("role") == "assistant":
                reply = history[index + 1].get("content", "")
            return entry.get("content", ""), reply
    return None

def new_entries(previous, current):
    if not previous:
        return current
    # History may be shortened by the bot. Only emit entries after a known overlap.
    for size in range(min(len(previous), len(current)), 0, -1):
        if previous[-size:] == current[:size]:
            return current[size:]
    return []

def watch_all(timeout):
    db = ROOT / "data/sessions.db"
    def snapshot():
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
            return {cid: json.loads(raw).get("history", [])
                    for cid, raw in conn.execute("SELECT client_id,state FROM sessions")}
    with LogTail(ROOT / "logs/bot.log") as log:
        histories = snapshot()
        show("MODE", "All new conversations. Existing history is excluded.")
        show("INSTRUCTIONS", "Send any Instagram message now. Ctrl+C stops watching.")
        show("NOTE", "Saved text appears after AI processing. Send API success is shown separately in logs.")
        started = time.monotonic()
        while not timeout or time.monotonic() - started < timeout:
            for line in log.readlines():
                event = re.search(r"instagram\.message\.(received|processing|sent)\b", line)
                who = re.search(r"(?:sender_id|recipient_id)=(\d+)", line)
                stamp = re.match(r"(\S+)", line)
                if event and who:
                    show("ACTUAL SERVER LOG", {"timestamp": stamp.group(1) if stamp else "",
                         "event": event.group(0), "user_id": who.group(1)})
            current = snapshot()
            for cid, history in current.items():
                for entry in new_entries(histories.get(cid, []), history):
                    role = entry.get("role")
                    if role in ("user", "assistant"):
                        show("SAVED INCOMING MESSAGE" if role == "user" else "SAVED OUTGOING MESSAGE",
                             {"user_id": cid, "text": entry.get("content", "")})
            histories = current
            time.sleep(1)
    show("STOP", "Watch duration completed")

def watch(marker, timeout):
    if marker is None:
        return watch_all(timeout)
    db = ROOT / "data/sessions.db"
    log_path = ROOT / "logs/bot.log"
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        if any(select_demo(json.loads(row[0]).get("history", []), marker)
               for row in conn.execute("SELECT state FROM sessions")):
            raise RuntimeError("Marker already exists. Choose a new marker and start BEFORE sending")
    show("MODE", "Read-only view of actual bot logs and saved test conversation")
    show("MATCH ONLY", marker)
    show("INSTRUCTIONS", "Now send an Instagram DM containing this marker. Wait for the bot reply.")
    show("NOTE", "Message text becomes available in the database after AI processing.")
    events = deque(maxlen=5000)
    started = time.monotonic()
    selected_id = None
    shown_events = set()
    shown_question = False
    with LogTail(log_path) as log:
        while not timeout or time.monotonic() - started < timeout:
            for line in log.readlines():
                event = re.search(r"instagram\.message\.(received|processing|sent)\b", line)
                who = re.search(r"(?:sender_id|recipient_id)=(\d+)", line)
                stamp = re.match(r"(\S+)", line)
                if event and who:
                    events.append((stamp.group(1) if stamp else "", event.group(0), who.group(1)))
            with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
                rows = (conn.execute("SELECT client_id,state FROM sessions WHERE client_id=?", (selected_id,))
                        if selected_id else conn.execute("SELECT client_id,state FROM sessions"))
                matches = []
                for client_id, raw in rows:
                    demo = select_demo(json.loads(raw).get("history", []), marker)
                    if demo:
                        matches.append((client_id, demo))
            if len(matches) > 1:
                raise RuntimeError("Marker matches multiple conversations; no conversation printed")
            if matches:
                selected_id, (question, reply) = matches[0]
                if not shown_question:
                    show("TEST INSTAGRAM USER ID", selected_id)
                    show("SAVED INCOMING TEST MESSAGE", question)
                    shown_question = True
                for event in events:
                    if event[2] == selected_id and event not in shown_events:
                        show("ACTUAL SERVER LOG", {"timestamp": event[0], "event": event[1], "user_id": event[2]})
                        shown_events.add(event)
                sent = any(e[1] == "instagram.message.sent" for e in shown_events)
                if reply is not None and sent:
                    show("SAVED BOT REPLY AFTER SUCCESSFUL SEND API CALL", reply)
                    show("NEXT", "Show this same reply in the native Instagram client to confirm delivery.")
                    return
            time.sleep(1)
    raise RuntimeError("Timed out. No matching complete reply confirmed; check test roles or manager pause")

def main():
    args = json.loads(base64.b64decode(sys.argv[1]))
    show("UTC TIME", datetime.now(timezone.utc).isoformat())
    if args["action"] == "watch":
        watch(args["marker"], args["timeout"])
    else:
        graph_demo(args["action"])

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print("STOP: " + (str(exc) if isinstance(exc, (AssertionError, RuntimeError))
                           else type(exc).__name__), flush=True)
        sys.exit(1)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "subscribe", "watch"))
    parser.add_argument("--marker", help="Optional: show only a test DM containing this text")
    parser.add_argument("--timeout", type=int, default=0, help="Watch duration in seconds; default 0 waits until Ctrl+C")
    args = parser.parse_args()
    if args.marker is not None and len(args.marker) < 8:
        parser.error("--marker must contain at least 8 characters when supplied")
    if args.timeout < 0:
        parser.error("--timeout must be zero or positive")
    config = Path.home() / ".ssh" / "config"
    if not config.is_file():
        parser.error("SSH config not found; use the configured workstation")
    options = base64.b64encode(json.dumps(vars(args)).encode()).decode()
    powershell = (
        "& 'C:\\travel-agent-bot\\.venv\\Scripts\\python.exe' -u -c "
        f'"exec(__import__(\'sys\').stdin.read())" {options}'
    )
    encoded = base64.b64encode(powershell.encode("utf-16le")).decode()
    try:
        result = subprocess.run([
            "ssh", "-F", str(config), "-o", "BatchMode=yes", "-o", "ConnectTimeout=30",
            "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
            "sundita-office", "powershell -NoProfile -EncodedCommand " + encoded,
        ], input=REMOTE, text=True, encoding="utf-8", check=False)
        raise SystemExit(result.returncode)
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
