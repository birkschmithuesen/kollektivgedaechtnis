# Betrieb der Station auf dem Ausstellungsrechner

**Für eine neue Session, die den Windows-Laptop betreut.** Diese Datei
beschreibt die *laufende Installation*, nicht die Entwicklung. Wer am Code
arbeitet, liest `docs/operations.md` (Betriebshandbuch) und den jüngsten
`docs/HANDOFF-*.md`.

Stand: 2026-08-31. Aufgebaut am 2026-08-29/30 in einer langen Session.

---

## Die Maschine

| | |
|---|---|
| Tailscale-Name | `tracking-laptop` |
| IP | `100.94.47.6` |
| Windows-Hostname | `DESKTOP-QTVMC5L` |
| Zugang | **nur SSH**, RDP ist zu |
| **Arbeitsbenutzer** | **`SF-Tracking`** — hier anmelden, hier arbeiten |
| Zweitbenutzer | `birk` — hält nur den Quelltext, sonst nichts |
| Sprache | **Deutsch** — siehe Fallstricke |

```bash
ssh -o BatchMode=yes SF-Tracking@100.94.47.6 "<cmd.exe-Befehl>"
```

### 🔴 Immer als `SF-Tracking` arbeiten, nicht als `birk`

Beide SSH-Zugänge funktionieren, und genau das ist die Falle: als `birk`
angemeldet läuft alles scheinbar, aber man arbeitet in einem Profil, in dem
Birk nie sitzt. Gemessen am 2026-09-01:

| | `SF-Tracking` | `birk` |
|---|---|---|
| Desktop-Verknüpfungen START/STOP | **ja** | nein |
| Claude-Login (`.claude/.credentials.json`) | **ja** | nein |
| Startdatei `kg-start/kollektivtraum.bat` | **ja** | ja (zweite Kopie!) |
| Token `.kg-mirror-token` | ja | ja |

Der Mensch sitzt als **`SF-Tracking`** an der Kiste. Wer eine Verknüpfung,
eine Startdatei oder eine Einstellung unter `birk` ablegt, legt sie dorthin,
wo sie am Ausstellungstag **niemand sieht** — und es fällt erst auf, wenn
etwas fehlt. Genau das ist am 2026-08-31 passiert und hat Zeit gekostet.

**Der Quelltext liegt dagegen unter `C:\Users\birk\`** (`kollektivgedaechtnis`,
`kg-spiegel`, `fundusbot`) und wird von dort auch als `SF-Tracking` benutzt —
Lesen und Schreiben sind geprüft, es gibt kein Rechteproblem. Deshalb steht
in den Startdateien bewusst der feste Pfad `C:\Users\birk\...` für den Code
und `%USERPROFILE%` für alles Benutzereigene (Token, Logs, Profile).

Faustregel:
- **Code, venv, Repos** → `C:\Users\birk\...` (fest verdrahtet, einmal da)
- **Token, Logs, Verknüpfungen, alles Sichtbare** → `%USERPROFILE%`, also
  `SF-Tracking`

Pfade mit doppelten Backslashes escapen; `scp`-Ziel für Code
`SF-Tracking@100.94.47.6:C:/Users/birk/`, für Benutzereigenes
`SF-Tracking@100.94.47.6:C:/Users/SF-Tracking/`.

Der zweite Laptop im Tailnet, `licht-laptop` (`100.121.5.39`), ist für den
**Kollektivtraum** vorgesehen. Dort ist SSH noch **nicht** offen — er
antwortet auf Ping, Port 22 ist zu. Muss vor einer Nutzung eingerichtet werden.

---

## Die vier Dienste

Alle laufen als **Scheduled Tasks unter SYSTEM**, Autostart `ONSTART`, also
reboot-fest und ohne angemeldete Sitzung.

| Task | Port | Was |
|---|---|---|
| `KgProxy` | 127.0.0.1:28764 | Anthropic-Abo-Proxy (nur lokal!) |
| `KgStt` | 0.0.0.0:5051 | Spracherkennung (ElevenLabs Scribe, deutsch) |
| `KgCore` | 0.0.0.0:8800 | Tool 1 — Interview, Graph, Wand |
| `KgDream` | 0.0.0.0:8810 | Tool 2 — Verdichtung, Bild, Traumwand |

**Startreihenfolge ist nicht beliebig:** Proxy → STT → Core → Dream. Der Core
verbindet sich beim Start mit Proxy und STT; startet er gegen einen toten
Proxy, sieht er funktionsfähig aus, liefert aber **stumm keine Begriffe**.

```bash
ssh SF-Tracking@100.94.47.6 "schtasks /Run /TN KgProxy"   # dann 10 s warten
ssh SF-Tracking@100.94.47.6 "schtasks /Run /TN KgStt"     # dann 15 s
ssh SF-Tracking@100.94.47.6 "schtasks /Run /TN KgCore"    # dann 25 s
ssh SF-Tracking@100.94.47.6 "schtasks /Run /TN KgDream"
```

Beenden: `schtasks /End /TN <name>`.

### Adressen (nur im Tailnet erreichbar)

- Wand (Graph): `http://100.94.47.6:8800/projection`
- Wand mit Touch: `http://100.94.47.6:8800/projection?touch=1`
- Operator Tool 1: `http://100.94.47.6:8800/operator`
- Testbild: `http://100.94.47.6:8800/testpattern`
- Traumwand: `http://100.94.47.6:8810/dream`
- Operator Tool 2: `http://100.94.47.6:8810/operator`
- STT-Operator (An/Aus, Pegel, Gerätewahl): `http://100.94.47.6:5051/operator`

