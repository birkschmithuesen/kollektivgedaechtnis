# Plan Nachbearbeitung — und was davon in die nächste Installation geht

**Grundlage:** [`docs/NACHBEREITUNG.md`](NACHBEREITUNG.md) (Bestandsaufnahme,
2026-09-03, 480 Zeilen). Dieses Dokument zieht die Schlüsse, die dort bewusst
nicht gezogen wurden.

**Zwei Ziele, getrennt gehalten:**

- **A — der jetzige Bestand.** Was am Datensatz und am Repo noch zu tun ist,
  damit der Graph vom NEW bauhaus 2026 als Werk und als Referenz taugt.
- **B — das übertragbare Verfahren.** Was eine nächste Installation dieser Art
  (Interview → Graph → Bild) am Tag 1 schon können sollte, statt es wieder
  unter Zeitdruck an der Wand zu entdecken.

Die Trennung ist der Punkt: A ist Aufräumen und endet. B ist das eigentliche
Ergebnis der zwei Ausstellungstage.

---

## Der eine Befund, der alles andere ordnet

Aus der Bestandsaufnahme, §7 und §1:

> Jeder Fehler wurde erst bemerkt, **nachdem er an der Wand stand** — und dann
> von Hand repariert, unter Zeitdruck, mehrfach.

Das gilt für alle vier Fehlerklassen des Festivals:

| Klasse | Beispiel | wurde bemerkt durch |
|---|---|---|
| Falsche **Zuordnung** | Foto beim vorigen Interview, Begriffe an falscher Person | Birks Blick auf die Wand |
| Schiefe **Namen** | „Sozialgemeinschaftsleben", „Naturierung" | Birks Blick auf die Wand |
| **Müll** aus leerer Auswertung | „Keine relevanten Informationen" als Begriff | Birks Blick auf die Wand |
| **Darstellung** | Knoten außerhalb des Bildes, 6,8-px-Schrift | Birks Blick auf die Wand |

1589 grüne Tests haben keine davon gefunden. Das ist kein Test-Versäumnis,
sondern eine Aussage über die Art der Fehler: Sie sind alle **Aussagen über
Material**, nicht über Code. Ein Test kann prüfen, dass ein Name gesetzt wird —
nicht, ob er trägt.

**Konsequenz für A und B gleichermaßen:** Es fehlt eine Instanz, die den
Bestand liest und Zweifel meldet. Nicht: die Sache repariert. Meldet.

---

## A — Der jetzige Bestand

### A1 🔴 Die Arbeit des 03.09. sichern

**Befund:** Bestandsaufnahme §7 — „Die Arbeit des 2026-09-03 ist noch nicht
committet." Der Spiegel auf herkules läuft **ohne Git**, Änderungen kamen per
`scp`; Sicherungen liegen als `~/backups/kg-mirror-web-<zeitstempel>/`.

**Aufgabe:** Arbeitsbaum committen, `scp`-Stand auf herkules gegen das Repo
diffen, Differenz als Commit nachziehen. Solange das offen ist, existiert der
Ausstellungsstand nur auf zwei Maschinen und in einem Backup-Ordner.

*Aufwand: klein. Risiko des Nichtstuns: Totalverlust bei Plattendefekt.*

### A2 Die Datenbank als Werk sichern

`data/kg.db` (34 Personen, 65 Begriffe, 134 Kanten) und
`dream-data/dreams.sqlite3` (27 Träume **mit vollständigem Prompt**) sind das
Ergebnis der Ausstellung. Der Prompt-Verlauf d1→d27 ist eine
Dokumentationsquelle, die es kein zweites Mal gibt.

**Aufgabe:** Ein datierter, unveränderlicher Abzug beider Datenbanken, außerhalb
des Ausstellungsrechners. **Ablage:** entity-seitig unter NewBauhaus2026, nicht
im Code-Repo (Binär, wächst nicht mehr).

🔴 **PII-Vorbehalt:** In `kg.db` stehen Klarnamen und wörtliche Zitate realer
Besucher. Der Abzug geht **nicht** ins öffentliche Repo und **nicht** in einen
LLM-Kontext. Der bestehende `scripts/sichern-in-cloud.sh` ist der Weg.

### A3 Die neun Umbenennungen zurückspielen — falls der Graph weiterlebt

Am 03.09. wurden neun Begriffsnamen von Hand korrigiert, alte Etiketten als
Alias erhalten. Das steht in `kg.db` auf dem Ausstellungsrechner. Wenn der
öffentliche Spiegel (`kollektivgedaechtnis.flashclash.de`) weiterlaufen soll,
muss dessen `graph.json` diesen Stand tragen.

