# Handoff: EU-Umstellung Kollektivgedächtnis + STT-Features

**Session vom 2026-08-31/09-01.** Für die nächste Session, die hier
weitermacht.

---

## Was diese Session erreicht hat

### 1. Die Station läuft vollständig über EU/Schweiz

| Stufe | Anbieter | Weg |
|---|---|---|
| LLM (Verdichtung, Wake-Word, Traumsatz) | Infomaniak Genf, Kimi K2.6 | direkt |
| Embeddings | Infomaniak, bge (3584 Dim.) | direkt |
| Bild | Black Forest Labs, `api.eu.bfl.ai` | vServer über Proxy, Windows direkt |
| STT | Infomaniak Whisper | neues Backend im fundusbot-STT-Server |

**Der Bild-Proxy** (`~/.hermes/profiles/birk/deploy/bfl-proxy/`) existiert nur,
weil auf dem vServer die nftables-Egress-Firewall uid `birk` den Zugriff auf
`bfl.ai` verwehrt und die BFL-Adressen geteilte Azure-IPs sind. Eigener
OS-User `bflproxy`, kennt genau ein Geheimnis für genau einen Zweck.
**Auf Windows ist kein Proxy nötig** — dort ist BFL direkt erreichbar
(HTTP 405 auf GET, also erreichbar).

**Nicht umgestellt:** Anthropic und OpenRouter bleiben als Rückfallwege in den
Configs erhalten (Birks Vorgabe).

**Embedding-Wechsel ist gemessen, nicht geraten:** 108 echte Merge-Paare aus
Lauf 19c, bge findet 69/108 in den Top-12, OpenAI 66/108. 12 Gewinne gegen 9
Verluste, und die Gewinne liegen bei Umschreibungen statt Wortstämmen — der
Fehlerklasse, die der Merge-Audit als Hauptursache benannt hatte.
`merge_neighbours = 12` bleibt richtig. Details:
`docs/embedding-vergleich-2026-08-31.md`.

### 2. Drei Features im STT-Server (fundusbot)

Branch **`eu-souveraen/infomaniak-whisper`**, gepusht, kein PR.
Repo ist fremd (`meredityman/fundusbot`) — `main` und
`win_fundusfantasma-dev-clean` sind unberührt und bleiben es.

* **VAD-Schwelle sichtbar und einstellbar** — als Linie im Pegel, per Regler
  zur Laufzeit änderbar (`POST /vad_threshold`).
* **Mikrofon-Gate** — der physische Schalter am Mikrofon schaltet Erkennung
  und Interview (`--mic-gate`, per Default AUS).
* **Persistenz** — eingestellte Schwellen überleben den Neustart
  (`settings/stt_runtime.json`). Rangfolge: getippt > gespeichert > `.env` >
  Vorgabe.

**Der zentrale Fallstrick, gemessen:** Das Pegelmeter zeigt **Peak**, der VAD
entscheidet über **RMS**. Der Server liefert deshalb `level_rms` zusätzlich;
die Schwellenlinien hängen am RMS-Balken. Wer sie an Peak hängt, lässt den
Operator systematisch falsch einstellen.

### 3. Interview-Signal im Core

Branch **`mikrofonschalter/interview-signal`** im
`kollektivgedaechtnis`-Repo. `POST /api/interview_switch`.

