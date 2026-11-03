# Instagram Keyword-DM-Funnel (Übergabe an Claude)

**An Claude, der dieses Repo bekommt:** Lies diese Datei zuerst ganz. Sie erklärt, was der Code tut, welche Dateien wichtig sind und was du einrichten und anpassen sollst. Der Code stammt aus einem privaten Projekt des Nutzers und läuft dort: Der Funnel wurde live auf Instagram getestet, und die 36 Tests sind grün. Er soll jetzt bei der Firma des Nutzers rund um die Uhr auf einem VPS laufen.

## 1. Worum es geht

**Ziel:** Jemand kommentiert unter einem Instagram-Beitrag ein Keyword (z. B. `GUIDE`). Dann passiert automatisch Folgendes:

1. Der Bot antwortet öffentlich unter dem Kommentar (zufällige Variante, z. B. „Check your DMs 📩“).
2. Er schickt eine **Private Reply** (DM) mit einem Button „Send link“.
3. Je nach Einstellung prüft er, ob die Person dem Konto folgt (`is_user_follow_business`), und/oder fragt per DM nach der E-Mail-Adresse.
4. Danach schickt er die Link-Nachricht mit dem Ressourcen-Link.

Der Nutzer stellt Keywords, Texte, Buttons, Links und den Ablauf in einer **Weboberfläche** ein (Seite „DM-Funnel“, mit Live-Vorschau) und wählt dort, unter welchen Beiträgen der Funnel aktiv ist.

**Was nicht hierher gehört:** Beiträge planen und veröffentlichen übernimmt **Postiz** (selbst gehostet, auf demselben VPS). Dieses Repo postet nichts. Es braucht keine KI und keine Content-Erstellung.

**Ablauf-Modi** (`mode`):
- `adaptive` (Standard): Es wird nur abgefragt, was fehlt. Folgt die Person nicht → Follow, dann Link. Folgt sie, aber es gibt keine E-Mail → E-Mail. Gibt es eine E-Mail, aber keinen Follow → Follow. Ist beides da → sofort der Link.
- `both`: immer Follow und E-Mail, Reihenfolge über `order` (`follow_first` | `email_first`).
- `follow`: nur Follow.
- `email`: nur E-Mail.

Am PC funktionieren Instagram-Buttons nicht zuverlässig. Deshalb erkennt der Bot auch getippte Antworten wie „SEND LINK“ oder „I followed ✅“ (Groß-/Kleinschreibung und Emoji egal).

## 2. Was im Repo ist

Wichtig sind nur diese Dateien:

| Datei | Aufgabe |
|---|---|
| `tools/instagram/keyword_dm.py` | **Kern des Funnels.** `trifft()` erkennt Keywords (ganzes Wort, Satzzeichen/Emoji egal, ab 5 Zeichen ein Tippfehler erlaubt). `verarbeite()` schickt die öffentliche Antwort und die Private Reply mit Button. `test_funnel_fortsetzen()` setzt offene Flows fort (Button-Klick oder getippte Antwort → Follow-Prüfung / E-Mail / Link). Zustand in `gedaechtnis/Kanal/keyword_dms.json`. |
| `tools/instagram/kommentare.py` | Holt neue Kommentare (Abfrage und/oder Webhook) und gibt sie an `keyword_dm.verarbeite()` weiter. Für den Funnel läuft es mit `--nur-keyword`. Den KI-Teil (`einordnen`, Groq/Claude) braucht ihr **nicht**. |
| `tools/instagram/konto.py` | Konten (`gedaechtnis/Kanal/konten.json`), Token, `api()` für graph.instagram.com, Sperrschutz bei Code 190/200. |
| `tools/instagram/tokens.py` | `pruefen` (Token gültig?), `erneuern` (60 Tage verlängern). |
| `tools/instagram/dms.py` | Wird nur wegen `konversationen()` gebraucht: liest DM-Antworten für die Flows. Die DM-Entwürfe per KI braucht ihr nicht. |
| `tools/automation/instagram_webhook.py` | Signaturgeprüfter Webhook-Empfänger (`/webhook`, Port 5091) für Button-Klicks und Kommentare. Mit `--worker` der **Dauerprozess**: alle 60 s (oder sofort bei Webhook-Kommentar) läuft der Keyword-Job, alle 5 s werden offene Flows fortgesetzt. |
| `tools/automation/keyword_config.py` | Einstellungen und Validierung: `gedaechtnis/Kanal/keyword_funnels.json` (`default` + `reels.<id>`). |
| `tools/automation/instagram_contacts.py` | E-Mails aus dem Funnel, privat in SQLite (`.secrets/automation/instagram_contacts.sqlite3`). |
| `tools/automation/run.py` | **Job-Einstieg**: ein Befehl je Job (`run.py keyword_dm`) mit Sperrdatei gegen Doppelstart, Log (`.secrets/automation/jobs.log`) und Exitcode. Der Worker ruft ihn auf. |
| `tools/automation/status.py` | Status je Job (`gedaechtnis/Kanal/bot_status.json`). |
| `tools/kanal.py` | Pfade, JSON lesen/schreiben, `env()` (liest `.env` im Projektordner oder bis zu zwei Ebenen darüber). |
| `tools/ressource.py` | Alter Fallback für den DM-Text aus einem Reel-Ordner. Wird importiert, ist für euch aber nicht nötig. |
| `cockpit/` | Weboberfläche des alten Projekts (`server.py` + `app.js` + `style.css`). **Für euch zählt nur die Seite `#/dm-funnel`** (in `app.js` die Funktion `keywordFunnelSeite()`, in `server.py` die Routen `/api/dm-funnel*` und `funnel_reels()`, in `style.css` die Klassen `.funnel-*` und `.ig-*`). |
| `deploy/vps/` | Ubuntu-Anleitung (`README.md`: Benutzer, venv, `.env`, systemd, Caddy-HTTPS, Meta-Webhook) und die systemd-Dateien. Für den Funnel ist `replybot-instagram-worker.service` der richtige Dienst. |
| `tests/bots/` | 36 Tests mit gemockter API: `python -X utf8 -m pytest tests/bots` (braucht `pip install pytest`). |
| `.env.example` | Alle Variablen ohne Werte. |
| `gedaechtnis/Kanal/` | Vorlagen: `konten.json` (Platzhalter `FIRMA_HANDLE`), `keyword_funnels.json` (Platzhalter-Link), `kanal.json` (`kommentar_bot.modus = probelauf`, `plattformen.aktiv = ["instagram"]`). |

