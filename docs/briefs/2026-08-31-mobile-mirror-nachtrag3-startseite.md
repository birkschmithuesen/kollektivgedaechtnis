# Nachtrag 3: Startseite + Transparenzseite bauen — und der Text steht im Präsens

Entscheidung Birk (2026-08-31, nach Nachtrag 2): Der EU-Umbau ist bis zum
Ausstellungstag fertig. Die Seite beschreibt deshalb den **Zustand**, nicht den
Umbau. Alle „wir bauen gerade um"-Formulierungen aus Nachtrag 2 entfallen.

Nachtrag 1 (Wegführung, Startseite, Texte für Willkommen und Knöpfe) gilt
unverändert. Dieser Nachtrag ersetzt nur den Datenschutz-Teil aus Nachtrag 2.

## Was noch zu bauen ist

Der Empfänger steht bereits (`mirror/receiver.py`, 35 Tests grün, von Hand
gegengeprüft). Es fehlen genau drei Dinge:

1. `GET /` liefert derzeit noch die Graph-Ansicht → wird die **Startseite**.
2. Die Graph-Ansicht zieht auf `GET /graph`.
3. `GET /transparenz` ist neu.

`/traum` bleibt, wie es ist. Die Reiter auf Graph- und Traum-Seite müssen nach
der Verschiebung weiter stimmen, und beide Seiten brauchen einen
unaufdringlichen Weg zurück zur Startseite.

## Startseite — der Datenschutz-Absatz, wörtlich

Ersetzt den Platzhalter aus Nachtrag 1:

> **Wo diese Daten verarbeitet werden**
>
> Diese Seite läuft auf einem Server in Deutschland, setzt keine Cookies,
> misst keine Zugriffe und bindet nichts von Dritten ein.
>
> Auch die Auswertung der Interviews läuft auf europäischer Infrastruktur, mit
> offen verfügbaren Modellen. → [Was wo läuft](/transparenz)

Der Pfeil-Link ist ein normaler Link, kein Knopf — er darf die beiden
Haupt-Knöpfe nicht überstimmen.

## `/transparenz` — Text, wörtlich übernehmen

> **Was wo läuft**
>
> Diese Installation verhandelt Künstliche Intelligenz als gesellschaftliches
> Thema. Sie dabei auf den Rechenzentren amerikanischer Konzerne laufen zu
> lassen, wäre ein stiller Widerspruch. Sie läuft deshalb auf europäischer
> Infrastruktur, mit offen verfügbaren Modellen — und hier steht, wo genau.
>
> **Diese Webseite**
> Sie läuft auf einem Server in Deutschland (Hetzner). Keine Cookies, keine
> Zugriffsmessung, keine Inhalte von fremden Servern. Sie zeigt nur, was auch
> im Haus auf den Projektionen zu sehen ist.
>
> **Die Auswertung der Interviews**
>
> - Spracherkennung — Infomaniak, Schweiz
> - Auswertung der Gespräche — Infomaniak, Schweiz, mit offen verfügbaren
>   Modellen
> - Ähnlichkeitsvergleich der Begriffe — Infomaniak, Schweiz
> - Erzeugung der Traumbilder — Black Forest Labs, Deutschland
>
> Infomaniak verarbeitet nach eigener Auskunft ausschliesslich in der Schweiz
> und trainiert seine Modelle nicht mit Kundendaten.
>
> **Was dabei offen bleibt**
> Wir schreiben das dazu, weil eine Transparenzseite ohne ihre eigenen Lücken
> nichts wert ist.
>
> Die Schweiz gehört nicht zur EU. Sie hat ein eigenes Datenschutzgesetz und
> ist von der EU-Kommission als sicheres Drittland anerkannt — der praktische
> Gewinn ist, dass amerikanisches Recht hier nicht zugreift.
>
> Das Portraitfoto und der Startimpuls laufen über Telegram, das nicht in der
> EU sitzt. Das Interview-Audio ist davon nicht betroffen.
>
> Wir betreiben für diese Installation keine automatische Anonymisierung. Wer
> interviewt wird, wird vorher gefragt und stimmt zu.
>
> **Warum wir das machen**
> Nicht weil ein Gesetz es verlangt, sondern weil es zur Arbeit gehört. Die
> Kette vom Interview über die Begriffe bis zum erzeugten Bild ist im Haus
> bewusst nachvollziehbar ausgestellt. Diese Seite setzt das eine Ebene tiefer
> fort: auch die Infrastruktur ist Teil des Werks.
>
> Fragen dazu: [birkschmithuesen.com](https://birkschmithuesen.com) ·
> [artesmobiles.art](https://artesmobiles.art)

**Nicht ergänzen, nicht ausschmücken.** Insbesondere nicht behaupten, der
Anbieter der Bildgenerierung trainiere nicht mit den Eingaben — das ist
ungeklärt, und deshalb steht dazu bewusst nichts auf der Seite. Der Absatz
„Was dabei offen bleibt" wird nicht gekürzt; er ist der Grund, warum der Rest
glaubwürdig ist.

## Umsetzung

- Beide Seiten statisch: kein `EventSource`, keine Abhängigkeit von einer
  eingegangenen Aufnahme. Sie funktionieren auch, wenn die Station gar nicht
  verbunden ist.
- Kein externes CSS, keine Schrift von einem fremden Server, kein CDN — sonst
  stimmt „bindet nichts von Dritten ein" nicht mehr.
- Die vier Aufzählungspunkte der Dienste an **einer** Stelle im Quelltext, mit
  einem Kommentar darüber: sie ändern sich, wenn sich der Stack ändert, und
  das darf kein Umbau der Seite sein.
- Kein Datum auf die Seite. Ein sichtbarer Stand, der nicht nachgepflegt wird,
  ist schlechter als keiner.
- `/transparenz` in die Fusszeile aller Seiten.
- Gestaltung wie die bestehenden Seiten: dunkler Grund, gleiche Schrift, keine
  neue Formensprache. Keine Logos, keine Bilder, keine Animation.
- Auf einem 390 × 660 px grossen Schirm müssen die beiden Knöpfe der
  Startseite ohne Wischen sichtbar sein; der Datenschutz-Absatz darf darunter
  liegen.

## Tests in `tests/test_mirror.py` ergänzen

- `GET /` → 200, enthält `/graph` und `/traum`, auch ohne jede Aufnahme.
- `GET /graph` → 200, liefert die Graph-Seite.
- `GET /transparenz` → 200, auch ohne jede Aufnahme.
- Die bestehenden 35 Tests bleiben grün. Wo einer auf `/` als Graph-Seite
  prüft, wird er auf `/graph` umgestellt — nicht gelöscht.

## Randbedingungen

Wie im Hauptbrief: nur `mirror/` und `tests/test_mirror.py` anfassen,
`frontend/`, `frontend2/`, `kg/`, `kg2/` unberührt lassen (dort arbeitet eine
parallele Session), keine Geheimnisse im Repo, `git add` nur mit ausdrücklichen
Pfaden, Commit auf `mobile-mirror` mit deutschem Titel.

Zum Schluss: `pytest tests/test_mirror.py` im **Vordergrund** laufen lassen und
die echte Zahl berichten.