**Entscheidung nötig:** Bleibt die Seite online? Wenn ja, ist sie ab jetzt ein
Archivstand — dann gehört ein Datum drauf („Stand 3. September 2026"), sonst
liest sie sich als Live-Anlage.

### A4 Zwei Belegstellen ohne Nachweis

Daniela „auch mit Lehm", Steffen „In jedem Fall die, die es betrifft" — in den
Transkripten nicht auffindbar, bewusst nicht erfunden.

**Aufgabe:** entweder im Transkript wiederfinden (STT hat womöglich anders
segmentiert) oder die Kante als beleglos markieren. Nicht stillschweigend
stehenlassen: 134/134 Kanten *mit* Belegstelle ist die dokumentierte Zahl, und
zwei davon halten nicht.

### A5 Der Begriff ohne Nachbarn

„Verschiedene Wohnformen für alle" hatte am 03.09. als einziger von 55
Begriffen keine `verwandt`-Einträge, nach dem Neustart drei. Embedding
vollständig (3584 Dimensionen). **Ursache nicht ermittelt.**

**Aufgabe:** Nach `systematic-debugging` untersuchen — nicht patchen. Ein
Begriff, dessen semantische Nachbarschaft vom Neustart abhängt, ist ein
Zustandsfehler in `kg/semantik.py` und trifft bei der nächsten Installation
wieder zu.

---

## B — Das übertragbare Verfahren

Hier liegt der eigentliche Ertrag. Fünf Bausteine, in der Reihenfolge ihres
belegten Nutzens.

### B1 🔴 Der Kurator — ein wiederkehrender Lauf über den Bestand

Die einzige Empfehlung der Bestandsaufnahme, und sie ist gut belegt: Alles,
was am 03.09. von Hand geschah, ist mechanisierbar. Vier Prüfungen:

| Prüfung | Belegter Anlass | Signal |
|---|---|---|
| **Trägt der Name noch?** | 9 von 65 Namen umbenannt; fast alle waren Kunstwörter aus dem ERSTEN Interview, überholt von fünf späteren | Name kommt in **keiner** seiner Belegstellen wörtlich vor |
| **Meinen zwei dasselbe?** | Antje Simon: alle 6 Begriffe Einmal-Nennungen, obwohl Partner existierten | hohe Embedding-Nähe + kein Alias |
| **Meint einer zwei Dinge?** | „Verzicht auf Keller" sammelte Aussagen über Wohnfläche; „KI-Grundrissplanung" musste geteilt werden | Belegstellen streuen semantisch weit |
| **Ist das überhaupt ein Ergebnis?** | „Keine relevanten Informationen über Begriffe" stand als Begriff an der Wand | Absage-Muster im Label |

Die vierte ist die billigste und die peinlichste — sie braucht kein LLM,
sondern eine Handvoll Muster. Sie kommt zuerst.

**Drei Entscheidungen, die dieser Baustein braucht** (aus der
Bestandsaufnahme ausdrücklich offengelassen — es sind Entscheidungen, keine
Befunde):

1. **Takt.** Nach jedem Interview? Alle 10? Stündlich?
2. **Befugnis.** Darf er ändern, oder nur vorschlagen?
3. **Schutz.** Wie erkennt er einen Namen, den ein Mensch bewusst gesetzt hat?

**Meine Empfehlung** — nach dem, was das Festival gezeigt hat:

> **Nur vorschlagen, nie ändern. Getaktet nach Bestandszuwachs, nicht nach Uhr.
> Handgesetzte Namen sind gesperrt, technisch, nicht per Konvention.**

Begründung: Der Kurator urteilt über *Bedeutung*, und genau dort war das
System am unzuverlässigsten (Merge-Judge zu streng UND zu großzügig, beides
belegt). Ein Vorschlag kostet einen Blick, eine falsche Änderung kostet den
Abend. Und: Birks Vorgabe vom 02.09. — *„du darfst auf keinen Fall den Inhalt
verändern oder etwas dazu erfinden"* — gilt für einen Automaten mindestens so
sehr wie für einen Agenten.

**Ausgabe:** eine Zeile pro Zweifel im Bedienpult, mit Beleg und einem Knopf.
Keine Mail, kein Log. Was am Ausstellungstag nicht in zwei Sekunden sichtbar
ist, existiert nicht.

### B2 Der Prompt-Verlauf als Methode

Die sieben Änderungen am Traumprompt (Bestandsaufnahme §2) sind kein
Projekt-Detail, sondern ein **Verfahren, wie man aus Interviews bessere Bilder
bekommt**. Jede Änderung hat einen belegten Anlass aus dem Raum:

| Beobachtung im Raum | Änderung | verallgemeinert |
|---|---|---|
| „Lehm kam in jedem Bild vor" | Negativliste der letzten drei Wandsätze | **Ein zustandsloser Generator wiederholt sich zwangsläufig — er braucht ein Gedächtnis der letzten Ausgaben** |
| „immer sehr klischeehafte Rollenbilder, fast immer Familie" | Bildinhalt entklischeet, Diversität explizit benannt | **Das Modell setzt Defaults, wo der Prompt schweigt. Diversität muss pro Person benannt werden** (schon 2026-08-16 bei den Renderings gelernt — dieselbe Lehre, zweiter Anlauf) |
| Begriffe zu weit weg von der befragten Person | Verbundenheit schlägt Häufigkeit; Nähe = Layout-Abstand | **Häufigkeit ist die falsche Achse, wenn ein einzelner Mensch gerade gesprochen hat** |
| „Wie oft ein Begriff genannt wurde … das sind harte Zahlen" | mechanische Pflichtliste statt Prosa-Bitte im Prompt | **Was zählbar ist, gehört in Code, nicht in den Prompt** |

Die letzte Zeile ist die wichtigste und deckt sich mit einer stehenden Regel:
*Auswahl aus Zahlen → CODE.* Ein Prompt, der bittet „berücksichtige die
häufigsten Begriffe", ist eine Wette. Eine Liste ist eine Liste.

**Aufgabe:** Diese Tabelle wandert in einen Skill, nicht in dieses Repo. Sie
gilt für jede Installation, die aus Gesprächen Bilder macht.

### B3 Der Testgraph muss so groß sein wie die Wand

Bestandsaufnahme §4, gemessene Ursache: Testgraph 5 Knoten, Wand 76. Bei fünf
Knoten fallen „die Auswahl ist sichtbar" und „alles ist sichtbar" zusammen —
sechs Darstellungsfehler blieben deshalb unsichtbar bei 1589 grünen Tests.

Die Gegenmaßnahme ist bereits eingebaut (`tests/test_tafel.py`, 72 Knoten,
Vorbedingungstest „die Kamera MUSS fahren"). **Verallgemeinert für die nächste
Installation:** Der Testdatensatz einer räumlichen Darstellung muss die
**Sättigung** erreichen, ab der sich Sichtbarkeit und Auswahl trennen. Ein
kleiner Testgraph ist kein kleinerer Fall, sondern ein anderer.

### B4 Zwei Zustände, die auseinanderlaufen — der Klassiker

Aus der Übergabe vom 02.09.: `mic_on: true` bei `status: paused`, und
`mic_on: true` bei `interview: None`. Beide Male sah alles nach Betrieb aus,
beide Male wurde nichts aufgezeichnet. **Der Zustand ist stabil falsch**, weil
das Mikrofongate nur bei Übergängen handelt.

**Verallgemeinert:** Jede Anlage aus mehreren Diensten braucht eine Prüfung
auf **Widerspruch zwischen den Zuständen**, nicht nur auf den Zustand jedes
einzelnen. Grüne Lampen an beiden Enden beweisen nichts über die Mitte.

Konkret hier offen: Der Kern könnte einen `final`-Text bei `mic_on && kein
offenes Interview` als Beleg werten, dass jemand spricht — und laut werden.

### B5 Die Prüfkette misst die ganze Kette

`kg/stt_health.py` misst absenden **und** abholen, weil das bloße Absenden
während des Infomaniak-Ausfalls 6 von 8 Mal HTTP 200 lieferte, ohne dass je
ein Ergebnis kam. Der Test dazu heißt
`test_ein_erfolgreiches_absenden_allein_reicht_nicht`.

**Verallgemeinert:** Eine Aufsicht, die vor dem Ergebnis aufhört, meldet in
genau dem Ausfall „alles gut", für den sie gebaut wurde.

---

## Reihenfolge

| # | Was | Warum jetzt |
|---|---|---|
| 1 | A1 — committen und sichern | einziger unwiederbringlicher Verlust |
| 2 | A2 — Datenbanken als Werk abziehen | dito, PII-konform |
| 3 | B1 Stufe 1 — Absage-Erkennung (kein LLM) | billigste Prüfung, peinlichster Fehler |
| 4 | B2 — Prompt-Lehren als Skill | verfällt am schnellsten, solange es nur im Kopf ist |
| 5 | A5 — Nachbarn-Fehler untersuchen | trifft die nächste Installation wieder |
| 6 | B1 Stufe 2–4 — Kurator mit LLM | braucht erst die drei Entscheidungen |
| 7 | A3/A4 — Spiegel und Belegstellen | hängt an der Entscheidung „bleibt online?" |

## Was dieser Plan bewusst nicht enthält

- **Ob `kg/merging.py` umgebaut wird.** Beide Fehlerrichtungen sind belegt,
  aber der Merge-Audit vom 27.08. rät ausdrücklich davon ab, `merge_style` zu
  lockern (gemessene Gegenbeispiele: „Tiefgaragen" vs. „Verzicht auf
  Tiefgaragen", cos 0,74, Rang 1 — Gegenteile mit hoher Ähnlichkeit). Der
  Kurator (B1) greift dasselbe Problem von hinten an, ohne dieses Risiko.
- **Beobachtungen aus dem Raum.** Wie Besucher reagiert haben, wie die
  Gespräche liefen — dafür gibt es keine Aufzeichnung, und ich erfinde keine.
- **Eine Bewertung, ob die Installation gelungen ist.** Das ist Birks und
  Ninas Urteil.
