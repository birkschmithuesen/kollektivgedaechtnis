# Nachbereitung — Bestandsaufnahme

**Projekt:** Kollektivgedächtnis, NEW BAUHAUS Festival, Weimarhalle
**Zeitraum:** 2026-08-12 (erster Commit) bis 2026-09-03
**Erstellt:** 2026-09-03, nach den beiden Ausstellungstagen

---

## Was dieses Dokument ist — und was nicht

Es ist eine **Bestandsaufnahme**, keine Bewertung. Es sagt, was war, nicht was
daraus folgt. Wer daraus Schlüsse zieht, zieht sie selbst.

**Quellenlage.** Aufgenommen ist nur, was sich belegen lässt:

| Quelle | wofür |
|---|---|
| `git log` (374 Commits) | Zeitpunkte und Themen der Änderungen |
| `data/kg.db` | Personen, Begriffe, Kanten, Belegstellen, Zusammenlegungen |
| `dream-data/dreams.sqlite3` | alle 27 Träume samt **vollständigem Prompt** |
| `docs/STAND.md` (2073 Zeilen) | die laufende Chronik der Sessions |
| Messungen am laufenden System | die Abschnitte zum 2./3. September |

**Wo die Belege dünner sind:** Die Zeit vor dem 2026-09-02 kenne ich nur aus
Commits und `STAND.md` — dort steht, was frühere Sessions notiert haben, nicht
was ich selbst gemessen habe. Solche Stellen sind mit *(aus STAND.md)*
gekennzeichnet. Der 2. und 3. September sind durchgehend selbst gemessen.

**Nicht enthalten:** Beobachtungen aus dem Raum (wie Besucher reagiert haben,
wie die Gespräche liefen). Dafür gibt es keine Aufzeichnung im Repo.

---

## Der Bestand in Zahlen

**Interviews und Graph** (Stand 2026-09-03, 12:00):

```
Personen gesamt            34        Begriffe                65
davon sichtbar             25        Kanten                 134
mit erkanntem Namen        25        davon mit Belegstelle  134  (100 %)
mit Portrait               28        Aliase                 177
                                     Zusammenlegungen        26
Zitate                     26
```

**Interviews pro Tag:** 2026-09-02: 25 · 2026-09-03: 9

**Träume:** 27, alle mit Status `done`, keiner verworfen.
Erster: 02.09. 11:02 · letzter: 03.09. 12:01.

**Commits pro Tag** — die Verteilung zeigt, wann gearbeitet wurde:

```
12.08.   6   Entwurf und Freigabe Tool 1
13.08.  32   Grundgerüst, Konfiguration
14.08.  10
15.08.   1   Umstellung der Projektion auf fcose
19.08.  10   Lesbarkeitsleiter, Überlappungsmessung
25.08.   4   Namenssperre nach der ersten geteilten Nennung
26.08.  55   Tool 2 (Kollektivtraum), 18 Aufgaben
27.08.   6   Verlaufsstreifen
28.08.  10   zwei Merge-Fehler
29.08.  22   Aktualitätsblock im Traumprompt
30.08.  34   Widerspruch sichtbar machen
31.08.  53   theme-f nach dem echten Rendering
01.09. 100   der letzte Tag vor der Ausstellung
02.09.  31   erster Ausstellungstag
03.09.   0   (Arbeit am zweiten Tag ist noch nicht committet)
```

---

## 1. Was musste von Hand nachgebessert werden?

### Fotos, die der falschen Person zugeordnet wurden

**Vier Vorfälle am 2026-09-02**, jeweils von Birk an der Wand bemerkt und von
Hand repariert (p3/p4/p5, später zwei weitere). Die Reihenfolge war immer
dieselbe: Ein Foto wurde kurz nach dem Interviewende geschossen und landete
noch beim gerade beendeten Gespräch statt beim nächsten.

Reparaturen am Verfahren, in dieser Reihenfolge:

1. Nachlauf am „Interview beenden"-Knopf: **6 s**, auf Birks Wunsch dann **8 s**
2. Das reichte nicht — Ursache war nicht der Knopf, sondern die
   Sprecherpausen-Erkennung (VAD), die bei durchgehendem Sprechen nie auslöst