**Chromium/Brave/Chrome benutzen, nicht Firefox** — nur Chromium ist geprüft.

### Logs

`C:\Users\birk\kg_proxy.log`, `kg_stt.log`, `kg_core.log`, `kg_dream.log`.

🔴 **`kg_stt.log` enthält den ElevenLabs-Key** (`args.py` druckt beim Start
die ganze `.env`) **und die Interview-Transkripte im Klartext**. Nie roh
ausgeben, nie weitergeben. Beim Lesen filtern:

```bash
ssh SF-Tracking@100.94.47.6 "powershell -NoProfile -Command \"Get-Content C:\Users\birk\kg_stt.log -Tail 20\"" | sed -E "s/sk_[A-Za-z0-9]+/<KEY>/g"
```

`kg_core.log` enthält den Telegram-Bot-Token in den URLs → mit
`s/bot[0-9]+:[A-Za-z0-9_-]+/bot<TOKEN>/` filtern.

---

## Die häufigsten Störungen (alle real vorgekommen)

### 1. Rechner geht in den Standby — die häufigste Ursache

Am 2026-08-30 **dreimal** passiert, zweimal mitten im Betrieb, einmal mitten
in einem Deployment. Belegt: `PowerEvent` im Anwendungsprotokoll um 18:05:45,
Task-Ergebnis `-2147023829` (ERROR_PROCESS_ABORTED) bei allen drei Diensten
gleichzeitig, kein Traceback.

**Erkennung:** kein Ping, kein SSH, alle Ports tot.
**Nicht verwechseln mit** einem Funkloch: Der Laptop hing zeitweise am
mobilen Hotspot; dann ist er ebenfalls unerreichbar, die Dienste **laufen aber
weiter** und sind nach der Rückkehr sofort wieder da. Ein Funkloch tötet keine
Prozesse.

**Dauerhafte Abhilfe liegt beim Menschen:** Energieoptionen → Energiesparmodus
„Nie", Zuklappen „Nichts unternehmen". Kein Skript kann eine schlafende
Maschine wecken. Stand 2026-08-31 **noch offen**.

Nach dem Aufwachen: Dienste prüfen, ggf. in der obigen Reihenfolge starten.

### 2. STT kommt pausiert hoch

Der STT-Server startet **immer** im Zustand `paused`. Ein laufender Prozess,
der nichts erkennt — die tückischste Halbstörung, weil alles gesund aussieht.

```bash
curl -X POST http://100.94.47.6:5051/resume
curl http://100.94.47.6:5051/status     # muss "running" sagen
```

Nach **jedem** Neustart von `KgStt` prüfen.

### 3. Abo-Token abgelaufen → Personen erscheinen, Begriffe nicht

