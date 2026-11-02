"""Cockpit des Reel-Kanals: lokaler Server (nur Python-Standardbibliothek) – liest Reels, Themen, Gedächtnis und Bibliothek,
schreibt Freigaben (über tools/status.py), Themen-Prioritäten, den Planungskalender und Uploads in die Bibliothek
(über tools/bibliothek.py add).

Start:  python cockpit/server.py [--lan]      → http://localhost:5090   (anderer Port: COCKPIT_PORT)
        --lan: auch im WLAN erreichbar (Handy); ohne nur auf diesem Rechner.

Daten, die das Cockpit liest (fehlt etwas, zeigt es einen leeren Zustand):
  reels/*/status.json, skript.md, storyboard.md, brief.md, caption.json/.md, audio/tts.json, review/review_vN.json/.md,
    review/pruefbogen_*.jpg, renders/*.mp4
  gedaechtnis/Themen/backlog.json, gedaechtnis/Themen/plan.json (Kalender, schreibt auch), gedaechtnis/Themen/<JJJJ>-KW<nn>.md, gedaechtnis/**/*.md (Wissen), gedaechtnis/Kanal/kanal.json
  bibliothek/library.json, Formate/thepsychnote/assets/library.json
  ElevenLabs-Credits über tools/credits.py (10 min zwischengespeichert)
  Phase 2 (tools/instagram/ schreibt diese Dateien):
    gedaechtnis/Kennzahlen/<plattform>.json  {"stand", "konto": {"follower", "verlauf": [{"datum", "follower", "views", "reichweite"}]},
                                        "reels": {"<reel-id>": {"views", "reichweite", "wiedergabe_s", "likes", "kommentare",
                                                                "shares", "saves", "stand"}}}
    gedaechtnis/Kanal/dms.json               {"stand", "quellen": {"<plattform>": {"ok", "hinweis"}}, "konversationen": [{"id", "plattform", "user", "zeit", "nachrichten", "offen", "erledigt"}]}
    gedaechtnis/Kanal/kommentare.json        {"bot": {"modus": "aus|probelauf|live", "letzter_lauf"},
                                        "kommentare": [{"id", "zeit", "plattform", "reel_id", "user", "text", "kategorie",
                                                        "antwort", "beantwortet", "ausblenden", "eskalieren", "grund", "erledigt"}]}
"""
import datetime
import importlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
from kanal import BIBLIOTHEK, KANAL, KIT, REELS, ROOT, STUFEN, THEMEN, GEDAECHTNIS, jetzt, lies, schreib  # noqa: E402
from automation import keyword_config  # noqa: E402

PORT = int(os.environ.get("COCKPIT_PORT") or 5090)
FREIGEGEBEN = [REELS, GEDAECHTNIS, BIBLIOTHEK, KIT.parent / "assets", KIT / "fonts"]   # nur hieraus liefert /datei/ aus
SPALTEN = {"skript": "arbeit", "stimme": "arbeit", "storyboard": "arbeit", "assets": "arbeit", "schnitt": "arbeit",
           "pruefung": "pruefung", "caption": "pruefung", "freigabe": "freigabe", "geplant": "geplant", "live": "live",
           "verworfen": "verworfen"}
PLATTFORMEN = ["instagram", "facebook", "tiktok", "youtube"]
_lock = threading.Lock()
_credits = {"zeit": 0, "daten": None, "fehler": None}

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/otf", ".otf")
mimetypes.add_type("font/ttf", ".ttf")
mimetypes.add_type("text/markdown", ".md")


def text(p):
    p = Path(p)
    return p.read_text(encoding="utf-8") if p.exists() else None


def rel(p):
    return Path(p).resolve().relative_to(ROOT).as_posix()


def abschnitt(md, titel):
    m = re.search(rf"^## {re.escape(titel)}\s*$(.*?)(?=^## |\Z)", md or "", re.M | re.S)
    return m.group(1).strip() if m else ""


def schluesselwort(d, st):
    """Großes Wort für die Reel-Karte: erstes Schlüsselwort aus skript.md, sonst ein Wort aus dem Titel."""
    tab = abschnitt(text(d / "skript.md"), "Schlüsselwörter")
    for zeile in tab.splitlines()[2:]:
        zellen = [z.strip(" *`") for z in zeile.strip().strip("|").split("|")]
        if len(zellen) >= 2 and zellen[1]:
            return zellen[1]
    worte = [w for w in re.findall(r"[A-Za-zÄÖÜäöüß']+", st.get("titel") or "") if len(w) > 3]
    return max(worte, key=len) if worte else (st.get("titel") or "?")


def kennzahlen(plattform):
    return lies(GEDAECHTNIS / "Kennzahlen" / f"{plattform}.json")


