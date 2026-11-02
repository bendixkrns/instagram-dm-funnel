"""Keyword-Kommentar → automatische DM (Private Reply) auf Instagram.

Kommentiert jemand unter einem Reel das Keyword (z. B. SLEEP), antwortet der Bot kurz öffentlich (wechselnde Varianten) und schickt
dem Kommentierenden eine kurze, warme DM mit Link auf das Ressourcen-PDF (reels/<id>/ressource.pdf, Hosting-Link von Hand) als Private Reply: POST /{ig-user-id}/messages mit
recipient {"comment_id": …} und message {"text": …} (graph.instagram.com, Instagram-Login). Grenzen laut Meta-Doku: höchstens 7 Tage
nach dem Kommentar, nur eine Nachricht je Kommentierendem, Berechtigungen instagram_business_manage_messages + instagram_business_manage_comments.

Einmaliger Live-Test: .secrets/automation/instagram_keyword_test.json überschreibt für genau ein Reel das Keyword mit TEST.
Nur der erste exakte Kommentar TEST bekommt eine Private Reply mit der Button-Vorlage „Send link“. Nach Button-Klick oder der DM-Antwort
SEND LINK wird is_user_follow_business geprüft; bei fehlendem Follow folgt ein Profil-Link mit „I followed ✅“-Button. Erst bei bestätigtem
Follow geht der Test-Link raus. Solange die Testdatei existiert, bleiben andere Instagram-Kommentare unbeantwortet.

Keyword je Reel: caption.json → instagram.keyword, sonst brief.md-Zeile „Keyword: **X**“. Erkennung deterministisch (ganzes Wort,
Groß-/Kleinschreibung egal, Emoji/Satzzeichen egal), VOR der Haiku-Einordnung – Treffer kosten keine Tokens.
Link je Reel: caption.json → instagram.ressource_link, sonst Datei reels/<id>/ressource_link.txt. OHNE Link wird nichts gesendet: der Kommentar
bleibt offen und wird im nächsten Lauf erneut versucht (solange er jünger als 7 Tage ist); das Cockpit zeigt „Ressourcen-Link fehlt“.
Doppelschutz + Ratenbremse: gedaechtnis/Kanal/keyword_dms.json. Gesendet wird nur im Modus live (probelauf zeigt nur an).
"""
import datetime
import random
import re
import time

import konto as K
from kanal import KANAL, REELS, ROOT, jetzt, lies, schreib
from ressource import dm_text as ressource_dm_text
from automation import keyword_config as C

DATEI = KANAL / "keyword_dms.json"
TEST_DATEI = ROOT / ".secrets" / "automation" / "instagram_keyword_test.json"
MAX_PRO_STUNDE = 20
PAUSE = (2, 6)                 # Sekunden, zufällig zwischen zwei Sendungen
FENSTER_TAGE = 7               # Meta: Private Reply nur bis 7 Tage nach dem Kommentar
MAX_FEHLER = 2                 # danach gibt der Bot auf und eskaliert
TEXT_MAX = 1000                # Instagram-Textlimit je Nachricht
VARIANTEN = [
    "Sent you a message. Check your DMs 📩",
    "Just sent it over. Check your DMs",
    "It's in your DMs now 📩",
    "Sent! Take a look in your DMs",
    "Your message is on its way 📩",
    "Check your DMs — it's there",
]


def testkonfiguration():
    """Einmaliger, lokaler Test. Eine vorhandene fehlerhafte Datei stoppt den Lauf sicher."""
    if not TEST_DATEI.exists():
        return None
    cfg = lies(TEST_DATEI, {}) or {}
    if not (cfg.get("aktiv") is True and cfg.get("reel_id") and cfg.get("keyword") == "TEST"
            and str(cfg.get("ziel_link", "")).startswith("https://")
            and str(cfg.get("profil_link", "")).startswith("https://www.instagram.com/")
            and cfg.get("funnel", "adaptive") in {"follow", "email", "follow_email", "adaptive"}):
        raise RuntimeError("Instagram-Keyword-Test: Konfiguration unvollständig; keine Aktion")
    return cfg