Das OAuth-Token gilt **8 Stunden**. Läuft es ab, schlägt die Extraktion mit
`auth_error` fehl — Fotos landen weiter als Personenknoten auf der Wand, aber
es wachsen keine Begriffe. Im `kg_core.log` steht dann
`llm attempt 1/2 failed: ... auth_error`.

Der Proxy erneuert seit 2026-08-30 **selbst** (Thread im Launcher, prüft alle
5 Min, erneuert unter 15 Min Restlaufzeit). Ist es trotzdem abgelaufen, hilft
nur ein **Login durch den Menschen** am Rechner als `SF-Tracking`:

```
claude
```

Danach zieht der Proxy die neue Datei automatisch, **kein Neustart nötig**.

Restlaufzeit prüfen:
```bash
ssh SF-Tracking@100.94.47.6 "powershell -NoProfile -Command \"\$p='C:\Users\SF-Tracking\.claude\.credentials.json'; \$d=Get-Content \$p -Raw|ConvertFrom-Json; \$e=[double]\$d.claudeAiOauth.expiresAt/1000; 'rest_h='+[math]::Round((\$e-[DateTimeOffset]::UtcNow.ToUnixTimeSeconds())/3600,2)\""
```

### 4. Wand lädt, ist gestylt und bleibt LEER

Windows löst MIME-Typen über die Registry auf, wo `.js` auf `text/plain`
steht. Chromium lehnt ES-Module dann strikt ab — ohne fehlende Datei, ohne
Traceback, ohne fehlgeschlagene Anfrage. Behoben in `kg/server.py` **und**
`kg2/server.py` (`mimetypes.add_type`). Tritt auf Linux nie auf.

Prüfen:
```bash
curl -s -o /dev/null -w "%{content_type}\n" http://100.94.47.6:8800/static/projection.js
# muss text/javascript sein, nicht text/plain
```

Tritt es wieder auf: Ein neuer Serverprozess ohne diese Registrierung.

### 5. Veralteter Frontend-Stand

Kommt vor, wenn ein Deployment nur den letzten Commit überträgt, während
lokal noch Ungespeichertes liegt. Symptom: Server liefert neues Datenformat,
altes JavaScript erwartet altes → leere Wand trotz korrekter `graph.json`.

**Vor jedem Deployment `git status` prüfen.** Stand vergleichen:
```bash
ssh SF-Tracking@100.94.47.6 "cd C:\Users\birk\kollektivgedaechtnis && git log --oneline -1"
```

---

## Deployment

Beide Repos sind **privat**; auf dem Windows-Rechner liegt bewusst **kein
Token**. Übertragung deshalb per Git-Bundle:

```bash
cd ~/projekte/kollektivgedaechtnis
git bundle create /tmp/kg.bundle master
scp /tmp/kg.bundle SF-Tracking@100.94.47.6:C:/Users/birk/kg.bundle
ssh SF-Tracking@100.94.47.6 "cd C:\Users\birk\kollektivgedaechtnis && git fetch C:\Users\birk\kg.bundle master:refs/remotes/bundle/master --force && git reset --hard refs/remotes/bundle/master"
```

Danach `KgCore` (und bei Tool-2-Änderungen `KgDream`) neu starten.

**Vorsicht:** `git reset --hard` verwirft lokale Änderungen auf dem
Ausstellungsrechner. Die `config.toml` und `config2.toml` dort sind **nicht**
im Repo und überleben das — aber prüfen, ob sie noch zum neuen Code passen.

---

## Geheimnisse

`C:\Users\birk\kg_secrets.bat` (Rechte auf birk/Admin/SYSTEM beschränkt) hält
`OPENROUTER_API_KEY` und `KG_TELEGRAM_TOKEN`. Wird von `kg_core.bat` und
`kg_dream.bat` geladen.

**Nicht** über Benutzervariablen (`setx`) setzen: Die Dienste laufen als
SYSTEM und sehen die Variablen von `birk` nicht. Das war am 2026-08-30 die
Ursache dafür, dass der Telegram-Bot trotz gesetztem Token nicht ansprang.

Der ElevenLabs-Key liegt in `C:\Users\birk\fundusbot\.env`.

---

## Was wo läuft

- **Tool 1 + 2** (`kollektivgedaechtnis`): `C:\Users\birk\kollektivgedaechtnis`,
  venv `.venv`, Python 3.12.7
