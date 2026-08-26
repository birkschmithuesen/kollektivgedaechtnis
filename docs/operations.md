# Betrieb — Station Kollektivgedächtnis

Runbook für den Ausstellungstag. Alles, was hier steht, ist am Operator-Laptop
oder am Projektionsrechner erreichbar — kein Eintrag beschreibt eine Einstellung,
die es im UI nicht gibt.

## Vor dem Festival

1. Drei Geheimnisse in die Umgebung exportieren (nie in `config.toml` schreiben,
   nie in eine `.env` im Projekt kopieren):

   ```bash
   export ANTHROPIC_API_KEY=...      # Extraktion + Merge-Judge
   export KG_TELEGRAM_TOKEN=...      # Foto-Auslöser
   export OPENROUTER_API_KEY=...     # nur Embeddings, darf ein eigener Schlüssel sein
   ```

   **Vor Ort ist das der einzige Weg** — der Ausstellungsrechner hat keine
   Hermes-Installation. Nur auf Birks vServer, für Vorbereitungsläufe
   (Register-Muster, Kalibrierung, Pre-Render), dürfen die Schlüssel stattdessen
   aus `~/.hermes/.env` in die Umgebung geladen werden (Freigabe Birk,
   2026-08-26):

   ```bash
   set -a; . ~/.hermes/.env; set +a
   ```

   Die Schlüssel leben dann nur in der Prozess-Umgebung des Kommandos. Der Code
   liest sie ausschließlich über `os.environ` (`kg/config.py`, `kg2/config.py`) —
   eine Projekt-`.env` gibt es nicht und soll es nicht geben.

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

## Browser

Die Station startet Chromium (`scripts/start.sh`), und dabei bleibt es. Zum
Draufschauen von einem anderen Rechner tut es jeder Chromium-Abkömmling
(Brave, Chrome, Edge).

**Firefox nicht zum Prüfen benutzen.** Beobachtet 2026-08-26: Zitate erscheinen
dort nicht. Nicht untersucht und bewusst nicht behoben (Birk) — die Wand läuft
auf Chromium, und ein zweiter Renderer wäre eine Fehlerquelle mehr ohne
Gegenwert. Wer die Station über Firefox kontrolliert, prüft nicht die Station.

## Ein Interview

1. Foto per Telegram → Personenknoten mit Portrait erscheint sofort.
2. Interview führen (Funkmikro läuft dauerhaft in den STT-Server).
3. Beenden: beliebige Textnachricht in Telegram ODER gesprochen
   „Interview beendet" ODER nach 15 Minuten automatisch.
4. Begriffe wachsen **nach** dem Stopp nach, nicht währenddessen.

Ein neues Foto schließt ein noch laufendes Interview implizit — es kann also nie
zwei offene Interviews geben.

## Die Live-Regler

Alle sitzen im Operator-Fenster und wirken sofort auf den gesamten Bestand.

**Dichte** — 1 = alles, 2 = nur Geteiltes, 3 = nur Häufiges. Reiner
Anzeigefilter: verwirft nichts, jederzeit umkehrbar. Startwert 2, siehe unten.
„Geteilt" heißt **von mindestens N verschiedenen Menschen genannt**, nicht
N-mal gesagt (`COUNT(DISTINCT person_id)`, `kg/store.py`). Sagt eine Person
denselben Begriff fünfmal, bleibt der Zähler bei 1.

**Kamera** — „alles zeigen" (ganzes Netz im Bild, steht still), „manuell"
(Besucher zoomt und schiebt per Touch), „automatisch schwenken" (die Kamera
wandert von selbst von Begriff zu Begriff). **Voreinstellung ist
„automatisch schwenken"** (`default_camera_mode` in `config.toml`) — eine
Station, die bewegungslos hochkommt, wirkt defekt.

**Zoom** — stufenloser Regler 1,00× bis 4,00×. 1× = ganzes Netz, 2× = halbe
Netzbreite auf der Wand. Wirkt in „alles zeigen" und „automatisch schwenken";
in „manuell" nicht, weil dort die Hand des Besuchers führt.

