Wir arbeiten am Kollektivgedächtnis in ~/projekte/kollektivgedaechtnis
(Branch master, GitHub öffentlich, MIT).

Lies zuerst docs/HANDOFF-2026-08-29-abend.md VOLLSTÄNDIG — Stand,
Entscheidungen, offene Punkte. Danach den Moduldocstring von kg2/imagegen.py
(Aufbau des Bildprompts) und den Abschnitt `_BASE` in kg2/condense.py (der
Stufe-1-Prompt, der die vier Texte erzeugt).

ZIEL DIESER SESSION: den Bildprompt so gut wie möglich machen. Das Festival
ist am 2./3. September — es geht nicht mehr um Architektur, sondern um die
Qualität dessen, was an der Wand hängt.

AUSGANGSLAGE

Gestern Abend sind fünf Befunde an realen Bildern behoben worden (Handoff §2).
Der aktuelle Stand liegt als fünf Bilder in out/tagesverlauf-tendenz/, jeweils
mit einer .md daneben, die Satz, Prompt-Bausteine auf Deutsch und die Werte
zeigt. Zum Vergleich stehen fünf frühere Läufe daneben (out/tagesverlauf*,
Reihenfolge im Handoff §2) — an denen lässt sich ablesen, was welche Änderung
bewirkt hat.

Die wichtigste Lehre aus gestern, bitte ernst nehmen: **Jeder der fünf Fehler
saß in einem BEISPIEL im Prompt, nicht im Modell.** Das Modell hat jedes Mal
exakt nachgeahmt, was ihm vorgemacht wurde — ein abstraktes Vorbild erzeugte
abstrakte Antworten, ein trennendes („neben") erzeugte geteilte Bilder, ein
beschriftetes Beispiel gegen ein Schriftverbot erzeugte leere Tafeln. Wenn
etwas nicht stimmt: **zuerst die Vorbilder im Prompt prüfen**, bevor du an
Parametern, am Modell oder an der Bausteinreihenfolge drehst.

VORGEHEN

1. Sieh dir zuerst den aktuellen Stand an, bevor du etwas änderst: die fünf
   Bilder in out/tagesverlauf-tendenz/ samt ihren .md-Dateien. Was daran ist
   gut, was fällt ab? Nenne mir konkret, was du siehst — nicht, was du
   vermutest.

2. Änderungen am Prompt gehen immer über einen echten Renderlauf, nicht über
   Plausibilität:

       set -a; . ~/.hermes/.env; set +a
       export ANTHROPIC_BASE_URL=http://127.0.0.1:28764
       export ANTHROPIC_API_KEY=proxy
       uv run python sim/probes/tagesverlauf.py out/<neuer-name>

   Fünf Zeitpunkte, ≈ 0,70 USD pro Lauf. Immer in einen NEUEN Ordner, damit
   der Vergleich erhalten bleibt.

3. Wo sich eine Wirkung MESSEN lässt, miss sie, statt sie zu behaupten. Gestern
   hat das dreimal etwas geklärt: Anteil Bilder mit Schrift (5/5 → 2/5),
   Trennwendungen in der Beschreibung (3 → 1), mood-Verlauf (3,2,2 → 3,3,2,3,3
   bei identischem Material). Ein kurzes Python-Skript über die .md-Dateien
   genügt.

4. Zeig mir Bilder einzeln nacheinander im Chat, jeweils mit dem deutschen
   Satz, den Prompt-Bausteinen und dem benannten Widerspruch — nicht als
   Sammelnachricht.

REGELN, DIE NICHT ZUR DISPOSITION STEHEN

- Der deutsche Wandsatz bleibt bei 16 Wörtern, ein Hauptsatz, kein Komma. An
  der Lesbarkeit gemessen. NICHT anfassen — nur der Bildkanal wird verbessert.
- Stimmung gehört in `mood`, Kohärenzgrad in `tension`, beide aus dem Material
  abgeleitet. NIEMALS ins Register: das beschreibt nur die Machart
  (hyperreale Schärfe und Detailtreue). Der düstere Ton eines früheren
  Registers kam genau daher, dass Stimmungswörter darin standen.
- Die Ehrlichkeitsklausel bleibt: Findet sich zu einer Seite nichts Belegbares
  im Material, wird sie NICHT erfunden. Weder Widerspruch noch Zuversicht.
  Sonst wird die offene Grundsatzfrage aus Spec §1 (wie verhält sich die
  Bildsprache zum kritischen Anspruch) still zugunsten der Freundlichkeit
  entschieden — die gehört Birk, nicht dem Agenten.
- Prompt durchgehend positiv formuliert (Googles „Semantic Negative Prompts").

ARBEITSWEISE

- Testsuite selbst fahren, nicht delegieren. Zwei Blöcke: erst
  `--ignore=tests/test_prerender.py --ignore=tests/test_projection.py`
  (~4 min, 758 Tests), dann diese beiden allein (~17 min, 61 Tests).
- Ein Hintergrundlauf verifiziert den Commit, auf dem er GESTARTET ist. Zahl
  vorher per `uv run pytest --collect-only -q | tail -1` bestimmen und mit dem
  Ergebnis vergleichen — das ist gestern zweimal schiefgegangen.
- Pfadgenau committen (`git commit -m "…" -- <pfade>`), eine Parallel-Session
  arbeitet im selben Arbeitsbaum. `-m` muss vor `--` stehen.
- Git: direkt auf master, Commit und Push ohne Rückfrage.
- Kosten: Renderläufe bis ~1 USD ohne Rückfrage. Die 40-Bilder-Serie
  (≈ 5,55 USD) nur mit meinem OK. OpenRouter-Guthaben im Blick behalten, es
  war gestern schon einmal leer.

Rückfragen bitte einzeln nacheinander, nicht gestapelt.

Sag mir zu Beginn kurz, was dir an den fünf aktuellen Bildern auffällt und wo
du den größten Hebel siehst. Fang dann an, ohne auf Freigabe zu warten.
