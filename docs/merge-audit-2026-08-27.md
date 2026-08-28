# Warum landen zwei Menschen nicht auf demselben Begriffsknoten?

Analyse über `/home/birk/projekte/kollektivgedaechtnis` (Branch master), Lauf 19c.
**Nur gelesen und gemessen** — kein Produktivcode geändert, nichts committet.
Analyse-Skripte lagen in `/tmp/` und sind bewusst nicht mit eingecheckt (Wegwerf-Code); die Belege unten sind aus `out/sim19c/sim.db` und dem Embedding-Cache reproduzierbar.

**Kurzfassung:** Die Hypothese („Extraktion zu spezifisch, Merge fängt es nicht ab")
trägt **nur zum kleineren Teil**. Gemessen: In **22 von 26** untersuchten
Duplikat-Paaren **stand der richtige bestehende Knoten in den Top-12 und wurde dem
Judge gezeigt** — er hat ihn gesehen und trotzdem nicht gemerged. Die
Kandidatenauswahl ist also nicht das Nadelöhr, das die Doku noch beschreibt.
Zusätzlich habe ich **zwei echte Code-Bugs** gefunden, die belegbar Merges
verworfen haben, die der Judge korrekt entschieden hatte.

---

## Phase 1 — Der Mechanismus (GEMESSEN, aus dem Code)

### Kette pro Interview (`kg/pipeline.py:50-70`)

1. `extract()` — 1 LLM-Aufruf, max. `terms_per_interview`=5 Labels.
2. `split_known()` (`merging.py:73-83`) — **exakter String-Vergleich** gegen die
   Alias-Tabelle (`store.find_term_by_alias`, Zeile 78). Keine Normalisierung,
   kein Casefold, kein Lemma.
3. `build_candidates()` (`merging.py:86-101`) — Embedding-Vorauswahl, Top-K.
4. `decide_merges()` (`merging.py:115-124`) — **1 LLM-Aufruf**, der Judge entscheidet.
5. `apply_merges()` (`merging.py:127-219`) — faltet Gruppen, schreibt Aliase.
   Labels ohne Gruppe bekommen via `get_or_create_term` (Zeile 209) einen
   **neuen eigenen Knoten**.

### Antworten

**Zuordnungskriterium:** Zwei Pfade — (a) exakter String gegen Aliase,
(b) sonst **LLM-Judge**. Embeddings entscheiden **nichts**; Docstring
`embeddings.py:1`: „Embeddings are preselection only".

**Schwelle:** **Es gibt KEINE.** `nearest()` (`embeddings.py:194-199`) sortiert
nach Cosinus und schneidet bei `k` ab — kein Mindestwert. Auch ein Kandidat mit
cos=0,05 wird gezeigt, wenn er in die Top-K rutscht. Es gibt folglich keinen
Schwellenwert, der „zu streng" stehen könnte. Der einzige Regler ist
`merge_style` (`config.py:19-22`), ein Prompt-Text:
> „Fasse nur zusammen, was wirklich dasselbe meint. Verwandte, aber
> unterschiedliche Ideen bleiben getrennte Knoten."

**Kandidatenzahl:** `merge_neighbours` = **12** (`config.py:37`,
`config.example.toml:38`) — **kalibriert, nicht geraten**. Die Begründung
(`config.example.toml:32-37`) nennt genau dieses Problem:
> „Run 19b: in 7 of 8 near-misses the concept's own node sat at rank 7-56 in the
> candidate pool, i.e. outside a window of 5 — the judge was never shown it."

**Extraktions-Prompt zur Granularität** (`extraction.py:46-56`, wörtlich):
> „2. BEGRIFFE. […] Optimiere auf KONKRETHEIT, nicht auf Häufigkeit.
>    Gut (konkret, bildhaft, überraschend): „Betonspritzen mit Drohnen", […]
>    Schlecht (nichtssagend, verbindet alles mit allem): „Nachhaltigkeit",
> „Zukunft", „Digitalisierung", […]
>    Regeln: deutsche Substantivphrase, 1–4 Wörter, ohne Artikel, keine ganzen
> Sätze […] Lieber weniger Begriffe als schwache Begriffe."

Der Merge-Prompt verstärkt das (`merging.py:30-32`):
> „Steige NIE auf einen Oberbegriff hoch („Nachhaltigkeit", „Digitalisierung") —
> das zerstört das Bild."

**Zur Hypothese:** Der Prompt fordert Spezifität, erzeugt aber **keine
satzartigen Begriffe** — die Regel „1–4 Wörter, keine ganzen Sätze" wird
eingehalten. Die 163 Labels sind durchweg Substantivphrasen. Die Formulierung
in der Hypothese („satzartig") trifft die Daten nicht.

---

## Phase 2 — Wie viele echte Duplikate gibt es? (GEMESSEN)

21 klare Duplikat-Gruppen aus den 163 Labels, konservativ gebildet. Pro Gruppe
die Nennungszahlen und — entscheidend — ob der Partner in den Top-12 stand:

| Gruppe | Summe | Partner in Top-12? |
|---|---|---|
| Bodenpolitik(1) + Bodenpolitik und Baurecht(1) | 2 | ja, **Rang 1**, cos 0,79 |
| Emotionale Raumqualität(2) + Atmosphäre eines Raums(2) + Bauchgefühl im Raum(2) | 6 | ja, Rang 1 / 2 |
| Gemeinsamer Hausbesitz(3) + Genossenschaftliches Modell(2) | 5 | ja, Rang 1 |
| Investorenentscheidungen(2) + …im Gemeinderat(1) + …im Hubschrauber(1) | 4 | ja, Rang 3 / 1 |
| Abriss-Neubau-Paradigma(3) + Bruch mit Neubauparadigma(4) + Tabula-rasa-Prinzip(1) | 8 | ja, Rang 1 / 1 |
| Klüger reparieren(2) + Strukturelle Reparatur(1) | 3 | ja, Rang 1 |
| Tiefgaragen(3) + Verzicht auf Tiefgaragen(1) | 4 | ja, Rang 1, cos 0,74 |
| Verzicht auf Unterkellerung(4) + Vollunterkellerung(1) | 5 | ja, Rang 1 |
| Versiegelte Höfe und Parkplätze(6) + Zugepflasterte Landschaft(2) | 8 | ja, Rang 5 |
| Zugebaute Freiflächen(5) + Unbebaute Freiflächen(1) | 6 | ja, Rang 1, cos 0,73 |
| Betonsprühende Maschinen(3) + Drohnen am Bau(1) + Mauerroboter(2) | 6 | **nein** (Sonderfall, s. Bug 1) |
| Fassadenbegrünung(1) + Dachbegrünung(1) + Eingebautes Grün(1) | 3 | teils (Rang 3 / außerhalb) |
| Scheinbeteiligung pro forma(7) + Fehlendes Gehörtwerden(1) | 8 | ja, Rang 9 |
| Entscheidungen von oben(3) + Blackbox Verwaltung(1) | 4 | ja, Rang 5 |
| Geteilte Gemeinschaftsräume(1) + Gemeinschaftliche Grünflächen(2) | 3 | ja, Rang 1 |
| Wiederverwendeter Abbruchschutt(5) + Bauteilrecycling(2) | 7 | ja, Rang 2 |
| Durchlässige(1) + Multicodierte Erdgeschosszonen(1) | 2 | ja, Rang 2, cos 0,70 |
| Grundrissoptimierung(5) + Optimierung von Bauteilquerschnitten(1) | 6 | ja, Rang 1 |
| Normen als Absicherung(1) + Complianceregeln(1) | 2 | ja, Rang 1 |
| Autofreie Stadt(3) + Stadt vom Rad aus(1) | 4 | ja, Rang 1 |
| Leerstehende Häuser im Dorfkern(4) + Ungenutzte Vorzeigeprojekte(1) | 5 | **nein**, Rang 58 |

**Grenzfälle (bewusst NICHT eingerechnet):**
- Nachmittagslicht im Dorfhaus(3) + Tageslicht im Zimmer(6) — cos 0,60, Rang 1
- Weiterbauen im Bestand(5) + Klüger reparieren(2) — cos 0,35, Rang 23
- Optimiertes Durchschnittshaus(2) + Schuhkarton-Architektur(1) — cos 0,35, Rang 17
- Wasserdurchlässiger Boden(1) + Rasengittersteine(1) — cos 0,33, Rang 44
- Aufenthaltsqualität im Freien(2) + Luft zum Atmen(1) — cos 0,40, Rang 4

### Die Zahlen

- **23 der 114 Einmal-Nennungen** hätten mit einem anderen Knoten verschmelzen
  müssen (114 → 91).
- **Gegenrechnung** (nur die 21 klaren Gruppen, Grenzfälle ausgeschlossen):

| | Begriffe | ≥2 Nennungen | genau 1 |
|---|---|---|---|
| IST | 163 | 49 | 114 |
| SOLL | **137** | **46** | **91** |

Verteilung IST: `{1:114, 2:23, 3:10, 4:8, 5:4, 6:3, 7:1}`
Verteilung SOLL: `{1:91, 2:16, 3:7, 4:9, 5:4, 6:6, 7:1, 8:3}`

**Ein wichtiges Ergebnis gegen die Intuition:** Die Zahl der Knoten mit ≥2
Nennungen *sinkt* leicht (49 → 46), weil die Merges überwiegend bereits geteilte
Knoten zu *noch dickeren* Knoten zusammenziehen. Der Gewinn liegt nicht in mehr
geteilten Knoten, sondern in einem **kürzeren Schwanz und schwereren Kernknoten**
(neu: drei Knoten mit 8 Nennungen). Der lange Einmal-Schwanz schrumpft nur um
20 %, nicht um die Hälfte — ein großer Teil der 114 Singletons ist **echt
einmalig gesagt**, kein Duplikat.

---

## Phase 3 — Woran liegt es konkret? (GEMESSEN)

Embeddings sind lokal aus dem Cache rechenbar: `data/embeddings.sqlite3`,
461 Vektoren, Modell `openai/text-embedding-3-small`. **Alle 163 Labels waren im
Cache** (0 Fehltreffer) — die Ähnlichkeiten unten sind echt gerechnet, kein Netz,
keine Kosten.

Da es **keine Schwelle** gibt, kann kein Paar „an der Schwelle gescheitert" sein.
Die Gründe sind andere:

**1. `Bodenpolitik und Baurecht` vs `Bodenpolitik`** — cos **0,792**, Rang **1**.
Der Judge (p23) hat korrekt entschieden: `{'canonical_label':'Bodenpolitik',
'members':['Bodenpolitik und Baurecht']}`. **Der Code hat die Entscheidung
verworfen** — `apply_merges` filtert Gruppen mit `len(members) < 2`
(`merging.py:152`). Der Judge hatte den bestehenden Knoten aber nur als
*canonical_label* genannt, nicht als Member. Ergebnis im Graph: beide Knoten
existieren mit je 1 Nennung. **→ BUG A.**

**2. `Sanieren, Umbauen, Weiterbauen` → `Weiterbauen im Bestand`** — dieselbe
Struktur bei p23 (`members` einelementig). Hier ging es gut aus: der Knoten
`Sanieren, Umbauen, Weiterbauen` fehlt im Graph, weil p36 ihn später korrekt
mit-merged hat. Der Fehler war also nur zufällig folgenlos.

**3. `Mauerroboter` vs `Betonsprühende Maschinen`** — cos 0,425. p31 entschied
korrekt: `['Mauerroboter', 'Weniger Handarbeit', 'Betonsprühende Maschinen']`.
Im Payload steht der dritte Member aber als `"Betonspr\\u00fchende Maschinen"` —
**doppelt escaptes Unicode**. `unquote_label` (`merging.py:46-61`) strippt nur
Anführungszeichen, keine Escape-Sequenzen. Der Lookup lief ins Leere, und in der
Alias-Tabelle steht heute nachweislich:
`Mauerroboter <- 'Betonspr\\u00fchende Maschinen'` — ein Alias, den nie jemand
trifft. Statt eines Knotens mit 6 Nennungen stehen jetzt `Betonsprühende
Maschinen`(3) und `Mauerroboter`(2) getrennt. **→ BUG B.** Derselbe Defekt bei
p34 (`\ru201eBürgerversammlung als Pflichttermin\ru201c`).

**4. `Verzicht auf Tiefgaragen` vs `Tiefgaragen`** — cos **0,743**, Rang **1**.
Kein Bug: der Judge sah den Knoten an erster Stelle und entschied gegen den
Merge. Das ist eine **Judge-Entscheidung**, und angesichts von `merge_style`
(„nur was wirklich dasselbe meint") sogar vertretbar — „Tiefgaragen" und
„Verzicht auf Tiefgaragen" sind Gegenteile in der Haltung, dasselbe im Thema.

**5. `Ungenutzte Vorzeigeprojekte` vs `Leerstehende Häuser im Dorfkern`** —
cos 0,273, Rang **58 von 87**. Der einzige klare Fall, in dem die
**Kandidatenauswahl** schuld ist: der Partner wurde nie gezeigt. Genau das
Muster, das die Doku beschreibt — aber es ist heute die Ausnahme, nicht die Regel.

**Bilanz über alle 26 gemessenen Paare: 22 mal stand der Partner in den Top-12.**

---

## Phase 4 — Wo sitzt die Ursache?

**Nicht (c) Kandidatenauswahl.** Gemessen 22/26 Partner in den Top-12. Die
Anhebung auf `merge_neighbours`=12 in Lauf 19c hat gewirkt; die Doku
(`docs/operations.md:278-280`, `config.example.toml:32-37`) beschreibt noch den
Zustand von Lauf 19b und ist an dieser Stelle **überholt**. Restfälle
(„Ungenutzte Vorzeigeprojekte", Rang 58) existieren, sind aber Einzelfälle.

**Nicht (b) Schwelle.** Es gibt keine. Diese Ursache scheidet mechanisch aus.

**(a) Extraktion — teilweise, aber anders als vermutet.** Die Labels sind keine
Sätze; die Prompt-Regeln werden eingehalten. Was der Prompt aber erzeugt, ist
**Perspektiv-Varianz auf gleicher Abstraktionsebene**: „Emotionale
Raumqualität" / „Atmosphäre eines Raums" / „Bauchgefühl im Raum" sind drei
gleich konkrete Namen für dieselbe Sache. Das ist ein direkter, gewollter
Effekt von „Optimiere auf KONKRETHEIT" plus dem Oberbegriff-Verbot. Diese
Diagnose stützt Ihre Hypothese im Kern — die Begründung („satzartig") stimmt
nicht, die Wirkung (unterschiedliche Formulierungen, getrennte Knoten) schon.

**Hauptursache (d), zwei Anteile — und der größere ist ein Bug, keine Kalibrierung:**

1. **Zwei Implementierungsfehler in `apply_merges`** verwerfen Entscheidungen,
   die der Judge korrekt getroffen hat. Belegt an p23 (`len(members)<2`) und p31/p34
   (doppelt escaptes Unicode). Das ist reparierbar ohne jede Abwägung — hier
   wird nichts falsch gemerged, hier geht korrektes Urteil verloren.
2. **Judge-Konservatismus im gezeigten Fenster.** In den verbleibenden Fällen sah
   der Judge den richtigen Knoten auf Rang 1–9 und entschied dagegen. Das ist
   `merge_style` in Aktion. Die Doku behauptet (`operations.md:281-283`), nur 1
   von 8 Beinahe-Treffern sei eine Judge-Entscheidung gewesen — nach meiner
   Messung ist das heute der **überwiegende** Anteil.

### Maßnahmen (höchstens drei, mit Preis)

**1. Die zwei Bugs in `apply_merges` beheben.** (a) Eine Gruppe mit einem Member
plus einem `canonical_label`, das auf einen bestehenden Knoten zeigt, ist eine
gültige Merge-Aussage und darf nicht bei `merging.py:152` fallen. (b) In
`unquote_label` zusätzlich literale `\uXXXX`-Sequenzen dekodieren.
*Preis:* gering und asymmetrisch — (a) kann nur greifen, wenn das
canonical_label tatsächlich einem Knoten entspricht; (b) ist reine
Normalisierung. Risiko eines Falsch-Merges praktisch null.
*Belegter Gewinn:* mindestens `Bodenpolitik`(2x) und `Betonsprühende
Maschinen`+`Mauerroboter`(5–6x).

**2. `merge_style` NICHT lockern.** Ich rate ausdrücklich ab, obwohl der Judge
der größte verbleibende Anteil ist. Gemessene Gegenbeispiele aus demselben
Kandidatenfenster: `Tiefgaragen` vs `Verzicht auf Tiefgaragen` (cos 0,743,
Rang 1) und `Zugebaute Freiflächen` vs `Unbebaute Freiflächen` (cos 0,734,
Rang 1) sind **Gegenteile mit sehr hoher Ähnlichkeit**. Ein lockererer Judge
verschmilzt genau diese zuerst — und ein Knoten, der „Tiefgaragen" und „Verzicht
auf Tiefgaragen" zusammenwirft, sagt auf der Wand nichts mehr aus. *Preis des
Nichtstuns:* der Schwanz bleibt etwa 20 Begriffe länger als nötig.

**3. Erwartung an die Wand korrigieren statt weiter am Merge drehen.** Die
Gegenrechnung zeigt: selbst bei perfektem Merge blieben **91 echte Einmal-
Nennungen** und nur 46 statt 49 geteilte Knoten. Die Verteilung „langer Schwanz,
wenig Mitte" ist bei 60 Interviews à 5 Begriffen und diesem Konkretheitsgrad
**strukturell**, nicht defekt. `default_min_mentions`=2 (`config.example.toml:57`)
ist die richtige Antwort darauf. *Preis:* die Wand zeigt weiterhin nur rund ein
Drittel der extrahierten Begriffe; alles Einmalige bleibt unsichtbar.

---

## GEMESSEN vs. VERMUTET

**Gemessen:** alle Zeilenangaben und Zitate; keine Schwelle im Code;
`merge_neighbours`=12; 22/26 Partner in Top-12; alle cos-Werte und Ränge (aus dem
lokalen Cache, alle 163 Labels vorhanden); 101 Judge-Gruppen über 60 Interviews,
8 davon leer; die zwei verworfenen p23-Gruppen; der `\\u00fc`-Alias auf
`Mauerroboter`; die Gegenrechnung 163→137 / 114→91.

**Vermutet (als solches markiert):** die Zuordnung „Perspektiv-Varianz ist ein
Effekt des Konkretheits-Prompts" ist eine Interpretation — sie ließe sich nur
durch einen erneuten Extraktionslauf mit geändertem Prompt beweisen, was einen
kostenpflichtigen LLM-Lauf erfordert und deshalb hier unterblieben ist. Ebenso
ist die Grenze zwischen „klarem Duplikat" und „Grenzfall" mein Urteil; ich habe
die Grenzfälle deshalb separat ausgewiesen und aus allen Zahlen herausgehalten.

**Nicht geprüft:** ob ein erneuter Lauf mit gefixten Bugs die vorhergesagten
Zahlen wirklich erreicht — das braucht `ANTHROPIC_API_KEY` und ist kostenpflichtig.
