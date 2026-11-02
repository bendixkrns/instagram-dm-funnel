# Kommentar-Regeln (Kommentar-Bot)

Gilt für die automatischen Antworten auf Instagram (Werkzeug `tools/instagram/kommentare.py`) sowie TikTok und YouTube (über Zernio, `tools/kommentare_zernio.py`); Skill `kommentare`. Das Cockpit-Programm startet beide alle 15 Minuten. Auf YouTube kann Spam nicht ausgeblendet werden – er geht an den Nutzer (YouTube Studio). Der Bot **antwortet selbst** (Nutzer, 2026-10-22; `kanal.json` → `kommentar_bot.modus` = `live`). Kritik und Heikles beantwortet er nie, das geht an den Nutzer. `probelauf` (nur protokollieren) bleibt als Schalter für Tests.

## Kategorien und Reaktion

| Kategorie | Beispiel | Reaktion |
|---|---|---|
| Frage | „Does this work for X too?“ | Kurz und ehrlich antworten (1–2 Sätze). Weiß der Kanal es nicht: sagen, keine Fakten erfinden. |
| Lob | „This is so true 😭“ | Kurz danken oder mitlachen, oft mit Gegenfrage („Which one got you?“). |
| Themenidee | „Do one about X“ | Danken, Idee in `gedaechtnis/Themen/aus-kommentaren.md` notieren. |
| Erfahrung teilen | „I do this every night“ | Kurz würdigen, nicht belehren. |
| Kritik / Widerspruch | „That study was debunked“ | **Keine Auto-Antwort.** An den Nutzer (Cockpit → Kommentare). |
| Heikel | psychische Krise, Selbstverletzung, Sucht, Gesundheit, Recht, Politik, Beschwerde | **Keine Auto-Antwort.** Sofort an den Nutzer. |
| Spam / Hass / Bots | Links, „DM me“, Beleidigungen | Ausblenden (hide), nicht antworten. |

## Ton

- Englisch, locker, klug, freundlich.
- **Ohne Absender:** kein „I“, kein „we“, keine Unterschrift, kein Name – die Antwort spricht für sich („Glad it hit home – which part felt most familiar?“).
- Höchstens 2 Sätze, höchstens 1 Emoji. Keine Hashtags.
- Nie belehren, nie diskutieren, nie verkaufen.

## Verboten

- Links, Werbung, Versprechen („follow for part 2“ nur, wenn es Teil 2 wirklich gibt).
- Medizinische, psychologische, rechtliche oder finanzielle Beratung.
- Zustimmung zu Beleidigungen oder Gruppenabwertung.
- Mehr als eine Antwort pro Thread und Person. Nie auf die eigenen Antworten antworten.
- Mehr als 30 Antworten pro Stunde.

## Eskalation

Alles, was nicht eindeutig in Frage/Lob/Themenidee/Erfahrung passt, geht an den Nutzer. Im Zweifel: nicht antworten.

## Keyword-Kommentare (automatische DM)

Kommentiert jemand das Keyword eines Reels (z. B. SLEEP; Groß-/Kleinschreibung, Emoji und Satzzeichen egal, ganzes Wort), läuft das **vor** der Haiku-Einordnung und ohne Tokens (`tools/instagram/keyword_dm.py`):
1. **Private Reply** mit dem Text aus `reels/<id>/ressource.md` (`POST /{ig-user-id}/messages`, `recipient.comment_id`; höchstens 7 Tage nach dem Kommentar, nur eine Nachricht je Kommentierendem; Berechtigungen `instagram_business_manage_messages` + `instagram_business_manage_comments`).
2. Danach **öffentliche Kurzantwort** aus wechselnden Varianten („Sent it to your DMs 📩“ …), ohne Absender, höchstens 1 Emoji.
3. **Doppelschutz** in `gedaechtnis/Kanal/keyword_dms.json`: nie zweimal an denselben Kommentar oder dieselbe Person je Reel.
4. **Ratenbremse:** höchstens 20 Private Replies pro Stunde, Rest beim nächsten Lauf; 2–6 s Zufallspause zwischen Sendungen; bei Fehlern/Sperre (konto.py) stoppt der Bot, nach 2 Fehlversuchen eskaliert der Kommentar.
5. Gesendet wird nur im Modus `live`; `probelauf` zeigt nur an. Fehlt `ressource.md`, wird nichts gesendet (nächster Lauf versucht es erneut). Sichtbar im Cockpit: Übersicht (Zähler „Keyword-DMs“) und Kommentare (Filter „Keyword-DMs“).
