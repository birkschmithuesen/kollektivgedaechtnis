# Betrieb — Station Kollektivgedächtnis

Runbook für den Ausstellungstag. Alles, was hier steht, ist am Operator-Laptop
oder am Projektionsrechner erreichbar — kein Eintrag beschreibt eine Einstellung,
die es im UI nicht gibt.

## Vor dem Festival

1. Drei Geheimnisse in die Umgebung exportieren (nie `~/.hermes/.env` verwenden,
   nie in `config.toml` schreiben):

   ```bash
   export ANTHROPIC_API_KEY=...      # Extraktion + Merge-Judge
   export KG_TELEGRAM_TOKEN=...      # Foto-Auslöser
   export OPENROUTER_API_KEY=...     # nur Embeddings, darf ein eigener Schlüssel sein
   ```

2. `cp config.example.toml config.toml` und Werte prüfen. Die kalibrierten Werte
   stehen unten und werden im Betrieb **nicht** verändert.

3. `uv sync`, dann ein Rauchtest ohne externe Dienste:

   ```bash
   uv run python -m kg --no-telegram --no-stt
   ```

   Es wird kein Modell heruntergeladen. Embeddings kommen von OpenRouter und
   liegen danach im Cache `data/embeddings.sqlite3` — **diese Datei nicht
   löschen**, sie spart Geld und macht Wiederholungen offlinefähig.

4. STT-Server starten (Vertrag: `docs/stt-contract.md`):

   ```bash
   python -m fundusapps.stt_server elevenlabs-scribe --language de
   curl -N http://127.0.0.1:5051/events      # muss Events liefern
   ```

5. Touch prüfen. Der Touchscreen ist bestätigt beschafft — bestätigt ist aber
   nicht dasselbe wie funktionierend:

   ```bash
   dmesg | grep -i hid
   libinput list-devices     # muss ABS_MT_* Achsen zeigen
   ```

   Meldet sich das Gerät als HID-Maus statt als Multitouch-Digitizer, gibt es
   nur einen Kontaktpunkt und keine Gesten. Dann Kamera auf „automatisch
   schwenken" stellen — dieser Modus ist der vorgesehene Fallback.

## Start am Ausstellungstag

```bash
./scripts/start.sh
```

Startet Core, Projektionsfenster (Beamer, Kiosk) und Operator-Fenster (Laptop).
Jeder Teil startet nach einem Absturz neu. Das Skript wartet, bis der Server
wirklich antwortet, bevor es die Browser öffnet.

Liegt der Beamer nicht rechts neben dem Laptop-Panel, Position anpassen:
`xrandr --listmonitors` zeigt den Offset, dann
`KG_PROJECTION_POS=<x>,<y> ./scripts/start.sh`.

## Netzwerk für Screen B und Screen C

Tool 1 hört im Normalfall nur auf `127.0.0.1` — dann erreicht **keine** andere
Maschine die Station. Für den Ausstellungstag in `config.toml`:

```toml
server_host = "0.0.0.0"
```

Bewusste Entscheidung: **keine Authentifizierung** (Tool-2-Spec §3.1). Die
Station läuft einen Tag lang in einem isolierten lokalen Netz; ein Login wäre
hier zusätzliche Komplexität und eine zusätzliche Fehlerquelle um 9 Uhr
morgens.

Nach dem Start druckt der Core drei URLs — mit der **aufgelösten** Adresse,
nicht mit `0.0.0.0`. Die dritte ist die, die die Traum-Maschine braucht.

**Die Prüfung wird von der ANDEREN Maschine aus gefahren, niemals per
localhost auf dem Ausstellungsrechner.** Ein `curl` auf dem Server selbst
gelingt auch dann, wenn der Bind falsch ist, und beweist deshalb nichts:

```bash
# auf der Traum-Maschine, nicht auf dem Ausstellungsrechner:
curl -s http://<adresse-vom-core-ausgegeben>:8800/graph.json | head -c 200
```

Kommt hier JSON mit `"version": 1` zurück, ist die Netzwerkhälfte beantwortet
— und zwar genau mit dem Aufruf, den der Watcher im Betrieb macht.

Schlägt es fehl: Bind prüfen (`ss -ltnp | grep 8800` muss `0.0.0.0:8800`
zeigen, nicht `127.0.0.1:8800`), dann die Firewall, dann ob beide Maschinen
wirklich im selben Netz hängen.

Sieht die gedruckte Adresse selbst nach `127.0.0.1` aus: Der Code versucht
genau das intern schon selbst (u. a. per `ip -4 addr show scope global`) —
wenn trotzdem nichts gefunden wurde, haben alle drei Auflösungsversuche keine
LAN-Adresse ergeben (z. B. direktes Kabel oder Switch ohne konfiguriertes
Gateway, und kein `ip`-Kommando verfügbar). Die echte Adresse mit
`ip -4 addr show scope global` (oder `ip addr`) nachsehen und von Hand
einsetzen.

## Ein Interview

1. Foto per Telegram → Personenknoten mit Portrait erscheint sofort.
2. Interview führen (Funkmikro läuft dauerhaft in den STT-Server).
3. Beenden: beliebige Textnachricht in Telegram ODER gesprochen
   „Interview beendet" ODER nach 15 Minuten automatisch.
