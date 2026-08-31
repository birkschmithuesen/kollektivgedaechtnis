# Brief: Mobiler Public-Mirror für Kollektivgedächtnis + Kollektivtraum

Auftrag von Birk (2026-08-31). Du arbeitest im Worktree
`/home/birk/projekte/kg-mobile-mirror`, Branch `mobile-mirror`.
Sprache im Code/Kommentar: Deutsch, wie im restlichen Repo.

## Ziel

Besucher:innen der Konferenz sollen die beiden Projektionsseiten am eigenen
Handy abrufen können:

1. den Graphen aus Tool 1 („Kollektivgedächtnis")
2. das Traumbild + den Traumsatz aus Tool 2 („Kollektivtraum")

Öffentlich erreichbar über HTTPS, ausserhalb des Tailnets, ohne Login.
Nur-Lesen: von aussen darf nichts an der Station verändert werden.

## Warum eine eigene Ansicht und keine Spiegelung der Wand

Die Wand (`frontend/projection.html`) ist eine 16:9-Vollbildansicht mit
autonomer Kamerafahrt und Portrait-Nodes, die für 4 m Projektionsbreite
kalibriert ist. Am Telefon im Hochformat ist das unlesbar. Die Mobilansicht
ist deshalb eine eigene, schlanke Seite — sie benutzt dieselben Daten
(`graph.json`, Traumzustand), aber ein eigenes Layout.

## Topologie (fix, nicht neu verhandeln)

```
Ausstellungsrechner (Windows, Venue-WLAN, hinter NAT)
  Tool 1  127.0.0.1:8800   (graph.json, /media/portraits/*)
  Tool 2  127.0.0.1:8810   (/api/state,  /media/images/*)
        │
        │  mirror/uploader.py  — PUSH, alle N Sekunden, HTTPS + Bearer
        ▼
herkules 91.98.143.165  (Ubuntu 24.04, nginx 1.24 auf :80/:443, LE-Certbot)
  nginx  ──proxy_pass──▶  mirror/receiver.py  auf 127.0.0.1:8820
        │
        ▼
  Besucher:innen-Handy   https://<host>/  (Graph)  und  /traum
```

PUSH, nicht PULL: der Server kann den Ausstellungsrechner nicht erreichen
(NAT, fremdes WLAN). Der Uploader läuft dort und schiebt hoch.

## Deliverable 1 — `mirror/receiver.py` (läuft auf herkules)

FastAPI-App, Uvicorn auf `127.0.0.1:8820`. Zustand im Speicher **und** auf
Platte (`mirror-data/`), damit ein Neustart nicht die letzte Ansicht verliert.

Aufnahme-Endpunkte, alle mit `Authorization: Bearer <token>` geschützt
(Token aus `os.environ["KG_MIRROR_TOKEN"]`, niemals im Code, niemals in einer
Datei im Repo). Ohne oder mit falschem Token: 401.

- `POST /ingest/graph` — Body ist das komplette `graph.json` von Tool 1.
  Ersetzt den Bestand vollständig (es gibt kein Delta, siehe `kg/export.py`).
- `POST /ingest/dream` — Body ist der Traumzustand (`/api/state` von Tool 2).
- `POST /ingest/media/{kind}/{name}` — `kind` ∈ {`portraits`, `images`},
  Body ist die Bilddatei. `name` MUSS validiert werden: nur `[A-Za-z0-9._-]+`,
  kein `/`, kein `..`, sonst 400. Ein Pfad-Ausbruch hier wäre ein
  Schreibzugriff auf fremde Dateien.

Öffentliche Endpunkte, **ohne** Token, alle nur lesend:

- `GET /` → die Graph-Seite (mobil)
- `GET /traum` → die Traum-Seite (mobil)
- `GET /api/graph` → der letzte empfangene Graph
- `GET /api/dream` → der letzte empfangene Traumzustand
- `GET /media/portraits/{name}`, `GET /media/images/{name}` → die Bilder
- `GET /events` → SSE, schiebt `graph`- und `dream`-Ereignisse an offene
  Seiten, sobald eine Aufnahme eintrifft. Muster und Keep-Alive-Kommentar
  genau wie in `kg/server.py` / `kg2/server.py` (15 s), damit Proxys die
  Verbindung nicht zumachen.
- `GET /healthz` → `{"ok": true, "graph_age_s": …, "dream_age_s": …}`

Wenn noch nie etwas eingegangen ist: die Seiten liefern eine ruhige
Wartemeldung („Die Station ist gerade nicht verbunden"), keinen Fehler und
keine leere weisse Seite.

**Alter sichtbar machen:** liegt die letzte Aufnahme länger als 90 Sekunden
zurück, zeigen beide Seiten dezent an, dass der Stand nicht mehr live ist.
Lieber ein ehrlicher alter Stand als eine Seite, die Aktualität vortäuscht.

## Deliverable 2 — `mirror/uploader.py` (läuft auf dem Ausstellungsrechner)

Ein einzelnes Python-Skript, stdlib + `httpx` (ist über `pyproject.toml`
schon da). Muss auf Windows laufen. Konfiguration über Umgebungsvariablen:
`KG_MIRROR_URL`, `KG_MIRROR_TOKEN`, optional `KG_TOOL1_URL`
(Vorgabe `http://127.0.0.1:8800`), `KG_TOOL2_URL` (Vorgabe
`http://127.0.0.1:8810`), `KG_MIRROR_INTERVAL` (Vorgabe 3.0 s).

Schleife:

1. `GET {tool1}/graph.json` → wenn der Inhalt sich seit dem letzten Mal
   geändert hat (Hash über den serialisierten Körper), hochladen.
2. `GET {tool2}/api/state` → dito.
3. Aus beiden Antworten die referenzierten Bild-Dateinamen sammeln
   (`portrait`-Feld der Personen-Nodes; Bildpfade im Traumzustand). Jede
   Datei, die noch nie erfolgreich hochgeladen wurde, holen und hochladen.
   Erfolgreiche Uploads in `mirror-uploaded.json` neben dem Skript merken,
   damit ein Neustart nicht alles noch einmal schickt.

Robustheit ist hier die eigentliche Anforderung — das Ding läuft einen Tag
lang unbeaufsichtigt in einem fremden WLAN:

- **Kein Netzfehler darf das Skript beenden.** Jede Netz-Operation in
  `try/except Exception`, Fehler auf stderr protokollieren, weiterlaufen.
- Ist Tool 1 oder Tool 2 nicht erreichbar, wird der jeweils andere trotzdem
  weiter hochgeladen. Die beiden Werkzeuge fallen unabhängig voneinander aus
  (Spec §9) — der Uploader darf diese Unabhängigkeit nicht aufheben.
- Timeouts überall (connect 5 s, read 20 s), sonst hängt ein halboffenes
  WLAN die Schleife auf.
- Rückwärts-Abstand nach wiederholten Fehlern (max. 60 s), damit ein toter
  Server nicht dauerhaft Bandbreite frisst.
- Ausgabe beim Start: welche URLs, welches Intervall — aber **niemals das
  Token**, weder beim Start noch in einer Fehlermeldung.

## Deliverable 3 — die beiden Mobilseiten

Neu unter `mirror/web/`. Eigenständig, sie dürfen NICHT aus `frontend/` oder
`frontend2/` importieren — die Wand wird gerade parallel weiterentwickelt,
eine gemeinsame Datei würde beide Baustellen verkoppeln. Vendor-Bibliotheken
(Cytoscape) aus `frontend/static/vendor/` kopieren, nicht verlinken.

Gemeinsam für beide Seiten:

- `<meta name="viewport" content="width=device-width, initial-scale=1,
  viewport-fit=cover">`
- Hochformat ist der Normalfall, Querformat muss ebenfalls funktionieren.
- `env(safe-area-inset-*)` beachten (iPhone-Notch).
- Dunkler Hintergrund wie die Wand; die Seite wird in einem abgedunkelten
  Raum aufs Handy geholt.
- Bedienelemente mindestens 44 × 44 px.
- Kein horizontales Scrollen, keine festen Pixelbreiten, keine Tabellen.
- Ein dezenter Wechsel zwischen beiden Ansichten (zwei Reiter oben).
- Verbindung über `EventSource('/events')`; bei Abbruch nach ein paar
  Sekunden neu verbinden (der Browser tut das teils selbst, aber nicht
  zuverlässig nach einem Netzwechsel WLAN→Mobilfunk).

**Graph-Seite (`/`):** Cytoscape wie an der Wand, aber:
- keine autonome Kamerafahrt — am Handy führt die Person selbst,
- Pinch-Zoom und Wischen an, Doppeltipp = alles einpassen,
- Tipp auf einen Personen-Node zeigt Portrait + Zitat als Blatt von unten
  (Muster: `frontend/static/quote-overlay.js` als Vorlage lesen, aber eigene
  mobile Umsetzung schreiben),
- Begriffs-Beschriftungen müssen auf einem 390 px breiten Schirm lesbar sein;
  weniger Begriffe gleichzeitig als an der Wand ist richtig, nicht falsch.

**Traum-Seite (`/traum`):** Bild gross, Traumsatz darunter gut lesbar,
darunter ein waagerecht wischbarer Streifen der letzten Träume; Tipp öffnet
das jeweilige Bild gross. Kein Zuschneiden einzelner Bilder (Birks
Entscheidung 2026-08-26, siehe `frontend2/dream.html`).

## Deliverable 4 — Betrieb

- `mirror/README.md`: Start beider Teile, die Umgebungsvariablen, wie man
  prüft ob die Kette steht (mit `curl`-Kommandos, die man tatsächlich
  eintippen kann), und die Fehlerbilder.
- `mirror/kg-mirror.service` — eine `systemd --user`-Unit für herkules
  (User `fundusbot`), die den Empfänger startet und nach einem Absturz
  wieder hochfährt. `EnvironmentFile=%h/.config/kg-mirror.env` für das
  Token. `LogLevelMax=notice` setzen (auf diesen Maschinen füllen
  gesprächige Units die Logs).
- `mirror/nginx-kg-mirror.conf` — Vhost-Vorlage, gebaut wie das bestehende
  `/etc/nginx/sites-enabled/herkules` auf dieser Maschine: `:80` leitet auf
  HTTPS um mit einer Ausnahme für `/.well-known`, `:443` mit den
  Let's-Encrypt-Pfaden und `proxy_pass http://127.0.0.1:8820`. Zusätzlich
  für SSE zwingend: `proxy_buffering off;`, `proxy_read_timeout 3600s;`,
  `proxy_set_header Connection "";` und `proxy_http_version 1.1;` — ohne
  das puffert nginx den Ereignisstrom und die Seite bleibt stehen.
  Der Servername steht als `__HOST__` in der Vorlage.

## Tests

`tests/test_mirror.py`, im Stil der vorhandenen Tests, über FastAPIs
`TestClient` — kein Netz, keine Schlafbefehle:

1. Aufnahme ohne Token → 401; mit falschem Token → 401.
2. Graph aufnehmen, dann `GET /api/graph` liefert genau das Aufgenommene.
3. `POST /ingest/media/portraits/../../etc/passwd` → 400, und es wird
   nachweislich nichts ausserhalb von `mirror-data/` geschrieben.
4. Vor der ersten Aufnahme liefert `/api/graph` einen leeren, aber gültigen
   Graphen (`nodes`/`edges` vorhanden), keinen 500er.
5. `/healthz` meldet das Alter der letzten Aufnahme.
6. Uploader: die Änderungserkennung schickt unveränderte Daten kein zweites
   Mal (Funktion isoliert testen, ohne echten Netzverkehr).

## Randbedingungen

- Python 3.12 auf herkules, Windows auf dem Ausstellungsrechner.
- **Keine Geheimnisse im Repo**, in keiner Beispieldatei, in keinem Test.
  Das Token kommt ausschliesslich aus der Prozess-Umgebung.
- Der Empfänger darf **keinen** Schreib-Endpunkt Richtung Station haben.
  Von aussen ist alles lesend — das ist die Sicherheitsgrenze dieses Aufbaus,
  weil es bewusst keinen Login gibt.
- `frontend/`, `frontend2/`, `kg/`, `kg2/` NICHT verändern. An `frontend/`
  arbeitet gerade eine parallele Session. Deine Arbeit liegt vollständig
  unter `mirror/` und `tests/test_mirror.py`.
- Git: nur `git add` mit ausdrücklichen Pfaden, niemals `git add -A`,
  niemals `git stash`/`git checkout --`/`git restore`/`git clean`.
  Commits auf `mobile-mirror`, deutsche Commit-Titel wie im Repo üblich.

## Prüfen, bevor du fertig meldest

Die Testsuite im VORDERGRUND laufen lassen und die echten Zahlen berichten
(`N passed`). Ein Lauf, den du in den Hintergrund schickst und nicht
abwartest, zählt nicht als Prüfung — nach deinem Zug gibt es kein Später.
Zusätzlich den Empfänger tatsächlich starten, mit `curl` eine Aufnahme
machen und `/api/graph` gegenlesen; das Ergebnis dieses Laufs in die
Abschlussmeldung.
