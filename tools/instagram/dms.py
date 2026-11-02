"""DMs: Direktnachrichten der Kanalkonten holen und für das Cockpit (Seite „DMs“) ablegen. Sendet nie von selbst, nur auf Knopfdruck des Nutzers im Cockpit.

  python -X utf8 tools/instagram/dms.py [--konto ID | --alle] [--trocken]      holen + Antwortvorschläge (Haiku, Skill `dms`)
  echo "Text" | python -X utf8 tools/instagram/dms.py senden <konversation-id>   Antwort des Nutzers abschicken (nur aus dem Cockpit)

Protokoll: gedaechtnis/Kanal/dms.json  {"stand", "quellen": {"<plattform>": {"ok", "stand", "hinweis"}}, "konversationen": [...]}.
Instagram: Graph-API /me/conversations, braucht die Berechtigung instagram_business_manage_messages (Token neu erzeugen, wenn sie fehlt).
TikTok und Facebook haben hier noch keine Anbindung (TikTok bietet Creator-Konten keine DM-Schnittstelle, Facebook braucht ein
Seiten-Token mit pages_messaging); sie stehen in „quellen“ mit dem Grund. Eine Konversation ist „offen“, wenn die letzte Nachricht
von der Gegenseite kam und sie nicht im Cockpit erledigt wurde.

Bei aktiver Instagram-Sperre (konto.py, < 6 h) macht das Werkzeug keinen Aufruf, sondern meldet es nur.
"""
import argparse
import datetime
import json
import sys

import konto as K
from kanal import KANAL, ROOT, jetzt, kanal, lies, schreib
from automation import llm
from automation import status as bot_status

SKILL = ROOT / ".claude" / "skills" / "dms" / "SKILL.md"
FENSTER_STUNDEN = 24       # Instagram erlaubt Antworten nur bis 24 h nach der letzten Nachricht der Gegenseite

DATEI = KANAL / "dms.json"
NACHRICHTEN = 10
NICHT_ANGEBUNDEN = {
    "tiktok": "TikTok-DMs sind hier nicht angebunden; derzeit im TikTok-Postfach prüfen.",
    "youtube": "YouTube-DMs sind hier nicht angebunden; Kommentare werden separat geprüft.",
    "facebook": "Facebook-Seite noch nicht verbunden (Seiten-Token mit pages_messaging nötig).",
}


def konversationen(k, tok):
    """→ Liste von Konversationen des Instagram-Kontos (neueste zuerst), mit den letzten Nachrichten."""
    r = K.api("GET", "me/conversations",
              {"platform": "instagram", "limit": 25,
               "fields": f"id,updated_time,participants,messages.limit({NACHRICHTEN}){{id,message,from,created_time}}"}, tok)
    eigene = str(K.user_id(k))
    out = []
    for c in r.get("data", []):
        gegenueber = next((p for p in (c.get("participants") or {}).get("data", []) if str(p.get("id")) != eigene), {})
        msgs = [{"id": m.get("id"), "von": "wir" if str((m.get("from") or {}).get("id")) == eigene else "user",
                 "text": m.get("message") or "", "zeit": m.get("created_time")}
                for m in (c.get("messages") or {}).get("data", [])]
        msgs.sort(key=lambda m: m["zeit"] or "")
        out.append({"id": c["id"], "plattform": "instagram", "konto": k["id"], "user": gegenueber.get("username") or gegenueber.get("id") or "?", "user_id": gegenueber.get("id"),
                    "zeit": c.get("updated_time"), "nachrichten": msgs})
    return out


def vorschlaege(liste):
    """Validierte Entwürfe für offene Konversationen über das konfigurierte Backend."""
    if not liste:
        return {}
    regeln = (KANAL / "Kommentar-Regeln.md").read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8").split("---", 2)[-1]
    eingabe = [{"id": c["id"], "user": c["user"], "nachrichten": [{"von": m["von"], "text": m["text"]} for m in c["nachrichten"]]} for c in liste]
    teile = [skill, "# Regeln (gedaechtnis/Kanal/Kommentar-Regeln.md)", regeln, "# Ton (kanal.json)", str(kanal().get("ton", "")),
             "# Hinweis", "Du brauchst keine Werkzeuge; die Eingabe steht unten. Antworte nur mit dem JSON-Array.",
             "# Eingabe", json.dumps(eingabe, ensure_ascii=False)]
    prompt = "\n".join(teile)
    return llm.classify("dms", prompt, [c["id"] for c in liste])