4. Begriffe wachsen **nach** dem Stopp nach, nicht währenddessen.

Ein neues Foto schließt ein noch laufendes Interview implizit — es kann also nie
zwei offene Interviews geben.

## Die Live-Regler

Alle drei sitzen im Operator-Fenster und wirken sofort auf den gesamten Bestand.

**Dichte** — 1 = alles, 2 = nur Geteiltes, 3 = nur Häufiges. Reiner
Anzeigefilter: verwirft nichts, jederzeit umkehrbar. Startwert 2, siehe unten.

**Kamera** — „alles zeigen" (Voreinstellung, ganzes Netz im Bild), „manuell"
(Besucher darf per Touch zoomen und schieben), „automatisch schwenken" (die
Kamera wandert von selbst; der Fallback ohne funktionierenden Touch).

**Zoom** — 1× ganzes Netz, 1,5×, 2× halbes Netz. Wirkt in „alles zeigen" und
„automatisch schwenken"; in „manuell" nicht, weil dort die Hand des Besuchers
führt und ein Nachrahmen dagegen arbeiten würde.

> **Kamera und Zoom werden vor Ort am echten Screen eingestellt** (Entscheidung
> D4). Die Vorab-Renderings beantworten die Lesbarkeitsfrage, nicht die Frage
> nach Beamer, Wand und Raumtiefe. Richtwerte aus der Serie bei 50 Personen:
> 1× ergibt ~13 px Schrift auf 1920 Pixel Wandbreite, 2× ergibt ~25 px bei noch
> 71 % der Knoten im Bild.

## Notausgang

„ausblenden" neben einem Eintrag im Operator-UI. Kein Löschen, kein Bearbeiten.
Wieder einblenden ist derselbe Knopf.

## Wenn etwas ausfällt

| Symptom | Bedeutung | Maßnahme |
|---|---|---|
| STT-Badge rot | STT-Server weg | Server neu starten; der Core verbindet sich selbst neu. Fotos und Personenknoten laufen weiter. |
| Kein Personenknoten nach Foto | Telegram/Bot offline | Bot-Token prüfen, Core-Log ansehen. |
| Begriffe fehlen bei einer Person | LLM-Aufruf gescheitert (`status=failed`) | Nichts tun — der Personenknoten steht; das Interview lässt sich nicht wiederholen. |
| Zwei Interviews scheinen offen | Kann nicht passieren | Ein neues Foto schließt das laufende implizit. |
| Graph verschoben | Layout-Fehler | Kamera auf „alles zeigen" stellen; Positionen bleiben persistiert. |
| Nach Absturz leere Wand | — | Nicht möglich: der Zustand wird vollständig aus SQLite rekonstruiert, inklusive Knotenpositionen und laufendem Interview. |

**Was ein Neustart erhält:** alle Personen, Begriffe, Kanten, Zitate, die
Knotenpositionen (die Wand steht danach exakt wie vorher), die vom Operator
gesetzte Dichte, der Kameramodus und der Zoom — und ein Interview, das beim
Absturz noch lief, bleibt offen und lässt sich normal beenden.

## Kalibrierte Werte (Simulationslauf 19c, 60 Interviews)

Diese Werte stehen in `config.toml` und werden im Betrieb **nicht** verändert.

- `terms_per_interview` = **5** — das Modell bleibt von selbst bei ~4,4
  Begriffen pro Interview; ein niedrigerer Wert schneidet gute Begriffe ab statt
  den Einzelnennungs-Rand.
- `merge_neighbours` = **12** — von 5 angehoben. Bei 5 lag der passende
  bestehende Knoten in 7 von 8 Beinahe-Treffern auf Rang 7 bis 56, wurde dem
  Judge also nie gezeigt.
- `merge_style` — unverändert (`kg.config.DEFAULT_MERGE_STYLE`). Nur 1 von 8
  Beinahe-Treffern war eine Fehlentscheidung des Judge; ein Lockern würde auch
  die rund 50 von 60 Interviews lockern, in denen er gut entscheidet.
- **Empfohlene Startdichte = 2** (`default_min_mentions`). Lauf 19c erzeugte 163
  Begriffe, davon 114 von genau einer Person genannt. Bei 1 ersaufen die
  geteilten Konzepte in Einzelnennungen; bei 2 zeigt die Wand 49 Begriffe, jeder
  von mindestens zwei Menschen geteilt; bei 3 sind es 26.
- **Gewähltes Theme = B**, Standard-Kamera = „alles zeigen" (D4).

**Merge-Güte zur Einordnung:** 2 von 5 absichtlich gepflanzten Konzepten sind im
Testlauf vollständig zu einem Knoten zusammengewachsen (Verlauf über die drei
Läufe: 0 → 1 → 2). Die übrigen drei haben sich deutlich verdichtet, ohne ganz zu
verschmelzen. Der Rest ist echte Bedeutungsdistanz — „3D-Drucker" und
„betonsprühende Drohnen" liegen für das Embedding-Modell weit auseinander,
obwohl beide „Roboter auf der Baustelle" meinen. Ein größeres Kandidatenfenster
würde dem Judge nur mehr Rauschen zeigen. Das ist der erwartete Zustand, kein
Defekt: die Wand zeigt dann zwei verwandte Knoten statt einem.
