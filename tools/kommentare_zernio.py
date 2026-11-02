"""Kommentar-Bot für TikTok und YouTube (über Zernio, Inbox-API). Gleiche Regeln und gleiches Protokoll wie tools/instagram/kommentare.py.

  python -X utf8 tools/kommentare_zernio.py [--konto ID | --alle] [--modus aus|probelauf|live] [--trocken]

Modus aus kanal.json → kommentar_bot.modus (live = antwortet selbst, probelauf = nur protokollieren, aus = nichts).
Protokoll: gedaechtnis/Kanal/kommentare.json (Cockpit → Kommentare, mit Plattform-Filter). Regeln: gedaechtnis/Kanal/Kommentar-Regeln.md,
Einordnung durch Claude (Haiku, Skill `kommentare`). Kritik und Heikles werden nie beantwortet, sondern eskaliert.
Grenzen: Zernio liefert Kommentare bis zu 10 Minuten verzögert. TikTok nur für Konten aus der TikTok-for-Business-App (sonst PLATFORM_LIMITATION).
YouTube: Zernio kann Kommentare lesen und beantworten, aber nicht ausblenden – Spam wird dort an den Nutzer gemeldet (YouTube Studio).
"""
import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "instagram"))
import kommentare as KI  # noqa: E402  Einordnung, Protokoll und Limits des Instagram-Bots mitbenutzen
from kanal import KANAL, REELS, jetzt, kanal, lies, schreib  # noqa: E402
from zernio import api  # noqa: E402
from automation import status as bot_status  # noqa: E402

PLATTFORMEN = ("tiktok", "youtube")


def konten():
    reg = lies(KANAL / "konten.json", {}) or {}
    return [k for k in reg.get("konten", []) if k.get("plattform") in PLATTFORMEN and k.get("aktiv", True)
            and k.get("anbieter") == "zernio" and k.get("zernio_account_id")]


def eigene_reels(k):
    """→ [(reel-id, Ordner, status, post-id)] der live gepostenen Reels dieses Kontos, höchstens TAGE_ZURUECK Tage alt."""
    grenze = datetime.datetime.now() - datetime.timedelta(days=KI.TAGE_ZURUECK)
    out = []
    for sp in sorted(REELS.glob("*/status.json")) if REELS.exists() else []:
        st = lies(sp, {})
        e = st.get(k["plattform"]) or {}
        post_id = e.get("post_id") if k["plattform"] == "tiktok" else e.get("video_id")
        if not post_id or e.get("konto") != k["id"] or e.get("entwurf"):
            continue
        wann = e.get("gepostet_am") or e.get("hochgeladen_am")
        if wann and datetime.datetime.fromisoformat(wann) < grenze:
            continue
        out.append((st["id"], sp.parent, st, post_id))
    return out


def _eigen(c):
    return bool((c.get("from") or {}).get("isOwner"))


def _eintrag(k, c, thread, rid, st, d, post_id, auf_uns):
    von = c.get("from") or {}
    return {"id": c["id"], "text": c.get("message", ""), "user": von.get("username") or von.get("name") or "", "zeit": c.get("createdTime"),
            "thread": thread, "post_id": post_id, "reel_id": rid, "reel_titel": st.get("titel", ""), "reel_skript": KI.sprechtext(d),
            "ist_antwort_auf_uns": auf_uns}


def neue_kommentare(k, bekannt):
    neu = []
    fehler = []
    for rid, d, st, post_id in eigene_reels(k):
        try:
            r = api("GET", f"/inbox/comments/{post_id}?accountId={k['zernio_account_id']}&limit=50")
        except SystemExit as e:
            print(f"{rid}: Kommentare nicht abrufbar: {e}")
            fehler.append(f"{rid}: {e}")
            continue
        for c in r.get("comments", []):
            antworten = c.get("replies") or []
            wir = any(_eigen(a) for a in antworten)
            if not _eigen(c) and c["id"] not in bekannt:
                neu.append(_eintrag(k, c, c["id"], rid, st, d, post_id, False))
            for a in antworten:
                if not _eigen(a) and a["id"] not in bekannt:
                    neu.append(_eintrag(k, a, c["id"], rid, st, d, post_id, wir))
    if fehler:
        raise RuntimeError("; ".join(fehler))
    return neu


