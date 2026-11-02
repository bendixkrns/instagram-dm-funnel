"""Offline bot checks: no real API, model, or send calls."""
import datetime
import hashlib
import hmac
import json
import sys
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "instagram"))

import kommentare as ig  # noqa: E402
import kommentare_zernio as zernio  # noqa: E402
import dms  # noqa: E402
import keyword_dm as kw  # noqa: E402
from automation import llm  # noqa: E402
from automation import status as bot_status  # noqa: E402
from automation import instagram_webhook as webhook  # noqa: E402
from automation import instagram_contacts as contacts  # noqa: E402
from automation import keyword_config as funnel_config  # noqa: E402
sys.path.insert(0, str(ROOT / "cockpit"))
import server as cockpit_server  # noqa: E402

ACCOUNT = {"id": "test", "handle": "test", "plattform": "instagram"}
COMMENT = {"id": "c1", "text": "SLEEP", "user": "private_account", "zeit": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "thread": "c1", "reel_id": "test-reel", "reel_titel": "Test", "reel_skript": "", "ist_antwort_auf_uns": False}


class BotTests(unittest.TestCase):
    def setUp(self):
        # Tests dürfen nie die echten, im Cockpit gespeicherten Funnel-Einstellungen lesen
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch.object(funnel_config, "FILE", Path(temp.name) / "keyword_funnels.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_keyword_tolerates_punctuation_case_and_one_long_word_typo(self):
        self.assertTrue(kw.trifft("🔥sLeEp!", "SLEEP"))
        self.assertTrue(kw.trifft("SLEPE", "SLEEP"))
        self.assertTrue(kw.trifft("SLEP", "SLEEP"))
        self.assertTrue(kw.trifft("SLEEPP", "SLEEP"))
        self.assertTrue(kw.trifft("✅test!", "TEST"))
        self.assertFalse(kw.trifft("TES", "TEST"))
        self.assertFalse(kw.trifft("SLOPPY", "SLEEP"))
        self.assertFalse(kw.trifft("Where is the SLEEP thing?", "SLEEP"))

    def test_cockpit_funnel_settings_inherit_and_validate(self):
        with TemporaryDirectory() as temp, patch.object(funnel_config, "FILE", Path(temp) / "funnels.json"):
            funnel_config.save_default({"mode": "adaptive", "start_button": "Get guide"})
            funnel_config.save_reel("my-reel", {"mode": "email", "keyword": "Guide", "link": "https://example.com/free"})
            configured = funnel_config.for_reel("my-reel")
            self.assertEqual(configured["keyword"], "GUIDE")
            self.assertEqual(configured["mode"], "email")
            self.assertEqual(configured["start_button"], "Get guide")
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                funnel_config.save_reel("my-reel", {"link": "http://example.com/free"})

    def test_cockpit_funnel_api_saves_reel_override(self):
        with TemporaryDirectory() as temp, patch.object(funnel_config, "FILE", Path(temp) / "funnels.json"), \
             patch.object(cockpit_server, "reels", return_value=[{"id": "my-reel", "titel": "My Reel"}]):
            server = ThreadingHTTPServer(("127.0.0.1", 0), cockpit_server.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = "http://127.0.0.1:" + str(server.server_port)
                with urllib.request.urlopen(base + "/api/dm-funnel") as response:
                    before = json.load(response)
                self.assertEqual(before["default"]["mode"], "adaptive")
                self.assertEqual(before["reel_list"][0]["id"], "my-reel")
                req = urllib.request.Request(base + "/api/dm-funnel/reel/my-reel",
                                             data=json.dumps({"mode": "email", "keyword": "GUIDE",
                                                              "link": "https://example.com/free"}).encode(),
                                             headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req) as response:
                    saved = json.load(response)
                self.assertEqual(saved["mode"], "email")
                self.assertEqual(funnel_config.for_reel("my-reel")["keyword"], "GUIDE")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_production_keyword_uses_configured_button_funnel(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            config = folder / "funnels.json"
            with patch.object(funnel_config, "FILE", config):
                funnel_config.save_reel("test-reel", {"mode": "email", "keyword": "GUIDE",
                                                       "link": "https://example.com/free", "start_button": "Get guide"})
                with patch.object(kw, "TEST_DATEI", folder / "no-test.json"), patch.object(kw, "DATEI", folder / "state.json"), \
                     patch.object(kw.K, "gesperrt", return_value=None), patch.object(kw.K, "user_id", return_value="business"), \
                     patch.object(kw.K, "api", side_effect=[{"recipient_id": "u1"}, {}]) as api:
                    rest, entries, errors = kw.verarbeite(ACCOUNT, "token", [{**COMMENT, "text": "guide!"}], "live", False)
                    self.assertEqual((rest, errors), ([], []))
                    self.assertEqual(len(entries), 1)
                    payload = api.call_args_list[0].kwargs["koerper"]["message"]["attachment"]["payload"]
                    self.assertEqual(payload["buttons"][0]["title"], "Get guide")
                    flow = kw._zustand()["testlaeufe"]["c1"]
                    self.assertEqual(flow["config"]["mode"], "email")

    def test_empty_comment_list_with_nonzero_count_is_error(self):
        with patch.object(ig, "eigene_reels", return_value=[("test-reel", ROOT, {"post": {"media_id": "m1"}})]), \
             patch.object(ig.K, "api", side_effect=[{"data": []}, {"comments_count": 2}]):
            with self.assertRaisesRegex(RuntimeError, "liefert aber keine Kommentar-Daten"):
                ig.neue_kommentare(ACCOUNT, "token", set())

    def test_one_time_keyword_funnel_with_follow_check(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            config = folder / "instagram_keyword_test.json"
            config.write_text(json.dumps({"aktiv": True, "reel_id": "test-reel", "keyword": "TEST",
                                          "profil_link": "https://www.instagram.com/thepsychnote/",
                                          "ziel_link": "https://12axes.vercel.app/"}), encoding="utf-8")
            comment = {**COMMENT, "text": "TEST"}
            with patch.object(kw, "TEST_DATEI", config), patch.object(kw, "DATEI", folder / "state.json"), \
                 patch.object(kw.K, "gesperrt", return_value=None), patch.object(kw.K, "user_id", return_value="business"), \
                 patch.object(kw.K, "api", side_effect=[{"recipient_id": "u1", "message_id": "m0"}, {}]) as api:
                rest, entries, errors = kw.verarbeite(ACCOUNT, "token", [comment, {**comment, "id": "c2", "text": "hello"}], "live", False)
                self.assertEqual(len(rest), 1)
                self.assertEqual(len(entries), 1)
                self.assertEqual(errors, [])
                first_payload = api.call_args_list[0].kwargs["koerper"]["message"]["attachment"]["payload"]
                self.assertEqual(first_payload["buttons"][0]["title"], "Send link")
                self.assertEqual(first_payload["text"],
                                 "Thanks for commenting! 👏\nTap on the button and I will send you the link 🔥\nOn desktop? Reply SEND LINK.")
                self.assertEqual(kw._zustand()["testlauf"]["user_id"], "u1")
            def conversation(message_id, text):
                later = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=1)).isoformat()
                return [{"user_id": "u1", "nachrichten": [{"id": message_id, "von": "user", "text": text, "zeit": later}]}]
            with patch.object(kw, "TEST_DATEI", config), patch.object(kw, "DATEI", folder / "state.json"), \
                 patch.object(dms, "konversationen", return_value=conversation("m1", "Send link")), \
                 patch.object(kw, "_folgt", return_value=False), patch.object(kw.K, "user_id", return_value="business"), \
                 patch.object(kw.K, "api", return_value={}) as api:
                kw.test_funnel_fortsetzen(ACCOUNT, "token", "live", False)
                self.assertEqual(kw._zustand()["testlauf"]["status"], "wartet_auf_follow")
                buttons = api.call_args.kwargs["koerper"]["message"]["attachment"]["payload"]["buttons"]
                follow_text = api.call_args.kwargs["koerper"]["message"]["attachment"]["payload"]["text"]
                self.assertIn("Sorry, this resource is only for my followers.", follow_text)
                self.assertIn("tap I followed ✅ or reply I followed ✅", follow_text)
                self.assertEqual(buttons[0]["url"], "https://www.instagram.com/thepsychnote/")
                self.assertEqual(buttons[0]["title"], "Follow Now")
                self.assertTrue(buttons[1]["payload"].startswith("KW_FOLLOWED:"))
                self.assertEqual(buttons[1]["title"], "I followed ✅")
            with patch.object(kw, "TEST_DATEI", config), patch.object(kw, "DATEI", folder / "state.json"), \
                 patch.object(dms, "konversationen", return_value=conversation("m2", "I followed ✅")), \
                 patch.object(kw, "_folgt", return_value=True), patch.object(kw.K, "user_id", return_value="business"), \
                 patch.object(kw.K, "api", return_value={}) as api:
                kw.test_funnel_fortsetzen(ACCOUNT, "token", "live", False)
                self.assertEqual(kw._zustand()["testlauf"]["status"], "fertig")
                self.assertIn("https://12axes.vercel.app/", api.call_args.kwargs["koerper"]["message"]["text"])
    def test_follow_button_without_follow_repeats_prompt(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            config = folder / "instagram_keyword_test.json"
            config.write_text(json.dumps({"aktiv": True, "reel_id": "test-reel", "keyword": "TEST",
                                          "profil_link": "https://www.instagram.com/thepsychnote/",
                                          "ziel_link": "https://12axes.vercel.app/"}), encoding="utf-8")
            state = folder / "state.json"
            state.write_text(json.dumps({"testlauf": {"konto": "test", "user_id": "u1",
                                                       "status": "wartet_auf_follow", "gesehen": [],
                                                       "seit_utc": "2026-01-01T00:00:00+00:00"}}), encoding="utf-8")
            messages = [{"user_id": "u1", "nachrichten": [{"id": "m1", "von": "user", "text": "I followed ✅",
                                                          "zeit": "2026-01-02T00:00:00+00:00"}]}]
            with patch.object(kw, "TEST_DATEI", config), patch.object(kw, "DATEI", state), \
                 patch.object(dms, "konversationen", return_value=messages), \
                 patch.object(kw, "_folgt", return_value=False), patch.object(kw.K, "user_id", return_value="business"), \
                 patch.object(kw.K, "api", return_value={}) as api:
                kw.test_funnel_fortsetzen(ACCOUNT, "token", "live", False)
                payload = api.call_args.kwargs["koerper"]["message"]["attachment"]["payload"]
                self.assertIn("You're not following me yet", payload["text"])
                self.assertEqual([b["title"] for b in payload["buttons"]], ["Follow Now", "I followed ✅"])
                self.assertEqual(kw._zustand()["testlauf"]["status"], "wartet_auf_follow")

    def test_existing_follower_gets_link_without_follow_prompt(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            config = folder / "instagram_keyword_test.json"
            config.write_text(json.dumps({"aktiv": True, "reel_id": "test-reel", "keyword": "TEST", "funnel": "follow",
                                          "profil_link": "https://www.instagram.com/thepsychnote/",
                                          "ziel_link": "https://12axes.vercel.app/"}), encoding="utf-8")
            state = folder / "state.json"
            state.write_text(json.dumps({"testlauf": {"konto": "test", "user_id": "u1",
                                                       "status": "wartet_auf_button", "gesehen": [],
                                                       "seit_utc": "2026-01-01T00:00:00+00:00"}}), encoding="utf-8")
            messages = [{"user_id": "u1", "nachrichten": [{"id": "m1", "von": "user", "text": "sEnD lInK",
                                                          "zeit": "2026-01-02T00:00:00+00:00"}]}]
            with patch.object(kw, "TEST_DATEI", config), patch.object(kw, "DATEI", state), \
                 patch.object(dms, "konversationen", return_value=messages), \
                 patch.object(kw, "_folgt", return_value=True), patch.object(kw.K, "user_id", return_value="business"), \
                 patch.object(kw.K, "api", return_value={}) as api:
                kw.test_funnel_fortsetzen(ACCOUNT, "token", "live", False)
                self.assertEqual(kw._zustand()["testlauf"]["status"], "fertig")
                self.assertEqual(api.call_count, 1)
                self.assertIn("https://12axes.vercel.app/", api.call_args.kwargs["koerper"]["message"]["text"])

    def test_two_commenters_keep_separate_funnel_states(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            config = folder / "instagram_keyword_test.json"
            config.write_text(json.dumps({"aktiv": True, "reel_id": "test-reel", "keyword": "TEST", "funnel": "follow",
                                          "profil_link": "https://www.instagram.com/thepsychnote/",
                                          "ziel_link": "https://12axes.vercel.app/"}), encoding="utf-8")
            comments = [{**COMMENT, "id": cid, "thread": cid, "text": "TEST", "user": ""} for cid in ("c1", "c2")]
            state = folder / "state.json"
            with patch.object(kw, "TEST_DATEI", config), patch.object(kw, "DATEI", state), \
                 patch.object(kw.K, "gesperrt", return_value=None), patch.object(kw.K, "user_id", return_value="business"), \
                 patch.object(kw.time, "sleep"), \
                 patch.object(kw.K, "api", side_effect=[{"recipient_id": "u1"}, {}, {"recipient_id": "u2"}, {}]):
                rest, entries, errors = kw.verarbeite(ACCOUNT, "token", comments, "live", False)
                self.assertEqual((rest, errors), ([], []))
                self.assertEqual(len(entries), 2)
                self.assertEqual(set(kw._zustand()["testlaeufe"]), {"c1", "c2"})
            later = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=1)).isoformat()
            conversations = [{"user_id": user, "nachrichten": [{"id": "m" + user, "von": "user",
                                                                 "text": "send link", "zeit": later}]} for user in ("u1", "u2")]
            with patch.object(kw, "TEST_DATEI", config), patch.object(kw, "DATEI", state), \
                 patch.object(dms, "konversationen", return_value=conversations), \
                 patch.object(kw, "_folgt", side_effect=[True, False]), \
                 patch.object(kw.K, "user_id", return_value="business"), \
                 patch.object(kw.K, "api", return_value={}) as api:
                kw.test_funnel_fortsetzen(ACCOUNT, "token", "live", False)
                flows = kw._zustand()["testlaeufe"]
                self.assertEqual(flows["c1"]["status"], "fertig")
                self.assertEqual(flows["c2"]["status"], "wartet_auf_follow")
                self.assertEqual(api.call_args_list[0].kwargs["koerper"]["recipient"]["id"], "u1")
                self.assertEqual(api.call_args_list[1].kwargs["koerper"]["recipient"]["id"], "u2")

    def test_existing_follower_email_is_saved_and_reused(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            config = folder / "instagram_keyword_test.json"
            config.write_text(json.dumps({"aktiv": True, "reel_id": "test-reel", "keyword": "TEST",
                                          "funnel": "follow_email", "profil_link": "https://www.instagram.com/thepsychnote/",
                                          "ziel_link": "https://12axes.vercel.app/"}), encoding="utf-8")
            state = folder / "state.json"
            state.write_text(json.dumps({"testlauf": {"konto": "test", "user_id": "u1",
                                                       "status": "wartet_auf_button", "gesehen": [],
                                                       "seit_utc": "2026-01-01T00:00:00+00:00"}}), encoding="utf-8")
            def conversation(mid, body):
                later = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=1)).isoformat()
                return [{"user_id": "u1", "nachrichten": [{"id": mid, "von": "user", "text": body, "zeit": later}]}]
            with patch.object(contacts, "DB", folder / "contacts.sqlite3"), \
                 patch.object(kw, "TEST_DATEI", config), patch.object(kw, "DATEI", state), \
                 patch.object(kw, "_folgt", return_value=True), patch.object(kw.K, "user_id", return_value="business"), \
                 patch.object(kw.K, "api", return_value={}) as api:
                with patch.object(dms, "konversationen", return_value=conversation("m1", "SEND LINK")):
                    kw.test_funnel_fortsetzen(ACCOUNT, "token", "live", False)
                self.assertEqual(kw._zustand()["testlauf"]["status"], "wartet_auf_email")
                self.assertIn("Sorry, I need your email address", api.call_args.kwargs["koerper"]["message"]["text"])
                with patch.object(dms, "konversationen", return_value=conversation("m2", "ME@Example.com")):
                    kw.test_funnel_fortsetzen(ACCOUNT, "token", "live", False)
                self.assertEqual(contacts.email_for("test", "u1"), "me@example.com")
                self.assertEqual(kw._zustand()["testlauf"]["status"], "fertig")
                self.assertIn("https://12axes.vercel.app/", api.call_args.kwargs["koerper"]["message"]["text"])
                state.write_text(json.dumps({"testlauf": {"konto": "test", "user_id": "u1",
                                                           "status": "wartet_auf_button", "gesehen": [],
                                                           "seit_utc": "2026-01-01T00:00:00+00:00"}}), encoding="utf-8")
                api.reset_mock()
                with patch.object(dms, "konversationen", return_value=conversation("m3", "send link")):
                    kw.test_funnel_fortsetzen(ACCOUNT, "token", "live", False)
                self.assertEqual(kw._zustand()["testlauf"]["status"], "fertig")
                self.assertEqual(api.call_count, 1)
                self.assertIn("https://12axes.vercel.app/", api.call_args.kwargs["koerper"]["message"]["text"])

    def test_new_follower_skips_email_in_combined_mode(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            config = folder / "instagram_keyword_test.json"
            config.write_text(json.dumps({"aktiv": True, "reel_id": "test-reel", "keyword": "TEST",
                                          "funnel": "follow_email", "profil_link": "https://www.instagram.com/thepsychnote/",
                                          "ziel_link": "https://12axes.vercel.app/"}), encoding="utf-8")
            state = folder / "state.json"
            state.write_text(json.dumps({"testlauf": {"konto": "test", "user_id": "u2",
                                                       "status": "wartet_auf_follow", "gesehen": [],
                                                       "seit_utc": "2026-01-01T00:00:00+00:00"}}), encoding="utf-8")
            messages = [{"user_id": "u2", "nachrichten": [{"id": "m1", "von": "user", "text": "i followed ✅",
                                                          "zeit": "2026-01-02T00:00:00+00:00"}]}]
            with patch.object(contacts, "DB", folder / "contacts.sqlite3"), \
                 patch.object(kw, "TEST_DATEI", config), patch.object(kw, "DATEI", state), \
                 patch.object(dms, "konversationen", return_value=messages), \
                 patch.object(kw, "_folgt", return_value=True), patch.object(kw.K, "user_id", return_value="business"), \
                 patch.object(kw.K, "api", return_value={}) as api:
                kw.test_funnel_fortsetzen(ACCOUNT, "token", "live", False)
                self.assertEqual(kw._zustand()["testlauf"]["status"], "fertig")
                self.assertIsNone(contacts.email_for("test", "u2"))
                self.assertIn("https://12axes.vercel.app/", api.call_args.kwargs["koerper"]["message"]["text"])

    def test_random_word_is_rejected_as_email(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            config = folder / "instagram_keyword_test.json"
            config.write_text(json.dumps({"aktiv": True, "reel_id": "test-reel", "keyword": "TEST",
                                          "funnel": "email", "profil_link": "https://www.instagram.com/thepsychnote/",
                                          "ziel_link": "https://12axes.vercel.app/"}), encoding="utf-8")
            state = folder / "state.json"
            state.write_text(json.dumps({"testlauf": {"konto": "test", "user_id": "u1",
                                                       "status": "wartet_auf_email", "gesehen": [],
                                                       "seit_utc": "2026-01-01T00:00:00+00:00"}}), encoding="utf-8")
            messages = [{"user_id": "u1", "nachrichten": [{"id": "m1", "von": "user", "text": "Hallo",
                                                          "zeit": "2026-01-02T00:00:00+00:00"}]}]
            with patch.object(contacts, "DB", folder / "contacts.sqlite3"), \
                 patch.object(kw, "TEST_DATEI", config), patch.object(kw, "DATEI", state), \
                 patch.object(dms, "konversationen", return_value=messages), \
                 patch.object(kw.K, "user_id", return_value="business"), \
                 patch.object(kw.K, "api", return_value={}) as api:
                kw.test_funnel_fortsetzen(ACCOUNT, "token", "live", False)
                self.assertEqual(kw._zustand()["testlauf"]["status"], "wartet_auf_email")
                self.assertIsNone(contacts.email_for("test", "u1"))
                self.assertIn("valid email", api.call_args.kwargs["koerper"]["message"]["text"])

    def test_follow_api_error_keeps_button_reply_pending(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            config = folder / "instagram_keyword_test.json"
            config.write_text(json.dumps({"aktiv": True, "reel_id": "test-reel", "keyword": "TEST",
                                          "profil_link": "https://www.instagram.com/thepsychnote/",
                                          "ziel_link": "https://12axes.vercel.app/"}), encoding="utf-8")
            state = folder / "state.json"
            state.write_text(json.dumps({"testlauf": {"konto": "test", "user_id": "u1",
                                                       "status": "wartet_auf_button", "gesehen": [],
                                                       "seit_utc": "2026-01-01T00:00:00+00:00"}}), encoding="utf-8")
            conversation = [{"user_id": "u1", "nachrichten": [{"id": "m1", "von": "user", "text": "Send link",
                                                               "zeit": "2026-01-02T00:00:00+00:00"}]}]
            with patch.object(kw, "TEST_DATEI", config), patch.object(kw, "DATEI", state), \
                 patch.object(dms, "konversationen", return_value=conversation), \
                 patch.object(kw, "_folgt", side_effect=SystemExit("User consent is required")), \
                 patch.object(kw.K, "api") as api:
                with self.assertRaisesRegex(SystemExit, "User consent is required"):
                    kw.test_funnel_fortsetzen(ACCOUNT, "token", "live", False)
                self.assertEqual(kw._zustand()["testlauf"]["gesehen"], [])
                self.assertEqual(kw._zustand()["testlauf"]["status"], "wartet_auf_button")
                api.assert_not_called()

    def test_webhook_postback_is_deduplicated_and_readable(self):
        with TemporaryDirectory() as temp, patch.object(webhook, "DB", Path(temp) / "events.sqlite3"):
            event = {"object": "instagram", "entry": [{"messaging": [
                {"sender": {"id": "u1"}, "timestamp": 1792930000000,
                 "postback": {"payload": "TEST_SEND_LINK"}}
            ]}]}
            self.assertEqual(webhook.save_events(event), 1)
            self.assertEqual(webhook.save_events(event), 1)
            found = webhook.button_events("u1", "2026-01-01T00:00:00+00:00")
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["text"], "Send link")
            self.assertEqual(webhook.button_events("u2", "2026-01-01T00:00:00+00:00"), [])

    def test_webhook_rejects_wrong_signature(self):
        body = b'{"object":"instagram"}'
        signature = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
        self.assertTrue(webhook.valid_signature(body, signature, "secret"))
        self.assertFalse(webhook.valid_signature(body + b" ", signature, "secret"))
        self.assertFalse(webhook.valid_signature(body, "", "secret"))

    def test_button_postback_can_complete_funnel_without_dm_text(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            config = folder / "instagram_keyword_test.json"
            config.write_text(json.dumps({"aktiv": True, "reel_id": "test-reel", "keyword": "TEST", "funnel": "follow",
                                          "profil_link": "https://www.instagram.com/thepsychnote/",
                                          "ziel_link": "https://12axes.vercel.app/"}), encoding="utf-8")
            state = folder / "state.json"
            state.write_text(json.dumps({"testlauf": {"konto": "test", "user_id": "u1",
                                                       "status": "wartet_auf_button", "gesehen": [],
                                                       "seit_utc": "2026-01-01T00:00:00+00:00"}}), encoding="utf-8")
            postback = [{"id": "p1", "von": "user", "text": "Send link", "zeit": "2026-01-02T00:00:00+00:00"}]
            with patch.object(kw, "TEST_DATEI", config), patch.object(kw, "DATEI", state), \
                 patch.object(dms, "konversationen", return_value=[{"user_id": "u1", "nachrichten": []}]), \
                 patch.object(webhook, "button_events", return_value=postback), \
                 patch.object(kw, "_folgt", return_value=True), patch.object(kw.K, "user_id", return_value="business"), \
                 patch.object(kw.K, "api", return_value={}) as api:
                kw.test_funnel_fortsetzen(ACCOUNT, "token", "live", False)
                self.assertEqual(kw._zustand()["testlauf"]["status"], "fertig")
                self.assertIn("https://12axes.vercel.app/", api.call_args.kwargs["koerper"]["message"]["text"])

    def test_two_open_funnels_of_one_user_get_their_own_resource(self):
        def flow(cid, link, seit):
            return {"comment_id": cid, "reel_id": "r-" + cid, "konto": "test", "user_id": "u1", "status": "wartet_auf_button",
                    "gesehen": [], "seit_utc": seit,
                    "config": {**funnel_config.DEFAULT, "mode": "follow", "keyword": "PLAN", "link": link,
                               "profile_link": "https://www.instagram.com/x/"}}
        with TemporaryDirectory() as temp:
            state = Path(temp) / "state.json"
            state.write_text(json.dumps({"testlaeufe": {
                "cA": flow("cA", "https://example.com/a", "2026-01-01T00:00:00+00:00"),
                "cB": flow("cB", "https://example.com/b", "2026-01-02T00:00:00+00:00")}}), encoding="utf-8")
            click = [{"id": "p1", "von": "user", "text": "Send link", "zeit": "2026-01-03T00:00:00+00:00", "cid": "cA", "art": "button"}]
            typed = [{"id": "m1", "von": "user", "text": "Send link", "zeit": "2026-01-03T00:00:20+00:00"}]
            with patch.object(kw, "DATEI", state), patch.object(dms, "konversationen", return_value=[{"user_id": "u1", "nachrichten": typed}]),                  patch.object(webhook, "button_events", return_value=click), patch.object(kw, "_folgt", return_value=True),                  patch.object(kw.K, "user_id", return_value="business"), patch.object(kw.K, "api", return_value={}) as api:
                kw.test_funnel_fortsetzen(ACCOUNT, "token", "live", False)
                sent = [c.kwargs["koerper"]["message"]["text"] for c in api.call_args_list]
                self.assertEqual(len(sent), 1)
                self.assertIn("https://example.com/a", sent[0])
                flows = kw._zustand()["testlaeufe"]
                self.assertEqual(flows["cA"]["status"], "fertig")
                self.assertEqual(flows["cB"]["status"], "wartet_auf_button")

    def test_comment_webhook_events_feed_the_comment_job(self):
        event = {"object": "instagram", "entry": [{"id": "ig1", "time": int(time.time()) - 60, "changes": [
            {"field": "comments", "value": {"id": "c9", "text": "PLAN", "from": {"id": "u1", "username": "fan"},
                                           "media": {"id": "m1", "media_product_type": "REELS"}}},
            {"field": "comments", "value": {"id": "c10", "text": "mine", "from": {"id": "b", "username": "test"},
                                           "media": {"id": "m1"}}},
            {"field": "comments", "value": {"id": "c11", "text": "other post", "from": {"username": "fan"}, "media": {"id": "other"}}}]}]}
        with TemporaryDirectory() as temp, patch.object(webhook, "DB", Path(temp) / "events.sqlite3"):
            self.assertEqual(webhook.save_comment_events(event), 3)
            self.assertEqual(webhook.save_comment_events(event), 3)           # doppelt geliefert: nur einmal gespeichert
            self.assertTrue(webhook.WAKE.is_set())
            self.assertEqual(len(webhook.comment_events("ig1")), 3)
            self.assertEqual(webhook.comment_events("ig2"), [])
            reels = [("r1", ROOT, {"post": {"media_id": "m1"}, "titel": "T"})]
            with patch.object(ig, "eigene_reels", return_value=reels), patch.object(ig.K, "user_id", return_value="ig1"):
                found = ig.neue_kommentare_webhook({"id": "test", "handle": "@test"}, {"c9x"})
                self.assertEqual([c["id"] for c in found], ["c9"])            # eigener und fremder Beitrag fallen weg
                self.assertEqual(found[0]["reel_id"], "r1")
                self.assertEqual(ig.neue_kommentare_webhook({"id": "test", "handle": "@test"}, {"c9"}), [])
                self.assertNotIn("c9", [e["id"] for e in webhook.comment_events("ig1")])      # erledigt → aus dem Zwischenspeicher

    def test_comment_source_setting(self):
        for value, expected in [("webhook", "webhook"), ("BEIDES", "beides"), ("unsinn", "poll"), ("", "poll")]:
            with patch.object(ig, "env", return_value=value):
                self.assertEqual(ig.kommentar_quelle(), expected)
        with patch.object(ig, "env", side_effect=SystemExit("fehlt")):
            self.assertEqual(ig.kommentar_quelle(), "poll")
        with patch.object(ig, "kommentar_quelle", return_value="beides"),              patch.object(ig, "neue_kommentare_webhook", return_value=[{"id": "a"}]),              patch.object(ig, "neue_kommentare_abfrage", return_value=[{"id": "a"}, {"id": "b"}]):
            self.assertEqual([c["id"] for c in ig.neue_kommentare(ACCOUNT, "t", set())], ["a", "b"])

    def test_several_keywords_per_reel_ignore_case(self):
        self.assertEqual(funnel_config.validate({"keywords": ["sleep", "Rest", "SLEEP"]}, reel=True)["keywords"], ["SLEEP", "REST"])
        for bad in ([], ["ab"], ["two words"], "SLEEP", ["x" * 33]):
            with self.assertRaises(ValueError):
                funnel_config.validate({"keywords": bad}, reel=True)
        self.assertEqual(funnel_config.validate({"keywords": ["plan"]})["keywords"], ["PLAN"])      # auch im Standard
        with patch.object(kw, "testkonfiguration", return_value=None),              patch.object(kw.C, "for_reel", return_value={"keywords": ["sleep", "Rest"]}),              patch.object(kw.C, "load", return_value={"default": {"keywords": ["plan", "rest"]}, "reels": {}}):
            keywords = kw.keyword_fuer(Path("reels") / "r1")
        self.assertEqual(keywords, ["SLEEP", "REST", "PLAN"])       # Reel-Keywords plus Standard-Keywords
        self.assertTrue(any(kw.trifft(text, k) for text in ("sleep", "REST!", "ReSt 😴") for k in keywords))
        self.assertFalse(any(kw.trifft("rest of my day", k) for k in keywords))

    def test_mode_both_asks_follow_then_email_and_default_values_can_be_removed(self):
        cfg = {**funnel_config.DEFAULT, "mode": "both", "link": "https://example.com/r", "profile_link": "https://www.instagram.com/x/"}
        flow = {"comment_id": "c1", "konto": "test", "user_id": "u1", "status": "wartet_auf_follow", "gesehen": [],
                "seit_utc": "2026-01-01T00:00:00+00:00", "config": cfg}
        click = [{"id": "p1", "von": "user", "text": "I followed", "zeit": "2026-01-02T00:00:00+00:00", "cid": "c1", "art": "button"}]
        with TemporaryDirectory() as temp:
            state = Path(temp) / "state.json"
            state.write_text(json.dumps({"testlaeufe": {"c1": flow}}), encoding="utf-8")
            with patch.object(kw, "DATEI", state), patch.object(dms, "konversationen", return_value=[{"user_id": "u1", "nachrichten": []}]),                  patch.object(webhook, "button_events", return_value=click), patch.object(kw, "_folgt", return_value=True),                  patch.object(contacts, "email_for", return_value=None),                  patch.object(kw.K, "user_id", return_value="business"), patch.object(kw.K, "api", return_value={}) as api:
                kw.test_funnel_fortsetzen(ACCOUNT, "token", "live", False)
                self.assertEqual(kw._zustand()["testlaeufe"]["c1"]["status"], "wartet_auf_email")     # nach Follow noch die E-Mail
                self.assertIn("email address", api.call_args.kwargs["koerper"]["message"]["text"])
        with TemporaryDirectory() as temp, patch.object(funnel_config, "FILE", Path(temp) / "f.json"):
            funnel_config.save_default({"link": "https://example.com/a", "keywords": ["plan"]})
            self.assertEqual(funnel_config.load()["default"]["link"], "https://example.com/a")
            funnel_config.save_default({"link": None, "keywords": None})
            self.assertNotIn("link", funnel_config.load()["default"])
            self.assertNotIn("keywords", funnel_config.load()["default"])
            self.assertEqual(funnel_config.validate({"mode": "both"})["mode"], "both")
            with self.assertRaises(ValueError):
                funnel_config.validate({"link": None}, reel=True)

    def test_cockpit_settings_reach_the_bot_end_to_end(self):
        """Wie im Cockpit gespeichert → Kommentar → alle DMs enthalten genau diese Texte, Buttons, Links und Reihenfolge."""
        settings = {"mode": "both", "order": "email_first", "keywords": ["plan", "Guide"], "link": "https://example.com/mein-link",
                    "profile_link": "https://www.instagram.com/mein_konto/", "public_replies": ["Schau in deine DMs!"],
                    "intro_text": "HALLO erste DM", "start_button": "Los", "follow_text": "FOLGE MIR bitte", "follow_now_button": "Jetzt folgen",
                    "follow_button": "Erledigt", "follow_again_text": "Noch nicht gefolgt.", "email_text": "DEINE MAIL?",
                    "email_again_text": "Ungültig.", "link_text": "Hier: {link} Viel Spaß"}
        later = lambda m: (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=m)).isoformat()
        with TemporaryDirectory() as temp, patch.object(kw, "DATEI", Path(temp) / "state.json"),              patch.object(contacts, "DB", Path(temp) / "contacts.sqlite3") if hasattr(contacts, "DB") else patch.object(kw, "_jetzt_utc", kw._jetzt_utc):
            funnel_config.save_reel("test-reel", settings)
            sent = []

            def api(method, path, params, tok, koerper=None):
                if koerper:
                    sent.append(koerper)
                return {"recipient_id": "u" + koerper["recipient"]["comment_id"][1:], "message_id": "m"} if koerper and "comment_id" in koerper.get("recipient", {}) else {}
            follows = {"value": False}
            with patch.object(kw, "testkonfiguration", return_value=None), patch.object(kw.K, "gesperrt", return_value=None),                  patch.object(kw.K, "user_id", return_value="biz"), patch.object(kw.K, "api", side_effect=api),                  patch.object(kw.time, "sleep"), patch.object(kw, "_folgt", side_effect=lambda *a: follows["value"]),                  patch.object(contacts, "email_for", return_value=None), patch.object(contacts, "save_email"):
                rest, entries, errors = kw.verarbeite(ACCOUNT, "token", [{**COMMENT, "text": "  PLAN!! 😴"}, {**COMMENT, "id": "c2", "user": "x", "text": "guide"},
                                                                         {**COMMENT, "id": "c3", "user": "y", "text": "sleep"}], "live", False)
                self.assertEqual((len(rest), len(entries), errors), (1, 2, []))            # SLEEP ist kein Keyword dieses Reels
                first = sent[0]["message"]["attachment"]["payload"]
                self.assertEqual(first["text"], "HALLO erste DM")
                self.assertEqual(first["buttons"][0]["title"], "Los")
                self.assertEqual(entries[0]["antwort"], "Schau in deine DMs!")
                self.assertEqual(kw._zustand()["testlaeufe"]["c1"]["config"]["link"], "https://example.com/mein-link")
                sent.clear()

                def step(text, minute):
                    conv = [{"user_id": "u1", "nachrichten": [{"id": f"m{minute}", "von": "user", "text": text, "zeit": later(minute)}]}]
                    with patch.object(dms, "konversationen", return_value=conv):
                        kw.test_funnel_fortsetzen(ACCOUNT, "token", "live", False)
                    return sent[-1]["message"] if sent else None
                # Reihenfolge E-Mail zuerst: Start → E-Mail-Frage
                self.assertEqual(step("Los", 1)["text"], "DEINE MAIL?")
                with patch.object(contacts, "normalize_email", return_value="a@b.de"):
                    msg = step("a@b.de", 2)                                                  # dann Follow-Nachricht mit eigenen Buttons
                payload = msg["attachment"]["payload"]
                self.assertEqual(payload["text"], "FOLGE MIR bitte")
                self.assertEqual([b["title"] for b in payload["buttons"]], ["Jetzt folgen", "Erledigt"])
                self.assertEqual(payload["buttons"][0]["url"], "https://www.instagram.com/mein_konto/")
                follows["value"] = True
                self.assertEqual(step("Erledigt", 3)["text"], "Hier: https://example.com/mein-link Viel Spaß")
                self.assertEqual(kw._zustand()["testlaeufe"]["c1"]["status"], "fertig")

    def test_test_mode_ignores_non_keyword_without_model(self):
        with patch.object(ig.KW, "testkonfiguration", return_value={"aktiv": True}), \
             patch.object(ig.K, "token", return_value="token"), patch.object(ig, "lies", return_value={}), \
             patch.object(ig, "neue_kommentare", return_value=[{**COMMENT, "text": "hello"}]), \
             patch.object(ig.KW, "verarbeite", return_value=([{**COMMENT, "text": "hello"}], [], [])), \
             patch.object(ig.KW, "test_funnel_fortsetzen"), patch.object(ig, "einordnen") as model, \
             patch.object(ig.K, "api") as api:
            ig.lauf(ACCOUNT, "live", False)
            model.assert_not_called()
            api.assert_not_called()

    def test_instagram_api_error_is_not_empty_success(self):
        with patch.object(ig, "eigene_reels", return_value=[("test-reel", ROOT, {"post": {"media_id": "m1"}})]), \
             patch.object(ig.K, "api", side_effect=SystemExit("API down")):
            with self.assertRaisesRegex(RuntimeError, "API down"):
                ig.neue_kommentare(ACCOUNT, "token", set())

    def test_zernio_api_error_is_not_empty_success(self):
        with patch.object(zernio, "eigene_reels", return_value=[("test-reel", ROOT, {}, "p1")]), \
             patch.object(zernio, "api", side_effect=SystemExit("API down")):
            with self.assertRaisesRegex(RuntimeError, "API down"):
                zernio.neue_kommentare({**ACCOUNT, "zernio_account_id": "a"}, set())

    def test_comment_dry_and_probelauf_never_send_or_write(self):
        safe = {"c1": {"id": "c1", "kategorie": "lob", "antwort": "Thanks!", "ausblenden": False,
                       "eskalieren": False, "grund": "", "themenidee": None}}
        for mode, dry in (("live", True), ("probelauf", False)):
            with self.subTest(mode=mode, dry=dry), patch.object(ig.K, "token", return_value="token"), \
                 patch.object(ig, "lies", return_value={}), patch.object(ig, "neue_kommentare", return_value=[COMMENT]), \
                 patch.object(ig.KW, "verarbeite", return_value=([COMMENT], [], [])), \
                 patch.object(ig, "einordnen", return_value=safe), patch.object(ig, "schreib") as write, \
                 patch.object(ig.K, "api") as api:
                ig.lauf(ACCOUNT, mode, dry)
                write.assert_not_called()
                api.assert_not_called()

    def test_keyword_dry_has_variants_but_no_send_or_write(self):
        with patch.object(kw, "_zustand", return_value={"ohne_link": {}, "gesendet": {}, "personen": {}, "fehler": {}, "zeiten": [],
                                                   "zaehler": {}, "letzte_variante": None}), \
             patch.object(kw, "keyword_fuer", return_value="SLEEP"), patch.object(kw, "ressource_fuer", return_value="Your plan https://example.test"), \
             patch.object(kw.K, "gesperrt", return_value=None), patch.object(kw.K, "api") as api, patch.object(kw, "schreib") as write:
            rest, entries, errors = kw.verarbeite(ACCOUNT, "token", [COMMENT], "probelauf", False)
            self.assertEqual(rest, [])
            self.assertEqual(entries, [])
            self.assertEqual(errors, [])
            api.assert_not_called()
            write.assert_not_called()

    def test_keyword_duplicate_person_is_skipped(self):
        second = {**COMMENT, "id": "c2", "thread": "c2"}
        with patch.object(kw, "_zustand", return_value={"ohne_link": {}, "gesendet": {}, "personen": {}, "fehler": {}, "zeiten": [],
                                                   "zaehler": {}, "letzte_variante": None}), \
             patch.object(kw, "keyword_fuer", return_value="SLEEP"), patch.object(kw, "ressource_fuer", return_value="Your plan https://example.test"), \
             patch.object(kw.K, "gesperrt", return_value=None), patch.object(kw.K, "api") as api, patch.object(kw, "schreib") as write:
            _, entries, _ = kw.verarbeite(ACCOUNT, "token", [COMMENT, second], "probelauf", True)
            self.assertEqual(len(entries), 1)
            self.assertIn("schon", entries[0]["grund"])
            api.assert_not_called()
            write.assert_not_called()

    def test_keyword_missing_resource_never_sends(self):
        with patch.object(kw, "_zustand", return_value={"ohne_link": {}, "gesendet": {}, "personen": {}, "fehler": {}, "zeiten": [],
                                                   "zaehler": {}, "letzte_variante": None}), \
             patch.object(kw, "keyword_fuer", return_value="SLEEP"), patch.object(kw, "ressource_fuer", return_value=None), \
             patch.object(kw, "ressource_dm_text", return_value="plan"), patch.object(kw.K, "api") as api, patch.object(kw, "schreib") as write:
            kw.verarbeite(ACCOUNT, "token", [COMMENT], "probelauf", False)
            api.assert_not_called()
            write.assert_not_called()

    def test_invalid_model_output_escalates_after_retry(self):
        with patch.object(llm, "_groq", return_value={"items": []}) as model:
            result = llm.classify("kommentare", "prompt", ["c1"], "groq")
            self.assertEqual(model.call_count, 2)
            self.assertTrue(result["c1"]["eskalieren"])
            self.assertEqual(result["c1"]["antwort"], "")

    def test_sensitive_and_spam_output_cannot_send_reply(self):
        raw = {"items": [{"id": "c1", "kategorie": "heikel", "antwort": "Bad advice", "ausblenden": False,
                           "eskalieren": True, "grund": "crisis", "themenidee": None},
                          {"id": "c2", "kategorie": "spam", "antwort": "Thanks", "ausblenden": False,
                           "eskalieren": False, "grund": "", "themenidee": None}]}
        result = llm._validate(raw, "kommentare", {"c1", "c2"})
        self.assertEqual(result["c1"]["antwort"], "")
        self.assertEqual(result["c2"]["antwort"], "")
        self.assertTrue(result["c2"]["ausblenden"])

    def test_all_safe_comment_categories_validate(self):
        categories = ("frage", "lob", "themenidee", "erfahrung")
        raw = {"items": [{"id": f"c{index}", "kategorie": category, "antwort": "Thanks for sharing.",
                           "ausblenden": False, "eskalieren": False, "grund": "",
                           "themenidee": "A new topic" if category == "themenidee" else None}
                          for index, category in enumerate(categories)]}
        result = llm._validate(raw, "kommentare", {f"c{i}" for i in range(len(categories))})
        self.assertEqual({item["kategorie"] for item in result.values()}, set(categories))

    def test_hourly_reply_limit_blocks_send(self):
        safe = {"c1": {"id": "c1", "kategorie": "lob", "antwort": "Thanks!", "ausblenden": False,
                       "eskalieren": False, "grund": "", "themenidee": None}}
        with patch.object(ig, "MAX_PRO_STUNDE", 0), patch.object(ig.KW, "testkonfiguration", return_value=None), \
             patch.object(ig.K, "token", return_value="token"), \
             patch.object(ig, "lies", return_value={}), patch.object(ig, "neue_kommentare", return_value=[COMMENT]), \
             patch.object(ig.KW, "verarbeite", return_value=([COMMENT], [], [])), \
             patch.object(ig, "einordnen", return_value=safe), patch.object(ig, "schreib") as write, \
             patch.object(ig.K, "api") as api:
            ig.lauf(ACCOUNT, "live", False)
            api.assert_not_called()
            self.assertIn("Stundenlimit", write.call_args.args[1]["kommentare"][0]["grund"])

    def test_dm_dry_never_writes_or_sends(self):
        conversation = {"id": "d1", "plattform": "instagram", "konto": "test", "user": "person", "user_id": "u1",
                        "zeit": COMMENT["zeit"], "nachrichten": [{"id": "m1", "von": "user", "text": "Hi", "zeit": COMMENT["zeit"]}]}
        with patch.object(dms, "lies", return_value={}), patch.object(dms.K, "token", return_value="token"), \
             patch.object(dms, "konversationen", return_value=[conversation]), patch.object(dms, "schreib") as write, \
             patch.object(dms.K, "api") as api:
            dms.lauf(ACCOUNT, True)
            write.assert_not_called()
            api.assert_not_called()

    def test_status_error_is_persisted(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp, patch.object(bot_status, "FILE", Path(temp) / "bot_status.json"):
            bot_status.record("kommentare", "test", False, "API down")
            data = json.loads(bot_status.FILE.read_text(encoding="utf-8"))
            self.assertFalse(data["kommentare:test"]["ok"])
            self.assertEqual(data["kommentare:test"]["fehler"], "API down")

    def test_api_failure_exits_nonzero_and_cockpit_receives_error(self):
        with patch.object(ig.sys, "argv", ["kommentare.py", "--konto", "test", "--modus", "live"]), \
             patch.object(ig.K, "gesperrt", return_value=None), patch.object(ig.K, "konto", return_value=ACCOUNT), \
             patch.object(ig, "lauf", side_effect=RuntimeError("API down")), \
             patch.object(ig.bot_status, "record") as record:
            with self.assertRaises(SystemExit) as exit_result:
                ig.main()
            self.assertEqual(exit_result.exception.code, 1)
            self.assertEqual(record.call_args.args[:3], ("kommentare", "test", False))
            self.assertEqual(str(record.call_args.args[3]), "API down")
        real_lies = cockpit_server.lies
        with patch.object(cockpit_server, "lies", side_effect=lambda p, default=None: (
                {"kommentare:test": {"ok": False, "stand": "2026-10-25T12:00:00", "fehler": "API down"}}
                if str(p).endswith("bot_status.json") else real_lies(p, default))):
            self.assertEqual(cockpit_server.uebersicht()["bot"]["status"]["kommentare:test"]["fehler"], "API down")


if __name__ == "__main__":
    unittest.main()
