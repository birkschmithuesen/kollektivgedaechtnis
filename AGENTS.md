# Kollektivgedächtnis — Arbeitsanweisung für Agenten-Sessions

Diese Datei wird von jeder Session automatisch geladen, die in diesem Repo
arbeitet. Sie ist kurz und verweist auf das, was verbindlich ist.

## 🔴 Offener Auftrag (Stand 2026-09-01)

**Die Testreihe zur Gesichtserkennung fahren.** Foto-App, Sucherrahmen,
Portrait-Vorschau und Messwerkzeug sind gebaut und einsatzbereit —
**gemessen ist noch nichts.** Birk hat die Durchführung ausdrücklich an die
übernehmende Session übergeben.

Vollständiger Auftrag: `docs/HANDOFF-foto-app-uebergabe.md`
Ablauf und Werkzeug: `docs/HANDOFF-fototest-zuschnitt.md`

## 🔴 Zuerst: `docs/STAND.md`

**Das ist das EINE Dokument, mit dem eine Session anfängt.** Was läuft, was
ungeprüft ist, welche Entscheidungen Birk selbst trifft, und was als Nächstes
zu tun wäre. Alles Ältere liegt unter `docs/archiv/` und ist erledigt —
dort steht nichts, was noch gilt.

Neue Erkenntnisse gehören **in `docs/STAND.md`**, nicht in ein neues Handoff.
Am 2026-09-01 lagen elf Handoff-Dateien nebeneinander, acht davon erledigt;
niemand konnte sagen, welche noch stimmte.

## 🔴 Vor JEDEM Zugriff auf den Ausstellungsrechner

**`docs/ARBEITSREGELN-ausstellungsrechner.md` lesen.** Vollständig, nicht
überfliegen. Alle Regeln dort stammen aus Fehlern, die real passiert sind und
Arbeit gekostet haben.

Die vier, an denen am häufigsten etwas schiefging:

1. **Immer als `SF-Tracking` einloggen, nie als `birk`.** Beide Zugänge
   funktionieren — deshalb merkt man den Fehler erst, wenn der Mensch etwas
   nicht findet.
2. **Die Startdatei nur im Repo ändern** (`mirror/kollektivtraum.bat`). Die
   Station zieht sie sich bei jedem Start selbst nach; eine Änderung am
   Rechner wird lautlos überschrieben.
3. **Dienste nie direkt über SSH starten** — sie sterben mit der Sitzung und
   hinterlassen ein Log, das wie ein sauberer Start aussieht. Über
   `schtasks`, oder den Menschen START drücken lassen.
4. **Erreichbarkeit messen, nicht annehmen.** „Log sagt gestartet" ist kein
   Beleg; erst ein `Get-NetTCPConnection` plus ein `curl` über Tailnet ist einer.

## Parallele Sessions

Es arbeitet mehr als eine Session an diesem Projekt. Der gemeinsame Checkout
steht oft auf einem fremden Branch:

```bash
cd ~/projekte/kollektivgedaechtnis && git status -sb && git log --oneline -3
```

Eigene Arbeit in einen eigenen Worktree
(`git worktree add ~/projekte/kg-<zweck> master`), nie in den gemeinsamen
Checkout. Vor dem Push `git fetch` und prüfen, ob die andere Session dieselben
Dateien angefasst hat.

## Demodaten für die Kalibrierung (Routine — wird öfter gebraucht)

Zum Einrichten der Größen (Portrait, Begriffe, Zitatkarte) braucht die Wand
Inhalt in mehreren Dichten. Auf echte Besucher zu warten geht nicht, und ein
einzelnes Testfoto sagt nichts über den Fall „sechzig Personen".

**Erzeugt wird mit `sim/seed_graph.py`** — echte Portraits, echte
Begriffslängen aus dem Konferenzthema, **kein LLM, keine Kosten**:

