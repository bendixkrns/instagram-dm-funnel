"""Ressource eines Reels als PDF: reels/<id>/ressource.md -> reels/<id>/ressource.pdf (Seiten 1080x1350, Kanal-CI The PsychNote).

    python -X utf8 tools/ressource.py <reel-id oder Ordner> [--html]    (--html lässt die erzeugte HTML-Datei als ressource.html liegen)

Format: 1080x1350 (4:5) statt A4 - füllt auf dem Handy die ganze Breite, Schrift bleibt ohne Zoomen lesbar (A4 würde auf ca. 55 % schrumpfen).
ressource.md: optionales Frontmatter (--- ... ---) mit titel, untertitel, quelle (Zeile oder Liste "- ..."), dm (Text für die DM, sonst aus der ersten Zeile).
Danach Einleitungszeile, nummerierte Schritte "1. Titel. Text ..." (erster Satz = Kartenüberschrift), optional Schlussabsatz.
Chrome: derselbe headless-Chrome wie Formate/thepsychnote/kit/qa.py (Hyperframes-Cache). Schriften lokal aus dem Kit, keine externen Abrufe.
"""
import glob
import html
import pathlib
import re
import subprocess
import sys
import tempfile

from kanal import KANAL, KIT, REELS, lies

VORLAGE = pathlib.Path(__file__).with_name("ressource_vorlage.html")
LOGO = KANAL / "marke" / "profilbild.png"
SATZ = r"(?<=[.!?:])\s+"


def chrome():
    c = sorted(glob.glob(str(pathlib.Path.home() / ".cache/hyperframes/chrome/chrome-headless-shell/*/chrome-headless-shell-*/chrome-headless-shell*")))
    c = [x for x in c if not x.endswith(".zip")]
    if not c:
        sys.exit("FEHLER: Chrome nicht gefunden - einmal `npx --yes hyperframes@0.5.7 render` ausführen (füllt den Hyperframes-Cache).")
    return c[-1]


def zerlege(text):
    """-> (meta, einleitung[], schritte[(titel, text)], schluss[]). Frontmatter optional."""
    meta, m = {}, re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if m:
        text, key = text[m.end():], None
        for z in m.group(1).splitlines():
            if z.strip().startswith("- ") and key:
                if not isinstance(meta.get(key), list):
                    meta[key] = []
                meta[key].append(z.strip()[2:].strip())
            elif ":" in z:
                key, w = z.split(":", 1)
                key = key.strip()
                meta[key] = w.strip().strip('"')
    text = text.strip()
    h = re.match(r"^#\s+(.+)\n+", text + "\n")
    if h:
        meta.setdefault("titel", h.group(1).strip())
        text = text[h.end():].strip()
    einl, schritte, schluss = [], [], []
    for t in [t.strip() for t in re.split(r"\n\s*\n", text) if t.strip()]:
        mm = re.match(r"^(\d+)[.)]\s+(.*)$", t, re.S)
        if mm:
            body = " ".join(mm.group(2).split())
            s = re.match(r"^(.+?[.!?:])(?:\s+(.*))?$", body)
            schritte.append((s.group(1).rstrip(".") if s else body, (s.group(2) or "") if s else ""))
        elif schritte:
            schluss.append(" ".join(t.split()))
        else:
            einl.append(" ".join(t.split()))
    return meta, einl, schritte, schluss


def dm_text(d):
    """Kurzer Teaser der DM aus der ersten Zeile ("Here's your 3-step evening plan" + Pfeil), oder Frontmatter `dm`."""
    p = d / "ressource.md"
    if not p.exists():
        return None
    meta, einl, _, _ = zerlege(p.read_text(encoding="utf-8"))
    if meta.get("dm"):
        return meta["dm"]
    if not einl:
        return None
    return re.split(SATZ, einl[0])[0].rstrip(".:!") + " \U0001F447"


def inline(s):
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(s, quote=False))


def baue(d):
    meta, einl, schritte, schluss = zerlege((d / "ressource.md").read_text(encoding="utf-8"))
    kanal = lies(KANAL / "kanal.json", {}) or {}
    erste = re.split(SATZ, einl[0], maxsplit=1) if einl else [""]
    titel = meta.get("titel") or erste[0].rstrip(":.")
    rest_einl = ([erste[1]] if len(erste) > 1 else []) + einl[1:]
    w = titel.rsplit(" ", 1)
    titel_html = (html.escape(w[0]) + " <em>" + html.escape(w[1]) + "</em>") if len(w) == 2 else html.escape(titel)
    karten = ""
    for i, (h, t) in enumerate(schritte, 1):
        karten += f'<div class="karte"><div class="nr">{i}</div><div class="inh"><h2>{inline(h)}</h2>' + (f"<p>{inline(t)}</p>" if t else "") + "</div></div>\n"
    quellen = meta.get("quelle") or []
    quellen = [quellen] if isinstance(quellen, str) else quellen
    f = KIT / "fonts"
    ers = {
        "TITEL_TEXT": html.escape(titel), "TITEL": titel_html, "HANDLE": kanal.get("handle", "thepsychnote"),
        "FONT_BOLD": (f / "HelveticaNeueLTStd-75Bold.otf").as_uri(), "FONT_REGULAR": (f / "HelveticaNeue-Regular.ttf").as_uri(),
        "LOGO": f'<img class="logo" src="{LOGO.as_uri()}" alt="">' if LOGO.exists() else "",
        "UNTER": f'<p class="unter">{inline(meta["untertitel"])}</p>' if meta.get("untertitel") else "",
        "EINL": "".join(f'<p class="einl">{inline(x)}</p>' for x in rest_einl),
        "KARTEN": karten,
        "SCHLUSS": "".join(f'<p class="schluss">{inline(x)}</p>' for x in schluss),
        "QUELLE": f'<p class="quelle"><b>Source:</b> {inline("; ".join(quellen))}</p>' if quellen else "",
        "FUSS_RECHTS": "Psychology you can use",
    }
    h = VORLAGE.read_text(encoding="utf-8")
    for k, v in ers.items():
        h = h.replace("{{" + k + "}}", v)
    return h


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    d = pathlib.Path(args[0])
    d = d if d.is_dir() else REELS / args[0]
    if not (d / "ressource.md").exists():
        sys.exit(f"FEHLER: {d / 'ressource.md'} fehlt")
    htmlp = d / "ressource.html" if "--html" in sys.argv else pathlib.Path(tempfile.mkdtemp()) / "ressource.html"
    htmlp.write_text(baue(d), encoding="utf-8")
    pdf = d / "ressource.pdf"
    r = subprocess.run([chrome(), "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", htmlp.as_uri()], capture_output=True, text=True, timeout=120)
    if not pdf.exists():
        sys.exit("FEHLER: PDF nicht erzeugt\n" + (r.stderr or "")[-500:])
    seiten = len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))
    print(f"OK {pdf} ({pdf.stat().st_size // 1024} KB, {seiten} Seite(n)); DM-Text: {dm_text(d)}")


if __name__ == "__main__":
    main()