> **Bei 1,00× läuft die automatische Fahrt ins Leere.** Dann sind per
> Definition alle Knoten im Bild, die Kamera fährt zu Zielen, die schon zu
> sehen sind, und die Wand wirkt bewegungslos. Der Regler schreibt das selbst
> dazu. Für eine sichtbare Fahrt mindestens ~1,5× (gemessen: bei 1,5× sind
> 66 % der Knoten im Bild, bei 2× noch 37 %).

**Tempo** — Geschwindigkeit der automatischen Fahrt, 1/1 bis 1/4. Rechter
Anschlag ist das Tempo, auf das die Bewegung abgestimmt wurde; nach links wird
sie bis auf ein Viertel gedehnt (gemessen: 5,2 s → 20,9 s pro Etappe). Es gibt
bewusst keine Einstellung, die schneller läuft. Ein Reglerzug wirkt ab der
**nächsten** Etappe — eine laufende neu zu skalieren würde die Kamera springen
lassen.

> **Kamera, Zoom und Tempo werden vor Ort am echten Screen eingestellt**
> (Entscheidung D4). Die Vorab-Renderings beantworten die Lesbarkeitsfrage,
> nicht die Frage nach Beamer, Wand und Raumtiefe. Richtwerte aus der Serie bei
> 50 Personen: 1× ergibt ~13 px Schrift auf 1920 Pixel Wandbreite, 2× ergibt
> ~25 px bei noch 71 % der Knoten im Bild.

## Der Touchscreen (Fläche A)

Aufruf mit `?touch=1` — also `http://<adresse>:8800/projection?touch=1`. Ohne
das Flag ist die Seite reine Anzeige; genau so läuft Fläche C im Plenumssaal.

**Gerät:** iiyama ProLite TE6568MIS-B1AG, 65", `IR Touch 20points`, USB-HID
(Handbuch, Specs-Tabelle). Kein Treiber nötig, HID-Multitouch ist im Kernel.

| Geste | Wirkung |
|---|---|
| Ein Finger ziehen | Ausschnitt verschieben |
| Zwei Finger auf/zu | Zoom |
| Portrait antippen | Zitat der Person erscheint; nochmal = nächstes Zitat |
| Hintergrund antippen | Zitat weg (sonst nach 12 s von selbst) |
| „Übersicht" | ganzes Netz, Zoom 1×, zurück zur Automatik |
| Dichte-Knöpfe | alle / geteilt (ab 2) / häufig (ab 3), mit Anzahl |

**Berührung schaltet lokal auf „manuell", 30 s ohne Kontakt schaltet zurück.**
Lokal heißt: Der Wechsel wird **nicht** an den Server gemeldet. `camera_mode`
ist globaler Zustand — ein POST würde Fläche C im Plenumssaal mit auf
„manuell" ziehen, wo niemand etwas anfassen kann. Die Dichte-Knöpfe posten
dagegen sehr wohl: *wohin die Kamera schaut* ist lokal, *was die Wand zeigt*
gilt überall.

Zwei Warnungen aus dem Handbuch, die den Aufbau betreffen:

- *„Permanent damage can occur if Sharp Edged, Pointed or Metal items are used
  to activate Touch."* — keine Stifte, keine Ringe.
- IR-Touch ist **lichtempfindlich**: „incident light that contains large
  quantities of infrared light may affect touch screen operation". Direkte
  Sonne oder Halogenspots auf der Scheibe erzeugen Geisterkontakte. Position
  gegen die Beleuchtung prüfen, bevor die Wand steht.

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

## Kollektivtraum — Screen B (Tool 2)

Läuft auf einer **eigenen kleinen Maschine** neben dem Ausstellungsrechner
(Spec §9). Tool 1 und Tool 2 hängen nicht voneinander ab: Fällt Tool 2 aus,
bleibt die Wand unberührt; fällt Tool 1 aus, zeigt Screen B seinen letzten
Traum und den vollen Verlaufsstreifen weiter.

