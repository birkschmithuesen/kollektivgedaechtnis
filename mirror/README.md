# Mobiler Public-Mirror

Besucherinnen und Besucher der Konferenz rufen die beiden Projektionsseiten am
eigenen Telefon ab: den Graphen aus Tool 1 und das Traumbild samt Traumsatz aus
Tool 2. Öffentlich über HTTPS, ausserhalb des Tailnets, ohne Login, **nur
lesend** — von aussen lässt sich an der Station nichts verändern.

```
Ausstellungsrechner (Windows, Venue-WLAN, hinter NAT)
  Tool 1  127.0.0.1:8800   (graph.json, /media/portraits/*)
  Tool 2  127.0.0.1:8810   (/api/state,  /media/images/*)
        │
        │  mirror/uploader.py  — PUSH, alle 3 s, HTTPS + Bearer
        ▼
herkules 91.98.143.165  (Ubuntu 24.04, nginx auf :80/:443, LE-Certbot)
  nginx  ──proxy_pass──▶  mirror/receiver.py  auf 127.0.0.1:8820
        │
        ▼
  Besucher:innen-Handy   https://<host>/   (Startseite)
```

| Pfad | Was dort steht |
|---|---|
| `/` | Startseite: Begrüssung, zwei Knöpfe, kurzer Datenschutzabsatz. Statisch. |
| `/graph` | die Graph-Ansicht |
| `/traum` | Traumbild, Traumsatz und der Streifen der letzten Träume |
| `/transparenz` | „Was wo läuft" — welcher Schritt bei welchem Anbieter liegt. Statisch. |

Startseite und Transparenzseite hängen an keinem Zustand: sie stehen
vollständig da, auch wenn nie eine Aufnahme eingegangen ist.

PUSH, nicht PULL: der Server kann den Ausstellungsrechner nicht erreichen
(NAT, fremdes WLAN). Der Uploader läuft dort und schiebt hoch.

## Das Token

Ein einziges gemeinsames Geheimnis, in **beiden** Umgebungen dieselbe
Zeichenkette. Es steht nirgends im Repo, in keiner Beispieldatei und in keiner
Logzeile — es kommt ausschliesslich aus der Prozessumgebung.

Erzeugen (einmal, auf irgendeiner der beiden Maschinen):

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Auf herkules in `~/.config/kg-mirror.env` legen (`chmod 600`), auf dem
Ausstellungsrechner als Umgebungsvariable des Uploader-Fensters setzen.

Ohne gesetztes Token startet der Empfänger gar nicht erst; wird die Unit ohne
`EnvironmentFile` gestartet, beantwortet er jede Aufnahme mit 401 und zeigt
weiter den letzten Stand von der Platte.

## Teil 1 — der Empfänger auf herkules

| Variable | Vorgabe | Bedeutung |
|---|---|---|
| `KG_MIRROR_TOKEN` | — | **Pflicht.** Das gemeinsame Geheimnis. |
| `KG_MIRROR_HOST` | `127.0.0.1` | Nur lokal binden; nach aussen geht nginx. |
| `KG_MIRROR_PORT` | `8820` | |
| `KG_MIRROR_DATA` | `mirror-data` | Wohin der Stand auf Platte geschrieben wird. |

```bash
# Von Hand, zum Ausprobieren:
cd ~/kollektivgedaechtnis
KG_MIRROR_TOKEN=… .venv/bin/python -m mirror.receiver

# Im Betrieb:
cp mirror/kg-mirror.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now kg-mirror
loginctl enable-linger fundusbot     # läuft weiter, wenn niemand angemeldet ist
journalctl --user -u kg-mirror -f
```

Der vhost:

```bash
sed 's/__HOST__/spiegel.example.org/g' mirror/nginx-kg-mirror.conf \
  | sudo tee /etc/nginx/sites-available/kg-mirror
sudo ln -s ../sites-available/kg-mirror /etc/nginx/sites-enabled/kg-mirror
sudo certbot certonly --webroot -w /var/www/html -d spiegel.example.org
sudo nginx -t && sudo systemctl reload nginx
```

Die vier SSE-Zeilen in der Vorlage (`proxy_buffering off`,
`proxy_read_timeout 3600s`, `proxy_set_header Connection ""`,
`proxy_http_version 1.1`) sind nicht optional — siehe „Fehlerbilder".

## Teil 2 — der Uploader auf dem Ausstellungsrechner

| Variable | Vorgabe | Bedeutung |
|---|---|---|
| `KG_MIRROR_URL` | — | **Pflicht.** `https://spiegel.example.org` |
| `KG_MIRROR_TOKEN` | — | **Pflicht.** Dasselbe wie oben. |
| `KG_TOOL1_URL` | `http://127.0.0.1:8800` | |
| `KG_TOOL2_URL` | `http://127.0.0.1:8810` | |
| `KG_MIRROR_INTERVAL` | `3.0` | Sekunden zwischen zwei Runden. |