def lauf(k, trocken):
    daten = lies(DATEI, {}) or {}
    alt = {c["id"]: c for c in daten.get("konversationen", [])}
    quellen = daten.setdefault("quellen", {})
    try:
        neu = konversationen(k, K.token(k))
    except SystemExit as e:
        quellen["instagram"] = {"ok": False, "stand": jetzt(), "hinweis": str(e).replace("FEHLER Instagram-API: ", "").replace("FEHLER: ", "")}
        print(quellen["instagram"]["hinweis"])
        if not trocken:
            schreib(DATEI, daten)
        raise SystemExit(1)
    for c in neu:
        vorher = alt.pop(c["id"], {})
        if vorher.get("erledigt") and (vorher.get("zeit") or "") >= (c["zeit"] or ""):
            c["erledigt"] = vorher["erledigt"]
        c["offen"] = bool(c["nachrichten"]) and c["nachrichten"][-1]["von"] == "user" and not c.get("erledigt")
        letzte = c["nachrichten"][-1]["id"] if c["nachrichten"] else None
        if vorher.get("vorschlag", {}).get("nachricht_id") == letzte:
            c["vorschlag"] = vorher["vorschlag"]               # schon Entwurf zur aktuellen letzten Nachricht
    brauchen = [c for c in neu if c["offen"] and not c.get("vorschlag")]
    if brauchen and not trocken:
        erg = vorschlaege(brauchen)
        for c in brauchen:
            e = erg.get(c["id"])
            if e:
                c["vorschlag"] = {"nachricht_id": c["nachrichten"][-1]["id"], "kategorie": e.get("kategorie", ""), "entwurf": e.get("entwurf") or "",
                                  "eskalieren": bool(e.get("eskalieren")) or not e.get("entwurf"), "grund": e.get("grund", "")}
    rest = [c for c in alt.values() if c.get("konto") != k["id"] or c.get("plattform") != "instagram"]
    daten["konversationen"] = sorted(neu + rest, key=lambda c: c.get("zeit") or "", reverse=True)
    quellen["instagram"] = {"ok": True, "stand": jetzt(), "hinweis": ""}
    for pf, hinweis in NICHT_ANGEBUNDEN.items():
        quellen[pf] = {"ok": False, "stand": None, "hinweis": hinweis, "nicht_angebunden": True}
    daten["stand"] = jetzt()
    print(f"{k['id']}: {len(neu)} Konversationen, {sum(1 for c in neu if c['offen'])} offen")
    if not trocken:
        schreib(DATEI, daten)


def senden(kid):
    """Text von stdin als Antwort auf die Konversation `kid` schicken (nur Instagram, nur im 24-h-Fenster)."""
    text = sys.stdin.read().strip()
    daten = lies(DATEI, {}) or {}
    c = next((x for x in daten.get("konversationen", []) if x["id"] == kid), None)
    if not c or c.get("plattform") != "instagram":
        raise SystemExit(f"FEHLER: Konversation {kid} nicht gefunden oder nicht von Instagram")
    if not text or len(text) > 1000:
        raise SystemExit("FEHLER: Text fehlt oder ist länger als 1000 Zeichen")
    letzte = next((m for m in reversed(c["nachrichten"]) if m["von"] == "user"), None)
    if not letzte or not c.get("user_id"):
        raise SystemExit("FEHLER: keine Nachricht der Gegenseite, auf die geantwortet werden kann")
    t = datetime.datetime.fromisoformat(letzte["zeit"].replace("+0000", "+00:00"))
    if datetime.datetime.now(datetime.timezone.utc) - t > datetime.timedelta(hours=FENSTER_STUNDEN):
        raise SystemExit("FEHLER: Das 24-Stunden-Antwortfenster von Instagram ist abgelaufen – bitte in der Instagram-App antworten")
    k = K.konto(c.get("konto"))
    r = K.api("POST", "me/messages", {"recipient": json.dumps({"id": c["user_id"]}), "message": json.dumps({"text": text})}, K.token(k))
    c["nachrichten"].append({"id": r.get("message_id") or f"gesendet-{jetzt()}", "von": "wir", "text": text, "zeit": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")})
    c.update(offen=False, zeit=c["nachrichten"][-1]["zeit"])
    c.pop("vorschlag", None)
    schreib(DATEI, daten)
    print("gesendet")


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "senden":
        return senden(sys.argv[2])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--konto")
    ap.add_argument("--alle", action="store_true")
    ap.add_argument("--trocken", action="store_true", help="nichts speichern")
    a = ap.parse_args()
    if K.gesperrt():
        msg = K.sperre_melden()
        for k in (K.konten() if a.alle else [K.konto(a.konto)]):
            bot_status.record("dms", k["id"], False, msg, dry=a.trocken)
        raise SystemExit(msg)
    failed = False
    for k in (K.konten() if a.alle else [K.konto(a.konto)]):
        if k.get("aktiv", True):
            try:
                lauf(k, a.trocken)
                bot_status.record("dms", k["id"], True, dry=a.trocken)
            except SystemExit as exc:
                failed = True
                bot_status.record("dms", k["id"], False, exc, dry=a.trocken)
                print(f"FEHLER {k['id']}: {exc}", file=sys.stderr)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