def kampagne_fuer(reel, k=None):
    test = testkonfiguration()
    if test:
        if reel != test["reel_id"]:
            return None
        return {**C.load()["default"], "mode": "adaptive" if test.get("funnel", "adaptive") == "follow_email" else test.get("funnel", "adaptive"),
                "keyword": test["keyword"], "link": test["ziel_link"], "profile_link": test["profil_link"], "test": True}
    config = C.for_reel(reel)
    if config.get("active") is False:
        return None
    # Link: eigener des Reels → Reel-Caption/ressource_link.txt → Standard-Link
    config["link"] = (C.load()["reels"].get(reel) or {}).get("link") or ressource_link_fuer(REELS / reel) or C.load()["default"].get("link")
    if k:
        config["profile_link"] = config.get("profile_link") or "https://www.instagram.com/" + k["handle"].lstrip("@") + "/"
    return config


def _erste_test_text(cfg=None):
    return (cfg or C.DEFAULT)["intro_text"]


def _erste_test_dm(cfg=None, cid=""):
    cfg = cfg or C.DEFAULT
    return {"attachment": {"type": "template", "payload": {
        "template_type": "button", "text": _erste_test_text(cfg),
        "buttons": [{"type": "postback", "title": cfg["start_button"], "payload": "KW_SEND:" + str(cid)}]}}}


def _folge_dm(cfg, erneut=False, cid=""):
    text = cfg.get("follow_text", C.DEFAULT["follow_text"])
    if erneut:
        text = cfg.get("follow_again_text", C.DEFAULT["follow_again_text"]) + " " + text
    return {"attachment": {"type": "template", "payload": {
        "template_type": "button",
        "text": text,
        "buttons": [{"type": "web_url", "url": cfg.get("profile_link") or cfg["profil_link"], "title": cfg.get("follow_now_button", C.DEFAULT["follow_now_button"])},
                    {"type": "postback", "payload": "KW_FOLLOWED:" + str(cid), "title": cfg.get("follow_button", C.DEFAULT["follow_button"])}]}}}


def _email_frage(cfg):
    return cfg.get("email_text", C.DEFAULT["email_text"])


def _link_senden(k, tok, flow, cfg):
    K.api("POST", f"{K.user_id(k)}/messages", {}, tok,
          koerper={"recipient": {"id": flow["user_id"]},
                   "message": {"text": cfg.get("link_text", C.DEFAULT["link_text"]).replace("{link}", cfg.get("link") or cfg["ziel_link"])}})
    flow["status"] = "fertig"


def _email_oder_link(k, tok, flow, cfg):
    from automation import instagram_contacts as contacts
    if contacts.email_for(k["id"], flow["user_id"]):
        _link_senden(k, tok, flow, cfg)
    else:
        K.api("POST", f"{K.user_id(k)}/messages", {}, tok,
              koerper={"recipient": {"id": flow["user_id"]}, "message": {"text": _email_frage(cfg)}})
        flow["status"] = "wartet_auf_email"


def _follow_schritt(k, tok, flow, cfg):
    """Folgt die Person schon → Link, sonst Follow-Nachricht."""
    if _folgt(k, tok, flow["user_id"]):
        _link_senden(k, tok, flow, cfg)
    else:
        K.api("POST", f"{K.user_id(k)}/messages", {}, tok,
              koerper={"recipient": {"id": flow["user_id"]}, "message": _folge_dm(cfg, cid=flow.get("comment_id", ""))})
        flow["status"] = "wartet_auf_follow"


def _email_zuerst(cfg):
    """Ablauf „beides“ mit eingestellter Reihenfolge E-Mail vor Follow."""
    return (cfg.get("mode") or cfg.get("funnel")) == "both" and cfg.get("order") == "email_first"


def _folgt(k, tok, user_id):
    if not user_id:
        raise RuntimeError("Instagram hat keine Empfänger-ID für die Folgeprüfung geliefert")
    profil = K.api("GET", str(user_id), {"fields": "is_user_follow_business"}, tok)
    if not isinstance(profil.get("is_user_follow_business"), bool):
        raise RuntimeError("Instagram hat keinen verlässlichen Follow-Status geliefert")
    return profil["is_user_follow_business"]


def _jetzt_utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _nach_letzter_aktion(nachricht, flow):
    try:
        zeit = datetime.datetime.fromisoformat(nachricht["zeit"].replace("+0000", "+00:00"))
        seit = datetime.datetime.fromisoformat(flow["seit_utc"])
        return zeit > seit
    except (KeyError, TypeError, ValueError):
        return False


