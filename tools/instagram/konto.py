"""Konten und Instagram-API-Zugriff für alle Instagram-Werkzeuge (token, posten, warteschlange).

Mehrere Konten: Register in gedaechtnis/Kanal/konten.json, Schlüssel je Konto in der .env
(INSTAGRAM_<ID>_ACCESS_TOKEN, INSTAGRAM_<ID>_USER_ID). Erneuerte Tokens liegen in .secrets/instagram_tokens.json,
die .env wird nie umgeschrieben. Tokens werden nie ausgegeben.

Sperre: Antwortet Meta mit Code 200 „API access blocked“ oder Code 190 (Token ungültig), schreibt _fehler .secrets/instagram_gesperrt.json
(Zeit, Meldung). Solange die Datei jünger als SPERRE_STUNDEN (6 h) ist, macht api() keinen Aufruf (SystemExit mit dem Hinweis), und
Warteschlange (Instagram-Teil), kommentare, dms und kennzahlen überspringen Instagram mit einer Meldung. Die Sperre zählt nicht
als Fehlversuch. `python tools/instagram/tokens.py pruefen` fragt immer echt nach und löscht die Datei bei Erfolg (= Sperre aufgehoben).
"""
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kanal import KANAL, ROOT, env, jetzt, lies, schreib  # noqa: E402

KONTEN = KANAL / "konten.json"
TOKENS = ROOT / ".secrets" / "instagram_tokens.json"
GESPERRT = ROOT / ".secrets" / "instagram_gesperrt.json"
SPERRE_STUNDEN = 6
SPERR_HINWEIS = ("Meta hat den API-Zugriff gesperrt: developers.facebook.com → App → Warnungen/App-Review prüfen, "
                 "Instagram → Einstellungen → Kontostatus")
BASIS = "https://graph.instagram.com"
VERSION = os.environ.get("INSTAGRAM_API_VERSION") or "v23.0"


def env_opt(name):
    try:
        return env(name)
    except SystemExit:
        return None


def konten():
    """Instagram-Konten (andere Plattformen stehen im selben Register, werden von deren Werkzeugen gelesen)."""
    return [k for k in (lies(KONTEN, {}) or {}).get("konten", []) if k.get("plattform", "instagram") == "instagram"]


def konto(kid=None):
    """Konto-Eintrag laut konten.json (kid None → Standardkonto)."""
    reg = lies(KONTEN, {}) or {}
    kid = kid or reg.get("standard")
    for k in konten():
        if k["id"] == kid:
            return k
    raise SystemExit(f"FEHLER: Instagram-Konto „{kid}“ steht nicht in {KONTEN} (bekannt: {[k['id'] for k in konten()]})")


def prefix(k):
    return "INSTAGRAM_" + re.sub(r"[^A-Z0-9]+", "_", k["id"].upper())


def user_id(k):
    v = env_opt(prefix(k) + "_USER_ID")
    if not v:
        raise SystemExit(f"FEHLER: {prefix(k)}_USER_ID fehlt in .env (Instagram-Konto-ID von „{k['id']}“)")
    return v


def token(k):
    """Neuester Token: erst .secrets (erneuert), sonst .env."""
    t = (lies(TOKENS, {}) or {}).get(k["id"], {}).get("access_token")
    t = t or env_opt(prefix(k) + "_ACCESS_TOKEN")
    if not t:
        raise SystemExit(f"FEHLER: {prefix(k)}_ACCESS_TOKEN fehlt in .env (Konto „{k['id']}“)")
    return t


def token_speichern(k, tok, laeuft_ab):
    d = lies(TOKENS, {}) or {}
    d[k["id"]] = {"access_token": tok, "laeuft_ab": laeuft_ab, "erneuert": datetime.datetime.now().isoformat(timespec="seconds")}
    schreib(TOKENS, d)


def token_ablauf(k):
    return (lies(TOKENS, {}) or {}).get(k["id"], {}).get("laeuft_ab")


def gesperrt():
    """→ {"zeit", "meldung"}, wenn die Sperr-Datei jünger als SPERRE_STUNDEN ist, sonst None."""
    d = lies(GESPERRT, None)
    try:
        if d and datetime.datetime.now() - datetime.datetime.fromisoformat(d["zeit"]) < datetime.timedelta(hours=SPERRE_STUNDEN):
            return d
    except (KeyError, ValueError):
        pass
    return None


def sperre_melden():
    """Kurze Meldung für Werkzeuge, die Instagram wegen der Sperre überspringen."""
    g = gesperrt()
    return f"Instagram übersprungen (gesperrt seit {g['zeit'][:16].replace('T', ' ')}): {SPERR_HINWEIS} · aufheben: python tools/instagram/tokens.py pruefen"


def sperre_aufheben():
    GESPERRT.unlink(missing_ok=True)


def _fehler(e):
    err = {}
    try:
        err = json.loads(e.read().decode("utf-8")).get("error", {})
        msg = f"{err.get('message')} (Code {err.get('code')}, Subcode {err.get('error_subcode')})"
    except Exception:
        msg = f"HTTP {e.code}"
    code, text = err.get("code"), str(err.get("message") or "")
    if code == 190 or (code == 200 and "blocked" in text.lower()):
        schreib(GESPERRT, {"zeit": jetzt(), "code": code, "meldung": text, "hinweis": SPERR_HINWEIS})
        raise SystemExit(f"FEHLER Instagram-API: {msg}\n{SPERR_HINWEIS}")
    raise SystemExit(f"FEHLER Instagram-API: {msg}")


def api(methode, pfad, params=None, tok=None, versioniert=True, trotz_sperre=False, koerper=None):
    """JSON-Aufruf der Instagram-API. params als Query (GET) bzw. Formular (POST). Der Token wird mitgeschickt, nie ausgegeben.
    Bei aktiver Sperre (gesperrt()) kein Aufruf, außer trotz_sperre=True (nur tokens.py pruefen).
    koerper (dict): wird bei POST als JSON-Body gesendet (Private Replies); params bleiben dann in der Query."""
    if not trotz_sperre and gesperrt():
        raise SystemExit("FEHLER Instagram-API: " + sperre_melden())
    p = dict(params or {})
    if tok:
        p["access_token"] = tok
    url = f"{BASIS}/{VERSION + '/' if versioniert else ''}{pfad.lstrip('/')}"
    data = None
    kopf = {}
    if methode == "GET":
        url += "?" + urllib.parse.urlencode(p)
    elif koerper is not None:
        url += "?" + urllib.parse.urlencode(p)
        data = json.dumps(koerper).encode()
        kopf["Content-Type"] = "application/json"
    else:
        data = urllib.parse.urlencode(p).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method=methode, headers=kopf), timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        _fehler(e)
    except urllib.error.URLError as e:
        raise SystemExit(f"FEHLER: keine Verbindung zur Instagram-API ({e.reason})")
