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

   > **Achtung, 2026-08-26 beobachtet:** `~/.hermes/.env` enthält zwar eine
   > Zeile `ANTHROPIC_API_KEY=`, aber **ohne Wert** — Birks Hermes fährt Claude
   > über das Abo (`anthropic_plan`) und einen lokalen Proxy, nicht über einen
   > API-Schlüssel. Ein Vorbereitungslauf, der Stufe 1 braucht
   > (`sim.dream_calibrate terms` / `mood` / `quotes`), scheitert deshalb an
   > `set -a; . ~/.hermes/.env; set +a` allein mit „Could not resolve
   > authentication method" — und zwar in **jedem** Teilschritt, sodass der
   > Lauf durchläuft und nur FEHLER druckt. Für Stufe-1-Läufe auf dem vServer
   > zusätzlich auf den Proxy zeigen (verifiziert):
   >
   > ```bash
   > export ANTHROPIC_BASE_URL=http://127.0.0.1:28764
   > export ANTHROPIC_API_KEY=proxy      # Platzhalter; der Proxy authentifiziert
   > ```
   >
   > Nur für Vorbereitungsläufe auf dem vServer. **Vor Ort gilt das nicht** —
   > der Ausstellungsrechner hat weder Hermes noch den Proxy und braucht einen
   > echten `ANTHROPIC_API_KEY` in der Umgebung. `OPENROUTER_API_KEY` ist
   > davon nicht betroffen, der liegt mit echtem Wert in der Datei.

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

## Beide Werkzeuge zusammen starten

Der vollständige Ablauf für einen Ausstellungstag mit Wand **und** Screen B.
Die Reihenfolge ist eine Empfehlung, keine Abhängigkeit: die beiden Werkzeuge
kennen sich nur über `graph.json`, und jedes läuft weiter, wenn das andere
ausfällt (Spec §9). Tool 1 zuerst zu starten spart nur die erste
Fehlermeldung.

**Wo läuft was?** Tool 1 auf dem Ausstellungsrechner (Beamer, Touchscreen,
Telegram, STT), Tool 2 auf einer eigenen kleinen Maschine daneben. Beide auf
einer Kiste ist möglich — die Ports (8800/8810) und die Datenverzeichnisse
(`data/` vs. `dream-data/`) kollidieren nicht — und für einen Probedurchlauf
genau richtig. Vor Ort trennt sie, dass ein Absturz des einen den anderen
nicht mitnimmt.

**1. Auf dem Ausstellungsrechner: Tool 1.**

```bash
export ANTHROPIC_API_KEY=... KG_TELEGRAM_TOKEN=... OPENROUTER_API_KEY=...
./scripts/start.sh
```