### Auf dem MacBook (seit 2026-09-01 die Ausstellungsmaschine)

```bash
scripts/token-verteilen.sh datei ~/.kg-mirror-token   # einmalig, holt von herkules
./scripts/spiegel-start-mac.sh --pruefen              # nachsehen, sendet nichts
./scripts/spiegel-start-mac.sh                        # senden
```

Das Skript setzt die fünf Variablen selbst und liest das Token aus
`~/.kg-mirror-token` — dieselbe Stelle wie `%USERPROFILE%\.kg-mirror-token`
auf dem Windows-Rechner, nur mit Unix-Rechten. Beide Formen der Datei werden
akzeptiert, mit und ohne `KG_MIRROR_TOKEN=`-Präfix.

🔴 Es läuft **nicht** in `scripts/start-station.sh` mit. Der Sammelstart
startet, was im Haus läuft; dieses Skript schiebt Interviewdaten ins
öffentliche Netz, und das ist eine Entscheidung. `start-station.sh` weist am
Ende auf den eigenen Knopf hin.

### Auf dem Windows-Rechner

Doppelklick auf `mirror/spiegel-start.bat`, oder von Hand in der PowerShell:

```powershell
cd C:\kollektivgedaechtnis
$env:KG_MIRROR_URL   = "https://spiegel.example.org"
$env:KG_MIRROR_TOKEN = "…"
.venv\Scripts\python.exe -m mirror.uploader
```

Beim Start schreibt er die URLs, das Intervall und den Pfad seines
Gedächtnisses — **nie** das Token. Er läuft, bis das Fenster geschlossen wird;
kein Netzfehler beendet ihn.

`mirror/mirror-uploaded.json` merkt sich, welche Bilder schon oben liegen. Wer
alle Bilder erneut hochladen will (neuer Server, geleertes `mirror-data/`),
löscht diese Datei.

## Prüfen, ob die Kette steht

Der Reihe nach; jeder Schritt setzt den vorigen voraus. `HOST` und `TOKEN`
einmal setzen:

```bash
HOST=https://spiegel.example.org
TOKEN=…
```

**1. Läuft der Empfänger überhaupt, und wie alt ist sein Stand?**

```bash
curl -s $HOST/healthz
# {"ok":true,"graph_age_s":2.4,"dream_age_s":9.1,"stale_after_s":90.0}
```

`null` heisst: seit dem Start des Dienstes ist dafür nichts eingegangen.
Zahlen über 90 heissen: der Uploader liefert nicht mehr (die Seiten sagen es
den Besucherinnen dann auch).

**2. Kommt der Graph an?**

```bash
curl -s $HOST/api/graph | python -c "import json,sys; g=json.load(sys.stdin); print(len(g['nodes']),'Knoten,',len(g['edges']),'Kanten')"
# 223 Knoten, 267 Kanten
```

**3. Ist die Aufnahme wirklich zu?** (muss zweimal 401 ergeben)

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST $HOST/ingest/graph -d '{}'
curl -s -o /dev/null -w "%{http_code}\n" -X POST $HOST/ingest/graph -H "Authorization: Bearer falsch" -d '{}'
```

**4. Von Hand etwas aufnehmen und gegenlesen** (ersetzt den Stand vollständig,
also nur, wenn gerade keine Ausstellung läuft):

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST $HOST/ingest/graph \
  -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  --data-binary @sim/data/graph-19c.json
# 200
curl -s $HOST/api/graph | python -c "import json,sys; print(len(json.load(sys.stdin)['nodes']),'Knoten')"
# 223 Knoten
```

**5. Läuft der Ereignisstrom durch nginx durch?** Muss innerhalb einer Sekunde
zwei `data:`-Zeilen ausgeben und dann offen bleiben:

```bash
timeout 20 curl -s -N $HOST/events | cut -c1-60
# data: {"type": "graph", "graph": {"version": 1, "generat
# data: {"type": "dream", "dream": {"current": null, "hist
# (danach alle 15 s: ": keep-alive")
```

**6. Kommen die Bilder mit?**

```bash
NAME=$(curl -s $HOST/api/graph | python -c "
import json,sys
g=json.load(sys.stdin)
print(next((n['portrait'].rsplit('/',1)[-1] for n in g['nodes'] if n.get('portrait')), ''))")
echo "${NAME:-noch kein Portrait im Graphen}"
curl -s -o /dev/null -w "%{http_code} %{content_type} %{size_download}\n" \
  $HOST/media/portraits/$NAME
# 200 image/jpeg 29505
```