Die Ordnernamen (`gedaechtnis/`, `reels/`) stammen aus dem alten Projekt. Sie dürfen bleiben oder umbenannt werden, die Pfade stehen in `tools/kanal.py`.

Diese Teile sind noch drin, weil Cockpit oder Tests sie importieren. Für den Funnel braucht ihr sie nicht, und sie dürfen beim Aufräumen weg: `tools/kommentare_zernio.py`, `tools/zernio.py` (YouTube/TikTok), `tools/automation/llm.py` mit `.claude/skills/kommentare/` und `Kommentar-Regeln.md` (KI-Kommentarantworten), `replybot@.service`, `replybot-kommentare.timer` und `windows-jobs.ps1`. Löscht ihr sie, müsst ihr die Tests anpassen.

## 3. Deine Aufgaben (in dieser Reihenfolge)

### A. Lokal lauffähig machen
1. Python ≥ 3.11 (nur Standardbibliothek, für die Tests zusätzlich `pytest`). Tests laufen lassen.
2. `.env` aus `.env.example` anlegen, **nie committen**. Für den Funnel nötig: `INSTAGRAM_<KONTO>_ACCESS_TOKEN`, `INSTAGRAM_<KONTO>_USER_ID` (`<KONTO>` = `id` aus `konten.json` in Großbuchstaben, z. B. `INSTAGRAM_FIRMA_…`), `INSTAGRAM_API_VERSION`, `META_APP_SECRET`, `META_WEBHOOK_VERIFY_TOKEN`, optional `BOT_KOMMENTARE_QUELLE` (`poll` | `webhook` | `beides`). Groq-, Zernio- und YouTube-Variablen braucht ihr nicht.
3. `konten.json` mit dem Firmenkonto füllen, dann `python -X utf8 tools/instagram/tokens.py pruefen`.
4. Meta-App der Firma: Instagram-Professional-Konto, „Instagram API with Instagram Login“, Berechtigungen `instagram_business_basic`, `instagram_business_manage_comments`, `instagram_business_manage_messages`. Ohne App Review funktioniert das nur für Konten mit einer Rolle in der App. Das reicht für das eigene Firmenkonto.

### B. Post-Auswahl auf die echten Instagram-Beiträge umstellen (Code-Änderung, nötig)
Bisher kennt der Bot nur Beiträge, die das alte Projekt selbst angelegt hat (Ordner `reels/<id>/status.json` mit `post.media_id`). Bei der Firma postet Postiz, es gibt also keine Reel-Ordner. Der Nutzer will in der Oberfläche **aus den echten Beiträgen des Kontos auswählen**, unter welchen der Funnel läuft.

