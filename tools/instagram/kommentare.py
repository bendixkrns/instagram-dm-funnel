"""Kommentar-Bot: neue Kommentare unter den eigenen Reels holen, mit Claude (Haiku, Skill `kommentare`) einordnen,
antworten/ausblenden/eskalieren – je Konto.

  python -X utf8 tools/instagram/kommentare.py [--konto ID | --alle] [--modus aus|probelauf|live] [--trocken]

Modus aus kanal.json → kommentar_bot.modus (live = antwortet selbst, probelauf = nur protokollieren, aus = nichts).
Protokoll: gedaechtnis/Kanal/kommentare.json (Cockpit → Kommentare). Kritik und Heikles werden nie beantwortet, sondern eskaliert.
Regeln: gedaechtnis/Kanal/Kommentar-Regeln.md. Höchstens 30 Antworten pro Stunde, eine Antwort je Reel und Person.
Keyword-Kommentare (z. B. SLEEP) erledigt vorher keyword_dm.py ohne Haiku: öffentliche Kurzantwort + Private Reply mit reels/<id>/ressource.md.
Themenideen landen in gedaechtnis/Themen/aus-kommentaren.md. Braucht die Berechtigung instagram_business_manage_comments.

Bei aktiver Instagram-Sperre (konto.py, < 6 h) macht das Werkzeug keinen Aufruf, sondern meldet es nur.
"""
import argparse
import datetime
import json
import sys

import keyword_dm as KW
import konto as K
from kanal import KANAL, REELS, ROOT, THEMEN, env, jetzt, kanal, lies, schreib
from automation import llm
from automation import status as bot_status

DATEI = KANAL / "kommentare.json"
SKILL = ROOT / ".claude" / "skills" / "kommentare" / "SKILL.md"
MAX_PRO_STUNDE = 30
TAGE_ZURUECK = 30


def eigene_reels(k):
    """→ [(reel-id, Ordner, status)] der Reels dieses Kontos, die live und höchstens TAGE_ZURUECK Tage alt sind."""
    standard = K.konto()["id"]
    grenze = datetime.datetime.now() - datetime.timedelta(days=TAGE_ZURUECK)
    out = []
    for sp in sorted(REELS.glob("*/status.json")) if REELS.exists() else []:
        st = lies(sp, {})
        post = st.get("post") or {}
        if post.get("media_id") and st.get("konto", standard) == k["id"] and post.get("gepostet_am") \
                and datetime.datetime.fromisoformat(post["gepostet_am"]) > grenze:
            out.append((st["id"], sp.parent, st))
    return out


def sprechtext(d):
    t = (d / "skript.md")
    if not t.exists():
        return ""
    s = t.read_text(encoding="utf-8")
    a = s.find("## Sprechtext")
    if a < 0:
        return ""
    e = s.find("\n## ", a + 5)
    return s[a + 13: e if e > 0 else None].strip()[:1600]


def kommentar_quelle():
    """BOT_KOMMENTARE_QUELLE: poll (Standard, fragt Meta ab) | webhook (nur Ereignisse) | beides (Webhook, dazu Abfrage als Sicherung)."""
    try:
        wert = (env("BOT_KOMMENTARE_QUELLE") or "poll").strip().lower()
    except SystemExit:
        return "poll"
    return wert if wert in {"poll", "webhook", "beides"} else "poll"


def neue_kommentare_webhook(k, bekannt):
    """→ neue Kommentare aus den vom Webhook gespeicherten Ereignissen (kein Meta-Aufruf, gleiche Felder wie die Abfrage)."""
    from automation import instagram_webhook as hook
    reels = {st["post"]["media_id"]: (rid, d, st) for rid, d, st in eigene_reels(k)}
    neu = []
    events = hook.comment_events(K.user_id(k))
    hook.forget_comment_events([e["id"] for e in events if e["id"] in bekannt])      # schon bearbeitet: nicht länger vorhalten
    for e in events:
        if e["media"] not in reels or e["id"] in bekannt or e["username"] == k["handle"].lstrip("@"):
            continue
        rid, d, st = reels[e["media"]]
        neu.append(_eintrag({"id": e["id"], "text": e["text"], "username": e["username"], "timestamp": e["zeit"]},
                            e["parent"] or e["id"], rid, st, d, False))
    return neu


def neue_kommentare(k, tok, bekannt):
    """→ Liste neuer Kommentare je nach Quelle (kommentar_quelle) mit den Feldern des Skills `kommentare`."""
    quelle = kommentar_quelle()
    if quelle == "poll":
        return neue_kommentare_abfrage(k, tok, bekannt)
    aus_webhook = neue_kommentare_webhook(k, bekannt)
    if quelle == "webhook":
        return aus_webhook
    gesehen = {c["id"] for c in aus_webhook}
    return aus_webhook + [c for c in neue_kommentare_abfrage(k, tok, bekannt) if c["id"] not in gesehen]


