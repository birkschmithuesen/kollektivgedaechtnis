# Kollektivgedächtnis — Arbeitsanweisung für Agenten-Sessions

Diese Datei wird von jeder Session automatisch geladen, die in diesem Repo
arbeitet. Sie ist kurz und verweist auf das, was verbindlich ist.

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

## Wo was steht

| Thema | Datei |
|---|---|
| **Regeln Ausstellungsrechner** | `docs/ARBEITSREGELN-ausstellungsrechner.md` |
| Betrieb, Dienste, Fehlerbilder | `docs/BETRIEB-ausstellungsrechner.md` |
| Runbook Ausstellungstag | `docs/operations.md` |
| Spec | `docs/superpowers/specs/2026-08-12-kollektivgedaechtnis-design.md` |
| Foto-App (Android) | `android/README.md` |
| Öffentlicher Spiegel + Abholer | `mirror/README.md` |

## Tests

```bash
uv run pytest -q          # ~1100 Tests, ~18 min
```

`python3 -m pytest` läuft auf der falschen Python-Version und sieht aus wie
ein kaputtes Repo — immer `uv run`.

Für sicherheitsrelevante oder verhaltenstragende Änderungen gilt:
**Mutationsprobe**. Eine Wache, die nie ausgelöst hat, ist unbewiesen — den
Code kaputtmachen und prüfen, dass genau der zuständige Test rot wird.