- **Beitragsliste:** In `cockpit/server.py` die Funktion `funnel_reels()` ersetzen. Sie soll `GET /{ig-user-id}/media?fields=id,caption,media_product_type,thumbnail_url,media_url,permalink,timestamp,comments_count` über `konto.api()` holen und z. B. alle 10 Minuten cachen. Jeder Eintrag hat `id` = Media-ID, Titel = erste Caption-Zeile, Vorschaubild = `thumbnail_url` bzw. `media_url`, dazu wirksame Keywords, Link und aktiv/inaktiv.
- **Schlüssel:** In `keyword_funnels.json` die Media-ID als Schlüssel unter `reels` nehmen (oder `reels` in `posts` umbenennen, dann überall in `keyword_config.py`, `keyword_dm.py`, `server.py` und `app.js`).
- **Beobachtete Beiträge:** `eigene_reels()` in `tools/instagram/kommentare.py` so umbauen, dass es die aktiven Beiträge aus der Einstellung liefert statt `reels/*/status.json`. `neue_kommentare_abfrage()` und `neue_kommentare_webhook()` nutzen davon nur die Media-ID.
- **Keyword/Link je Beitrag:** In `keyword_dm.py` lesen `keyword_fuer(d)`, `ressource_link_fuer(d)`, `ressource_fuer(d)` und `kampagne_fuer()` aus dem Reel-Ordner (`caption.json`, `brief.md`, `ressource_link.txt`). Diese Ordner-Fallbacks entfernen, damit Keywords und Link nur aus `keyword_funnels.json` kommen (Beitrag → Standard). Ohne Link wird nichts gesendet, das ist so gewollt.
- **Aktiv-Logik:** Entweder wie bisher „Standard gilt für alle Beiträge, einzelne abschaltbar“ oder sicherer „nur ausdrücklich eingeschaltete Beiträge“. Ein Schalter im Standard (z. B. `all_posts`) deckt beides ab. Mit dem Nutzer klären.
- **Einmal-Test:** Ist `.secrets/automation/instagram_keyword_test.json` vorhanden, gilt ein TEST-Modus, der alle anderen Kommentare ignoriert (`testkonfiguration()`). Der Name `testlaeufe` im Zustand ist historisch und steht für **alle** Flows, nicht nur Tests.
- Tests in `tests/bots/test_bots.py` entsprechend anpassen (sie patchen `eigene_reels`, `REELS` usw.).

### C0. Zuerst den Nutzer fragen: Wo soll die Oberfläche leben?
Bei der Arbeit gibt es schon ein eigenes Content-Erstellungstool, mit dem Posts gemacht werden. **Frag den Nutzer, bevor du an der Oberfläche arbeitest**, ob die DM-Funnel-Einstellungen dort eingebaut werden sollen, statt als eigenes Cockpit zu laufen. Zwei Wege:

- **Einbauen ins vorhandene Tool:** Das Tool bekommt eine Funnel-Seite oder einen Funnel-Bereich direkt am Post (Keywords, Link, Ablauf, Texte, aktiv ja/nein). Es spricht mit dem Bot über eine kleine API. Die vorhandenen Routen `GET/POST /api/dm-funnel`, `/api/dm-funnel/default`, `/api/dm-funnel/reel/<id>`, `/api/dm-funnel/reset/<id>` in `cockpit/server.py` und die Validierung in `keyword_config.py` sind dafür die Vorlage. Alternativ schreibt das Tool direkt in `keyword_funnels.json`, wenn es auf demselben Server läuft. Die UI-Logik und die Live-Vorschau aus `keywordFunnelSeite()` in `cockpit/app.js` können übernommen werden. Vorteil: Funnel-Einstellung und Post entstehen am selben Ort. Wenn das Tool die Instagram-Media-ID nach dem Posten kennt (über Postiz oder die API), lässt sich der Funnel gleich an den richtigen Beitrag hängen. Erst den Aufbau des Tools ansehen (Sprache, Framework, wo es läuft, Login), dann entscheiden.
- **Eigenständig lassen:** Dann gilt Abschnitt C.

Der Bot selbst (Worker, Webhook) bleibt in beiden Fällen gleich und läuft auf dem VPS.

### C. Oberfläche auf den DM-Funnel reduzieren und absichern (wenn eigenständig)
- Aus dem Cockpit nur die DM-Funnel-Seite behalten: Navigation, Pipeline, Themen, Wissen, Bibliothek, Kalender, Kommentare und DMs entfernen, `#/dm-funnel` als Startseite. Server-Routen entsprechend kürzen. Die Hintergrundschleifen in `server.py` (`kennzahlen_schleife`, `warteschlange_schleife`, ganz unten) entfernen. Die Warteschlange würde sonst posten, und das macht Postiz.
- **Das Cockpit hat keinen Login.** Es lauscht auf `127.0.0.1:5090`. Auf dem VPS hinter Caddy mit `basic_auth` (oder dem Firmen-SSO) über HTTPS stellen und nie offen ins Netz. Alternativ nur per SSH-Tunnel (`ssh -L 5090:127.0.0.1:5090 user@vps`). Kein `--lan`.
- Die Vorschau zeigt ein Profilbild aus `gedaechtnis/Kanal/marke/profilbild.png`. Stattdessen `profile_picture_url` von `GET /me` verwenden oder das Bild dort ablegen.