def neue_kommentare_abfrage(k, tok, bekannt):
    """→ Liste neuer Kommentare (ohne eigene), per Meta-Abfrage geholt."""
    neu = []
    fehler = []
    for rid, d, st in eigene_reels(k):
        try:
            r = K.api("GET", f"{st['post']['media_id']}/comments",
                      {"fields": "id,text,username,timestamp,replies{id,text,username,timestamp}", "limit": 50}, tok)
        except SystemExit as e:
            print(f"{rid}: Kommentare nicht abrufbar: {e}")
            fehler.append(f"{rid}: {e}")
            continue
        if not r.get("data"):
            try:
                meta = K.api("GET", st["post"]["media_id"], {"fields": "comments_count"}, tok)
            except SystemExit as e:
                fehler.append(f"{rid}: Kommentarzahl nicht abrufbar: {e}")
                continue
            if meta.get("comments_count", 0) > 0:
                fehler.append(f"{rid}: Meta meldet {meta['comments_count']} Kommentare, liefert aber keine Kommentar-Daten; App-Modus/Berechtigung prüfen")
                continue
        for c in r.get("data", []):
            antworten = (c.get("replies") or {}).get("data", [])
            wir_haben_geantwortet = any(a.get("username") == k["handle"] for a in antworten)
            if c.get("username") != k["handle"] and c["id"] not in bekannt:
                neu.append(_eintrag(c, c["id"], rid, st, d, False))
            for a in antworten:
                if a.get("username") != k["handle"] and a["id"] not in bekannt:
                    neu.append(_eintrag(a, c["id"], rid, st, d, wir_haben_geantwortet))
    if fehler:
        raise RuntimeError("; ".join(fehler))
    return neu


def _eintrag(c, thread, rid, st, d, auf_uns):
    return {"id": c["id"], "text": c.get("text", ""), "user": c.get("username", ""), "zeit": c.get("timestamp"), "thread": thread,
            "reel_id": rid, "reel_titel": st.get("titel", ""), "reel_skript": sprechtext(d), "ist_antwort_auf_uns": auf_uns}


def einordnen(liste):
    """Kommentare über das konfigurierte Backend einordnen; Fehler werden eskaliert."""
    regeln = (KANAL / "Kommentar-Regeln.md").read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8").split("---", 2)[-1]
    eingabe = [{k: c[k] for k in ("id", "text", "user", "reel_id", "reel_titel", "reel_skript", "ist_antwort_auf_uns")} for c in liste]
    prompt = (f"{skill}\n\n# Regeln (gedaechtnis/Kanal/Kommentar-Regeln.md)\n{regeln}\n\n# Ton (kanal.json)\n{kanal().get('ton', '')}\n\n"
              "# Hinweis\nIm Feld reel_skript steht der Sprechtext des Reels (statt reel_payoff). Du brauchst keine Werkzeuge; die Eingabe steht unten. "
              f"Antworte nur mit dem JSON-Array.\n\n# Eingabe\n{json.dumps(eingabe, ensure_ascii=False)}")
    return llm.classify("kommentare", prompt, [c["id"] for c in liste])


def themenidee_notieren(c, idee, k):
    p = THEMEN / "aus-kommentaren.md"
    kopf = "# Themenideen aus Kommentaren\n\n" if not p.exists() else ""
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"{kopf}- {jetzt()[:10]} · @{c['user']} unter {c['reel_id']} ({k['id']}): „{c['text'][:200]}“ → {idee}\n")