Damit die Traum-Maschine überhaupt herankommt, muss in `config.toml`
`server_host = "0.0.0.0"` stehen (siehe „Netzwerk für Screen B und Screen C").
Der Core druckt beim Start drei URLs mit der **aufgelösten** Adresse — die
dritte ist die, die gleich in `config2.toml` gehört.

**2. Netz prüfen, von der Traum-Maschine aus.** Nicht überspringen: ein `curl`
auf dem Ausstellungsrechner selbst gelingt auch bei falschem Bind und beweist
deshalb nichts.

```bash
# auf der Traum-Maschine:
curl -s http://<gedruckte-adresse>:8800/graph.json | head -c 200
```

**3. Auf der Traum-Maschine: `tool1_url` eintragen und Tool 2 starten.**

```bash
cp config2.example.toml config2.toml      # einmalig
# tool1_url auf die Adresse aus Schritt 1 setzen
export ANTHROPIC_API_KEY=... OPENROUTER_API_KEY=...
./scripts/start-dream.sh
```

Das Skript prüft die Adresse aus `config2.toml` und **sagt, was es findet** —
aber es wartet nicht darauf. Ist Tool 1 nicht erreichbar, kommt Screen B
trotzdem hoch und träumt von selbst weiter, sobald Tool 1 antwortet. Das ist
Absicht: ein Tool 1, das um 14 Uhr neu gestartet werden muss, darf nicht auch
den zweiten Schirm mitreißen.

Wie `scripts/start.sh` startet es Watcher, Server und die beiden
Browser-Fenster (Screen B im Kiosk-Modus, Operator als normales Fenster) und
fährt jeden Teil nach einem Absturz wieder hoch. Liegt Screen B nicht rechts
neben dem Panel: `KG2_DREAM_POS=<x>,<y> ./scripts/start-dream.sh`.

**4. Gegenprobe, dass die Kette wirklich steht.** Ein Interview führen (oder
im Operator-Fenster von Tool 2 „Jetzt träumen" drücken). Innerhalb von
`poll_interval_s` + Modellzeit erscheint auf Screen B erst der Satz, dann das
Bild. Bleibt es aus: Tabelle „Wenn etwas ausfällt" unten.

**Was der Probedurchlauf kostet.** Pro Traum ein Anthropic-Aufruf (Satz) und
ein Bildaufruf (≈ 0,139 USD, gemessen). 10–15 Interviews sind also 1,40–2,10
USD. Ein voller Ausstellungstag mit ~40 Träumen ≈ 5,55 USD.

**Beim zweiten Tag** vorher `dream-data/` leeren — siehe „Neuer
Ausstellungstag", sonst öffnet Tag 2 mit den Träumen von Tag 1 im Streifen.

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

**Begriffe auf der Wand** (`max_terms`, bis 2026-08-29 `min_mentions`) —
Stufen **20 / 32 / 45 / alle**, Startwert **32**. Reiner Anzeigefilter:
verwirft nichts, jederzeit umkehrbar. Ersetzt den alten Schwellwert-Regler
(„zeige nur Begriffe ab N Nennungen") durch eine direkte Obergrenze für die
Begriffszahl — die Messung vom 2026-08-29 (Tabelle unten) zeigte, dass der
Schwellwert die eigentliche Frage („wie viele Begriffe passen auf die Wand,
ohne dass Beschriftungen kollidieren oder zu klein werden") nur indirekt und
unzuverlässig beantwortete.

Auswahlregel (identisch mit Tool 2's `kg2/weighting.py`, siehe unten):
**alle Begriffe ab 2 Nennungen zuerst, aufgefüllt mit den jüngsten
Einmal-Nennungen bis zur Obergrenze.** Übersteigen allein schon die geteilten
Begriffe die Obergrenze, wird auch bei ihnen gekappt — häufigste zuerst. „Ab 2
Nennungen" heißt **von mindestens 2 verschiedenen Menschen genannt**, nicht
2-mal gesagt (`COUNT(DISTINCT person_id)`, `kg/store.py`). Sagt eine Person
denselben Begriff fünfmal, bleibt der Zähler bei 1.

Eine Mindeststandzeit (`MIN_STAND_REVISIONS` in `frontend/static/projection.js`,
3 Graph-Aktualisierungen) verhindert sichtbares Zucken: ein Begriff, der
gerade erst auf die Wand gekommen ist, bleibt mindestens drei weitere
Interviews sichtbar, selbst wenn er rechnerisch schon wieder unter die Grenze
fiele. Gemessen (2026-08-29, `sim.dream_calibrate.prefix_graph` über 60
Interviews): ohne diese Regel wechseln 3,5 bis 5,2 Begriffe pro Interview die
Sichtbarkeit — weit über der Grenze, ab der es als „selten" gelten würde. Der
größte Teil davon ist gewollte Fluktuation durch neue Einmal-Nennungen, aber
echtes Sofort-Zucken (ein Begriff verschwindet und taucht im nächsten
Interview wieder auf) kam mit rund 0,3 Fällen pro Interview trotzdem vor —
genug, um die Mindeststandzeit zu rechtfertigen. Die Standzeit hält einen
Begriff bewusst **zusätzlich zur Obergrenze** fest, statt einem frisch
genannten Begriff seinen Platz streitig zu machen — sonst würde genau das
verhindert, was die „jüngste-zuerst"-Regel eigentlich soll. Die Wand kann
dadurch kurzzeitig etwas über der eingestellten Zahl liegen; das ist durch die
Standzeit selbst begrenzt (grob: Anzahl der Begriffe, die pro Interview aus
der Auswahl fallen, mal drei) und baut sich von selbst wieder ab, sobald die
Standzeit einzelner Begriffe abläuft. Ein Regler-Wechsel durch den
Operator selbst ist davon ausgenommen und wirkt sofort, ohne auf die
Standzeit anderer Begriffe zu warten.

> Jede Stufe trägt die Zahl der Begriffe, die sie übrig ließe — „32 (32)", bei
> jedem Graph-Push nachgeführt. Früh am Tag können mehrere Stufen dieselbe,
> kleinere Zahl zeigen (z. B. „32 (8)" und „45 (8)"): dann ist die Stufe nicht
> kaputt, der Graph hat nur noch nicht so viele Begriffe. Jede Stufe bleibt
> wählbar — der Graph wächst hinein.

**Gemessen** (`sim/probes/wall_legibility.py`, 60 Personen / 163 Begriffe,
echtes Frontend, 1920×1080): der alte Regler produzierte bei seinem
Standardwert (`min_mentions=1`) eine unlesbare Wand — 56 überlappende
Label-Paare, 51 Labels auf Portraits. Die neue Obergrenze hält die
Kollisionen über den ganzen getesteten Bereich einstellig:

| Obergrenze | Schrift px | Label-Kollisionen | Labels auf Portraits | Fläche |
|---|---|---|---|---|
| 20 | 16,5 | 1 | 4 | 8,9 % |
| 26 | 13,0 | 2 | 9 | 8,7 % |
| 32 | 14,7 | 2 | 3 | 11,9 % |
| 40 | 14,3 | 1 | 7 | 14,6 % |
| 49 | 12,4 | 5 | 7 | 15,1 % |
| 60 | 10,3 | 1 | 2 | 15,5 % |

Die genauen Stufenwerte (20/32/45) sind ein Vorschlag, kein Naturgesetz — sie
werden vor Ort am echten Beamer überprüft (siehe D4 unten); die Messung deckt
20–60 ab.

> **Bewusst NICHT an Tool 2's Trauminhalt gekoppelt.** Beide Werkzeuge folgen
> derselben Auswahlregel, aber mit eigenen Grenzen: die Wand kappt aus einem
> physikalischen Grund (Fläche, Schriftgröße), der Traum aus einem
> inhaltlichen (das Modell soll nicht in Randnotizen ertrinken). Eine Kopplung
> würde einen Operator, der wegen der Schriftgröße am Regler dreht,
> unabsichtlich ändern lassen, woraus die Bilder entstehen — zwei
> Ausstellungstage mit unterschiedlicher Reglerstellung wären dann nicht mehr
> vergleichbar, obwohl die Menschen dasselbe gesagt haben.

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

**Porträtgröße** — stufenloser Regler **40 px bis 260 px**, Startwert
**120 px**. Er setzt, wie groß ein Porträtkreis auf der Wand erscheint, in
echten Bildschirmpixeln: gleich groß bei einer Person wie bei sechzig, und
unabhängig davon, wie weit der Zoom danebensteht. Anlass (Birk, 2026-08-29, an
der Station beobachtet): bei einer einzelnen Person füllte das Porträt den
ganzen Schirm. Gemessen vor der Änderung, ein Mensch und ein Begriff auf
1920×1080: 367 px (Thema a) bzw. 450 px (Thema b) — gegen 29 px bei fünfzig
Personen. Die Schrift folgt weiter dem alten Prinzip (Modelleinheiten mal
Zoom) und wird mit wachsendem Netz kleiner; ausgenommen sind nur die Porträts.

> **Der Regler ändert die Platzierung nicht.** Das Layout rechnet unverändert
> mit der Modellgröße des Themas (`--person-size`) und weiß nichts von der
> eingestellten Bildschirmgröße. Auf einer vollen Wand werden die Porträts
> damit größer gezeichnet, als das Layout angenommen hat, und können sich
> berühren. Gemessen am 50-Personen-Netz (2026-08-29), Paare sich berührender
> Porträts von 1225 möglichen: 9 bei 40 px, 62 bei 80 px, 108 bei 120 px, 268
> bei 260 px; bei 20 Personen 0 / 3 / 13 / 34. Wenn sich die Kreise stapeln,
> ist der Regler nach links das Mittel — die Platzierung selbst mitzuziehen
> wäre ein eigener Umbau.

> **Nicht dasselbe wie Zoom.** Der Zoom wählt den Ausschnitt (wie viel vom Netz
> auf der Wand steht), die Porträtgröße die Größe der Gesichter darin. Beide
> wirken unabhängig: ein Zoomzug lässt die Porträts unverändert groß, ein Zug
> an der Porträtgröße ändert den Ausschnitt nicht.

**Tempo** — Geschwindigkeit der automatischen Fahrt, 1/1 bis 1/4. Rechter
Anschlag ist das Tempo, auf das die Bewegung abgestimmt wurde; nach links wird
sie bis auf ein Viertel gedehnt (gemessen: 5,2 s → 20,9 s pro Etappe). Es gibt
bewusst keine Einstellung, die schneller läuft. Ein Reglerzug wirkt ab der
**nächsten** Etappe — eine laufende neu zu skalieren würde die Kamera springen
lassen.

> **Kamera, Zoom, Porträtgröße und Tempo werden vor Ort am echten Screen
> eingestellt**
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

„Übersicht" ist der **einzige** Knopf am Touchscreen. Alles, was ein Besucher
dort tut, bleibt auf diesem Schirm.

**Berührung schaltet lokal auf „manuell", 30 s ohne Kontakt schaltet zurück.**
Lokal heißt: Der Wechsel wird **nicht** an den Server gemeldet. `camera_mode`
ist globaler Zustand — ein POST würde Fläche C im Plenumssaal mit auf
„manuell" ziehen, wo niemand etwas anfassen kann.

> **Die Dichte gehört dem Operator, nicht dem Gast** (Birk, 2026-08-26). Bis
> dahin standen die drei Dichte-Knöpfe mit am Touchscreen und posteten
> `/api/min_mentions` — mit der Begründung, *wohin die Kamera schaut* sei lokal,
> *was die Wand zeigt* gelte überall. Für den Operator stimmt das; er hat den
> Regler ohnehin. Für einen Finger im Foyer stimmt es nicht: Fläche A steht am
> Eingang, Fläche C im Plenumssaal, und ein Gast, der dort „häufig (ab 3)"
> drückte, riss die Saalwand vor dem sitzenden Publikum mit um. Die Knöpfe sind
> weg; der Regler sitzt nur noch im Operator-Fenster. „Übersicht" bleibt, weil
> er nichts Globales verstellt — ohne ihn käme man aus einer verpinchten Ansicht
> nur durch 30 s Warten wieder heraus.

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
gesetzte Dichte, der Kameramodus, der Zoom und die Porträtgröße — und ein
Interview, das beim Absturz noch lief, bleibt offen und lässt sich normal
beenden.

## Kalibrierte Werte (Simulationslauf 19c, 60 Interviews)

Diese Werte stehen in `config.toml` und werden im Betrieb **nicht** verändert.

- `terms_per_interview` = **5** — das Modell bleibt von selbst bei ~4,4
  Begriffen pro Interview; ein niedrigerer Wert schneidet gute Begriffe ab statt
  den Einzelnennungs-Rand.
- `merge_neighbours` = **12** — von 5 angehoben. Bei 5 lag der passende
  bestehende Knoten in Lauf 19b in 7 von 8 Beinahe-Treffern auf Rang 7 bis 56,
  wurde dem Judge also nie gezeigt. Eine spätere Auswertung von Lauf 19c
  bestätigt, dass die Anhebung wirkt: in 22 von 26 untersuchten
  Duplikat-Paaren stand der richtige bestehende Knoten in den Top-12, meist
  auf Rang 1 (`docs/merge-audit-2026-08-27.md`). Die Kandidatenauswahl ist damit
  nicht mehr das Nadelöhr — der verbleibende Nichtmerge-Anteil sind heute
  überwiegend bewusste Judge-Entscheidungen. Einzelfälle bleiben trotzdem
  außerhalb des Fensters, z. B. „Ungenutzte Vorzeigeprojekte" vs.
  „Leerstehende Häuser im Dorfkern" auf Rang 58 von 87.
- `merge_style` — unverändert (`kg.config.DEFAULT_MERGE_STYLE`). Nur 1 von 8
  Beinahe-Treffern war eine Fehlentscheidung des Judge; ein Lockern würde auch
  die rund 50 von 60 Interviews lockern, in denen er gut entscheidet.
- **Empfohlene Obergrenze = 32** (`default_max_terms`, seit 2026-08-29 —
  ersetzt die frühere Empfehlung „Startdichte = 2" für den alten
  `min_mentions`-Regler). Lauf 19c erzeugte 163 Begriffe, davon 114 von genau
  einer Person genannt; unbegrenzt kollidierten 56 Label-Paare. Bei einer
  Obergrenze von 32 misst die Sonde 14,7 px Schrift und 2 Kollisionen (siehe
  Tabelle oben) — die mittlere der drei vorgeschlagenen Stufen.
- **Gewähltes Theme = B**, Standard-Kamera = „alles zeigen" (D4).

**Merge-Güte zur Einordnung:** 2 von 5 absichtlich gepflanzten Konzepten sind im
Testlauf vollständig zu einem Knoten zusammengewachsen (Verlauf über die drei
Läufe: 0 → 1 → 2). Die übrigen drei haben sich deutlich verdichtet, ohne ganz zu
verschmelzen. Der Rest ist echte Bedeutungsdistanz — „3D-Drucker" und
„betonsprühende Drohnen" liegen für das Embedding-Modell weit auseinander,
obwohl beide „Roboter auf der Baustelle" meinen. Ein größeres Kandidatenfenster
würde dem Judge nur mehr Rauschen zeigen. Das ist der erwartete Zustand, kein
Defekt: die Wand zeigt dann zwei verwandte Knoten statt einem.

## Ende-zu-Ende-Tests (Tool 1)

Zwei Tests laufen durch die echten Ketten statt durch Attrappen — `tests/e2e/`:

- `test_telegram_photo.py` — Telegram-Update → Download → Portraitzuschnitt →
  Personenknoten, und die Textnachricht, die das Interview wieder schließt. Der
  echte `TelegramSource` redet dabei mit einem lokalen Bot-API-Server statt mit
  Telegram: kein Token, kein Netz, kostenlos.
- `test_stt_to_wall.py` — SSE-Zeilen nach `docs/stt-contract.md` → Transkript →
  gesprochenes Interviewende → **echter Anthropic-Aufruf** (Extraktion und
  Merge) → Begriffe, Zitate, `graph.json`, Live-Ereignis an den Browser.

```bash
pytest -m e2e tests/e2e
```

Beide sind aus der Standardsuite **deselektiert** (`addopts = "-m 'not e2e'"` in
`pyproject.toml`), damit kein gewöhnlicher Testlauf Geld kostet; `-m e2e` ist der
bewusste Weg hinein. Kostenbremse im Test selbst: **ein** Interview, ein kurzes
Transkript, genau **zwei** Modellaufrufe (`claude-opus-5`, Effort `high`). Der
ganze Lauf dauert rund 20 Sekunden. Eine USD-Zahl steht hier absichtlich nicht —
sie wäre geschätzt, und geschätzte Kosten sind in diesem Dokument schon einmal um
den Faktor fünf danebengelegen (siehe Kostenkorrektur bei Tool 2).

Der Schlüssel kommt wie überall nur aus der Prozess-Umgebung. Zwei Wege hinein:

```bash
export ANTHROPIC_API_KEY=...                        # vor Ort: echter Schlüssel
export ANTHROPIC_BASE_URL=http://127.0.0.1:28764    # vServer: Abo über den Proxy
```

Das Anthropic-SDK liest `ANTHROPIC_BASE_URL` selbst aus der Umgebung, solange
niemand ein `base_url=` übergibt — `kg/llm.py` braucht dafür also nichts, und der
Test geht durch denselben Konstruktionsweg wie der Betrieb. Über den Proxy reicht
ein Platzhalter-Schlüssel; er authentifiziert die lokale Sitzung, nicht einen
Schlüssel. Ist **keins** von beiden gesetzt, überspringt `test_stt_to_wall.py`
sich selbst, statt mit einem Authentifizierungsfehler zu scheitern.

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

5. **Vor der ersten echten Ausstellung, einmalig:** ~~den Bild-Endpunkt
   sondieren~~ — **erledigt am 2026-08-26.** `docs/dream-image-contract.md`
   ist jetzt verifiziert (drei echte Aufrufe): Request-Form bestätigt, zwei
   Abweichungen in der Response gefunden und dort dokumentiert, `kg2` folgt.
   Nicht erneut nötig.

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
Überblenddauer; Streifenhöhe; Streifenlänge (nur die letzten N Träume, Rest
bleibt in `dreams.sqlite3` und wird beim Hochsetzen wieder sichtbar);
Schreibmaschine an/aus.

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

Diese Werte stehen teils in `config2.toml`, teils als Modul-Konstanten im Code
(dort, wo sie eine Eigenschaft des Verfahrens sind und kein Tagesregler). Alle
unten genannten sind inzwischen an generiertem Material gemessen; wo ein Wert
gesetzt statt feinkalibriert ist, steht das ausdrücklich dabei — der
Unterschied wird hier nicht verwischt.

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
- `SINGLE_MENTION_BUDGET` / `SHARED_TERMS_SATURATION` (`kg2/weighting.py`,
  **20** / **25**) — **gemessen und bewusst gesetzt** (2026-08-28,
  `sim.dream_calibrate terms`, `out/calibrate-terms.txt`). Das sind die zwei
  Parameter der gleitenden Begriffsauswahl: alle geteilten Begriffe (≥2
  Nennungen) laufen immer mit, dazu höchstens `SINGLE_MENTION_BUDGET`
  Einmal-Nennungen — die jüngsten zuerst —, wobei dieses Budget linear auf 0
  schrumpft, während die Zahl der geteilten Begriffe von 0 auf
  `SHARED_TERMS_SATURATION` wächst.

  **Der Befund des Laufs ist, dass es hier wenig zu entscheiden gibt:** 36
  echte Stufe-1-Läufe über vier Graphgrößen × N ∈ {10, 20, 30} × X ∈ {15, 25,
  40}. Ab 30 Personen ist die Wahl **wirkungslos** — dort liegen 25 bzw. 49
  geteilte Begriffe vor, also über jedem geprüften X, und es kommen ohnehin
  null Einmal-Nennungen mehr durch. Ein Unterschied entsteht nur bei 3 und 10
  Personen, und dort war unter allen neun Kombinationen kein
  Qualitätsunterschied lesbar; die Sätze sind durchweg brauchbar und greifen
  nur andere Randbegriffe auf. Die Werte sind daher **gesetzt statt
  feinkalibriert**, mit der Messung als Beleg, dass das zulässig ist: N=20 ist
  die Mitte des geprüften Bereichs, X=25 die Zahl geteilter Begriffe, die der
  reale Graph bei 30 Personen erreicht — also etwa zur Tagesmitte, ab wann der
  Traum nur noch aus Geteiltem entsteht.

  Absichtlich Modul-Konstanten, nicht Config-Werte: Sie sind eine Eigenschaft
  des Verfahrens, kein Tagesregler — anders als Tool 1's `max_terms`, das
  ein Anzeigeregler ist. **Wer sie später ändert, sollte den Lauf wiederholen
  statt zu raten.**
- `RECENT_TERMS` (`kg2/weighting.py`, **5**) — **gemessen und gesetzt**
  (2026-08-29, `sim.dream_calibrate recency`, `out/calibrate-recency.txt`).
  Zweite, von der Gewichtung unabhängige Achse: ein eigener Block „Zuletzt
  gesagt" im
  Prompt, mit den `RECENT_TERMS` jüngsten Begriffen nach `created_at` — aus
  geteilten UND einmaligen Begriffen zusammen, unverändert in ihrer
  Nennungszahl. Grund: Ein Begriff, der im gerade fertigen Interview zum
  ersten Mal fällt, hat zu diesem Zeitpunkt noch kaum Nennungen und kann über
  die Gewichtung allein nicht durchdringen, obwohl die interviewte Person
  meist noch vor dem Schirm steht und die Kausalität zwischen Interview und
  Traum sichtbar sein soll. Das ist ein **Verzögerungseffekt**, keine
  strukturelle Bevorzugung des Frühen — am Endstand zählt weiterhin nur die
  Häufigkeit. Bewusst ein zweiter Block statt eines Alterungsfaktors auf die
  Zahl: Die Nennungszahl im Prompt soll ehrlich bleiben, kein Kunstwert.
- **Bewusst NICHT an Tool 1's `max_terms` gekoppelt.** Beide Werkzeuge
  folgen jetzt derselben Regel (alle geteilten, aufgefüllt mit den jüngsten
  einmaligen), aber jedes rechnet sie unabhängig aus seinen eigenen
  Konstanten. Die Wand kappt aus einem **physikalischen** Grund (Fläche,
  Schriftgröße auf dem Touchscreen); der Traum kappt aus einem **inhaltlichen**
  (das Modell soll nicht in Randnotizen ertrinken). Eine Kopplung würde einen
  Operator, der am `max_terms`-Regler wegen der Schriftgröße dreht,
  unabsichtlich ändern lassen, woraus die Bilder entstehen — und zwei
  Ausstellungstage wären nicht mehr vergleichbar. Das ist eine bewusste
  Entscheidung, keine Lücke — bitte nicht „aufräumen".

**Neuer Befund (2026-08-28): die Reihenfolge der Begriffe im Prompt hat
keinen nachweisbaren Einfluss.** Gemessen mit 6 Läufen über denselben
60-Personen-Graphen: drei Kontrollläufe mit identischem Prompt lieferten drei
deutlich verschiedene Sätze; die Läufe mit umgekehrter und mit gewürfelter
Reihenfolge unterschieden sich nicht stärker davon. Ein Shuffle wurde deshalb
bewusst **nicht** gebaut — er hätte die Reproduzierbarkeit aus Spec §5.3
gekostet (der Seed im Datensatz) ohne belegten Nutzen. Die vom Eigentümer
beobachtete Ähnlichkeit der Sätze bei 30 vs. 60 Personen hat eine andere
Ursache: von 163 Begriffen sind 114 Einmal-Nennungen, die in den Sätzen
ohnehin fast nie vorkommen; die häufigen Begriffe sind bei 30 und 60 Personen
weitgehend dieselben.

### Offene Entscheidungen

**Stand 2026-08-29:** Die Läufe für 2.–6. und 9. sind **gefahren**, die
Ergebnisse liegen als Dateien vor. Punkt 1 braucht seit dem Umbau keinen Lauf
mehr (reine Textentscheidung, siehe dort). Was jetzt noch offen ist, sind
Birks Entscheidungen an diesem Material — nicht mehr die Beschaffung des
Materials. Punkt 8 (40-Bilder-Serie) hängt unverändert an 6. und 7.

Kein Wert aus dieser Liste darf ungeprüft in den Ausstellungsbetrieb gehen.
`config2.example.toml` trägt weiterhin nur vorläufige Startwerte.

> **Kostenkorrektur (gemessen, nicht geschätzt):** Ein Bildaufruf kostet
> **≈ 0,139 USD**, nicht „ein paar Cent". Damit: Registermuster ≈ 0,56 USD
> (bezahlt), 40-Bilder-Serie **≈ 5,55 USD**, Ausstellungstag ≈ 5,55 USD.
> Beleg: `usage.cost`, siehe `docs/dream-image-contract.md`.

1. **Wortlaut der Leitfrage** (`guiding_question`) — **ENTSCHIEDEN am
   2026-08-26.** Birk hat aus den vier Kandidaten gewählt:
   **„Wie wollen wir in zehn Jahren zusammen wohnen und bauen?"** Begründung:
   der soziale Miteinander-Aspekt ist ihm wichtig. Der Wert steht so in
   `config2.example.toml`.

   Grundlage waren 16 kalt gelesene Sätze (4 Formulierungen × 3/10/30/60
   Personen) in `out/calibrate-questions.txt` (Lauf vom 2026-08-26, vor dem
   Umbau unten), erzeugt ohne Empfehlung im Output.

   **SEIT 2026-08-28 gegenstandslos für den Trauminhalt:** Die Leitfrage
   steuert nur noch die Überschrift auf dem Schirm (`kg2/server.py`), nicht
   mehr Stufe 1's Prompt (`kg2/condense.py`) — ein weiterer Vergleichslauf
   über generierte Sätze ergibt daher keinen Sinn mehr, der Befehl
   `sim.dream_calibrate questions` wurde ersatzlos entfernt. Bleibt offen: ob
   das Programm der NEW bauhaus 2026 eine Formulierung nahelegt, die in noch
   mehr Vorträgen als Fragestellung steckt (`docs/HANDOFF-2026-08-26.md`,
   Punkt D) — das ist jetzt eine reine Textentscheidung, kein Kalibrierlauf.

2. **Gleitende Begriffsauswahl** (`SINGLE_MENTION_BUDGET` /
   `SHARED_TERMS_SATURATION`, `kg2/weighting.py`) — **ENTSCHIEDEN am
   2026-08-28: 20 / 25.** Der Lauf hat gezeigt, dass die Wahl ab 30 Personen
   wirkungslos ist und darunter keinen lesbaren Qualitätsunterschied macht;
   die Werte sind deshalb gesetzt statt feinkalibriert. Vollständige
   Begründung oben bei „Kalibrierte Werte (Tool 2)", Rohdaten in
   `out/calibrate-terms.txt`.

   ```bash
   # gefahren am 2026-08-28; Wiederholung nur nötig, wenn jemand die Werte ändern will:
   export ANTHROPIC_BASE_URL=http://127.0.0.1:28764; export ANTHROPIC_API_KEY=proxy
   uv run python -m sim.dream_calibrate terms | tee out/calibrate-terms.txt
   ```

3. **Skala für Stimmung und Spannung** (`mood`/`tension`, `kg2/condense.py`)
   — **ENTSCHIEDEN am 2026-08-29: beide bleiben.**

   `mood` war bereits im ersten Lauf sauber: 5 / 3 / 3 / 1 über vier gebaute
   Extreme, dreimal reproduziert (`out/calibrate-mood.txt`).

   `tension` war im ersten Lauf **ungültig getestet** und musste nachgeholt
   werden. Der alte Testfall „eindeutig negativ, zerstritten" bestand aus
   Begriffen, die alle in dieselbe negative Richtung zeigten (Schimmel,
   Räumungsbescheide, abgesagte Versprechen) — einhellig negativ, aber gerade
   **kein** Widerspruch. Dass `tension` dort nur 2 lieferte, war korrekt; der
   Test hatte die falsche Größe konstruiert.

   Der Nachtest (`sim.dream_calibrate tension`, `out/calibrate-tension.txt`)
   entkoppelt beide Achsen in einem 2×2-Raster und beantwortet die eigentliche
   Frage — reagiert `tension` auf Widersprüchlichkeit oder läuft es nur mit
   `mood` mit?

   | | einig | zerstritten |
   |---|---|---|
   | **positiv** | A: tension 1, 1, 1 | **B: tension 5, 5, 5** |
   | **negativ** | C: tension 2, 2, 2 | D: tension 4, 2, 4 |

   - Widerspruchs-Achse: einig **1,50** → zerstritten **4,17** = **+2,67**
   - Stimmungs-Achse: positiv **3,00** → negativ **2,67** = **−0,33**

   Der Widerspruchs-Effekt ist rund **achtmal so groß** wie der
   Stimmungs-Effekt und sogar gegenläufig. Entscheidend ist Fall B, der im
   ersten Testmaterial ganz fehlte: durchweg optimistische, aber unvereinbare
   Begriffe erzeugen bei mittlerer Stimmung (`mood=3`) den **höchsten**
   `tension`-Wert überhaupt. `tension` misst also Widerspruch, nicht Stimmung.

   Zwei Einschränkungen, bewusst festgehalten: Fall D streute einmal auf 2
   statt 4 (drei von vier Fällen sind exakt reproduzierbar, einer nicht), und
   am **realen** Graphen liegen die Werte eng — `tension` 3/4/4/4 und `mood`
   3/2/3/2 über die vier Größen, über je drei Wiederholungen stabil. Die Skala
   ist korrekt, bewegt sich am echten Material aber nur in einem schmalen
   Band.

   ```bash
   # beide gefahren; Wiederholung nur nötig, wenn die Fragen im Prompt sich ändern:
   export ANTHROPIC_BASE_URL=http://127.0.0.1:28764; export ANTHROPIC_API_KEY=proxy
   uv run python -m sim.dream_calibrate mood    | tee out/calibrate-mood.txt
   uv run python -m sim.dream_calibrate tension | tee out/calibrate-tension.txt
   ```

4. **Zitate im Material** (`include_quotes`, `kg2/weighting.py::render_material`)
   — **Lauf erledigt**, Entscheidung endgültig zu bestätigen. Seit
   2026-08-28 ist der Standard OHNE Zitate (§5.1: auf der Wand sind nur die
   Begriffe sichtbar, Zitate erschienen bei 60 Personen bisher als 76 % des
   Materialblocks — für etwas im Raum Unsichtbares). Ergebnis, je Graphgröße
   ein Satzpaar mit/ohne Zitate: `out/calibrate-quotes.txt`.

   ```bash
   export ANTHROPIC_BASE_URL=http://127.0.0.1:28764; export ANTHROPIC_API_KEY=proxy
   uv run python -m sim.dream_calibrate quotes | tee out/calibrate-quotes.txt
   ```

5. **Aktualitätsblock „Zuletzt gesagt"** (`RECENT_TERMS`,
   `kg2/weighting.py::render_material`) — **ENTSCHIEDEN am 2026-08-29: bleibt,
   `RECENT_TERMS` = 5.** Der Lauf (`out/calibrate-recency.txt`, je Graphgröße
   ein Satzpaar ohne/mit Block) zeigt die Wirkung in **allen vier Größen**:
   Der Satz greift jeweils einen der fünf jüngsten Begriffe auf, der ohne den
   Block nicht vorkam — bei 30 Personen „Bürgerversammlung als Pflichttermin",
   bei 60 „Bestandsbaum auf Grundstück". Ohne Block bleiben es dieselben
   Vormittagsthemen.

   `RECENT_TERMS` = 5 ist gesetzt, nicht feinkalibriert: Der Block ist ein
   Akzent neben der Gewichtung, kein zweiter Themenblock. Wird die Zahl
   deutlich größer, konkurriert er mit der Gewichtung, die er gerade nicht
   aufheben soll.

   ```bash
   # gefahren am 2026-08-29:
   export ANTHROPIC_BASE_URL=http://127.0.0.1:28764; export ANTHROPIC_API_KEY=proxy
   uv run python -m sim.dream_calibrate recency | tee out/calibrate-recency.txt
   ```

6. **Bildregister** (`visual_register`) — **gerendert**, Wahl offen.
   Vier Bilder in `out/register1/`, plus eine 2×2-Kontaktkarte
   `out/register1/UEBERSICHT-4-register.png`. Alle PNG 1376 × 768 (16:9).

   ```bash
   uv run python -m sim.dream_register --out out/register1     # gefahren, 4 Aufrufe ≈ 0,56 USD
   ```

   **Ein maschineller Vorbehalt, keine ästhetische Wertung:** Der Prompt
   verlangt für jedes Register „keine Schrift im Bild". Eine OCR-Prüfung über
   die vier Muster findet bei **Siebdruck** schriftähnliche Zeichen (`三上`,
   Konfidenz 0,67); Aquarell, malerisch-atmosphärisch und Radierung sind
   sauber. Wer Siebdruck wählt, wählt ein Register, dessen Muster die eigene
   Regel einmal gebrochen hat — das kann Zufall eines Laufs sein, sollte aber
   vor der 40-Bilder-Serie bewusst sein.

7. **Modus des Verlaufsstreifens** — **entschieden von Birk am 2026-08-26**,
   an den gerenderten Vergleichen. Sechs Dateien in
   `out/dream-strip-comparison/` (Dateinamen tragen den Modus), dazu zwei
   gestapelte Vergleichskarten `UEBERSICHT-20-traeume.png` und
   `UEBERSICHT-40-traeume.png` — drei Modi übereinander, gleiche Breite.

   | Modus | 20 Träume | 40 Träume | Beobachtung |
   |---|---|---|---|
   | `cover` (bisheriger Standard) | 80×210 px | 31×210 px | Zuschnitt auf einen mittigen Streifen; bei 40 nahezu vollständiger Verlust von links/rechts. |
   | `aspect` | 80×45 px | 31×18 px | Kein Zuschnitt, aber beide Maße schrumpfen bis zur Unleserlichkeit; das reservierte Streifenband bleibt bei 40 größtenteils leer. |
   | `wrap` (**gewählt**) | 372×210 px | 372×210 px (pro Bild) | Kein Zuschnitt einzelner Bilder — der von Birk genannte Grund. Die Zeilenhöhe ist fest mit `overflow: hidden`; ohne Gegenmaßnahme wäre bei 40 gleichzeitigen Träumen ein Teil stillschweigend abgeschnitten worden. |

   Entscheidung: `wrap`, jetzt Standardwert in `frontend2/dream.html` und
   `frontend2/static/dream-harness.html` (`data-strip-mode`) sowie in
   `sim.dream_prerender`'s `--strip-mode`. Der `?strip_mode=`-URL-Parameter
   bleibt für Vergleichsrenderings erhalten (per `--strip-mode` beim
   Pre-Rendering und `data-strip-mode` auf der Seite wählbar).

   Zusammen mit dieser Wahl eingeführt: eine Obergrenze `strip_max` im
   Operator-UI („Streifenlänge", Default 10) — sie begrenzt den Streifen auf
   die letzten N Träume und ist genau die Gegenmaßnahme zum oben genannten
   Abschneiden bei vielen gleichzeitigen Träumen. Die Begrenzung betrifft nur
   die Anzeige; `dreams.sqlite3` bleibt vollständig, und ein Hochsetzen macht
   ältere Träume wieder sichtbar.

8. **Die 40-Bilder-Vorab-Serie** — **noch nicht gefahren**, bewusst: braucht
   Register **und** Streifenmodus aus 6. und 7., damit die 40 echten Bilder
   nicht an einer noch unfertigen Anzeige verschwendet werden.

   ```bash
   uv run python -m sim.dream_prerender --out out/dream-prerender2 --generate
   ```

   Braucht `OPENROUTER_API_KEY`, 40 Bildaufrufe — **≈ 5,55 USD** (gemessen,
   siehe Kostenkorrektur oben), ein sichtbarer, bewusster Kostenposten.

9. **Vertrag des Bild-Endpunkts** — **erledigt am 2026-08-26.**
   `docs/dream-image-contract.md` ist verifiziert: Request-Form bestätigt,
   zwei Abweichungen dokumentiert (`images` hat zwei pixelidentische Einträge;
   `message.content` ist `None`). `kg2/imagegen.py` wurde entsprechend
   nachgezogen, der Erfolgspfad war nicht betroffen.

**Vorab-Renderings, sobald 3.–5. entschieden sind:** `out/dream-prerender2/`
zeigt die Seite bei 1, 5, 20 und 40 Träumen. Der Streifen wird voll beurteilt,
nicht leer — 40 ist der Zustand um 17 Uhr.