def _zeitnah(a, b, sekunden=90):
    try:
        x, y = (datetime.datetime.fromisoformat(s.replace("+0000", "+00:00")) for s in (a, b))
        return abs((x - y).total_seconds()) <= sekunden
    except (AttributeError, TypeError, ValueError):
        return False


def _antwort_norm(text):
    return re.sub(r"[^a-z ]", "", (text or "").casefold()).strip()


def test_funnel_fortsetzen(k, tok, modus, trocken):
    """Alle offenen Test-DMs unabhängig voneinander fortsetzen."""
    if modus != "live" or trocken:
        return
    z = _zustand()
    flows = z.get("testlaeufe") or {}
    if not flows and z.get("testlauf"):
        legacy = z["testlauf"]
        flows = {str(legacy.get("comment_id") or "legacy:" + str(legacy.get("user_id"))): legacy}
        z["testlaeufe"] = flows
    pending = {cid: flow for cid, flow in flows.items()
               if flow.get("konto") == k["id"] and flow.get("status") in {"wartet_auf_button", "wartet_auf_follow", "wartet_auf_email"}}
    if not pending:
        return
    import dms  # lokaler Import: nur der Keyword-Pfad sendet automatisch
    from automation.instagram_webhook import button_events
    conversations = {str(conv.get("user_id")): conv for conv in dms.konversationen(k, tok)}
    # Mehrere offene Flows desselben Nutzers (z. B. zwei Reels): Buttons gehören über ihre Kommentar-ID zu genau einem Flow,
    # frei getippte Antworten (PC) zum zuletzt gestarteten.
    neuester = {}
    for cid, flow in pending.items():
        uid = str(flow.get("user_id") or "")
        if uid and (uid not in neuester or flow.get("seit_utc", "") > pending[neuester[uid]].get("seit_utc", "")):
            neuester[uid] = cid
    for cid, flow in pending.items():
        if not flow.get("user_id"):
            continue
        cfg = flow.get("config") or testkonfiguration()
        if not cfg:
            continue
        conv = conversations.get(str(flow["user_id"]), {})
        ist_neuester = neuester.get(str(flow["user_id"])) == cid
        buttons = button_events(flow["user_id"], flow["seit_utc"])
        fremd = [e for e in buttons if e.get("cid") and e["cid"] != str(cid)]
        texte = [m for m in conv.get("nachrichten", []) if not any(
            _antwort_norm(m.get("text")) == _antwort_norm(e["text"]) and _zeitnah(m.get("zeit"), e["zeit"]) for e in fremd)] if ist_neuester else []
        eingang = texte + [e for e in buttons if e.get("cid") == str(cid) or (not e.get("cid") and ist_neuester)]
        neu = [m for m in eingang if m["von"] == "user" and m["id"] not in flow.get("gesehen", [])
               and _nach_letzter_aktion(m, flow)]
        neu.sort(key=lambda m: m.get("zeit") or "")
        for m in neu:
            antwort = _antwort_norm(m.get("text"))
            if flow["status"] == "wartet_auf_button" and antwort in {"send link", _antwort_norm(cfg.get("start_button", "Send link"))}:
                mode = cfg.get("mode") or cfg.get("funnel", "adaptive")
                if mode == "email":
                    _email_oder_link(k, tok, flow, cfg)
                elif _email_zuerst(cfg):
                    from automation import instagram_contacts as contacts
                    if contacts.email_for(k["id"], flow["user_id"]):
                        _follow_schritt(k, tok, flow, cfg)
                    else:
                        _email_oder_link(k, tok, flow, cfg)
                elif _folgt(k, tok, flow["user_id"]):
                    if mode in {"adaptive", "follow_email", "both"}:
                        _email_oder_link(k, tok, flow, cfg)
                    else:
                        _link_senden(k, tok, flow, cfg)
                else:
                    K.api("POST", f"{K.user_id(k)}/messages", {}, tok,
                          koerper={"recipient": {"id": flow["user_id"]}, "message": _folge_dm(cfg, cid=flow.get("comment_id", ""))})
                    flow["status"] = "wartet_auf_follow"
            elif flow["status"] == "wartet_auf_follow" and antwort in {"i followed", _antwort_norm(cfg.get("follow_button", "I followed ✅"))}:
                if _folgt(k, tok, flow["user_id"]):
                    (_email_oder_link if (cfg.get("mode") or cfg.get("funnel")) == "both" and not _email_zuerst(cfg) else _link_senden)(k, tok, flow, cfg)
                else:
                    K.api("POST", f"{K.user_id(k)}/messages", {}, tok,
                          koerper={"recipient": {"id": flow["user_id"]}, "message": _folge_dm(cfg, erneut=True, cid=flow.get("comment_id", ""))})
            elif flow["status"] == "wartet_auf_email":
                from automation import instagram_contacts as contacts
                if contacts.normalize_email(m.get("text")):
                    contacts.save_email(k["id"], flow["user_id"], m["text"])
                    (_follow_schritt if _email_zuerst(cfg) else _link_senden)(k, tok, flow, cfg)
                else:
                    K.api("POST", f"{K.user_id(k)}/messages", {}, tok,
                          koerper={"recipient": {"id": flow["user_id"]},
                                   "message": {"text": cfg.get("email_again_text", C.DEFAULT["email_again_text"]) + " " + _email_frage(cfg)}})
            flow.setdefault("gesehen", []).append(m["id"])
            flow["stand"] = jetzt()
            z["testlaeufe"][cid] = flow
            if (z.get("testlauf") or {}).get("comment_id") == flow.get("comment_id") or "comment_id" not in flow:
                z["testlauf"] = flow
            schreib(DATEI, z)
            break