def lauf(k, modus, trocken, test=None, nur_keyword=False):
    nur_keyword = nur_keyword or bool(KW.testkonfiguration())
    persist = modus == "live" and not trocken and not test
    tok = K.token(k) if not test else None
    if not test:
        KW.test_funnel_fortsetzen(k, tok, modus, trocken)
    daten = lies(DATEI, {}) or {}
    daten.setdefault("bot", {})
    liste = daten.setdefault("kommentare", [])
    bekannt = {c["id"] for c in liste}
    if test:                                           # Fixture statt API: nie senden, nichts speichern
        neu = [c for c in test["kommentare"] if c["id"] not in bekannt]
        trocken = True
    else:
        neu = neue_kommentare(k, tok, bekannt)
    print(f"{k['id']}: {len(neu)} neue Kommentare (Modus {modus})")
    neu, keyword_eintraege, keyword_fehler = KW.verarbeite(k, tok, neu, modus, trocken, test=bool(test), ressourcen=(test or {}).get("ressourcen"))
    liste.extend(keyword_eintraege)                    # Keyword-Treffer: deterministisch, ohne Haiku
    if keyword_eintraege or not neu:
        daten["bot"].update(modus=modus, letzter_lauf=jetzt())
        if persist:
            schreib(DATEI, daten)
    if not neu:
        if keyword_fehler:
            raise RuntimeError("Keyword-DM fehlgeschlagen: " + "; ".join(keyword_fehler))
        return
    if nur_keyword:
        if keyword_fehler:
            raise RuntimeError("Keyword-DM fehlgeschlagen: " + "; ".join(keyword_fehler))
        return
    if test:
        print(f"  {len(neu)} Kommentare ohne Keyword gingen an Haiku (im Test übersprungen)")
        return
    erg = einordnen(neu)
    stunde = datetime.datetime.now() - datetime.timedelta(hours=1)
    gesendet = sum(1 for c in liste if c.get("beantwortet") and c["beantwortet"] > stunde.isoformat(timespec="seconds"))
    for c in neu:
        e = erg.get(c["id"])
        if not e:
            continue  # nicht eingeordnet → nächster Lauf versucht es erneut
        antwort = (e.get("antwort") or "").strip() or None
        eintrag = {"id": c["id"], "zeit": c["zeit"], "plattform": "instagram", "konto": k["id"], "reel_id": c["reel_id"],
                   "user": c["user"], "text": c["text"], "kategorie": e.get("kategorie"), "antwort": antwort, "beantwortet": None,
                   "ausblenden": bool(e.get("ausblenden")), "eskalieren": bool(e.get("eskalieren")), "grund": e.get("grund", ""),
                   "erledigt": None}
        schon = any(x.get("beantwortet") and x.get("reel_id") == c["reel_id"] and x.get("user") == c["user"] for x in liste)
        if e.get("kategorie") in ("kritik", "heikel") or (antwort and e.get("eskalieren")):
            eintrag.update(antwort=None, eskalieren=True)
        elif antwort and schon:
            eintrag.update(antwort=None, grund="schon beantwortet (eine Antwort je Reel und Person)")
        if modus == "live" and not trocken:
            try:
                if eintrag["ausblenden"]:
                    K.api("POST", c["id"], {"hide": "true"}, tok)
                elif eintrag["antwort"] and gesendet < MAX_PRO_STUNDE:
                    K.api("POST", f"{c['thread']}/replies", {"message": eintrag["antwort"]}, tok)
                    eintrag["beantwortet"] = jetzt()
                    gesendet += 1
                elif eintrag["antwort"]:
                    eintrag.update(antwort=None, grund="Stundenlimit erreicht – im Cockpit prüfen")
            except SystemExit as err:
                eintrag.update(eskalieren=True, grund=f"Senden fehlgeschlagen: {err}")
        if e.get("themenidee") and persist:
            themenidee_notieren(c, e["themenidee"], k)
        liste.append(eintrag)
        print(f"  {eintrag['kategorie']:<10} @{c['user']}: " + ("→ beantwortet" if eintrag["beantwortet"] else "eskaliert" if eintrag["eskalieren"]
                                                                  else "ausgeblendet" if eintrag["ausblenden"] else "(keine Aktion)"))
    daten["bot"].update(modus=modus, letzter_lauf=jetzt())
    if persist:
        schreib(DATEI, daten)
    if keyword_fehler:
        raise RuntimeError("Keyword-DM fehlgeschlagen: " + "; ".join(keyword_fehler))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--konto")
    ap.add_argument("--alle", action="store_true")
    ap.add_argument("--modus", choices=["aus", "probelauf", "live"])
    ap.add_argument("--trocken", action="store_true", help="nichts senden, nichts speichern")
    ap.add_argument("--nur-keyword", action="store_true", help="nur Keyword-DMs bearbeiten")
    ap.add_argument("--test-kommentare", metavar="JSON",
                    help='Fixture {"kommentare": [{id,text,user,reel_id,thread,zeit}], "ressourcen": {reel_id: Text}} statt API; sendet nie')
    a = ap.parse_args()
    test = lies(a.test_kommentare) if a.test_kommentare else None
    modus = a.modus or (kanal().get("kommentar_bot") or {}).get("modus", "aus")
    if modus == "aus":
        print("Kommentar-Bot ist aus (kanal.json → kommentar_bot.modus)")
        return
    if K.gesperrt() and not test:
        msg = K.sperre_melden()
        for k in (K.konten() if a.alle else [K.konto(a.konto)]):
            bot_status.record("keyword_dm" if a.nur_keyword else "kommentare", k["id"], False, msg,
                              dry=a.trocken or modus != "live")
        raise SystemExit(msg)
    failed = False
    for k in (K.konten() if a.alle else [K.konto(a.konto)]):
        if k.get("aktiv", True):
            try:
                lauf(k, modus, a.trocken, test, a.nur_keyword)
                bot_status.record("keyword_dm" if a.nur_keyword else "kommentare", k["id"], True,
                                  dry=a.trocken or modus != "live" or bool(test))
            except (RuntimeError, SystemExit) as exc:
                failed = True
                print(f"FEHLER {k['id']}: {exc}", file=sys.stderr)
                bot_status.record("keyword_dm" if a.nur_keyword else "kommentare", k["id"], False, exc,
                                  dry=a.trocken or modus != "live" or bool(test))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