### Vor dem Festival, auf der Traum-Maschine

1. Zwei Geheimnisse exportieren (nie in `config2.toml`, nie in eine
   Projekt-`.env`):

   ```bash
   export ANTHROPIC_API_KEY=...      # Stufe 1: Graph -> Satz
   export OPENROUTER_API_KEY=...     # Stufe 2: Satz -> Bild
   ```

   Für Vorbereitungsläufe auf Birks vServer (nicht vor Ort) gilt derselbe
   Kurzweg wie oben: `set -a; . ~/.hermes/.env; set +a`.

2. `cp config2.example.toml config2.toml`, dann `tool1_url` auf die Adresse
   setzen, die der Core beim Start ausgibt.

3. **Netzprüfung, von DIESER Maschine aus** (siehe „Netzwerk für Screen B und
   Screen C" oben — auf dem Ausstellungsrechner selbst gelingt sie auch bei
   falschem Bind und beweist deshalb nichts):

   ```bash
   # auf der Traum-Maschine, nicht auf dem Ausstellungsrechner:
   curl -s http://<adresse>:8800/graph.json | head -c 200
   ```

4. Rauchtest ohne Ausstellungsrechner und ohne Modelle:

   ```bash
   uv run python -m kg2 --no-watch
   ```

   Danach `http://<traum-maschine>:8810/dream` und `/operator` öffnen.

5. **Vor der ersten echten Ausstellung, einmalig:** den Bild-Endpunkt
   sondieren. `docs/dream-image-contract.md` ist als „NOCH NICHT VERIFIZIERT"
   markiert — die Request-/Response-Form, gegen die `kg2/imagegen.py`
   geschrieben wurde, stammt aus der Modell-Dokumentation, nicht aus einem
   echten Aufruf. Das Sondierungsskript steht in diesem Dokument unter
   „Aktion für einen Menschen mit Schlüssel"; es kostet einen Aufruf (ein paar
   Cent) und druckt nur die Form der Antwort. Ergebnis dort eintragen, bevor
   der erste echte Traum am Ausstellungstag entsteht.

### Der Rhythmus

Ein Traum entsteht, **wenn ein Interview fertig verarbeitet ist** — nicht nach
der Uhr, nie während der Stille. Der Watcher fragt alle
`poll_interval_s` Sekunden `graph.json` ab und erkennt ein fertiges Interview
daran, dass ein Personenknoten **Kanten hat**. Ein Personenknoten ohne Kanten
ist erst das Foto; die Begriffe kommen Sekunden bis Minuten später (Spec §4.1).

Zwischen zwei Träumen liegen mindestens `min_interval_s` Sekunden. Landen
mehrere Interviews in diesem Fenster, werden sie zu **einem** Traum
zusammengefasst — der Traum ist der des ganzen Graphen, nicht der einer Person.

### Die Regler (alle im Operator-Fenster der Traum-Maschine)

**Anzeige** — Leitfrage zeigen/verbergen und nach N Sekunden ausblenden;
Überblenddauer; Streifenhöhe; Schreibmaschine an/aus.

**Ablauf** — „Jetzt träumen" (ignoriert den Mindestabstand; für den Moment, in
dem jemand vom Veranstalter vor dem Schirm steht), „Pause", „Aktuellen Traum
verwerfen".

> **Verwerfen ist der einzige Notausgang** (Spec §7). Es nimmt das Bild in
> einem Schritt vom großen Schirm **und** aus dem Verlaufsstreifen; der
> vorherige Traum rückt wieder nach vorn. Der Datensatz bleibt erhalten —
> „zurückholen" ist derselbe Knopf. Kein Freigabeprozess, keine Kuratierung.