- **STT-Server** (`meredityman/fundusbot`, Branch
  `win_fundusfantasma-dev-clean`): `C:\Users\birk\fundusbot`, venv `venv`
- **Proxy**: `C:\Users\birk\anthropic-proxy\` (`proxy.py` +
  `run_proxy.py`, Kopie des `anthropic_plan`-Plugins vom vServer)

Die Erweiterungen am STT-Operator (An/Aus, Pegelanzeige, Gerätewahl) liegen
im Branch `stt-operator-start-stop` von `meredityman/fundusbot`. **Nicht
gemergt, kein PR** — bei einem Neuausrollen von fundusbot gehen sie sonst
verloren.

---

## Ablauf eines Interviews

1. **Foto** an den Telegram-Bot → Personenknoten, Interview öffnet.
   **Oder ohne Foto:** das Mikrofon einschalten → Interview öffnet ebenso, der
   Personenknoten ist dann eine schlichte Scheibe ohne Bild. Für alle, die
   nicht fotografiert werden wollen. Ein Foto darf jederzeit nachkommen; es
   wird dieser laufenden Person zugeordnet und beginnt kein neues Interview.
2. **Sprechen** — der STT läuft dauerhaft, ordnet aber nur zu, solange ein
   Interview offen ist
3. **Beenden**, drei Wege:
   - Gesprochen: „Interview beendet" (ein Einschub erlaubt: „ist **damit**
     beendet"; muss am Satzende stehen)
   - Sicherer: den Bot beim Namen ansprechen — **„Utopia, …"**. Dahinter darf
     freier formuliert werden; erkennt die Mechanik nichts, entscheidet ein
     kleines Modell, ob ein Beenden gemeint war (1–2 s).
   - Am sichersten: **irgendeine Textnachricht** an den Bot
4. Erst nach dem Stopp laufen Extraktion und Merge — die Begriffe wachsen
   **nicht** während des Gesprächs

Ein neues Foto schließt ein offenes Interview automatisch — außer es ist das
erste Foto zu einem per Mikrofonschalter begonnenen Interview, dann wird es
nachgetragen (siehe Punkt 1). Nach 15 Minuten ohne Stopp fällt ein Interview
von selbst zu.

⚠️ Das Wake-Word ist **„Utopia", nicht „Utopie"**. Die Prüfung läuft auf
ganzen Wörtern, „wir brauchen eine Utopie" löst also nichts aus — genau dafür
wurde der Name gewählt.

---

## Fallstricke der Umgebung

- **Windows ist deutsch.** `netstat` schreibt `ABHÖREN`, nicht `LISTENING`;
  `findstr LISTENING` findet nichts und liefert Exit 1. Locale-unabhängig
  filtern (z. B. auf die Spalte `0.0.0.0:0`, die nur Listener haben).
- **Ausgabe ist CP850/CP1252**, nicht UTF-8. Strenges Dekodieren wirft
  `UnicodeDecodeError` → `errors="replace"` benutzen.
- **`PYTHONUTF8=1` bringt Python zum Absturz** (`invalid PYTHONUTF8
  environment variable value`) — nicht setzen.
- **Scheduled Tasks mit `/IT`** starten ohne interaktive Sitzung nicht
  (Ergebnis 267011). Alle vier Dienste laufen deshalb als SYSTEM ohne `/IT`.
- **SYSTEM hat einen anderen PATH.** `python` und `claude` müssen in den
  Batch-Dateien mit vollem Pfad stehen. War die Ursache dafür, dass der
  Token-Refresh scheiterte.
- Ein SYSTEM-Task **kommt** ans Mikrofon (gemessen: 131.776 Frames, Pegel
  0,27) — Session-0-Isolation ist hier kein Hindernis.

---

## Verwandte Dokumente

- `docs/operations.md` — das Betriebshandbuch (Regler, Ablauf, Notausgang)
- `docs/stt-contract.md` — Schnittstelle zum STT-Server
- `docs/dream-image-contract.md` — Schnittstelle Tool 1 → Tool 2
- `docs/HANDOFF-2026-08-30.md` — Entwicklungsstand
- Skill `windows-remote-ops` — allgemeine Windows-Fernwartung
