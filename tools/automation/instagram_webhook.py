"""Minimaler, signaturgeprüfter Instagram-Webhook für den Keyword-Test.

Lokal nur auf 127.0.0.1 lauschen und per HTTPS-Tunnel als /webhook anbieten.
Ereignisse werden in SQLite dedupliziert; private Nachrichtentexte werden nicht gespeichert.
"""
import argparse
import datetime
import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kanal import ROOT, env  # noqa: E402

DB = ROOT / ".secrets" / "automation" / "instagram_webhook.sqlite3"
MAX_BODY = 1_000_000
COMMENT_KEEP_DAYS = 8           # Zwischenspeicher: Private Replies gehen nur bis 7 Tage nach dem Kommentar
WAKE = threading.Event()          # gesetzt, sobald ein Kommentar-Ereignis eintrifft: der Worker startet den Kommentarjob sofort


def _connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB, timeout=10)
    connection.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, sender TEXT NOT NULL, "
                       "kind TEXT NOT NULL, payload TEXT NOT NULL, occurred_at TEXT NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS comment_events (id TEXT PRIMARY KEY, account TEXT NOT NULL, media TEXT NOT NULL, "
                       "parent TEXT, username TEXT, text TEXT NOT NULL, occurred_at TEXT NOT NULL)")
    return connection


def _events(data):
    if data.get("object") != "instagram":
        return []
    out = []
    for entry in data.get("entry", []):
        for message in entry.get("messaging", []):
            sender = str((message.get("sender") or {}).get("id") or "")
            if not sender:
                continue
            postback = message.get("postback") or {}
            quick_reply = (message.get("message") or {}).get("quick_reply") or {}
            payload = postback.get("payload") or quick_reply.get("payload")
            if not payload:
                continue
            kind = "postback" if postback else "quick_reply"
            stamp = message.get("timestamp") or entry.get("time")
            try:
                timestamp = datetime.datetime.fromtimestamp(int(stamp) / 1000 if int(stamp) > 10_000_000_000 else int(stamp),
                                                             datetime.timezone.utc).isoformat()
            except (TypeError, ValueError, OverflowError):
                continue
            event_id = hashlib.sha256(json.dumps(message, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            out.append((event_id, sender, kind, str(payload), timestamp))
    return out


def _comment_events(data):
    """Instagram-Webhook-Feld `comments` → [(comment_id, konto_id, media_id, parent_id, username, text, zeit)]."""
    if data.get("object") != "instagram":
        return []
    out = []
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            if change.get("field") != "comments" or not value.get("id") or not (value.get("media") or {}).get("id"):
                continue
            stamp = entry.get("time")
            try:
                seen = datetime.datetime.fromtimestamp(int(stamp), datetime.timezone.utc).isoformat()
            except (TypeError, ValueError, OverflowError):
                seen = datetime.datetime.now(datetime.timezone.utc).isoformat()
            out.append((str(value["id"]), str(entry.get("id") or ""), str(value["media"]["id"]),
                        str(value["parent_id"]) if value.get("parent_id") else None,
                        (value.get("from") or {}).get("username") or "", str(value.get("text") or ""), seen))
    return out


def save_comment_events(data):
    events = _comment_events(data)
    if not events:
        return 0
    with closing(_connect()) as connection:
        with connection:
            connection.executemany("INSERT OR IGNORE INTO comment_events VALUES (?, ?, ?, ?, ?, ?, ?)", events)
            limit = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=COMMENT_KEEP_DAYS)).isoformat()
            connection.execute("DELETE FROM comment_events WHERE occurred_at < ?", (limit,))
    WAKE.set()
    return len(events)


def comment_events(account):
    """Gespeicherte Kommentar-Ereignisse dieses Instagram-Kontos (Konto-ID wie in `entry.id`), älteste zuerst."""
    if not DB.exists():
        return []
    with closing(_connect()) as connection:
        rows = connection.execute("SELECT id, media, parent, username, text, occurred_at FROM comment_events "
                                  "WHERE account = ? ORDER BY occurred_at, id", (str(account),)).fetchall()
    return [{"id": r[0], "media": r[1], "parent": r[2], "username": r[3], "text": r[4], "zeit": r[5]} for r in rows]


def forget_comment_events(ids):
    """Erledigte Kommentare aus dem Zwischenspeicher löschen."""
    ids = [(str(i),) for i in ids]
    if ids and DB.exists():
        with closing(_connect()) as connection:
            with connection:
                connection.executemany("DELETE FROM comment_events WHERE id = ?", ids)