**Nicht im Interface, absichtlich:** Leitfrage, Bildregister und Gewichtung.
Alle drei werden morgens in `config2.toml` gesetzt. Eine wandernde Leitfrage
macht genau die Vergleichbarkeit kaputt, für die der Verlaufsstreifen da ist.

### Wenn etwas ausfällt

| Symptom | Bedeutung | Maßnahme |
|---|---|---|
| Bild wechselt nicht mehr, Streifen steht | Cloud oder Netz weg | Nichts tun. Das letzte Bild bleibt stehen, der nächste Trigger versucht es erneut. Kein Retry-Sturm, keine Zusatzkosten. |
| Nie ein neuer Traum, obwohl Interviews laufen | Tool 1 nicht erreichbar | `curl http://<adresse>:8800/graph.json` **von der Traum-Maschine**. Danach Bind und Firewall prüfen. |
| Nie ein neuer Traum, obwohl Interviews laufen, UND ein Neustart hat nicht geholfen | Systemuhr der Traum-Maschine ist zurückgesprungen (RTC beim Booten vor der echten Zeit, später per NTP korrigiert) — der gespeicherte Start-Zeitstempel des letzten Traums liegt dann in der Zukunft, und ein Neustart liest genau diesen Zeitstempel aus `dreams.sqlite3` zurück, löscht ihn also nicht | Nichts zu tun: Der Trigger erkennt einen Start-Zeitstempel in der Zukunft selbst als Uhrsprung und lässt den nächsten Traum trotzdem zu (mit Log-Eintrag). Bleibt er dennoch aus, Systemzeit prüfen (`date`). |
| Screen B ist schwarz | Tool-2-Prozess tot | Neu starten. Wand und zweiter Raum sind unberührt. |
| Bild ist unbrauchbar oder peinlich | Bildmodell | „Aktuellen Traum verwerfen". Der vorherige kommt zurück. |
| Traum steht auf „läuft" und wird nicht fertig | Absturz mitten im Zyklus | Nichts tun — er erscheint nie auf dem Schirm. Der nächste Trigger macht einen neuen. |
| Platte voll | ~40 Bilder am Tag zu einigen hundert KB | Für einen Tag kein Thema (Spec §8). Bewusst nicht wegprogrammiert. |

**Physischer Rückfallweg:** LTE-Stick. Beide Cloud-Aufrufe hängen am Uplink,
und Messe-WLAN ist genau dort um 14 Uhr am schwächsten.

**Was ein Neustart erhält:** den aktuellen Traum, den vollständigen
Verlaufsstreifen inklusive der verworfenen Einträge (als verworfen), jede
Anzeige-Einstellung, den Pausenzustand — und die Information, welche Interviews
schon geträumt wurden, sodass nach dem Neustart weder alles noch einmal geträumt
wird noch gar nichts mehr. Alles liegt in `dreams.sqlite3`; nichts nur im
Speicher.

### Neuer Ausstellungstag

Genau das eben beschriebene Verhalten — `dreams.sqlite3` und die Bilder
überleben jeden Neustart — hat eine Kehrseite: Es gibt sonst nichts, das einen
Tag vom nächsten trennt. Ohne Eingriff öffnet Tag 2 mit den ~40 Träumen von
Tag 1 noch im Verlaufsstreifen und wächst von dort weiter.

Der Streifen ist die Beweiskette für GENAU EINEN Tag (Spec §6, §8) — er zeigt,
was an diesem einen Tag gesagt wurde, nicht eine über mehrere Tage
akkumulierte Sammlung. Vor dem zweiten (und jedem weiteren) Ausstellungstag,
auf der Traum-Maschine, bei gestopptem Prozess:

```bash
rm dream-data/dreams.sqlite3
rm -rf dream-data/images/
```

Beide Pfade werden beim nächsten Start automatisch neu angelegt (leere
Datenbank, leerer Bilderordner) — dasselbe Verzeichnis, das `config2.toml`
unter `data_dir` nennt.

### Kalibrierte Werte (Tool 2)