3. **60-Sekunden-Regel** (`kg/core.py`, `NACHREICH_FENSTER_S = 60.0`): Ein Foto,
   das später als 60 s nach Interviewende kommt, gehört zum **nächsten**
   Interview und wird bis dahin geparkt
4. **VAD-Auslöser am Stop-Knopf** (`kg/vad_satzende.py`, neu): Der Knopf hebt
   die Schwelle kurz an und erzwingt damit ein Satzende

### Namen

*(aus STAND.md)* Die Namenserkennung fiel wiederholt aus; bei drei aufeinander
folgenden Interviews wurde der Name nicht erkannt. Ein Name musste aus einem zu
spät gestarteten Interview von Hand rekonstruiert werden.

**Stand heute:** 25 von 34 Personen tragen einen Namen. „Ohne Namen" ist im
Code als gültiger Fall geführt, nicht als Fehler.

### Begriffe: zusammenlegen und trennen

**Automatisch zusammengelegt:** 26 Entscheidungen (`merge_decision`), 177 Aliase.

**Von Hand nachgebessert** — belegt für den 2./3. September:

| Datum | Eingriff | Anlass |
|---|---|---|
| 02.09. | „KI-Grundrissplanung" untersucht und aufgeteilt | Birk: Begriff überladen |
| 02.09. | Drei Begriffe zu Martin Kranz umgehängt | falsche Person |
| 02.09. | Johan Pijpers zu „Routinearbeiten" einsortiert | fehlende Verbindung |
| 02.09. | Zwei Interviews als eine Person zusammengelegt | dieselbe Person zweimal |
| 02.09. | Alle Belegzitate durchgesehen, zu lange gekürzt | Birk: Aussagekraft |
| 03.09. | „Menschen mitnehmen" → „Involvierung der Menschen" | Antje Simon isoliert |
| 03.09. | „basisdemokratische Entwicklungen" → „Stimmrecht vom Volk" | dito |
| 03.09. | „Flächeneffizienz" → „Naturierung statt Flächenverbrauch" | dito |
| 03.09. | Neuer Begriff **„kleinere Wohnflächen"**, zwei Belege umgehängt | „Verzicht auf Keller" sammelte Aussagen, die nicht vom Keller handelten |
| 03.09. | Testinterview p27 samt 4 Begriffen gelöscht | Test von Birk |

**Der Fall Antje Simon (03.09.)** ist der klarste Beleg für die eine Richtung:
Alle sechs ihrer Begriffe waren Einmal-Nennungen, obwohl es im Netz Partner
gab. Nach den drei Zusammenlegungen hängt sie an Themen mit 4, 5 und 7 Stimmen.

**Der Fall „Verzicht auf Keller" (03.09.)** ist der Beleg für die andere: Von
vier Belegstellen handelten zwei nicht vom Keller —

```
Laurens Van Roijen: verzichten würde ich tatsächlich auf den Keller        ✓
Dennis Sterz:       Wer auf den Keller verzichtet …                        ✓
Martin Kranz:       Also die Räume, ob Schlafräume, Aufenthaltsräume …     ✗
René Gabriel:       dass wir die Wohnfläche deutlich verringern …          ✗
```

Bei allen Eingriffen galt Birks Vorgabe vom 02.09.: **„du darfst auf keinen
Fall den Inhalt verändern oder etwas dazu erfinden."** Verschoben wurden
Zuordnungen, nie Wortlaute.

### Die Begriffsnamen selbst — eine Durchsicht am Ende des zweiten Tages