def keyword_fuer(d):
    """→ Liste der Keywords (Großbuchstaben) des Reel-Ordners d oder None: Cockpit (keywords/keyword) → caption.json → instagram.keyword,
    sonst brief.md „Keyword: **X**“."""
    cfg = testkonfiguration()
    if cfg:
        return [cfg["keyword"]] if d.name == cfg["reel_id"] else None
    override = C.for_reel(d.name)
    if override.get("active") is False:
        return None
    standard = [k.strip().upper() for k in C.load()["default"].get("keywords", []) if k.strip()]
    if override.get("keywords"):
        eigene = [k.strip().upper() for k in override["keywords"] if k.strip()]
        return list(dict.fromkeys(eigene + standard)) or None
    c = lies(d / "caption.json", {}) or {}
    kw = override.get("keyword") or (c.get("instagram") or {}).get("keyword")
    if not kw and (d / "brief.md").exists():
        m = re.search(r"^\W*Keyword:\s*\**\s*([A-Za-z0-9]+)", (d / "brief.md").read_text(encoding="utf-8"), re.M)
        kw = m.group(1) if m else None
    eigene = [kw.strip().upper()] if kw and kw.strip() else []
    return list(dict.fromkeys(eigene + standard)) or None


def ressource_link_fuer(d):
    """→ Link auf das Ressourcen-PDF oder None: caption.json → instagram.ressource_link, sonst ressource_link.txt (erste Zeile)."""
    c = lies(d / "caption.json", {}) or {}
    link = ((c.get("instagram") or {}).get("ressource_link") or "").strip()
    if not link and (d / "ressource_link.txt").exists():
        zeilen = (d / "ressource_link.txt").read_text(encoding="utf-8").strip().splitlines()
        link = zeilen[0].strip() if zeilen else ""
    return link if link.lower().startswith("http") else None


def ressource_fuer(d):
    """→ DM-Text „Here's your 3-step evening plan 👇 <Link>“ oder None, wenn ressource.md oder der Link fehlt."""
    link = ressource_link_fuer(d)
    kurz = ressource_dm_text(d)
    return f"{kurz} {link}"[:TEXT_MAX] if link and kurz else None


def trifft(text, keyword):
    """Ganzes Wort mit Satzzeichen/Emoji; ab fünf Zeichen auch ein Tippfehler."""
    target = keyword.casefold()
    words = re.findall(r"[a-z0-9]+", (text or "").casefold())
    if len(words) != 1:
        return False
    word = words[0]
    return word == target or (len(target) >= 5 and _ein_tippfehler(word, target))