Diese Werte stehen in `config2.toml`. Zwei sind tatsächlich kalibriert, einer
ist ein Startwert aus der Spec, der noch nicht am generierten Material
überprüft wurde. Der Unterschied wird hier nicht verwischt.

- `min_interval_s` = **240** — kalibriert (`sim.dream_calibrate floor`,
  Simulationslauf 2026, kein Modell nötig, reine Arithmetik über den
  Tagestakt). Bei 60 Interviews über 8 h liegt die Taktung bei einem
  Interview alle 480 s. Ergebnistabelle:

  | `min_interval_s` | Träume | zusammengefasst |
  |---|---|---|
  | 120 | 60 | 0 |
  | 240 | 60 | 0 |
  | 360 | 60 | 0 |
  | 480 | 60 | 0 |
  | 900 | 30 | 30 |

  Bei 40 Interviews über 6 h (Takt 540 s) zeigt sich dieselbe Form.
  **Der eigentliche Befund:** Bei der erwarteten Taktung greift ein
  240-s-Boden **nie** — 60 Träume, 0 zusammengefasst, genau wie bei 120, 360
  und 480. Er ist keine laufende Bremse, sondern eine Versicherung gegen einen
  Schwall von Interviews, die dicht hintereinander eintreffen; erst deutlich
  über der Tagesspannung (hier: ab etwa 900 s) beginnt er, den Tag wirklich zu
  formen — und halbiert dort die Anzahl. Alles bei oder unter dem Tagesabstand
  ist ein No-op. **Das steht hier bewusst so deutlich, damit niemand den Wert
  später nach oben „nachjustiert" in der Annahme, er würde im Normalbetrieb
  etwas tun — das tut er nicht.**
- `poll_interval_s` = **5** — bei diesem Mindestabstand ist eine
  Erkennungsverzögerung von 5 s unsichtbar (Spec §4.1).
- `contradiction_min_persons` = **6** — **noch nicht kalibriert.** Das ist der
  Startwert aus der Spec (§5.1), nicht das Ergebnis eines Kalibrierungslaufs.
  Unterhalb dieser Personenzahl läuft Stufe 1 allein auf der Gewichtung, weil
  das Modell bei drei Interviews sonst einen Gegensatz erfinden würde, der im
  Material gar nicht da ist. Ob 6 die richtige Schwelle ist, sagt erst der
  Lauf unten in „Offene Entscheidungen" — mit echten generierten Sätzen, nicht
  mit der Annahme, die den Startwert begründet hat.

### Offene Entscheidungen

Die folgenden vier Werte sind **nicht** entschieden. `config2.example.toml`
trägt für die ersten beiden vorläufige Startwerte (dieselben, die
`kg2/config.py` als Ausgangspunkt für Task 16 nennt) — das sind KEINE
gewählten Werte, nur das, womit `kg2` offline läuft, solange niemand
gewählt hat. Jede Zeile hier nennt den exakten Befehl, der die Entscheidung
möglich macht. Kein Wert aus dieser Liste darf ungeprüft in den
Ausstellungsbetrieb gehen.

1. **Wortlaut der Leitfrage** (`guiding_question`). Vier Kandidaten, alle breit
   genug für alle drei Interviewthemen (Zukunft des Bauens, KI im Bauen, neue
   Formen des Zusammenlebens), werden bei 3/10/30/60 Personen als Sätze
   ausgegeben — Birk liest die Sätze kalt und wählt, ohne dass eine
   Empfehlung im Output steht:

   ```bash
   uv run python -m sim.dream_calibrate questions   | tee out/calibrate-questions.txt
   ```

   Braucht `ANTHROPIC_API_KEY`, ca. 16 Stufe-1-Aufrufe. Der aktuelle Wert in
   `config2.example.toml` (`"Wie leben und bauen wir in zehn Jahren?"`) ist der
   Vorschlag, mit dem die Kandidaten anfangen — nicht das Ergebnis der Wahl.