def reel_kurz(d):
    st = lies(d / "status.json") or {}
    renders = sorted((d / "renders").glob("*.mp4"), key=lambda p: p.stat().st_mtime) if (d / "renders").exists() else []
    zahlen = {}
    for pf in PLATTFORMEN:
        k = (kennzahlen(pf) or {}).get("reels", {}).get(d.name)
        if k:
            zahlen[pf] = k
    return {**{k: st.get(k) for k in ("id", "titel", "thema_id", "saeule", "ende", "stufe", "angelegt", "geaendert", "schritte",
                                      "pruefrunde", "pruefung", "freigabe", "post", "kosten")},
            "id": d.name, "spalte": SPALTEN.get(st.get("stufe"), "arbeit"), "wort": schluesselwort(d, st),
            "render": rel(renders[-1]) if renders else None, "caption": (d / "caption.json").exists(), "kennzahlen": zahlen}


def brief_keyword(d):
    m = re.search(r"Keyword:\s*\*\*([A-Za-z0-9]+)\*\*", text(d / "brief.md") or "")
    return m.group(1).upper() if m else ""


def funnel_reels():
    """Alle Reels (auch unveröffentlichte) mit wirksamem Keyword/Link für die Funnel-Seite."""
    daten = keyword_config.load()
    out = []
    for r in reels():
        if r.get("stufe") == "verworfen":
            continue
        d = REELS / r["id"]
        eigene = daten["reels"].get(r["id"]) or {}
        insta = (lies(d / "caption.json", {}) or {}).get("instagram") or {}
        link = eigene.get("link") or insta.get("ressource_link") or ""
        datei = d / "ressource_link.txt"
        if not link and datei.exists():
            zeilen = datei.read_text(encoding="utf-8").strip().splitlines()
            link = zeilen[0] if zeilen else ""
        out.append({"id": r["id"], "titel": r.get("titel") or r["id"], "stufe": r.get("stufe"), "keywords": eigene.get("keywords") or [x for x in [eigene.get("keyword") or insta.get("keyword") or brief_keyword(d)] if x],
                    "render": r.get("render"), "link": link, "eigene_regeln": bool(eigene), "aktiv": eigene.get("active", True)})
    return out


def reels():
    if not REELS.exists():
        return []
    out = [reel_kurz(d) for d in REELS.iterdir() if (d / "status.json").exists()]
    return sorted(out, key=lambda r: r.get("geaendert") or "", reverse=True)


