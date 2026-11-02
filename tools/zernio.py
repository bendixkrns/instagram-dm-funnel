"""Gemeinsame Zernio-Anbindung (https://docs.zernio.com) für TikTok und YouTube: API-Aufruf, Video-Upload, Konten zuordnen.

  python -X utf8 tools/zernio.py konten     verbundene Zernio-Konten auflisten und fehlende zernio_account_id in konten.json eintragen

Schlüssel: ZERNIO_API_KEY in der .env. Ein Konto in gedaechtnis/Kanal/konten.json läuft über Zernio, wenn es "anbieter": "zernio" hat.
"""
import json
import sys
import urllib.error
import urllib.request

from kanal import KANAL, env, lies, schreib

BASIS = "https://zernio.com/api/v1"
KONTEN = KANAL / "konten.json"

def api(methode, pfad, body=None):
    req = urllib.request.Request(BASIS + pfad, method=methode, data=json.dumps(body).encode("utf-8") if body is not None else None,
                                 headers={"Authorization": f"Bearer {env('ZERNIO_API_KEY')}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            txt = r.read().decode("utf-8")
            return json.loads(txt) if txt.strip() else {}
    except urllib.error.HTTPError as e:
        try:
            d = json.loads(e.read().decode("utf-8"))
            msg = d.get("error") or d.get("message") or d
        except Exception:  # noqa: BLE001
            msg = f"HTTP {e.code}"
        raise SystemExit(f"FEHLER Zernio-API: {msg}")
    except urllib.error.URLError as e:
        raise SystemExit(f"FEHLER: keine Verbindung zu Zernio ({e.reason})")

def hochladen(video):
    p = api("POST", "/media/presign", {"filename": video.name, "contentType": "video/mp4", "size": video.stat().st_size})
    req = urllib.request.Request(p["uploadUrl"], data=video.read_bytes(), method="PUT", headers={"Content-Type": "video/mp4"})
    try:
        urllib.request.urlopen(req, timeout=600).close()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"FEHLER: Upload zu Zernio abgelehnt (HTTP {e.code})")
    return p["publicUrl"]


def konten():
    """Zernio-Konten auflisten; Konten mit anbieter zernio ohne ID bekommen die passende (gleiche Plattform, eindeutig oder gleicher Handle)."""
    d = api("GET", "/accounts")
    liste = d.get("accounts", d if isinstance(d, list) else [])
    for a in liste:
        print(f"{a.get('_id')}  {a.get('platform'):<10} {a.get('username') or a.get('displayName') or ''}")
    reg = lies(KONTEN, {}) or {}
    neu = False
    for k in reg.get("konten", []):
        if k.get("anbieter") != "zernio" or k.get("zernio_account_id"):
            continue
        passend = [a for a in liste if a.get("platform") == k["plattform"]]
        if len(passend) > 1:
            passend = [a for a in passend if (a.get("username") or "").lower() == k.get("handle", "").lower()]
        if len(passend) == 1:
            k["zernio_account_id"] = passend[0]["_id"]
            neu = True
            print(f"→ {k['id']}: zernio_account_id eingetragen")
        else:
            print(f"⚠ {k['id']}: kein eindeutiges {k['plattform']}-Konto in Zernio – zernio_account_id von Hand eintragen")
    if neu:
        schreib(KONTEN, reg)


if __name__ == "__main__":
    if sys.argv[1:] == ["konten"]:
        konten()
    else:
        print(__doc__)