2. **Bestätigung der Widerspruchsschwelle** (`contradiction_min_persons`).
   Jede Kandidatengröße wird mit und ohne die Widerspruchs-Klausel
   nebeneinandergestellt, damit sichtbar wird, ob der Widerspruch im Material
   wirklich vorhanden war oder vom Modell erfunden wurde:

   ```bash
   uv run python -m sim.dream_calibrate contradiction   | tee out/calibrate-contradiction.txt
   ```

   Braucht `ANTHROPIC_API_KEY`, ca. 8 Stufe-1-Aufrufe.

3. **Bildregister** (`visual_register`). Vier Register — Aquarell, malerisch-
   atmosphärisch, Radierung, Siebdruck — werden auf demselben erfundenen Satz
   gerendert, alphabetisch aufgelistet, keine Reihenfolge, keine Empfehlung im
   Output:

   ```bash
   uv run python -m sim.dream_register --out out/register1
   ```

   Braucht `OPENROUTER_API_KEY`, 4 Bildaufrufe. Birk wählt an den Bildern,
   nicht am Text. Der gewählte Registertext kommt danach als
   `visual_register` in `config2.toml`.

4. **Modus des Verlaufsstreifens.** Drei Modi wurden bei 20 und 40 Träumen in
   `out/dream-strip-comparison/` gerendert und mit inhaltstragenden
   Platzhalterbildern gemessen (nicht mit einfarbigen Flächen, an denen ein
   Zuschnitt unsichtbar bliebe):

   | Modus | 20 Träume | 40 Träume | Beobachtung |
   |---|---|---|---|
   | `cover` (aktueller Standard) | 80×210 px | 31×210 px | Zuschnitt auf einen mittigen Streifen; bei 40 nahezu vollständiger Verlust von links/rechts. |
   | `aspect` | 80×45 px | 31×18 px | Kein Zuschnitt, aber beide Maße schrumpfen bis zur Unleserlichkeit; das reservierte Streifenband bleibt bei 40 größtenteils leer. |
   | `wrap` | 372×210 px | 372×210 px (pro Bild) | Kein Zuschnitt einzelner Bilder, aber die Zeilenhöhe ist fest mit `overflow: hidden` — nur ein Teil der Träume ist sichtbar, der Rest wird stillschweigend abgeschnitten. |

   Keiner der drei Modi ist hier empfohlen. Birk wählt anhand der gerenderten
   Dateien in `out/dream-strip-comparison/` (Dateinamen tragen den Modus).
   Gewählt wird per `--strip-mode` beim Pre-Rendering und per
   `data-strip-mode` auf der Seite.

5. **Die 40-Bilder-Vorab-Serie**, für die Beurteilung des vollen Tages statt
   eines leeren Streifens — braucht Register **und** Streifenmodus aus 3. und
   4., damit die 40 echten Bilder nicht an einer noch unfertigen Anzeige
   verschwendet werden:

   ```bash
   uv run python -m sim.dream_prerender --out out/dream-prerender2 --generate
   ```

   Braucht `OPENROUTER_API_KEY`, 40 Bildaufrufe — ein sichtbarer, bewusster
   Kostenposten, kein Nebeneffekt.

6. **Vertrag des Bild-Endpunkts.** Siehe Schritt 5 unter „Vor dem Festival"
   oben: `docs/dream-image-contract.md` ist als „NOCH NICHT VERIFIZIERT"
   markiert, weil beim Bau kein `OPENROUTER_API_KEY` zur Verfügung stand. Das
   eingebettete Sondierungsskript muss einmal mit echtem Schlüssel laufen,
   bevor der erste echte Traum am Ausstellungstag entsteht; Ergebnis wird in
   diesem Dokument nachgetragen.

**Vorab-Renderings, sobald 3.–5. entschieden sind:** `out/dream-prerender2/`
zeigt die Seite bei 1, 5, 20 und 40 Träumen. Der Streifen wird voll beurteilt,
nicht leer — 40 ist der Zustand um 17 Uhr.