```bash
uv run python -m sim.seed_graph --out /tmp/dichte-60 --persons 60 --gesichter
```

🔴 **`--gesichter` nicht vergessen.** Ohne die Fahne bekommt jede Person eine
leere graue Fläche (`_write_placeholder_photo`) — das ist für die
Vorab-Rendering-Reihe so gewollt (Entscheidung 2026-08-14: Farbe dort würde
Bedeutung vortäuschen), für die Kalibrierung aber unbrauchbar. Birk am
2026-09-01 vor Ort: *„Es werden überhaupt keine Gesichter angezeigt bei den
Demodaten."* Die Fahne nimmt die 16 Gesichter aus `sim/data/portraits/`
(erzeugt von `sim/cut_portrait_sheet.py`) und vergibt sie reihum.

**Prüfen, ob wirklich Gesichter drin sind** — nicht dem Dateinamen glauben:
die Graustufen-Streuung eines Portraits liegt bei ~75 und ist von Bild zu Bild
verschieden; eine leere Fläche liegt bei 46,8 und ist bei **allen** Personen
exakt gleich.

**Auf die Station bringen:** als `.tgz` nach
`C:\Users\birk\kollektivgedaechtnis\data-dichte\<n>\` entpacken (Windows kann
`tar` nicht verlässlich → mit Python `tarfile` entpacken).

**Umschalten** mit `scripts/dichte-umschalten.py` auf der Station:

```
python dichte-umschalten.py --stufe 1|10|40|60
python dichte-umschalten.py --stufe echt     # zurück in den Ausstellungsbetrieb
python dichte-umschalten.py --stufe status
```

🔴 **Station vorher beenden.** Das Skript prüft das selbst und verweigert den
Dienst, solange Port 8800/8810 lauscht — mit gutem Grund: die laufende Station
hält `embeddings.sqlite3` offen, und ein Umschalten mitten im Betrieb bricht
ab, **nachdem** es schon halb passiert ist (erlebt 2026-09-01: Datenbank in
beiden Ordnern, Bilder nur in einem).

Die echte Ausstellungsdatenbank wird beim ersten Umschalten **kopiert** nach
`data-echt/` und danach nie wieder angefasst. Umgeschaltet wird immer nur der
*Inhalt* von `data/`, der Ordner selbst bleibt stehen — Windows verweigert das
Löschen eines Ordners mit offener Datei.

## Wo was steht

| Thema | Datei |
|---|---|
| **Stand + was als Nächstes** | `docs/STAND.md` |
| **Regeln Ausstellungsrechner** | `docs/ARBEITSREGELN-ausstellungsrechner.md` |
| Betrieb, Dienste, Fehlerbilder | `docs/BETRIEB-ausstellungsrechner.md` |
| Runbook Ausstellungstag | `docs/operations.md` |
| Spec | `docs/superpowers/specs/2026-08-12-kollektivgedaechtnis-design.md` |
| Foto-App (Android) | `android/README.md` |
| **Übergabe / offene Punkte** | `docs/HANDOFF-foto-app-uebergabe.md` |
| **Fototest + Zuschnitt-Rückmeldung** | `docs/HANDOFF-fototest-zuschnitt.md` |
| Alternativ-Foto-Cache (offen) | `docs/HANDOFF-alternativ-foto-cache.md` |
| Öffentlicher Spiegel + Abholer | `mirror/README.md` |
| Erledigtes (nur zum Nachschlagen) | `docs/archiv/` |

## Tests

```bash
uv run pytest -q          # ~1100 Tests, ~18 min
```

`python3 -m pytest` läuft auf der falschen Python-Version und sieht aus wie
ein kaputtes Repo — immer `uv run`.

Für sicherheitsrelevante oder verhaltenstragende Änderungen gilt:
**Mutationsprobe**. Eine Wache, die nie ausgelöst hat, ist unbewiesen — den
Code kaputtmachen und prüfen, dass genau der zuständige Test rot wird.