**7. Und die Seiten selbst** — am besten wirklich mit einem Telefon, sonst:

```bash
for p in / /graph /traum /transparenz /static/graph.js /static/vendor/cytoscape.min.js; do
  curl -s -o /dev/null -w "$p -> %{http_code}\n" $HOST$p
done
```

## 🔴 Vor der Veröffentlichung: der Wortlaut

Startseite (`mirror/web/start.html`, Abschnitt „Wo diese Daten verarbeitet
werden") und `mirror/web/transparenz.html` machen Zusagen über den Umgang mit
personenbezogenen Daten Dritter. Sie gehen erst online, wenn Birk den Wortlaut
freigegeben hat, und der Wortlaut wird **am Ausstellungstag gegen den
tatsächlich laufenden Stand geprüft** — der Text steht im Präsens und
beschreibt damit einen Zustand, keinen Vorsatz.

Die vier Dienste stehen in `transparenz.html` an genau einer Stelle, zwischen
`==== Die Dienste ====` und `==== Ende der Dienste ====`. Ändert sich der
Stack, ändert sich dort eine Zeile — sonst nichts. Was ungeklärt ist, steht
bewusst nicht auf der Seite; der Abschnitt „Was dabei offen bleibt" wird nicht
gekürzt.

## Fehlerbilder

**Die Seite steht still, aber `/healthz` meldet ein kleines Alter.**
nginx puffert den Ereignisstrom. Die vier `proxy_*`-Zeilen aus der
vhost-Vorlage fehlen oder stehen im falschen `location`-Block. Prüfen mit
Schritt 5 oben: kommen die beiden `data:`-Zeilen erst nach dem Abbruch (oder
gar nicht), ist es der Puffer. Die Seiten holen sich zusätzlich alle 25 s den
Stand über `/api/…`, laufen also weiter — aber jede Änderung dauert dann bis
zu einer halben Minute statt einer Sekunde.

**Alle Seiten zeigen „Die Station ist gerade nicht verbunden".**
Es ist noch nie etwas eingegangen (`/healthz` meldet `null`). Entweder läuft
der Uploader nicht, oder er kommt nicht durch. Auf dem Ausstellungsrechner in
sein Fenster sehen: dort steht je Runde eine Zeile, warum.

**Der gelbe Streifen „Kein Kontakt zur Station seit …".**
Der Stand ist älter als 90 Sekunden. Das ist Absicht und kein Defekt: die
Seite zeigt weiter, was sie hat, sagt aber dazu, dass es nicht mehr live ist.
Ursachen in der Reihenfolge ihrer Häufigkeit: das Venue-WLAN, ein
geschlossenes Uploader-Fenster, ein abgestürztes Tool auf der Station.

**Der Uploader meldet dauernd `Tool 2: ConnectError`, Tool 1 läuft.**
Genau richtig so. Die beiden Werkzeuge fallen unabhängig voneinander aus
(Spec §9); der Graph geht weiter hoch, die Traumseite friert auf ihrem letzten
Stand ein und sagt das an. Nichts tun ausser Tool 2 wieder starten.

**Bilder fehlen, Text ist da.**
Der Uploader schickt erst den Zustand und dann die Dateien; dazwischen liegen
ein paar Sekunden. Bleibt es dabei, steht der Grund in seinem Fenster
(`[uploader] portraits/xyz.jpg: …`). Ein 404 auf der Station heisst meist: das
Portrait wird gerade noch zugeschnitten, die nächste Runde holt es.

**Alles antwortet mit 401.**
Die beiden Token stimmen nicht überein. Nicht in Logs suchen — sie stehen dort
nicht. Auf beiden Seiten neu setzen.

**`systemctl --user` sagt „Failed to connect to bus".**
`loginctl enable-linger fundusbot` wurde vergessen, oder die Session ist ohne
`XDG_RUNTIME_DIR` (`sudo -i` statt `ssh fundusbot@…`).

## Was hier NICHT passieren kann

Der Empfänger hat keinen Endpunkt, der etwas Richtung Station schickt — alles
Öffentliche ist lesend, und das ist die Sicherheitsgrenze dieses Aufbaus,
weil es bewusst keinen Login gibt. `tests/test_mirror.py` prüft das als
Eigenschaft: jede schreibende Route muss unter `/ingest/` liegen und damit
hinter dem Token.

Dateinamen aus dem Netz werden an genau einer Stelle zu Pfaden
(`_pruefe_namen`), beim Schreiben wie beim Lesen: nur `[A-Za-z0-9._-]+`,
sonst 400.