def save_events(data):
    events = _events(data)
    if not events:
        return 0
    with closing(_connect()) as connection:
        with connection:
            connection.executemany("INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?)", events)
    return len(events)


def button_events(sender, since):
    if not DB.exists():
        return []
    with closing(_connect()) as connection:
        rows = connection.execute("SELECT id, payload, occurred_at FROM events WHERE sender = ? AND occurred_at > ? "
                                  "ORDER BY occurred_at, id", (str(sender), since)).fetchall()
    labels = {"TEST_SEND_LINK": "Send link", "TEST_FOLLOWED": "I followed", "KW_SEND": "Send link", "KW_FOLLOWED": "I followed"}
    out = []
    for event_id, payload, timestamp in rows:
        name, _, cid = payload.partition(":")
        if name in labels:                       # ohne Kommentar-ID (altes Format): cid "" → gilt für den neuesten Flow
            out.append({"id": event_id, "von": "user", "text": labels[name], "zeit": timestamp, "cid": cid, "art": "button"})
    return out


def valid_signature(body, signature, app_secret):
    expected = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def handler(verify_token, app_secret):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path)
            query = parse_qs(path.query)
            if (path.path != "/webhook" or query.get("hub.mode") != ["subscribe"] or
                    not hmac.compare_digest(query.get("hub.verify_token", [""])[0], verify_token)):
                self.send_error(403)
                return
            challenge = query.get("hub.challenge", [""])[0].encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(challenge)))
            self.end_headers()
            self.wfile.write(challenge)

        def do_POST(self):
            if urlsplit(self.path).path != "/webhook":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_error(400)
                return
            if length <= 0 or length > MAX_BODY:
                self.send_error(413)
                return
            body = self.rfile.read(length)
            actual = self.headers.get("X-Hub-Signature-256", "")
            if not valid_signature(body, actual, app_secret):
                self.send_error(403)
                return
            try:
                payload = json.loads(body)
                count = save_events(payload)
                comments = save_comment_events(payload) if isinstance(payload, dict) else 0
            except (json.JSONDecodeError, TypeError, AttributeError):
                self.send_error(400)
                return
            print(f"Instagram-Webhook: {count} Button-Ereignisse, {comments} Kommentare empfangen", flush=True)
            self.send_response(200)
            self.end_headers()

        def log_message(self, format, *args):
            # Keine Query-Strings, Tokens oder Nachrichtentexte im Log.
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5091)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--poll-test", action="store_true", help="laufende Keyword-Test-DMs alle 5 Sekunden fortsetzen")
    group.add_argument("--worker", action="store_true", help="VPS: Kommentarjob und alle Keyword-DMs in einem dauerhaften Prozess")
    parser.add_argument("--comment-seconds", type=int, default=60)
    args = parser.parse_args()
    if args.poll_test or args.worker:
        if args.worker and args.comment_seconds < 15:
            parser.error("--comment-seconds muss mindestens 15 sein")

        def poll_funnels():
            sys.path.insert(0, str(ROOT / "tools" / "instagram"))
            import konto as K  # lokaler Import: nur der ausdrücklich gestartete Testmodus sendet
            import keyword_dm
            next_comments = 0.0
            while True:
                try:
                    if args.worker and (time.monotonic() >= next_comments or WAKE.is_set()):
                        WAKE.clear()
                        result = subprocess.run([sys.executable, "-X", "utf8", "tools/automation/run.py",
                                                 "keyword_dm", "--modus", "live"], cwd=ROOT, timeout=900,
                                                capture_output=True, text=True, encoding="utf-8", errors="replace")
                        print(f"Instagram-Worker: Keyword-Kommentarjob exit={result.returncode}", flush=True)
                        next_comments = time.monotonic() + args.comment_seconds
                    else:
                        for k in K.konten() if args.worker else [K.konto()]:
                            if k.get("aktiv", True):
                                keyword_dm.test_funnel_fortsetzen(k, K.token(k), "live", False)
                except (RuntimeError, SystemExit) as error:
                    print(f"Instagram-Worker: {str(error).splitlines()[0]}", flush=True)
                except subprocess.TimeoutExpired:
                    print("Instagram-Worker: Kommentarjob hat das Zeitlimit überschritten", flush=True)
                WAKE.wait(5)
        threading.Thread(target=poll_funnels, daemon=True, name="instagram-funnel-worker").start()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(env("META_WEBHOOK_VERIFY_TOKEN"), env("META_APP_SECRET")))
    print(f"Instagram-Webhook lauscht lokal auf Port {args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