def _ein_tippfehler(word, target):
    """Eine Einfügung, Auslassung, Ersetzung oder Vertauschung benachbarter Zeichen."""
    if abs(len(word) - len(target)) > 1:
        return False
    if len(word) == len(target):
        diff = [i for i, (a, b) in enumerate(zip(word, target)) if a != b]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1
                                  and word[diff[0]] == target[diff[1]] and word[diff[1]] == target[diff[0]])
    short, long = sorted((word, target), key=len)
    return any(short == long[:i] + long[i + 1:] for i in range(len(long)))


def _zustand():
    z = lies(DATEI, {}) or {}
    for f, v in (("ohne_link", {}), ("gesendet", {}), ("personen", {}), ("fehler", {}), ("zeiten", []), ("zaehler", {}), ("letzte_variante", None)):
        z.setdefault(f, v)
    return z


def _letzte_stunde(z):
    grenze = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat(timespec="seconds")
    z["zeiten"] = [t for t in z["zeiten"] if t > grenze]
    return len(z["zeiten"])


def zaehler():
    """Für das Cockpit: {gesamt, heute, letzte_stunde}."""
    z = _zustand()
    heute = jetzt()[:10]
    return {"gesamt": len(z["gesendet"]), "heute": sum(1 for g in z["gesendet"].values() if g.get("zeit", "")[:10] == heute),
            "letzte_stunde": _letzte_stunde(z)}