Am 2026-09-03, nach Abschluss der Interviews, wurden **alle 65 Begriffe mit
ihren Belegstellen gelesen** und neun davon umbenannt. Anlass war Birks
Beobachtung an einem einzelnen Namen („der Begriff 'Entrümpeln statt Neubau'
passt glaube ich nicht so ideal"), die Durchsicht danach ging über den ganzen
Bestand.

| bisher | jetzt | Stimmen | warum |
|---|---|---|---|
| Entrümpeln statt Neubau | **Bestand nutzen statt neu bauen** | 8 | „Entrümpeln" sagten 3 von 8; die Mehrheit sprach von Bestand, Leerstand, Sanieren |
| Sozialgemeinschaftsleben | **Orte der Begegnung** | 6 | Kunstwort, das niemand gesagt hat — im Material: „dritter Ort", „konsumzwangfrei in Begegnung bringen" |
| Naturierung statt Flächenverbrauch | **Weniger Fläche verbrauchen** | 7 | „Naturierung" sagte nur einer; die anderen sprachen von Fläche sparen |
| Umstrukturierung der Planung | **Bauvorschriften vereinfachen** | 6 | zu vage — im Material: „weniger Regulatorik", „die vielen Verordnungen entrümpeln" |
| Stimmrecht vom Volk | **Betroffene entscheiden mit** | 5 | sprachlich schief; im Material: „die, die es betrifft", „die wirklich Nutzenden" |
| Involvierung der Menschen | **Menschen einbeziehen** | 4 | Denglisch |
| Naturrespekt als Lebensweise | **Im Einklang mit der Natur leben** | 3 | Kunstwort |
| Kinder als Akteure der Entwicklung | **Junge Menschen einbeziehen** | 3 | sperrig |
| Mobilität in Kisten | **Riesige Kisten für eine Person** | 1 | der Name klang neutral, die Aussage war Kritik: „riesengroßen Kisten. Da wird EINE Person befördert" |

Das jeweils alte Etikett bleibt als **Alias** erhalten — künftige Nennungen
werden darüber zugeordnet, sonst liefe eine neue „Naturierung"-Aussage in einen
zweiten Knoten. Zwei der Namen standen als TEXT in den fixierten Widersprüchen
und mussten dort mitgezogen werden.

**Ein Muster, das dabei sichtbar wurde:** Die schiefen Namen sind fast alle
Kunstwörter, die in keinem einzigen Beleg vorkommen — „Sozialgemeinschaftsleben",
„Naturierung", „Naturrespekt". Sie entstehen beim ersten Auftreten eines
Begriffs aus einem einzelnen Interview und werden nie wieder überprüft, während
später fünf weitere Menschen etwas dazu sagen, das den Namen längst überholt
hat.

### 🔴 Müll aus einem leeren Interview stand an der Wand

Ebenfalls am 2026-09-03 gefunden: Aus einem Interview um 12:58 (8082 Zeichen
Transkript, ein Gespräch ohne verwertbaren Inhalt) war die **Fehlermeldung des
Modells als Daten in den Graphen gelangt** — und war sichtbar:

```
Person p37, Name:  „Keine Namensnennung, keine relevanten Informationen
                    über Begriffe oder Zitate."
Begriff t91:       „Keine Konversation, Zufriedenheit mit Noteneingabe,
                    Suche nach Essen"   — Belegstelle: „4-10"
Begriff t90:       „4-10"               — hing an niemandem
```

Alle drei wurden gelöscht. **Der Weg dorthin ist nicht untersucht:** Die
Auswertung hat ihre eigene Absage („keine relevanten Informationen") als
Ergebnis behandelt, statt das Interview als leer zu verwerfen.

### Zwei Belegstellen ohne Nachweis

Zwei Zitate ließen sich in den Transkripten nicht nachweisen und wurden **nicht**
erfunden: Daniela „auch mit Lehm", Steffen „In jedem Fall die, die es betrifft".

### Sätze unter den Traumbildern

Am 02.09. wurden **alle bestehenden Traumsätze nachträglich in Haikus
umgeschrieben**, nachdem die Haiku-Erzeugung eingebaut war. Das ist an den
Daten sichtbar: Traum d1 (02.09. 11:02) trägt heute ein Haiku, obwohl die
Haiku-Stufe erst am Abend entstand.

---

## 2. Wie hat sich der Traumprompt verändert?

Jeder Traum speichert seinen vollständigen Prompt. Die folgende Tabelle ist aus
`dreams.sqlite3` gelesen — welche Materialblöcke enthalten waren:

```
Traum  Zeit         Länge   P/B      geteilt  Randnotizen  zuletzt gezeigt
d1     02.09 11:02  13398Z   1P/ 5B     –          –             –
d2     02.09 11:11  13856Z   2P/10B     x          x             –
…
d10    02.09 13:32  15572Z  10P/34B     x          x             –
d11    02.09 13:50  17462Z  11P/37B     x          x             x   ← neu
…
d19    02.09 16:18  16955Z  18P/58B     x          –             x
d22    02.09 16:59  18112Z  21P/55B     x          x             x
d23    03.09 10:49  15894Z  22P/59B     x          –             x
d27    03.09 12:01  16076Z  25P/67B     x          –             x
```

**Ablesbar:**

- Der Prompt wuchs von **13 398 auf bis zu 19 296 Zeichen** (d21), zuletzt
  16 076 Zeichen
- **d2:** „Geteilte Begriffe" und „Randnotizen" kamen dazu
- **d11 (02.09. 13:50):** Der Block **„Zuletzt gezeigt"** kam dazu — die letzten
  drei Wandsätze als Negativliste. Anlass war Birks Beobachtung: *„Lehm kam in
  jedem Bild vor."* Jeder Traum entsteht als eigener Aufruf ohne Kenntnis der
  vorigen, traf bei gleichem Material also dieselbe naheliegende Wahl.
- **Randnotizen** erscheinen ab d19 unregelmäßig — sie hängen am
  Einmal-Nennungs-Budget, das je nach Bestand greift

### Die Änderungen an der Begriffsauswahl, chronologisch

| Datum | Änderung | Anlass (Birks Worte, wo belegt) |
|---|---|---|
| 29.08. | Aktualitätsblock: die jüngsten Begriffe | *(aus STAND.md)* |
| 30.08. | **Mechanische Pflichtliste** (`select_required`) statt Prosa-Bitte im Prompt | „Wie oft ein Begriff genannt wurde … das sind harte Zahlen. Da könntest du doch einfach mit einem Script die Liste machen." |
| 02.09. | **Verbundenheit schlägt Häufigkeit** — drei Stufen (eigene / verbundene / Rest) | „alle Begriffe … sollen sehr eng an der letzten interviewten Person dran sein" |
| 02.09. | Nähe = **Abstand im Layout** statt geteilter Sprecherschaft | „Die blauen Nachbarn sind oftmals über eine andere Person verbunden und erscheinen daher im Graphen sehr weit auseinander" |
| 02.09. | Zitate: nur noch das der interviewten Person | „werf auch die 3 letzten zitate raus" |
| 02.09. | **Haiku statt Prosasatz** unter dem Bild, eigener LLM-Aufruf, eigenes Modell | Birks Wunsch; Bedingung: bleibt bei Infomaniak (EU) |
| 02.09. | Bildinhalt: weniger Erfundenes, keine klischeehaften Rollenbilder | „außerdem gab es immer sehr klischeehafte rollenbilder. fast immer familie" |
| 02.09. | Menschen im Bild diverser | „people of color und diverse und queere menschen dürfen auch zu sehen sein" |
| 03.09. | **Nur noch das letzte Interview** — die drei Stufen werden vom Vorrang zum Filter; Materialblock zeigt nur ihre Begriffe | „ändere die auswahl der begriffe … so, dass nur das letzte interview visualisiert wird" |

**Wirkung der letzten Änderung, am Bestand vom 03.09. gemessen** — Materialblock
für dieselbe Person, vorher und nachher:

```
vorher (ganzer Tag)                        nachher (nur die letzte Person)
9× Verschiedene Wohnformen für alle        5× KI plant und gestaltet mit
7× Entrümpeln statt Neubau                 4× Verzicht auf Keller
6× KI nimmt Routinearbeit ab               2× Wohnzentren statt Einzelwohnungen
6× Naturierung statt Flächenverbrauch
6× Sozialgemeinschaftsleben
6× Umstrukturierung der Planung
5× KI plant und gestaltet mit
5× Mehr Grün in Städten
```

Die Negativliste „Zuletzt gezeigt" blieb dabei bestehen.

---

## 3. Was wurde technisch geändert — und was ging schief?

### Neue Bausteine (2./3. September)

| Datei | Zweck |
|---|---|
| `kg/vad_satzende.py` | erzwingt ein Satzende am Stop-Knopf |
| `kg/widerspruch.py` | findet Widersprüche, ein LLM-Aufruf nach jedem Interview |
| `kg/semantik.py` | t-SNE über die Embeddings, semantische Lage und Nachbarn |
| `kg2/haiku.py`, `kg2/silben.py` | Haiku statt Prosasatz, mit Silbenzählung |
| `frontend/static/tafel.js` | die Tafel — eigener Bereich neben dem Netz |
| `frontend/static/tafel-daten.js` | ihr Inhalt aus `graph.json` |
| `frontend/static/nachbarschaft.js` | Hervorhebung beim Antippen |
| `scripts/sichern-in-cloud.sh` | Sicherung der Interviewdaten |

### Fehler im Betrieb — was schiefging

**Ein Live-Ausfall, selbst verursacht (03.09.):** `git checkout` auf
`frontend/static/touch-controls.js`, um eine Testmutation zurückzunehmen — die
Datei hatte unversionierte Änderungen. Damit verschwand der „Bedeutung"-Knopf,
auf den `projection.html` zugreift; **die Projektionsseite brach beim Aufbau ab
und blieb leer.** Rekonstruiert aus den Tests. Regel daraus, im Repo notiert:
nie `git checkout` auf eine modifizierte Datei; Mutationsproben laufen über
Kopien außerhalb des Arbeitsverzeichnisses.

**Doppelter TOML-Schlüssel (02.09.):** Ein Eintrag wurde angehängt statt
geändert — `default_strip_max` stand zweimal in `config2.toml`, die Datei war
damit unlesbar. *(Aus STAND.md geht hervor, dass genau dieser Fehler in der
Nacht zuvor schon einmal die Station gestoppt hatte.)*

**Whisper-/Infomaniak-Ausfall (02.09.):** *(aus STAND.md)* Der Anbieter
antwortete zeitweise nicht. Daraus entstand: Die Wand sagt es jetzt selbst,
statt es in Zeile 14 000 des Protokolls zu verstecken.

**Der Schlüssel in der Befehlszeile (02.09.):** *(Commit)* Ein API-Schlüssel
stand als Argument im Aufruf — `argv` liest jeder Prozess mit. Behoben.

### Drei Fehler in der Datenhaltung, in der laufenden Ausstellung gefunden

1. **`fold_term` verlor Belegstellen** — betraf jede automatische
   Zusammenlegung. 134 von 134 Kanten tragen heute eine Belegstelle.
2. **`interview_end_index` schnitt Transkripte ab** — 26 von 91 Belegzitaten
   erschienen dadurch als „nicht auffindbar".
3. **`last_person_id` zeigte auf das noch laufende Interview** — die
   Traumverankerung an der zuletzt befragten Person war damit wirkungslos.

### Fehler im Zeichnen des Netzes (03.09.)

Von Birk an der Wand bemerkt: *„Der Node … hat sich nun mit René Gabriel
connected und dabei ein neues Label bekommen. Dieses neue Label war aber noch
nicht im Node."* Eine Ursache, drei Auswirkungen:

| Feld | vorher | jetzt |
|---|---|---|
| `label` | blieb nach dem Zusammenlegen das alte | wird nachgezogen |
| `mentions` | fror auf dem Wert beim ersten Erscheinen ein | wächst mit |
| `boxW`/`boxH` | Maß passte zum alten Wort | wird neu gemessen |

`mentions` trägt Größe und Randstärke der Begriffstafeln — ein von zehn
Menschen genannter Begriff sah dadurch aus wie eine Einmal-Nennung.

---

## 4. Welche Fehler waren nur am gerenderten Bild zu sehen?

Am 2026-09-03 stand die Testsuite auf **1589 Tests grün, kein einziger rot** —
und die Wand zeigte trotzdem folgendes:

| Fehler | gemessen | von Tests gefunden |
|---|---|---|
| Angetippter Knoten lag außerhalb des Bildes | x=1615 auf 1286 px Fläche; 1 von 5 Nachbarn sichtbar | nein |
| Zitatkarte lag zusätzlich zur Tafel über dem Netz | Option `stumm` war deklariert, wurde nirgends gelesen | nein |
| Schrift auf der Tafel unlesbar | Belege 6,8 px, Marken 5,2 px — bei kalibrierten 14 px Untergrenze | nein |
| Auswahl blieb nach dem Rückfall stehen | Wand fuhr weiter, Tafel erklärte einen weggefahrenen Knoten | nein |
| Hervorhebung im Spiegel überlebte keine 3 s | jeder Push setzt die Klassen neu | nein |
| Blatt im Spiegel verdeckte das ganze Netz | Netz y=248…562, Blatt ab y=236 | nein |

**Gemeinsame Ursache, soweit belegbar:** Der Testgraph hat 5 Knoten, die Wand
hatte an dem Tag 76. Bei fünf Knoten passt immer alles ins Bild — „die Auswahl
ist sichtbar" und „alles ist sichtbar" fallen zusammen und lassen sich nicht
unterscheiden.

**Gegenmaßnahme, eingebaut:** `tests/test_tafel.py` hat jetzt ein eigenes großes
Netz (72 Knoten, weit gespannt) mit den kalibrierten Werten der Wand — und
einen Test, der als Vorbedingung prüft, dass die Kamera darin überhaupt fahren
**muss**. Fällt der, prüfen alle darunter nichts mehr.

**Ehrlich vermerkt:** Zwei der neuen Verhaltenstests fangen den Rückbau
trotzdem nicht — ohne laufenden Kern bleibt die Wand im Testaufbau in der
Vollansicht, wo ohnehin alles sichtbar ist. Bewiesen wird der Fix von einem
Test, der die Entscheidung selbst misst.

---

## 5. Welche Werte wurden vor Ort kalibriert?

**Im Kern gespeichert** (`data/kg.db`, Stand 03.09.):

```
camera_min_label          12.0     (Wand)
plenum_camera_min_label   16.0     (Plenarsaal)
camera_mode               pan
camera_speed              0.25
max_terms                 80
portrait_size            235.0
plenum_hinweis_dauer      10.0
```

**Im Code festgelegt:**

| Wert | Stand | Anlass |
|---|---|---|
| `--quote-scale` | **0,4** | „Die Zitate sind auf dem realen Schirm viel zu groß, mach die Maße auf 40 %" |
| `--quote-schrift` | **0,8** | „das Zitat im Touchscreen ist viel zu klein, die Schrift wesentlich größer" — der Flächenregler hatte die Schrift mitverkleinert |
| `NACHREICH_FENSTER_S` | **60,0 s** | „wenn ein foto später als 60 sec nach interview stop geschossen wurde, dann gehört es zum nächsten interview" |
| Nachlauf am Stop-Knopf | 6 s → **8 s** | Fotozuordnung |
| `REQUIRED_TERMS` | 5 | Pflichtbegriffe je Bild |
| `RECENCY_SHARE` | 0,4 | Anteil „jüngste Begriffe" |
| `NEIGHBOUR_SHARE` | 0,4 | Anteil „Nachbarschaft" |
| `SHARED_TERMS_MAX` | 8 | Zeilen im Materialblock |
| `SINGLE_MENTION_BUDGET` | 20 | Einmal-Nennungen im Prompt |
| Slideshow-Takt | 8 s Bild, 1,2 s Überblendung | |
| t-SNE `perplexity` | 10 | gemessen: 54,8 % Nachbarschaftstreue gegen 31 % bei MDS/PCA |

**Ein Wert, der zurückgenommen wurde:** Eine Empfehlung, `camera_min_label` auf
30 zu setzen, wurde von Birk als Denkfehler zurückgewiesen — es solle sich alles
aus der Mindestschriftgröße ergeben. Der Wert blieb.

---

## 6. Was wurde gebaut und wieder zurückgenommen?

| Was | gebaut | zurückgenommen |
|---|---|---|
| Widerspruchsblock im Ruhezustand der Tafel | 02.09. abends, auf Wunsch („mache das design dafür richtig gut") | 03.09. („nimm den part wieder raus. in der idle ansicht soll keine seitenleiste da sein") |
| „Bedeutung"-Knopf an der Wand | 02.09. | 02.09. abends kurz entfernt („nimm den bedeutungs button wieder raus für jetzt"), danach wieder da |
| Randnotizen im Traumprompt | 02.09. | erscheinen ab d19 nur noch unregelmäßig |
| Leitfrage im Traum | *(aus STAND.md, 31.08.)* | ersatzlos entfallen — „Ja, ganz weg" |
| Farbcode-Legende im Spiegel | vorhanden | 02.09. verborgen („bei dem Spiegelview soll das Color Coding weg") |

Die Widerspruchsberechnung läuft weiter und steht in `graph.json` — nur die
Anzeige ist entfernt. Der Block im Code ist erhalten; ein Aufruf zeigt ihn
wieder.

---

## 7. Was ist offen geblieben?

**Am Verfahren:**

- **`kg/merging.py` ist nicht angefasst.** Beide Fehlerrichtungen sind belegt
  (Antje Simon: zu streng; „Verzicht auf Keller": zu großzügig) und werden
  wiederkommen, solange dort nichts geschieht.
- **Ein Begriff ohne semantische Nachbarn:** „Verschiedene Wohnformen für alle"
  war am 03.09. der einzige von 55 Begriffen ohne `verwandt`-Einträge. Sein
  Embedding ist vorhanden und vollständig (3584 Dimensionen). Nach dem Neustart
  hatte er drei. Ursache nicht ermittelt.
- **Zwei Belegstellen ohne Nachweis** (Daniela, Steffen) — bewusst nicht erfunden.

**🔴 Was daraus folgt — die einzige Empfehlung in diesem Dokument:**

Es bräuchte einen **wiederkehrenden Lauf über alle Begriffe** (Cron-Job), der
in Abständen dasselbe tut, was am 2026-09-03 von Hand geschah:

- prüfen, ob der NAME noch trägt, was die inzwischen hinzugekommenen
  Belegstellen sagen — die neun Umbenennungen oben betrafen fast nur Begriffe,
  deren Etikett aus dem ersten Interview stammte und von fünf späteren
  überholt worden war
- prüfen, ob zwei Begriffe dasselbe meinen (Antje Simons „Menschen mitnehmen"
  neben „Involvierung der Menschen") …
- … und ob einer zwei Dinge meint („Verzicht auf Keller" sammelte Aussagen über
  Wohnflächen; „KI-Grundrissplanung" musste am 02.09. geteilt werden)
- Ergebnisse einer Auswertung erkennen, die keine sind („Keine relevanten
  Informationen" als Begriff)

Alles davon ist an einem Ausstellungstag von Hand gemacht worden, mehrfach und
unter Zeitdruck, und jedes Mal erst, nachdem es jemandem an der Wand aufgefallen
war. Das ist die Arbeit, die sich am deutlichsten wiederholt hat.

**Nicht enthalten in dieser Empfehlung:** wie oft er laufen sollte, ob er
selbst ändern oder nur vorschlagen darf, und wie verhindert wird, dass er
Namen ändert, die jemand bewusst gesetzt hat. Das sind Entscheidungen, keine
Befunde.

**An den Flächen:**

- Die **eigene Slideshow des Spiegels** wird vom Schalter im Traum-Bedienpult
  nicht erreicht.
- Eine **exakte Kopie der `/projection`-Ansicht** auf dem Spiegel war gewünscht
  und wurde zurückgestellt; stattdessen bekam der Spiegel Hervorhebung,
  Seitenleiste und beide Anordnungen in seiner eigenen Bauweise.

**Am Betrieb:**

- Der Spiegel läuft auf herkules **ohne Git** — Änderungen werden per `scp`
  kopiert. Sicherungen liegen unter `~/backups/kg-mirror-web-<zeitstempel>/`.
- Die Arbeit des 2026-09-03 ist **noch nicht committet**.

---

## Anhang: die drei Widersprüche des Tages

Aus `data/kg.db` (Stand 03.09.), von `kg/widerspruch.py` erzeugt — jede Seite
mit wörtlicher Belegstelle:

1. **Sanierung als Hoffnung und als Bedrohung**
   *Entrümpeln statt Neubau* (Vicki) ↔ *Wohnungszwangssanierung* (Reza)
2. **Mehr Platz zwischen Häusern oder effizienter verdichten**
   *Mehr Platz zwischen Häusern* (Franka Klein) ↔ *Naturierung statt
   Flächenverbrauch* (Viktor Mechtcherine)
3. **Systembruch oder behutsame Evolution**
   *Umstrukturierung der Planung* (Vicki) ↔ *Evolution statt Revolution*
   (René Gabriel)