def lauf(k, modus, trocken):
    persist = modus == "live" and not trocken
    daten = lies(KI.DATEI, {}) or {}
    daten.setdefault("bot", {})
    liste = daten.setdefault("kommentare", [])
    bekannt = {c["id"] for c in liste}
    neu = neue_kommentare(k, bekannt)
    print(f"{k['id']}: {len(neu)} neue Kommentare (Modus {modus})")
    if not neu:
        daten["bot"].update(modus=modus, letzter_lauf=jetzt())
        if persist:
            schreib(KI.DATEI, daten)
        return
    erg = KI.einordnen(neu)
    stunde = datetime.datetime.now() - datetime.timedelta(hours=1)
    gesendet = sum(1 for c in liste if c.get("beantwortet") and c["beantwortet"] > stunde.isoformat(timespec="seconds"))
    for c in neu:
        e = erg.get(c["id"])
        if not e:
            continue  # nicht eingeordnet → nächster Lauf versucht es erneut
        antwort = (e.get("antwort") or "").strip() or None
        eintrag = {"id": c["id"], "zeit": c["zeit"], "plattform": k["plattform"], "konto": k["id"], "reel_id": c["reel_id"],
                   "user": c["user"], "text": c["text"], "kategorie": e.get("kategorie"), "antwort": antwort, "beantwortet": None,
                   "ausblenden": bool(e.get("ausblenden")), "eskalieren": bool(e.get("eskalieren")), "grund": e.get("grund", ""),
                   "erledigt": None}
        schon = any(x.get("beantwortet") and x.get("reel_id") == c["reel_id"] and x.get("user") == c["user"]
                    and x.get("plattform") == k["plattform"] for x in liste)
        if e.get("kategorie") in ("kritik", "heikel") or (antwort and e.get("eskalieren")):
            eintrag.update(antwort=None, eskalieren=True)
        elif antwort and schon:
            eintrag.update(antwort=None, grund="schon beantwortet (eine Antwort je Reel und Person)")
        if eintrag["ausblenden"] and k["plattform"] == "youtube":
            eintrag.update(ausblenden=False, eskalieren=True, grund="Spam – Zernio kann auf YouTube nicht ausblenden, bitte in YouTube Studio entfernen")
        if modus == "live" and not trocken:
            try:
                if eintrag["ausblenden"]:
                    api("POST", f"/inbox/comments/{c['post_id']}/{c['id']}/hide", {"accountId": k["zernio_account_id"]})
                elif eintrag["antwort"] and gesendet < KI.MAX_PRO_STUNDE:
                    api("POST", f"/inbox/comments/{c['post_id']}", {"accountId": k["zernio_account_id"], "message": eintrag["antwort"],
                                                                     "commentId": c["thread"]})
                    eintrag["beantwortet"] = jetzt()
                    gesendet += 1
                elif eintrag["antwort"]:
                    eintrag.update(antwort=None, grund="Stundenlimit erreicht – im Cockpit prüfen")
            except SystemExit as err:
                eintrag.update(eskalieren=True, grund=f"Senden fehlgeschlagen: {err}")
        if e.get("themenidee") and persist:
            KI.themenidee_notieren(c, e["themenidee"], k)
        liste.append(eintrag)
        print(f"  {eintrag['kategorie']:<10} @{c['user']}: " + ("→ beantwortet" if eintrag["beantwortet"] else "eskaliert" if eintrag["eskalieren"]
                                                                  else "ausgeblendet" if eintrag["ausblenden"] else "(keine Aktion)"))
    daten["bot"].update(modus=modus, letzter_lauf=jetzt())
    if persist:
        schreib(KI.DATEI, daten)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--konto")
    ap.add_argument("--alle", action="store_true")
    ap.add_argument("--modus", choices=["aus", "probelauf", "live"])
    ap.add_argument("--trocken", action="store_true", help="nichts senden, nichts speichern")
    a = ap.parse_args()
    modus = a.modus or (kanal().get("kommentar_bot") or {}).get("modus", "aus")
    if modus == "aus":
        print("Kommentar-Bot ist aus (kanal.json → kommentar_bot.modus)")
        return
    failed = False
    for k in konten():
        if a.alle or not a.konto or k["id"] == a.konto:
            try:
                lauf(k, modus, a.trocken)
                bot_status.record("kommentare", k["id"], True, dry=a.trocken or modus != "live")
            except (RuntimeError, SystemExit) as exc:
                failed = True
                print(f"FEHLER {k['id']}: {exc}", file=sys.stderr)
                bot_status.record("kommentare", k["id"], False, exc, dry=a.trocken or modus != "live")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