def verarbeite(k, tok, neu, modus, trocken, test=False, ressourcen=None):
    """Keyword-Treffer aus der Kommentarliste `neu` (Felder wie kommentare.neue_kommentare) abarbeiten.
    → (rest, eintraege, fehler): rest = Kommentare ohne Treffer (gehen an KI); eintraege = Protokollzeilen für kommentare.json.
    Treffer ohne Abschluss (Limit, Ressource fehlt, Sperre, 1. Fehler) bleiben unprotokolliert und werden im nächsten Lauf erneut versucht.
    test=True (Fixture): nie senden; ressourcen = {reel_id: Text} ersetzt fehlende ressource.md."""
    z = _zustand()
    kws, rest, treffer = {}, [], []
    for c in neu:
        if c["reel_id"] not in kws:
            liste = keyword_fuer(REELS / c["reel_id"])
            kws[c["reel_id"]] = [liste] if isinstance(liste, str) else (liste or [])
        kw = next((x for x in kws[c["reel_id"]] if trifft(c["text"], x)), None)
        if kw:
            treffer.append((c, kw))
        else:
            rest.append(c)
    eintraege = []
    fehler = []
    z["ohne_link"] = {}                                # wird unten neu gefüllt (nur aktuell wartende Kommentare)
    senden_ok = modus == "live" and not trocken and not test
    anzahl = _letzte_stunde(z)
    gesperrt = False
    erste = True
    geplant = set()                                  # Personen, die in diesem Lauf schon an der Reihe waren (auch im probelauf)
    for c, kw in treffer:
        cid, reel, user = c["id"], c["reel_id"], c["user"]
        campaign = None if test else kampagne_fuer(reel, k)
        if campaign and not campaign.get("link"):
            campaign = None
        basis = {"id": cid, "zeit": c["zeit"], "plattform": "instagram", "konto": k["id"], "reel_id": reel, "user": user, "text": c["text"],
                 "kategorie": "keyword", "antwort": None, "beantwortet": None, "ausblenden": False, "eskalieren": False, "erledigt": None,
                 "keyword": kw, "dm_gesendet": None}
        person = f"{reel}:{user.lower()}" if user else f"{reel}:comment:{cid}"
        if cid in z["gesendet"] or person in z["personen"] or person in geplant:
            grund = "DM an diese Person für dieses Reel schon gesendet"
            print(f"  keyword {kw:<8} @{user}: übersprungen ({grund})")
            eintraege.append({**basis, "grund": grund})
            continue
        try:
            alter = datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat((c["zeit"] or "").replace("+0000", "+00:00"))
            if alter > datetime.timedelta(days=FENSTER_TAGE):
                grund = f"Kommentar älter als {FENSTER_TAGE} Tage – Private Reply nicht mehr möglich"
                print(f"  keyword {kw:<8} @{user}: {grund}")
                eintraege.append({**basis, "grund": grund})
                continue
        except ValueError:
            pass
        text = ((ressourcen or {}).get(reel) if test else
                _erste_test_text(campaign) if campaign else ressource_fuer(REELS / reel))
        if not text:
            fehlt = "Ressourcen-Link fehlt (caption.json → instagram.ressource_link oder ressource_link.txt)" if ressource_dm_text(REELS / reel) else "ressource.md fehlt"
            print(f"  keyword {kw:<8} @{user}: {fehlt} in {reel} – nichts gesendet, Kommentar bleibt offen, nächster Lauf versucht es erneut")
            z["ohne_link"].setdefault(reel, {"grund": fehlt, "offen": {}})["offen"][cid] = c["zeit"]
            continue
        if gesperrt or K.gesperrt():
            gesperrt = True
            print(f"  keyword {kw:<8} @{user}: Instagram gesperrt – übrig für den nächsten Lauf")
            continue
        if anzahl >= MAX_PRO_STUNDE:
            print(f"  keyword {kw:<8} @{user}: Stundenlimit ({MAX_PRO_STUNDE}/h) erreicht – nächster Lauf")
            continue
        geplant.add(person)
        variants = (campaign or {}).get("public_replies") or VARIANTEN
        variante = random.choice([v for v in variants if v != z["letzte_variante"]] or variants)
        if not senden_ok:
            print(f"  keyword {kw:<8} @{user}: würde senden → öffentlich „{variante}“; DM ({len(text)} Zeichen): {text[:70].replace(chr(10), ' ')} …")
            continue
        if campaign:
            flow = {"comment_id": cid, "reel_id": reel, "konto": k["id"], "user": user,
                    "status": "sendet", "gesehen": [], "stand": jetzt(), "config": campaign}
            z.setdefault("testlaeufe", {})[cid] = flow
            z["testlauf"] = flow
            schreib(DATEI, z)
        if not erste:
            time.sleep(random.uniform(*PAUSE))
        erste = False
        try:
            antwort_dm = K.api("POST", f"{K.user_id(k)}/messages", {}, tok,
                               koerper={"recipient": {"comment_id": cid}, "message": _erste_test_dm(campaign, cid) if campaign else {"text": text}})
        except SystemExit as err:
            fehler.append(str(err))
            z["fehler"][cid] = z["fehler"].get(cid, 0) + 1
            print(f"  keyword {kw:<8} @{user}: Senden fehlgeschlagen ({str(err)[:160]}) – Versuch {z['fehler'][cid]}/{MAX_FEHLER}")
            gesperrt = bool(K.gesperrt())
            if z["fehler"][cid] >= MAX_FEHLER:
                eintraege.append({**basis, "eskalieren": True, "grund": f"Keyword-DM fehlgeschlagen: {str(err)[:200]}"})
            schreib(DATEI, z)
            continue
        jz = jetzt()
        z["gesendet"][cid] = {"reel_id": reel, "user": user, "keyword": kw, "zeit": jz}
        z["personen"][person] = cid
        z["zeiten"].append(jz)
        z["zaehler"][reel] = z["zaehler"].get(reel, 0) + 1
        z["letzte_variante"] = variante
        if campaign:
            flow.update(status="wartet_auf_button", user_id=(antwort_dm or {}).get("recipient_id"),
                        stand=jz, seit_utc=_jetzt_utc())
            z["testlaeufe"][cid] = flow
            z["testlauf"] = flow
            if not flow["user_id"]:
                fehler.append("Private Reply gesendet, aber Meta lieferte keine Empfänger-ID; Funnel kann nicht fortgesetzt werden")
        anzahl += 1
        schreib(DATEI, z)
        eintrag = {**basis, "antwort": variante, "dm_gesendet": jz, "grund": "Keyword-DM gesendet"}
        try:
            K.api("POST", f"{c['thread']}/replies", {"message": variante}, tok)
            eintrag["beantwortet"] = jetzt()
        except SystemExit as err:
            fehler.append(str(err))
            eintrag["grund"] = f"Keyword-DM gesendet, öffentliche Antwort fehlgeschlagen: {str(err)[:150]}"
        eintraege.append(eintrag)
        print(f"  keyword {kw:<8} @{user}: DM gesendet" + (" + öffentlich geantwortet" if eintrag["beantwortet"] else ""))
    if senden_ok:
        schreib(DATEI, z)
    return rest, eintraege, fehler
