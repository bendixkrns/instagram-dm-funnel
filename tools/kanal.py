"""Gemeinsame Helfer der Kanal-Werkzeuge: Pfade, Schlüssel aus ../.env, JSON lesen/schreiben, status.json je Reel.

Alle Werkzeuge in tools/ importieren dieses Modul (python tools/<werkzeug>.py …, Arbeitsordner egal).
"""
import datetime
import json
import os
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent          # …/Video Creation
GEDAECHTNIS = ROOT / "gedaechtnis"
KANAL = GEDAECHTNIS / "Kanal"
REELS = ROOT / "reels"
THEMEN = GEDAECHTNIS / "Themen"
BIBLIOTHEK = ROOT / "bibliothek"
KIT = ROOT / "Formate" / "thepsychnote" / "kit"

# Reihenfolge der Stufen eines Reels (Cockpit-Spalten fassen skript…schnitt zu „In Arbeit“ zusammen)
STUFEN = ["skript", "stimme", "storyboard", "assets", "schnitt", "pruefung", "caption", "freigabe", "geplant", "live"]
ENDSTUFEN = ["verworfen"]


def jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def lies(path, default=None):
    path = pathlib.Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def schreib(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def env(name):
    """Schlüssel aus der Umgebung oder der .env im Arbeitsordner bzw. darüber (Single Source of Truth: ../.env)."""
    if os.environ.get(name):
        return os.environ[name]
    for d in [ROOT, *ROOT.parents][:3]:
        f = d / ".env"
        if f.exists():
            for line in f.read_text(encoding="utf-8-sig").splitlines():
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit(f"FEHLER: {name} fehlt in .env (erwartet in {ROOT.parent / '.env'})")


def kanal():
    return lies(KANAL / "kanal.json", {})


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")).strip("-")
    return s[:48] or "reel"


def reel_dir(ref):
    """Reel-Ordner aus Pfad, Ordnername oder eindeutigem Teil davon."""
    p = pathlib.Path(ref)
    if p.is_dir() and (p / "status.json").exists():
        return p.resolve()
    hits = [d for d in REELS.iterdir() if d.is_dir() and ref in d.name] if REELS.exists() else []
    if len(hits) == 1:
        return hits[0]
    raise SystemExit(f"FEHLER: Reel „{ref}“ nicht eindeutig gefunden ({[h.name for h in hits]})")


def status(reel):
    return lies(pathlib.Path(reel) / "status.json")


def status_update(reel, fn):
    """status.json laden, fn(st) ändern lassen, speichern. Gibt den neuen Stand zurück."""
    p = pathlib.Path(reel) / "status.json"
    st = lies(p)
    if st is None:
        raise SystemExit(f"FEHLER: {p} fehlt – Reel erst mit tools/status.py neu anlegen")
    fn(st)
    st["geaendert"] = jetzt()
    schreib(p, st)
    return st


def log(reel, wer, text):
    status_update(reel, lambda st: st.setdefault("log", []).append({"zeit": jetzt(), "wer": wer, "text": text}))


# Plattformen, auf die ein freigegebenes Reel automatisch verteilt wird (kanal.json → plattformen.aktiv, nur mit Poster)
POSTER = ("instagram", "youtube", "tiktok")


def plattform_stand(st):
    """→ {plattform: gepostet?} für alle aktiven Plattformen mit Poster."""
    aktiv = [p for p in (kanal().get("plattformen") or {}).get("aktiv", []) if p in POSTER]
    gepostet = {"instagram": bool((st.get("post") or {}).get("media_id")), "youtube": bool((st.get("youtube") or {}).get("video_id") or (st.get("youtube") or {}).get("zernio_post_id")),
                "tiktok": bool((st.get("tiktok") or {}).get("post_id")) and not (st.get("tiktok") or {}).get("entwurf")}
    return {p: gepostet[p] for p in aktiv}


def live_wenn_fertig(reel):
    """Stufe auf live setzen, sobald das Reel auf allen aktiven Plattformen gepostet ist."""
    st = status(reel)
    stand = plattform_stand(st)
    if stand and all(stand.values()) and st.get("stufe") != "live":
        status_update(reel, lambda s: s.update(stufe="live"))
        log(reel, "publisher", "Auf allen Plattformen gepostet: " + ", ".join(stand))


# --- Postsperre: nur ein Post-Lauf gleichzeitig (Warteschlange, Cockpit-Thread, posten.py --jetzt) -----------------------
POSTSPERRE = ROOT / ".secrets" / "warteschlange.lock"
POSTSPERRE_MAX_MIN = 45          # eine ältere Sperre gilt als verwaist (Absturz)


def postsperre_nehmen():
    """→ True, wenn dieser Prozess die Postsperre bekommen hat (Datei atomar anlegen). Mit postsperre_freigeben() lösen."""
    POSTSPERRE.parent.mkdir(exist_ok=True)
    try:
        if POSTSPERRE.exists() and (datetime.datetime.now().timestamp() - POSTSPERRE.stat().st_mtime) / 60 > POSTSPERRE_MAX_MIN:
            POSTSPERRE.unlink()
        os.close(os.open(POSTSPERRE, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except FileExistsError:
        return False


def postsperre_freigeben():
    POSTSPERRE.unlink(missing_ok=True)