def reel_voll(rid):
    d = REELS / rid
    if not (d / "status.json").exists() or "/" in rid or "\\" in rid:
        return None
    r = reel_kurz(d)
    st = lies(d / "status.json")
    reviews = []
    for j in sorted((d / "review").glob("review_v*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)):
        reviews.append({"datei": rel(j), "daten": lies(j), "md": text(j.with_suffix(".md"))})
    bilder = sorted((d / "review").glob("pruefbogen*.jpg")) if (d / "review").exists() else []
    renders = sorted((d / "renders").glob("*.mp4"), key=lambda p: p.stat().st_mtime) if (d / "renders").exists() else []
    versionen = []
    bekannt = set()
    for v in st.get("versionen", []):
        p = d / v["datei"]
        bekannt.add(p.resolve())
        versionen.append({**v, "pfad": rel(p) if p.exists() else None})
    for p in renders:
        if p.resolve() not in bekannt:
            versionen.append({"datei": p.relative_to(d).as_posix(), "zeit": None, "notiz": "", "pfad": rel(p)})
    kom = (lies(KANAL / "kommentare.json", {}) or {}).get("kommentare", [])
    return {**r, "log": st.get("log", []), "versionen": versionen, "reviews": reviews, "pruefboegen": [rel(b) for b in bilder],
            "skript": text(d / "skript.md"), "storyboard": text(d / "storyboard.md"), "brief": text(d / "brief.md"),
            "caption_json": lies(d / "caption.json"), "caption_md": text(d / "caption.md"), "tts": lies(d / "audio" / "tts.json"),
            "stimme": rel(d / "audio" / "voice.wav") if (d / "audio" / "voice.wav").exists() else None,
            "final": rel(d / "renders" / "final_master.mp4") if (d / "renders" / "final_master.mp4").exists() else None,
            "kommentare": [k for k in kom if k.get("reel_id") == rid], "plan": plan_fuer(rid, st.get("thema_id"))}


def credits(neu=False):
    with _lock:
        if not neu and _credits["zeit"] and time.time() - _credits["zeit"] < 600:
            return {**_credits}
    try:
        import credits as cr, tts
        importlib.reload(tts)                   # Schlüssel aus der .env neu lesen (neues Konto ohne Server-Neustart)
        importlib.reload(cr)
        daten, fehler = cr.stand(), None
    except SystemExit as e:                     # tts.api beendet bei Fehlern mit sys.exit
        daten, fehler = None, str(e)
    except Exception as e:                      # noqa: BLE001  offline o. ä.
        daten, fehler = None, f"{type(e).__name__}: {e}"
    with _lock:
        _credits.update(zeit=time.time(), daten=daten or _credits["daten"], fehler=fehler)
        return {**_credits}


KENNZAHLEN_BEFEHL = {
    "instagram": ["tools/instagram/kennzahlen.py", "--alle"],
    "youtube": ["tools/youtube/youtube.py", "kennzahlen"],
    "tiktok": ["tools/tiktok/tiktok.py", "kennzahlen"],
}
_kz_lock = threading.Lock()
IG_ABRUF = {"ok": None, "fehler": None}      # letzter Instagram-Abruf (Kennzahlen/DMs): Erfolg und Fehler je mit Zeit, nur im Speicher


def ig_abruf(art, r):
    """Merkt sich Erfolg bzw. Fehler des letzten Instagram-Abrufs für die Übersicht."""
    if r["ok"]:
        IG_ABRUF["ok"] = {"zeit": jetzt(), "art": art}
    else:
        IG_ABRUF["fehler"] = {"zeit": jetzt(), "art": art, "meldung": str(r.get("fehler"))[:300]}
    return r


def kennzahlen_holen(plattform):
    """Holt die Kennzahlen einer Plattform über das jeweilige Werkzeug (schreibt gedaechtnis/Kennzahlen/<plattform>.json)."""
    befehl = KENNZAHLEN_BEFEHL.get(plattform)
    if not befehl:
        return {"ok": False, "fehler": f"Für {plattform} gibt es noch kein Abruf-Werkzeug."}
    with _kz_lock:
        try:
            r = subprocess.run([sys.executable, "-X", "utf8", *befehl], cwd=ROOT, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=180)
        except subprocess.TimeoutExpired:
            return {"ok": False, "fehler": "Zeitüberschreitung nach 180 s."}
    ausgabe = ((r.stdout or "") + (r.stderr or "")).strip()
    erg = {"ok": r.returncode == 0, "ausgabe": ausgabe[-600:], "fehler": None if r.returncode == 0 else (ausgabe[-300:] or f"Exit {r.returncode}")}
    return ig_abruf("Kennzahlen", erg) if plattform == "instagram" else erg


KENNZAHLEN_MINUTEN = float(os.environ.get("COCKPIT_KENNZAHLEN_MINUTEN") or 15)
KENNZAHLEN_STUNDEN = float(os.environ.get("COCKPIT_KENNZAHLEN_STUNDEN") or 0)   # 0 = bei jedem Durchlauf neu abfragen


def _alter_stunden(plattform):
    stand = (kennzahlen(plattform) or {}).get("stand")
    try:
        d = datetime.datetime.fromisoformat(str(stand))
        return (datetime.datetime.now(d.tzinfo) - d).total_seconds() / 3600
    except (TypeError, ValueError):
        return float("inf")


SPERR_DATEI = ROOT / ".secrets" / "instagram_gesperrt.json"
SPERRE_PRUEFEN_MIN = 30
_sperre_versuch = 0.0


def sperre_pruefen(erzwingen=False):
    """Selbstheilung: Ist die Sperr-Datei älter als 30 min (und der letzte Versuch auch), läuft `tokens.py pruefen`; bei Erfolg fällt die Sperre."""
    global _sperre_versuch
    sp = lies(SPERR_DATEI, None)
    if not sp:
        return {"ok": True, "ausgabe": "Keine Sperre."} if erzwingen else None
    try:
        alt = (datetime.datetime.now() - datetime.datetime.fromisoformat(sp["zeit"])).total_seconds() / 60
    except (KeyError, ValueError):
        alt = float("inf")
    if not erzwingen and (alt < SPERRE_PRUEFEN_MIN or time.time() - _sperre_versuch < SPERRE_PRUEFEN_MIN * 60):
        return None
    _sperre_versuch = time.time()
    r = subprocess.run([sys.executable, "-X", "utf8", "tools/instagram/tokens.py", "pruefen"], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=90)
    ausgabe = ((r.stdout or "") + (r.stderr or "")).strip()
    return {"ok": r.returncode == 0, "ausgabe": ausgabe[-300:], "fehler": None if r.returncode == 0 else ausgabe[-300:]}


def sperre_erneut_pruefen():
    """Knopf im Cockpit: sofort prüfen, bei Erfolg Kennzahlen und DMs neu holen."""
    r = sperre_pruefen(True)
    if r["ok"]:
        r["kennzahlen"] = kennzahlen_holen("instagram")
        r["dms"] = dms_holen()
    return r


def kennzahlen_schleife():
    """Holt die Kennzahlen aller aktiven Plattformen automatisch, solange der Server läuft (Abfrage alle KENNZAHLEN_MINUTEN)."""
    time.sleep(20)                                        # Server erst hochkommen lassen
    while True:
        try:
            r = sperre_pruefen()
            if r:
                print(f"Instagram-Sperre prüfen: {'aufgehoben' if r['ok'] else 'weiter gesperrt'}", flush=True)
        except Exception as e:                  # noqa: BLE001  die Schleife darf daran nie sterben
            print(f"Instagram-Sperre prüfen: {e}", flush=True)
        aktiv = ((lies(KANAL / "kanal.json", {}) or {}).get("plattformen") or {}).get("aktiv", [])
        for pf in KENNZAHLEN_BEFEHL:
            if pf in aktiv and _alter_stunden(pf) >= KENNZAHLEN_STUNDEN:
                r = kennzahlen_holen(pf)
                print(f"Kennzahlen {pf}: {'ok' if r['ok'] else 'FEHLER ' + str(r['fehler'])}", flush=True)
        if "instagram" in aktiv:
            r = dms_holen()
            print(f"DMs: {'ok' if r['ok'] else 'FEHLER ' + str(r['fehler'])}", flush=True)
        for pf, befehl in KOMMENTAR_BOT.items():
            if pf in aktiv or (pf == "zernio" and {"tiktok", "youtube"} & set(aktiv)):
                r = kommentar_bot_lauf(befehl)
                print(f"Kommentar-Bot {pf}: {'ok' if r['ok'] else 'FEHLER ' + str(r['fehler'])}", flush=True)
        time.sleep(KENNZAHLEN_MINUTEN * 60)


WARTESCHLANGE = ["tools/instagram/warteschlange.py"]     # postet fällige, freigegebene Reels auf allen aktiven Plattformen


KOMMENTAR_BOT = {"instagram": ["tools/instagram/kommentare.py", "--alle"], "zernio": ["tools/kommentare_zernio.py", "--alle"]}   # zernio = TikTok + YouTube


def kommentar_bot_lauf(befehl):
    """Lässt den Kommentar-Bot laufen (Modus aus kanal.json → kommentar_bot.modus; bei aus passiert nichts)."""
    with _kz_lock:
        try:
            r = subprocess.run([sys.executable, "-X", "utf8", *befehl], cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=900)
        except subprocess.TimeoutExpired:
            return {"ok": False, "fehler": "Zeitüberschreitung nach 15 min."}
    ausgabe = ((r.stdout or "") + (r.stderr or "")).strip()
    return {"ok": r.returncode == 0, "fehler": None if r.returncode == 0 else (ausgabe[-300:] or f"Exit {r.returncode}")}


def warteschlange_schleife():
    """Postet fällige, freigegebene Reels (eigener Takt, damit ein Post nicht auf den langsameren Kennzahlen-Lauf wartet)."""
    time.sleep(30)
    while True:
        try:                                               # eigener Unterprozess ohne _kz_lock: Kommentar-Läufe dürfen Posts nicht aufhalten
            r = subprocess.run([sys.executable, "-X", "utf8", *WARTESCHLANGE], cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=1800)
            if r.returncode != 0 or "gepostet" in (r.stdout or "").lower():
                print(f"Warteschlange: {((r.stdout or '') + (r.stderr or '')).strip()[-400:]}", flush=True)
        except subprocess.TimeoutExpired:
            print("Warteschlange: Zeitüberschreitung", flush=True)
        time.sleep(120)


def uebersicht():
    rs = reels()
    k = lies(KANAL / "kanal.json", {}) or {}
    offen = [f for f in ("name", "handle", "zielgruppe", "eigene_sprache") if str(k.get(f, "")).startswith("OFFEN")]
    zaehler = {}
    for r in rs:
        zaehler[r["spalte"]] = zaehler.get(r["spalte"], 0) + 1
    backlog = (lies(THEMEN / "backlog.json", {}) or {}).get("themen", [])
    zaehler["idee"] = sum(1 for t in backlog if t.get("status") == "idee")
    aktiv = (k.get("plattformen") or {}).get("aktiv", [])
    plattformen = [{"id": p, "aktiv": p in aktiv, "kennzahlen": kennzahlen(p)} for p in PLATTFORMEN]
    naechste = sorted([r for r in rs if r["stufe"] in ("geplant", "freigabe") and (r.get("freigabe") or {}).get("status") == "freigegeben"],
                      key=lambda r: (r.get("post") or {}).get("geplant_fuer") or "")
    kom = lies(KANAL / "kommentare.json", {}) or {}
    liste = kom.get("kommentare", [])
    sp = lies(ROOT / ".secrets" / "instagram_gesperrt.json", None)      # Instagram-Sperre (tools/instagram/konto.py), 6 h gültig
    try:
        sp = sp if sp and datetime.datetime.now() - datetime.datetime.fromisoformat(sp["zeit"]) < datetime.timedelta(hours=6) else None
    except (KeyError, ValueError):
        sp = None
    return {"dms": {"offen": sum(1 for c in dms()["konversationen"] if c.get("offen"))}, "kanal": k, "ig_gesperrt": sp, "ig_abruf": IG_ABRUF, "offen": offen, "zaehler": zaehler, "plattformen": plattformen, "naechste": naechste,
            "warten": [r for r in rs if r["stufe"] == "freigabe" and not (r.get("freigabe") or {}).get("status")],
            "bot": {**(kom.get("bot") or {"modus": "aus"}), "status": lies(KANAL / "bot_status.json", {}) or {}, "gesamt": len(liste),
                    "eskalationen": sum(1 for c in liste if c.get("eskalieren") and not c.get("erledigt")),
                    "beantwortet": sum(1 for c in liste if c.get("beantwortet")),
                    "ausgeblendet": sum(1 for c in liste if c.get("ausblenden")),
                    "keyword_dms": keyword_dms()},
            "reels": rs, "budget": lies(KANAL / "budget.json"), "stufen": STUFEN}


def keyword_dms():
    """Zähler der automatischen Keyword-DMs (tools/instagram/keyword_dm.py → keyword_dms.json)."""
    z = lies(KANAL / "keyword_dms.json", {}) or {}
    g = (z.get("gesendet") or {}).values()
    heute = datetime.datetime.now().isoformat()[:10]
    return {"gesamt": len(g), "heute": sum(1 for x in g if (x.get("zeit") or "")[:10] == heute), "je_reel": z.get("zaehler") or {},
            "link_fehlt": [{"reel_id": r, "anzahl": len(v.get("offen") or {}), "grund": v.get("grund")} for r, v in (z.get("ohne_link") or {}).items() if v.get("offen")]}


def themen():
    b = lies(THEMEN / "backlog.json", {}) or {}
    wochen = sorted(p.name for p in THEMEN.glob("*-KW*.md"))
    k = lies(KANAL / "kanal.json", {}) or {}
    return {"themen": b.get("themen", []), "saeulen": k.get("saeulen", []), "wochenlisten": wochen}


def thema_setzen(tid, daten):
    erlaubt = {"prio": (None, 1, 2, 3), "status": ("idee", "in_arbeit", "erledigt", "verworfen")}
    with _lock:
        p = THEMEN / "backlog.json"
        b = lies(p, {}) or {}
        for t in b.get("themen", []):
            if t["id"] == tid:
                for f, werte in erlaubt.items():
                    if f in daten:
                        if daten[f] not in werte:
                            raise ValueError(f"{f}={daten[f]!r} nicht erlaubt")
                        t[f] = daten[f]
                t["geaendert"] = jetzt()
                schreib(p, b)
                return t
    raise KeyError(f"Thema {tid} nicht gefunden")


def freigabe(rid, daten):
    """Über tools/status.py, damit Cockpit und Agenten dieselbe Logik nutzen."""
    entscheid = daten.get("entscheid")
    if entscheid not in ("freigegeben", "aendern", "verworfen"):
        raise ValueError("entscheid muss freigegeben, aendern oder verworfen sein")
    if entscheid == "aendern" and not (daten.get("feedback") or "").strip():
        raise ValueError("Bei „Ändern“ bitte beschreiben, was anders werden soll")
    cmd = [sys.executable, "-X", "utf8", str(ROOT / "tools" / "status.py"), str(REELS / rid), "freigabe", entscheid,
           "--agent", "nutzer (Cockpit)"]
    if daten.get("feedback"):
        cmd += ["--feedback", daten["feedback"].strip()]
    if entscheid == "freigegeben" and daten.get("um"):
        if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d", daten["um"]):
            raise ValueError("Zeit im Format JJJJ-MM-TTTHH:MM")
        cmd += ["--um", daten["um"]]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    if r.returncode:
        raise ValueError((r.stderr or r.stdout).strip().splitlines()[-1])
    return reel_voll(rid)


PLAN = THEMEN / "plan.json"


def plan():
    return (lies(PLAN, {}) or {}).get("eintraege", [])


def plan_fuer(rid, thema_id):
    """Kalender-Eintrag eines Reels (direkt oder über sein Thema) – Wunschtermin fürs Posten."""
    return next((e for e in plan() if e.get("reel_id") == rid or (thema_id and e.get("thema_id") == thema_id)), None)


def plan_pruefen(daten, e):
    if "datum" in daten:
        if not re.fullmatch(r"\d{4}-\d\d-\d\d", str(daten["datum"])):
            raise ValueError("Datum im Format JJJJ-MM-TT")
        e["datum"] = daten["datum"]
    if daten.get("thema_id"):
        if not any(t["id"] == daten["thema_id"] for t in (lies(THEMEN / "backlog.json", {}) or {}).get("themen", [])):
            raise KeyError(f"Thema {daten['thema_id']} nicht gefunden")
        e["thema_id"] = daten["thema_id"]
    if daten.get("reel_id"):
        if not (REELS / daten["reel_id"] / "status.json").exists() or "/" in daten["reel_id"]:
            raise KeyError(f"Reel {daten['reel_id']} nicht gefunden")
        e["reel_id"] = daten["reel_id"]
    if "notiz" in daten:
        e["notiz"] = str(daten["notiz"] or "").strip()[:300]
    if not (e.get("thema_id") or e.get("reel_id") or e.get("notiz")):
        raise ValueError("Thema, Reel oder Notiz angeben")


def plan_neu(daten):
    with _lock:
        p = lies(PLAN, {}) or {"_doc": "Planungskalender aus dem Cockpit: welches Thema an welchem Tag gepostet werden soll. "
                                      "/reel nimmt ohne Argument den nächsten Eintrag ab heute; der Tag ist der Wunschtermin bei der Freigabe.",
                                "eintraege": []}
        nummern = [int(re.sub(r"\D", "", e["id"]) or 0) for e in p["eintraege"]]
        e = {"id": f"P-{max(nummern, default=0) + 1:03d}", "angelegt": jetzt()}
        if "datum" not in daten:
            raise ValueError("Datum fehlt")
        plan_pruefen(daten, e)
        p["eintraege"].append(e)
        p["eintraege"].sort(key=lambda x: x["datum"])
        schreib(PLAN, p)
        return e


def plan_aendern(pid, daten):
    with _lock:
        p = lies(PLAN, {}) or {"eintraege": []}
        for i, e in enumerate(p["eintraege"]):
            if e["id"] == pid:
                if daten.get("loeschen"):
                    p["eintraege"].pop(i)
                else:
                    plan_pruefen(daten, e)
                    e["geaendert"] = jetzt()
                    p["eintraege"].sort(key=lambda x: x["datum"])
                schreib(PLAN, p)
                return {"ok": True, "eintrag": e}
    raise KeyError(f"Plan-Eintrag {pid} nicht gefunden")


def dms():
    d = lies(KANAL / "dms.json", {}) or {}
    return {"stand": d.get("stand"), "quellen": d.get("quellen") or {}, "konversationen": d.get("konversationen") or [],
            "bot_status": lies(KANAL / "bot_status.json", {}) or {}}


def dm_erledigt(cid):
    with _lock:
        p = KANAL / "dms.json"
        d = lies(p, {}) or {}
        for c in d.get("konversationen", []):
            if str(c.get("id")) == cid:
                c["erledigt"], c["offen"] = jetzt(), False
                schreib(p, d)
                return c
    raise KeyError(f"Konversation {cid} nicht gefunden")


def dms_holen():
    """Holt die DMs über tools/instagram/dms.py (schreibt gedaechtnis/Kanal/dms.json)."""
    with _kz_lock:
        try:
            r = subprocess.run([sys.executable, "-X", "utf8", "tools/instagram/dms.py", "--alle"], cwd=ROOT, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=180)
        except subprocess.TimeoutExpired:
            return {"ok": False, "fehler": "Zeitüberschreitung nach 180 s."}
    ausgabe = ((r.stdout or "") + (r.stderr or "")).strip()
    return ig_abruf("DMs", {"ok": r.returncode == 0, "fehler": None if r.returncode == 0 else (ausgabe[-300:] or f"Exit {r.returncode}")})


def dm_antworten(cid, daten):
    """Schickt die vom Nutzer bestätigte Antwort über tools/instagram/dms.py senden ab."""
    text = (daten.get("text") or "").strip()
    if not text:
        return {"ok": False, "fehler": "Bitte erst eine Antwort schreiben."}
    with _kz_lock:
        r = subprocess.run([sys.executable, "-X", "utf8", "tools/instagram/dms.py", "senden", cid], input=text, cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    ausgabe = ((r.stdout or "") + (r.stderr or "")).strip()
    return {"ok": r.returncode == 0, "fehler": None if r.returncode == 0 else (ausgabe[-300:] or f"Exit {r.returncode}")}


def kommentar_erledigt(cid):
    with _lock:
        p = KANAL / "kommentare.json"
        k = lies(p, {}) or {}
        for c in k.get("kommentare", []):
            if str(c.get("id")) == cid:
                c["erledigt"] = jetzt()
                schreib(p, k)
                return c
    raise KeyError(f"Kommentar {cid} nicht gefunden")


# Neben dem Gedächtnis zeigt „Wissen“ auch die Regeln der Skills und Agenten (nur lesen, Quelle ist .claude/)
REGELN = {"_skills": ("Abläufe (Skills)", lambda: sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md")), lambda p: p.parent.name),
          "_agenten": ("Agenten", lambda: sorted((ROOT / ".claude" / "agents").glob("*.md")), lambda p: p.stem)}


def gedaechtnis_baum():
    out = []
    def eintrag(p, pfad, ordner, name):
        out.append({"pfad": pfad, "ordner": ordner, "name": name,
                    "geaendert": time.strftime("%Y-%m-%dT%H:%M", time.localtime(p.stat().st_mtime))})
    for p in sorted(GEDAECHTNIS.rglob("*.md")):
        r = p.relative_to(GEDAECHTNIS).as_posix()
        if "stimm-casting" not in r:
            eintrag(p, r, p.parent.relative_to(GEDAECHTNIS).as_posix(), p.stem)
    for kurz, (titel, dateien, name) in REGELN.items():
        for p in dateien():
            eintrag(p, f"{kurz}/{name(p)}.md", titel, name(p))
    return out


def gedaechtnis_datei(pfad):
    kurz, _, rest = pfad.partition("/")
    if kurz in REGELN:
        p = next((d for d in REGELN[kurz][1]() if f"{REGELN[kurz][2](d)}.md" == rest), None)
        if not p:
            raise KeyError(f"Regel {pfad} nicht gefunden")
        return {"pfad": pfad, "text": p.read_text(encoding="utf-8"), "quelle": rel(p)}
    p = (GEDAECHTNIS / pfad).resolve()
    if GEDAECHTNIS.resolve() not in p.parents or p.suffix != ".md" or not p.exists():
        raise KeyError(f"Notiz {pfad} nicht gefunden")
    return {"pfad": pfad, "text": p.read_text(encoding="utf-8")}


def bibliothek():
    kanal = lies(BIBLIOTHEK / "library.json", {}) or {}
    fmt = lies(KIT.parent / "assets" / "library.json", {}) or {}
    def liste(lib, basis, quelle):
        out = []
        for art in ("images", "sfx", "musik", "clips"):
            for i, e in (lib.get(art) or {}).items():
                f = basis / e.get("file", "") if e.get("file") else None
                out.append({**e, "id": i, "art": art, "quelle_lib": quelle, "pfad": rel(f) if f and f.exists() else None})
        return out
    return {"eintraege": liste(kanal, BIBLIOTHEK, "kanal") + liste(fmt, KIT.parent / "assets", "format")}


UPLOAD_ENDUNGEN = {"bild": (".png", ".jpg", ".jpeg"), "sfx": (".wav", ".mp3", ".m4a", ".ogg"),
                   "musik": (".mp3", ".wav", ".m4a", ".ogg"), "clip": (".mp4", ".mov", ".webm")}
UPLOAD_MAX = 300 * 1024 * 1024


def hochladen(q, laenge, rfile):
    """Eigene Datei in die Kanal-Bibliothek – über tools/bibliothek.py add, damit ID-Regeln, WAV-Umwandlung und Einmessen
    genauso laufen wie bei den Agenten."""
    f = {k: (v[0] if v else "").strip() for k, v in q.items()}
    art = f.get("art")
    endung = Path(f.get("name") or "").suffix.lower()
    if art not in UPLOAD_ENDUNGEN:
        raise ValueError("Art muss bild, sfx, musik oder clip sein")
    if endung not in UPLOAD_ENDUNGEN[art]:
        raise ValueError(f"Dateityp {endung or '?'} passt nicht zu {art} (erlaubt: {', '.join(UPLOAD_ENDUNGEN[art])})")
    for feld in ("id", "tags", "quelle", "lizenz"):
        if not f.get(feld):
            raise ValueError(f"Feld {feld} fehlt")
    if not 0 < laenge <= UPLOAD_MAX:
        raise ValueError("Datei leer oder größer als 300 MB")
    tmp = Path(tempfile.mkdtemp(prefix="cockpit_upload_"))
    try:
        ziel = tmp / f"upload{endung}"
        with ziel.open("wb") as out:
            rest = laenge
            while rest > 0:
                chunk = rfile.read(min(1 << 20, rest))
                if not chunk:
                    raise ValueError("Upload abgebrochen")
                out.write(chunk)
                rest -= len(chunk)
        cmd = [sys.executable, "-X", "utf8", str(ROOT / "tools" / "bibliothek.py"), "add", str(ziel), "--art", art, "--id", f["id"],
               "--tags", f["tags"], "--quelle", f["quelle"], "--lizenz", f["lizenz"]]
        for feld in ("prompt", "credit", "rolle", "saeulen"):
            if f.get(feld):
                cmd += [f"--{feld}", f[feld]]
        if f.get("freisteller") == "1":
            cmd.append("--freisteller")
        with _lock:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        if r.returncode:
            raise ValueError(((r.stderr or r.stdout).strip().splitlines() or ["bibliothek.py fehlgeschlagen"])[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"ok": True, "id": f["id"], "bibliothek": bibliothek()}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path):
        if not path.is_file():
            self.send_error(404)
            return
        size = path.stat().st_size
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        rng = self.headers.get("Range")
        if rng and (m := re.match(r"bytes=(\d+)-(\d*)", rng)):
            start = int(m.group(1))
            end = min(int(m.group(2)) if m.group(2) else size - 1, size - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            length = end - start + 1
        else:
            start, length = 0, size
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if path.suffix.lower() in (".html", ".json", ".js", ".css", ".md"):
            self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        with path.open("rb") as f:
            f.seek(start)
            rest = length
            while rest > 0:
                chunk = f.read(min(1 << 20, rest))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                rest -= len(chunk)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _sicher(self, arbeit):
        try:
            arbeit()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (KeyError, ValueError) as e:
            self._json({"ok": False, "fehler": str(e).strip("'\"")}, 400)
        except Exception as e:                  # noqa: BLE001
            print(f"FEHLER bei {self.command} {self.path}:", flush=True)
            traceback.print_exc()
            self._json({"ok": False, "fehler": f"{type(e).__name__}: {e}"}, 500)

    def do_GET(self):
        self._sicher(self._get)

    def do_POST(self):
        self._sicher(self._post)

    def _get(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        p = unquote(u.path)
        if p in ("/", "/index.html"):
            return self._file(HERE / "index.html")
        if p in ("/app.js", "/style.css", "/md.js", "/favicon.svg"):
            return self._file(HERE / p[1:])
        if re.fullmatch(r"/icons/(instagram|facebook|tiktok|youtube|logo|apple-touch-icon)\.png", p):
            return self._file(HERE / p[1:])
        if p.startswith("/datei/"):
            f = (ROOT / p[len("/datei/"):]).resolve()
            if not any(f == b.resolve() or b.resolve() in f.parents for b in FREIGEGEBEN):
                return self.send_error(403)
            return self._file(f)
        api = {
            "/api/uebersicht": uebersicht,
            "/api/reels": lambda: {"reels": reels(), "stufen": STUFEN},
            "/api/themen": themen,
            "/api/dms": dms,
            "/api/kommentare": lambda: {**(lies(KANAL / "kommentare.json", {}) or {"bot": {"modus": "aus"}, "kommentare": []}),
                                         "bot_status": lies(KANAL / "bot_status.json", {}) or {}},
            "/api/dm-funnel": lambda: {**keyword_config.load(),
                                               "test_active": bool((lies(ROOT / ".secrets" / "automation" / "instagram_keyword_test.json", {}) or {}).get("aktiv")),
                                               "reel_list": funnel_reels()},
            "/api/gedaechtnis": lambda: {"notizen": gedaechtnis_baum()},
            "/api/bibliothek": bibliothek,
            "/api/plan": lambda: {"eintraege": plan()},
            "/api/credits": lambda: credits(neu="neu" in q),
        }
        if p in api:
            return self._json(api[p]())
        if p.startswith("/api/reel/"):
            r = reel_voll(p[len("/api/reel/"):])
            return self._json(r) if r else self._json({"fehler": "Reel nicht gefunden"}, 404)
        if p == "/api/gedaechtnis/datei":
            return self._json(gedaechtnis_datei(q.get("pfad", [""])[0]))
        self.send_error(404)

    def _post(self):
        u = urlparse(self.path)
        p = unquote(u.path)
        if p == "/api/bibliothek/upload":
            return self._json(hochladen(parse_qs(u.query), int(self.headers.get("Content-Length") or 0), self.rfile))
        if p == "/api/plan":
            return self._json(plan_neu(self._body()))
        if p == "/api/dm-funnel/default":
            return self._json(keyword_config.save_default(self._body()))
        if m := re.fullmatch(r"/api/dm-funnel/reel/([^/]+)", p):
            return self._json(keyword_config.save_reel(m.group(1), self._body()))
        if m := re.fullmatch(r"/api/dm-funnel/reset/([^/]+)", p):
            return self._json(keyword_config.reset_reel(m.group(1)))
        if m := re.fullmatch(r"/api/plan/([^/]+)", p):
            return self._json(plan_aendern(m.group(1), self._body()))
        if m := re.fullmatch(r"/api/reel/([^/]+)/freigabe", p):
            return self._json(freigabe(m.group(1), self._body()))
        if m := re.fullmatch(r"/api/thema/([^/]+)", p):
            return self._json(thema_setzen(m.group(1), self._body()))
        if m := re.fullmatch(r"/api/kennzahlen/(instagram|facebook|tiktok|youtube)", p):
            return self._json(kennzahlen_holen(m.group(1)))
        if p == "/api/instagram/pruefen":
            return self._json(sperre_erneut_pruefen())
        if p == "/api/dms/aktualisieren":
            return self._json(dms_holen())
        if m := re.fullmatch(r"/api/dm/([^/]+)/antworten", p):
            return self._json(dm_antworten(m.group(1), self._body()))
        if m := re.fullmatch(r"/api/dm/([^/]+)/erledigt", p):
            return self._json(dm_erledigt(m.group(1)))
        if m := re.fullmatch(r"/api/kommentar/([^/]+)/erledigt", p):
            return self._json(kommentar_erledigt(m.group(1)))
        self.send_error(404)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    host = "0.0.0.0" if "--lan" in sys.argv else "127.0.0.1"
    print(f"Cockpit läuft: http://localhost:{PORT}" + ("  (auch im WLAN)" if host == "0.0.0.0" else ""), flush=True)
    threading.Thread(target=kennzahlen_schleife, daemon=True).start()
    threading.Thread(target=warteschlange_schleife, daemon=True).start()
    ThreadingHTTPServer((host, PORT), Handler).serve_forever()