* Schalter **AUS** → Interview schließt, Grund `mic_switch`
* Schalter **AN** → Interview öffnet, **ohne Porträtfoto**
  (Birk: „Es kann ja sein, dass irgendwer nicht will, dass ein Foto von ihm
  oder ihr gemacht wird.")
* Foto danach → wird der laufenden Person **nachgetragen**
  (`portrait/late_photo`), kein neuer Besuch
* Zweites Foto → weiterhin neuer Besuch (`new_photo`) — **hier liegt die
  nächste Aufgabe**, siehe unten

Ein Knoten ohne Porträt war in theme-f **unsichtbar** (247 von 28392 Pixeln).
Jetzt `--person-blank: #6E6656` — keine neue Farbe, sondern die der ruhenden
Begriffsränder. Kein Avatar, kein Fragezeichen: die Entscheidung gegen ein
Bild soll nicht wie ein Fehler aussehen.

---

## Nächste Aufgabe

**`docs/HANDOFF-alternativ-foto-cache.md`** — Birk will, dass ein zweites Foto
während eines laufenden Interviews in einen Alternativ-Cache derselben Person
fällt statt einen neuen Besuch zu beginnen. Vorbereitet (Markierung im
Docstring von `SessionTracker.photo()`), **bewusst nicht gebaut**: ohne Cache
wäre das Foto sonst verloren.

Drei Entscheidungen brauchen Birk, bevor gebaut wird — vor allem: **wie fängt
dann der nächste Besuch an**, wenn kein Foto mehr ein Interview eröffnet?

---

## Offen, aber nicht blockierend

* **Gate-Schwelle einmessen.** Steht auf `0.0031` aus einem Persistenz-Test,
  nicht gemessen. Stiller Raum lag bei `level_rms` 0,0001. Vorgehen: Schalter
  aus → Wert ablesen, an und sprechen → Wert ablesen, Linie dazwischen.
* **Kette Schalter → STT → Core physisch durchspielen.** Beide Enden sind
  einzeln belegt, die Verbindung mit echter Hand am Schalter noch nicht.
* **ElevenLabs-Key rotieren.** Der STT-Server druckte beim Start die komplette
  `.env` im Klartext; der Schlüssel lag in Logs, die niemand als
  Geheimnisträger behandelt hat (`logs/sst_server/`, mehrere MB). Auf dem
  Branch behoben (Werte maskiert, Namen bleiben), aber alte Logs bestehen.
* **BFL-Datenschutz klären.** Laut Privacy Policy darf BFL auf Inputs und
  Outputs trainieren, Opt-out nur per Mail. Vor öffentlichen „kein
  Training"-Aussagen zu erledigen.
* **4 rote Tests** in `test_prerender.py` (Playwright-Browser fehlen) und
  `test_dream_runbook.py` — gehören zur Kamera-Ecke der Parallelsession, nicht
  zur EU-Umstellung.

---

## Wichtig für die nächste Session

**Es arbeitet parallel eine zweite Session am selben Repo.** Sie hat einen
eigenen Arbeitsbaum (`~/projekte/kg-fix`, dort ist `master` ausgecheckt) und
einen laufenden Core auf Port 8800. Während dieser Session lief `master`
dreimal weiter (Kamera, Projektion, QR-Code).

* **Nie im geteilten Arbeitsverzeichnis den Branch wechseln.** Ich habe das
  einmal getan und der anderen Session den Boden weggezogen — nichts ging
  verloren, aber der richtige Weg ist ein `git worktree`.
* **Vor jedem Push `git fetch` + Rebase auf `origin/master`**, danach die
  volle Suite. Bisher gab es keine Konflikte (ihre Arbeit liegt in
  `camera.js`/`projection.html`, meine in `session.py`/`core.py`).
* Zum Testen einen **eigenen Port und ein eigenes `data_dir`** nehmen
  (8800, 8899 sind belegt; ich habe 8853/8854 benutzt).

**Fallstricke auf der Windows-Maschine** (`tracking-laptop`, `100.94.47.6`)
stehen ausführlich in `docs/BETRIEB-stt-infomaniak.md`. Die drei wichtigsten:

1. **Nur ein STT-Server.** Ein zweiter meldet keinen Fehler, sondern erzeugt
   Stille bei ausschlagendem Pegel — er hält das Mikrofon, bekommt aber den
   Port nicht.
2. **Über SSH gestartete Server sterben mit der Verbindung.** WMI
   `Win32_Process.Create` hängt sie an den Dienst; `start /b` und
   `Start-Process -WindowStyle Hidden` reichen nicht, `schtasks` sprang gar
   nicht an.
3. **Argumentreihenfolge:** Der Backend-Name (`infomaniak-whisper`) muss ans
   **Ende** — `--audio_devices` und `--sample_rates` sind `nargs='+'` und
   schlucken ihn sonst.

Startdatei ist `C:\Users\birk\kg_stt.bat`. Die Schwellen stehen dort
**absichtlich nicht** mehr drin: ein getippter Wert schlägt den gespeicherten
und würde die Einmessung bei jedem Start überschreiben.

---

## Arbeitsweise, die sich bewährt hat

Jedes Feature wurde von Claude Code gebaut (Brief als `.task-*.md` im Repo),
danach **selbst nachgeprüft** statt dem Bericht zu glauben: Tests laufen
lassen **und** eine Mutationsprobe fahren — die Absicherung im Code
kaputtmachen und zeigen, dass genau die dafür zuständigen Tests rot werden.
Das hat in dieser Session dreimal bestätigt, dass die Tests wirklich messen,
was sie behaupten (Hysterese, Entprellung, Peak/RMS, Rangfolge,
Foto-Nachreichen).

Die Briefe liegen als `.task-*.md` in beiden Repos und sind git-ignoriert.
