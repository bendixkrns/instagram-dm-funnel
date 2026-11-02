"""Token der Instagram-Konten prüfen und erneuern.

  python tools/instagram/tokens.py konten                       Konten und Schlüssel-Stand (ohne Werte)
  python tools/instagram/tokens.py pruefen [--konto ID | --alle]   fragt die API: Token gültig? gehört er zum Konto?
  python tools/instagram/tokens.py erneuern [--konto ID | --alle] [--auch-frische]
                                                               verlängert um 60 Tage (nur wenn älter als 24 h und
                                                               nicht abgelaufen); --alle erneuert nur Tokens mit < 14 Tagen Rest
pruefen fragt immer echt nach (auch bei aktiver Sperre) und hebt die Sperre auf (.secrets/instagram_gesperrt.json), wenn es klappt.
Das erneuerte Token landet in .secrets/instagram_tokens.json (nicht im Git), die .env bleibt unverändert.
"""
import argparse
import datetime

import konto as K


def wahl(a):
    return K.konten() if a.alle else [K.konto(a.konto)]


def pruefen(k):
    me = K.api("GET", "me", {"fields": "user_id,username"}, K.token(k), trotz_sperre=True)
    soll = K.user_id(k)
    ok = str(me.get("user_id")) == str(soll) or str(me.get("id")) == str(soll)
    K.sperre_aufheben()
    ab = K.token_ablauf(k)
    print(f"{k['id']}: Token gültig, Konto @{me.get('username')}" + ("" if ok else f"  ⚠ User-ID passt nicht zu {K.prefix(k)}_USER_ID")
          + (f", läuft ab {ab[:10]}" if ab else ", Ablauf unbekannt (noch nicht erneuert)"))
    return ok


def erneuern(k, nur_faellige):
    ab = K.token_ablauf(k)
    if nur_faellige and ab:
        rest = (datetime.datetime.fromisoformat(ab) - datetime.datetime.now()).days
        if rest >= 14:
            print(f"{k['id']}: noch {rest} Tage, nichts zu tun")
            return
    r = K.api("GET", "refresh_access_token", {"grant_type": "ig_refresh_token"}, K.token(k), versioniert=False)
    laeuft = (datetime.datetime.now() + datetime.timedelta(seconds=int(r["expires_in"]))).isoformat(timespec="seconds")
    K.token_speichern(k, r["access_token"], laeuft)
    print(f"{k['id']}: erneuert, gültig bis {laeuft[:10]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["konten", "pruefen", "erneuern"])
    ap.add_argument("--konto")
    ap.add_argument("--alle", action="store_true")
    ap.add_argument("--auch-frische", action="store_true", help="auch Tokens mit viel Restlaufzeit erneuern")
    a = ap.parse_args()
    if a.cmd == "konten":
        for k in K.konten():
            tok = bool(K.env_opt(K.prefix(k) + "_ACCESS_TOKEN") or (K.lies(K.TOKENS, {}) or {}).get(k["id"]))
            uid = bool(K.env_opt(K.prefix(k) + "_USER_ID"))
            print(f"{k['id']:<16} @{k['handle']:<16} {'aktiv' if k.get('aktiv', True) else 'aus':<6} Token: {'ja' if tok else 'FEHLT'}  User-ID: {'ja' if uid else 'FEHLT'}"
                  f"  ({K.prefix(k)}_ACCESS_TOKEN / _USER_ID)")
    elif a.cmd == "pruefen":
        if not all([pruefen(k) for k in wahl(a)]):
            raise SystemExit(1)
    else:
        for k in wahl(a):
            erneuern(k, nur_faellige=a.alle and not a.auch_frische)


if __name__ == "__main__":
    main()
