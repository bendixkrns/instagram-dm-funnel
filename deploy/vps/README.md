# Bot-Jobs auf Ubuntu

Diese Anleitung bereitet einen VPS vor. Nichts wird durch das Einchecken der Dateien aktiviert.
`run.py` verwendet nur die Python-Standardbibliothek; für Tests wird `pytest` benötigt.
Die Groq-Anbindung nutzt standardmäßig `openai/gpt-oss-20b` und das kostenlose Kontingent.
Aktuelle Modell- und Kontolimits vor dem Einsatz prüfen: [Groq-Modelle](https://console.groq.com/docs/models),
[Rate Limits](https://console.groq.com/docs/rate-limits). Das Modell kann mit `GROQ_MODEL` geändert werden.

## Vorbereitung

1. Ubuntu mit Python 3.11 oder neuer, Git und `python3-venv` bereitstellen: `sudo apt update && sudo apt install python3 python3-venv git`.
2. Eigenen Benutzer anlegen: `sudo useradd --system --create-home --shell /usr/sbin/nologin replybot`. Projekt nach `/opt/replybot` kopieren oder dort klonen und mit `sudo chown -R replybot:replybot /opt/replybot` zuordnen. Nicht aus einem öffentlichen Repository echte Tokens beziehen.
3. Venv anlegen: `sudo -u replybot python3 -m venv /opt/replybot/.venv`. Laufzeitabhängigkeiten sind derzeit nicht nötig. Für den Testlauf optional: `sudo -u replybot /opt/replybot/.venv/bin/python -m pip install pytest`.
4. Die Schlüssel aus `.env.example` in `/opt/replybot/.env` eintragen (`chmod 600`). Für den Bot werden Instagram-Zugang, Zernio und `GROQ_API_KEY` benötigt. Für YouTube-Kennzahlen zusätzlich OAuth-Client und vorhandener Refresh-Token in `.secrets/`.
5. Bestehende lokale Zustandsdateien in `gedaechtnis/Kanal/` und `.secrets/` gesichert übertragen, Eigentümer `replybot`, Rechte nur für diesen Benutzer. Besonders `keyword_dms.json` und `kommentare.json` nicht verlieren, sonst drohen doppelte Antworten. Tokens niemals ins Git übernehmen.
6. Sicherer Probelauf: `.venv/bin/python -X utf8 tools/automation/run.py kommentare --modus probelauf --trocken --backend groq`. Ebenso `--backend claude`, falls die Claude-CLI und Anmeldung auf dem VPS vorhanden sind. Der Trockenlauf sendet und speichert nichts.

## Timer installieren

Die Service-Datei und gewünschten Timer nach `/etc/systemd/system/` kopieren: `sudo cp deploy/vps/*.service deploy/vps/*.timer /etc/systemd/system/` (aus `/opt/replybot`). Pfade und Benutzer bei abweichender Installation anpassen. Danach `sudo systemctl daemon-reload` und die gewünschten Timer mit `sudo systemctl enable --now replybot-kommentare.timer replybot-dms.timer replybot-kennzahlen.timer replybot-warteschlange.timer` aktivieren. `keyword_dm` ist im Kommentarjob enthalten; einen eigenen Keyword-Timer nur als Ersatz für den Kommentarjob verwenden, damit Abrufe nicht doppelt laufen.

Status: `systemctl list-timers 'replybot*'`. Logs: `journalctl -u 'replybot@kommentare.service' -n 100 --no-pager`; zusätzlich `.secrets/automation/jobs.log`. Ein Exitcode ungleich 0 bedeutet, dass mindestens ein Plattformlauf fehlgeschlagen ist. Der Sperrdatei-Pfad liegt in `.secrets/automation/`.

## Zustandsdateien und Cockpit

Nur eine Maschine soll live senden. Für Synchronisation stehen zwei Optionen offen:

- Cockpit und Jobs auf demselben VPS betreiben und das Cockpit geschützt erreichbar machen. Dann teilen sie direkt `gedaechtnis/Kanal/*.json`.
- Jobs auf dem VPS, Cockpit lokal: Zustandsdateien regelmäßig über einen privaten verschlüsselten Kanal synchronisieren. In beide Richtungen geschriebene JSON-Dateien brauchen eine eindeutige führende Instanz; besonders `kommentare.json`, `dms.json`, `keyword_dms.json` und `bot_status.json` dürfen nicht unabhängig geändert und blind überschrieben werden.

Die Wahl ist offen. Vor Aktivierung eines VPS-Timers den lokalen Cockpit-Hintergrundlauf deaktivieren oder umstellen, sonst laufen dieselben Jobs zweimal. Windows nutzt dieselben Befehle über `windows-jobs.ps1`; die Aufgabenplanung wird nicht automatisch eingerichtet.

## Einmaliger Instagram-Keyword-Test

Der Test nutzt lokal `.secrets/automation/instagram_keyword_test.json` mit `aktiv`, `reel_id`, `keyword` (`TEST`), `profil_link`, `ziel_link` und optional `funnel` (`adaptive`, `follow`, `email`). Während diese Datei existiert, ignoriert der Instagram-Kommentarjob andere Kommentare und Reels. Jeder neue `TEST`-Kommentar erhält einen eigenen Flow in `keyword_dms.json`; der Bot erkennt Groß-/Kleinschreibung, Satzzeichen und Emojis. Bei Keywords ab fünf Zeichen toleriert er einen Tippfehler. Die erste private Antwort ist eine echte Button-Vorlage „Send link“ als Private Reply. Im Standardmodus `adaptive` gilt: Wer weder folgt noch eine hinterlegte E-Mail hat, wird zuerst nach dem Follow gefragt und erhält den Link dann direkt; bestehende Follower ohne E-Mail erhalten die E-Mail-Frage; bei gespeicherter E-Mail ohne Follow kommt die Follow-Frage; mit beiden Bedingungen direkt der Link. `follow` und `email` erzwingen nur die jeweilige Frage. Die E-Mail muss ein gültiges Format haben und wird in `.secrets/automation/instagram_contacts.sqlite3` pro Instagram-Nutzer-ID gespeichert. Dies ist keine Newsletter-Einwilligung. Für den lokalen Dauer-Test `python -X utf8 tools/automation/instagram_webhook.py --worker --comment-seconds 30` starten; so werden Kommentare ohne Chat-Anstoß abgeholt und offene DMs alle fünf Sekunden fortgesetzt. Nach dem Test die Testdatei entfernen; Zustandsdateien für Doppelschutz behalten. `--modus probelauf --trocken` sendet nichts.

Im erneuten Live-Test akzeptierte Meta die erste Button-Vorlage auch als Private Reply mit `recipient.comment_id`; der Nutzer bestätigte Text, Emojis und Button in der Instagram-App und am PC den Texteingabeweg. Instagram-Buttons sind am Desktop nicht zuverlässig bedienbar. Der Bot erkennt deshalb zusätzlich `SEND LINK` und später `I followed ✅` unabhängig von Großschreibung und Emoji. Button-Vorlagen bleiben im Chat sichtbar; der gespeicherte Flow-Status verhindert Mehrfachlinks. Die Cockpit-Seite „Keyword-Funnel einstellen“ bearbeitet `gedaechtnis/Kanal/keyword_funnels.json`: Standardtexte und Modi sowie optionale Reel-Overrides für Keyword, Modus, Link, Buttons und Nachrichten. Die aktive private TEST-Datei hat während eines Tests Vorrang. Die E-Mail-Tabelle ist privat und nicht Teil einer Newsletter-Liste.

### Instagram-Webhooks für Buttons und Folgeprüfung

Der Instagram-Webhooks-Endpunkt ist `tools/automation/instagram_webhook.py` auf `127.0.0.1:5091/webhook`. Er prüft die Meta-Signatur mit `META_APP_SECRET`, beantwortet die Challenge mit `META_WEBHOOK_VERIFY_TOKEN` und speichert nur Button-Payloads mit Absender-ID in `.secrets/automation/instagram_webhook.sqlite3`. Beide Werte gehören in die private `.env`, niemals ins Git. `python -X utf8 tools/automation/instagram_webhook.py` startet den lokalen Empfänger. Für Meta muss `https://<öffentlich erreichbare Domain>/webhook` auf diesen Port zeigen; HTTPS und ein stabiler Host sind für Dauerbetrieb nötig. Für den einmaligen Test kann ein temporärer Cloudflare Quick Tunnel `cloudflared tunnel --url http://127.0.0.1:5091` verwendet werden. Dessen URL wechselt beim Neustart und darf nicht als dauerhafte Konfiguration betrachtet werden.

**Dauerbetrieb (Nutzerentscheidung 2026-10-25):** Den Webhook und die Bot-Jobs später auf einem VPS mit eigener stabiler HTTPS-Adresse betreiben. Cloudflare nicht für den Dauerbetrieb verwenden. Auf dem VPS den lokalen Python-Port nur intern erreichbar machen und HTTPS per Reverse Proxy bereitstellen; danach in Meta die Callback-URL auf die VPS-Domain ändern und die Instagram-Abo-Felder prüfen. Den temporären Quick Tunnel nach dem lokalen Test beenden.

Für den dauerhaften Keyword-Lauf liegt `replybot-instagram-worker.service` bereit. Der Dienst startet `instagram_webhook.py --worker`, prüft neue Keyword-Kommentare standardmäßig alle 60 Sekunden und offene DMs alle fünf Sekunden. Er wird **nicht** automatisch aktiviert. Den `replybot-kommentare.timer` nicht gleichzeitig für dasselbe Instagram-Konto aktivieren; sonst können zwei Prozesse dieselben Zustandsdateien schreiben. YouTube-/TikTok-Kommentarjobs können gesondert eingeplant werden. Vor dem Serverumzug die privaten SQLite-/JSON-Zustände mitnehmen und auf dem alten Rechner den Live-Lauf beenden.

In Meta for Developers die Instagram-Webhook-Felder `comments`, `messages` und `messaging_postbacks` auf diesen Callback registrieren und das Instagram-Profikonto zusätzlich mit `POST /<IG_ID>/subscribed_apps?subscribed_fields=comments,messages,messaging_postbacks` abonnieren. Die App muss dabei Live sein. Metas Profil-API lässt `is_user_follow_business` nur mit gültiger Instagram-scoped ID und Nutzerzustimmung zu; bei Fehler oder unklarem Wert wird der Ziel-Link nicht versendet. Beim lokalen Test waren die Abos aktiv, aber es trafen keine Webhook-Ereignisse ein. Der bestätigte Handy-Funnel lief über die Konversationsabfrage im 5-Sekunden-Takt. Die Webhook-Zustellung muss vor dem VPS-Dauerbetrieb gesondert geprüft werden.

## Webhook mit fester Adresse (HTTPS, Caddy)

Meta liefert Kommentare, Nachrichten und Button-Klicks nur an eine HTTPS-Adresse mit gültigem Zertifikat (keine nackte IP). Der Empfänger `tools/automation/instagram_webhook.py` lauscht lokal auf Port 5091 und prüft die Signatur; davor gehört ein Reverse-Proxy.

1. **Domain:** A-Record (z. B. `bot.beispiel.de`) auf die IP des VPS. Port 80 und 443 in der Firewall öffnen, 5091 nicht.
2. **Caddy** (`sudo apt install caddy`) mit `/etc/caddy/Caddyfile`; Zertifikat holt Caddy selbst:
   ```
   bot.beispiel.de {
       @hook path /webhook
       handle @hook {
           request_body { max_size 1MB }
           reverse_proxy 127.0.0.1:5091 {
               transport http { dial_timeout 3s response_header_timeout 10s }
           }
       }
       respond 404
   }
   ```
   Alles außer `/webhook` bekommt 404. Für Rate-Limits gegen Überlast das Caddy-Modul `rate_limit` oder `ufw limit 443/tcp` und `fail2ban` ergänzen; optional nur die IP-Bereiche von Meta zulassen.
3. **Dienst starten:** `replybot-instagram-worker.service` (Webhook-Empfänger und Worker in einem Prozess), `.env` mit `META_APP_SECRET` und `META_WEBHOOK_VERIFY_TOKEN`.
4. **Meta-Dashboard** → Instagram → API-Einrichtung → Webhooks: Callback-URL `https://bot.beispiel.de/webhook` und das Verify-Token aus der `.env` eintragen; Meta schickt eine GET-Prüfanfrage, der Empfänger beantwortet sie. Felder `comments`, `messages`, `messaging_postbacks` abonnieren. Das Konto muss die App abonnieren (`POST /<IG_ID>/subscribed_apps?subscribed_fields=comments,messages,messaging_postbacks`, oder im Dashboard das Konto aktivieren).
5. **Prüfen:** im Dashboard „Test senden“; im Journal erscheint „Instagram-Webhook: … empfangen“. Danach einen echten Kommentar und einen Button-Klick testen.
6. **Kommentare per Webhook:** `BOT_KOMMENTARE_QUELLE` in der `.env`. `poll` (Standard) fragt Meta alle ~30 s ab. `beides` verarbeitet Webhook-Ereignisse sofort und lässt die Abfrage als Sicherung laufen. `webhook` verzichtet auf die Abfrage; erst umstellen, wenn Kommentare mehrere Tage zuverlässig per Webhook ankamen. Eingehende Kommentar-Ereignisse weckt den Worker sofort, statt bis zum nächsten 30-s-Lauf zu warten. Kommentare liegen nur als Zwischenspeicher (höchstens 8 Tage, nach der Bearbeitung gelöscht) in `.secrets/automation/instagram_webhook.sqlite3`.