### D. VPS (Ubuntu), läuft rund um die Uhr
Die Schritt-für-Schritt-Anleitung steht in `deploy/vps/README.md`. Kurz:
1. Benutzer `replybot`, Code nach `/opt/replybot`, venv, `.env` mit `chmod 600`.
2. **Dienst:** `replybot-instagram-worker.service` (Webhook-Empfänger und Worker in einem Prozess, `Restart=always`). Daneben **nicht** `replybot-kommentare.timer` für dasselbe Konto aktivieren, sonst schreiben zwei Prozesse dieselben Zustandsdateien.
3. **Weboberfläche** als zweiter systemd-Dienst (`python -X utf8 cockpit/server.py`, `WorkingDirectory=/opt/replybot`). Dafür gibt es noch keine Datei, sie muss angelegt werden.
4. **Caddy** (HTTPS mit eigener Domain, kein Cloudflare-Tunnel, so hat der Nutzer entschieden). Ein Beispiel steht in `deploy/vps/README.md`. Aufteilung zum Beispiel:
   - `bot.firma.de/webhook` → `127.0.0.1:5091` (öffentlich, signaturgeprüft)
   - `funnel.firma.de` → `127.0.0.1:5090` mit `basic_auth`
   - `postiz.firma.de` → Postiz (eigene Installation nach Postiz-Doku, Ports nicht kollidieren lassen)
5. **Meta-Webhook:** Callback `https://bot.firma.de/webhook`, Verify-Token aus der `.env`, Felder `comments`, `messages`, `messaging_postbacks`. Das Konto muss die App abonnieren: `POST /<IG_ID>/subscribed_apps?subscribed_fields=comments,messages,messaging_postbacks`. Die App muss Live sein. Hinweis aus dem alten Projekt: Im lokalen Test kamen trotz aktiver Abos keine Webhook-Ereignisse an. Der Funnel lief zuverlässig über die Abfrage (`BOT_KOMMENTARE_QUELLE=poll`, Konversationen alle 5 s). Auf dem VPS die Webhook-Zustellung gesondert prüfen und erst nach einigen Tagen auf `beides` bzw. `webhook` umstellen.
6. **Token-Erneuerung:** Instagram-Tokens laufen nach 60 Tagen ab. Einen täglichen systemd-Timer für `tools/instagram/tokens.py erneuern --alle` anlegen (erneuert nur bei weniger als 14 Tagen Rest). Die Datei dafür fehlt noch.
7. Erst `--modus probelauf --trocken` testen: `python -X utf8 tools/automation/run.py keyword_dm --modus probelauf --trocken`. Das sendet und speichert nichts. Danach `kanal.json → kommentar_bot.modus` auf `live` stellen, **aber nur nach Freigabe durch den Nutzer**. Der Worker startet den Job selbst mit `--modus live`, deshalb den Dienst erst nach der Freigabe aktivieren.

### E. Klären mit dem Nutzer
- **Oberfläche ins vorhandene Content-Erstellungstool einbauen oder eigenständig lassen?** (siehe C0, zuerst fragen)
- Funnel-Texte (Standard ist Englisch), Keywords, Links, Ablauf-Modus.
- E-Mail-Abfrage und DSGVO: Hinweis im Text, Zweck, Löschung. Die Adressen gelten nicht als Newsletter-Einwilligung. Für Löschanfragen gibt es `instagram_contacts.delete_email()`.
- Ob der Funnel unter allen Beiträgen oder nur unter ausgewählten läuft.

## 4. Grenzen und Sicherheit (übernehmen)
- Limits im Funnel (`keyword_dm.py`): höchstens 20 erste DMs pro Stunde, 2–6 s Pause zwischen Sendungen, Private Reply nur bis 7 Tage nach dem Kommentar, eine DM je Beitrag und Person. Nach 2 Fehlversuchen bricht der Bot ab und vermerkt den Fehler.
- Der Link geht erst raus, wenn der Follow bestätigt ist. Liefert Meta keinen klaren Follow-Status, wird nichts gesendet.
- **Nur eine Maschine darf live senden.** Die Zustandsdateien (`gedaechtnis/Kanal/keyword_dms.json`, `.secrets/automation/*.sqlite3`) verhindern Doppel-DMs und dürfen nicht verloren gehen.
- Schlüssel nie ausgeben, nie committen (`.gitignore` deckt `.env`, `.secrets/` und die Zustandsdateien ab).
- Nichts live schalten oder Timer aktivieren ohne ausdrückliche Freigabe des Nutzers.
