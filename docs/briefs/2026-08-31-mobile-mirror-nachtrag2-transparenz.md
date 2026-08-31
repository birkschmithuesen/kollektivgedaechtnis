# Nachtrag 2: Der Datenschutz-Absatz der Startseite

Ergänzung von Birk (2026-08-31), ersetzt den Platzhalter aus Nachtrag 1.
Grundlage: `handoff-landingpage-hosting-datenschutz.md` (ArtesMobiles-Vault).

## Die Regel, die über allem steht

**Nichts im Präsens behaupten, was nicht läuft.** Der Umbau auf europäische
Dienste ist am 2026-08-31 begonnen, aber nicht abgeschlossen; die Station
läuft im Moment noch auf US-Diensten. Eine Transparenzseite, die ihre eigenen
Lücken verschweigt, ist Werbung — und bei einer Arbeit, die KI-Infrastruktur
zum Thema hat, eine stille Selbstwiderlegung.

Deshalb ist der Text unten im **Verlaufsmodus** geschrieben („wir bauen gerade
um"), nicht im Zustandsmodus („alles liegt in Europa").

## Aufbau: kurz auf der Startseite, ausführlich auf einer Unterseite

Die Startseite bleibt ein Wegweiser. Der lange Text bekommt eine eigene
Seite `/transparenz`, verlinkt aus dem kurzen Absatz und aus der Fusszeile.

### Auf der Startseite — wörtlich übernehmen

> **Wo diese Daten verarbeitet werden**
>
> Diese Seite läuft auf einem Server in Deutschland, setzt keine Cookies,
> misst keine Zugriffe und bindet nichts von Dritten ein.
>
> Die Interviews selbst werden von KI-Diensten ausgewertet. Wir stellen diese
> Dienste gerade auf europäische Anbieter um — offen dazu, wo das schon
> gelingt und wo noch nicht. → [Was wo läuft](/transparenz)

Der Pfeil-Link ist ein normaler Link, kein Knopf: er soll die beiden
Haupt-Knöpfe nicht überstimmen.

## Die Seite `/transparenz`

Statisch wie die Startseite, gleiche Gestaltung, keine Live-Verbindung.
Lesbar am Telefon, also kurze Absätze und **keine Tabelle** — die Liste
unten als Aufzählung setzen, jede Zeile „Schritt — Anbieter — Ort".

### Text, wörtlich übernehmen

> **Was wo läuft**
>
> Diese Installation verhandelt Künstliche Intelligenz als gesellschaftliches
> Thema. Sie dabei auf den Rechenzentren amerikanischer Konzerne laufen zu
> lassen, wäre ein stiller Widerspruch. Wir bauen sie deshalb gerade auf
> europäische Infrastruktur um — und zeigen hier, wie weit wir damit sind.
>
> **Diese Webseite**
> Sie läuft auf einem Server in Deutschland (Hetzner). Keine Cookies, keine
> Zugriffsmessung, keine Inhalte von fremden Servern. Sie zeigt nur, was auch
> im Haus auf den Projektionen zu sehen ist.
>
> **Die Auswertung der Interviews — im Umbau**
> Bis zum Ausstellungstag stellen wir um auf:
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
> Das Portraitfoto und der Startimpuls laufen weiterhin über Telegram, das
> nicht in der EU sitzt. Das Interview-Audio ist davon nicht betroffen.
>
> Ob der Anbieter der Bildgenerierung unsere Eingaben zum Training seiner
> Modelle nutzen darf, klären wir gerade. Solange das nicht schriftlich
> geklärt ist, behaupten wir hier nichts anderes.
>
> Wir betreiben für diese Installation keine automatische Anonymisierung.
> Wer interviewt wird, wird vorher gefragt und stimmt zu.
>
> **Warum wir das machen**
> Nicht weil ein Gesetz es verlangt, sondern weil es zur Arbeit gehört. Die
> Kette vom Interview über die Begriffe bis zum erzeugten Bild ist im Haus
> bewusst nachvollziehbar ausgestellt. Diese Seite setzt das eine Ebene
> tiefer fort: auch die Infrastruktur ist Teil des Werks.
>
> Fragen dazu: [birkschmithuesen.com](https://birkschmithuesen.com) ·
> [artesmobiles.art](https://artesmobiles.art)

## Umsetzungshinweise

- Der Umbaustand ändert sich noch. Setze die vier Aufzählungspunkte und die
  Absätze unter „Was dabei offen bleibt" so in die Vorlage, dass sie an einer
  Stelle im Quelltext stehen und ohne Umbau der Seite geändert werden können
  (eine Liste im Python-Modul, aus der die Seite gerendert wird, oder ein
  klar abgegrenzter Block in der HTML-Datei mit einem Kommentar darüber).
- Kein Datum auf die Seite schreiben. Ein sichtbarer Stand, der nicht
  nachgepflegt wird, ist schlechter als keiner.
- `/transparenz` in die Fusszeile aller Seiten aufnehmen.
- Test: `GET /transparenz` liefert 200, auch ohne jede Aufnahme.

## 🔴 Vor der Veröffentlichung

Diese Seite macht Zusagen über den Umgang mit personenbezogenen Daten
Dritter. Sie geht erst online, wenn Birk den Wortlaut freigegeben hat, und
der Wortlaut wird am Ausstellungstag gegen den tatsächlich laufenden Stand
geprüft. Vermerke das in `mirror/README.md`.
