# Nachtrag zum Brief „Mobiler Public-Mirror" — Startseite

Ergänzung von Birk (2026-08-31), nach dem Hauptbrief zu lesen. Alles im
Hauptbrief gilt unverändert; hier kommt eine dritte Seite dazu und die
Wegführung ändert sich.

## Was sich ändert: die Startseite ist neu die Wurzel

Bisher lag der Graph auf `/`. Neu:

| Pfad | Inhalt |
|---|---|
| `/` | **Startseite** (neu) — Begrüssung, Kontext, Datenschutzhinweis, zwei grosse Knöpfe |
| `/graph` | die Graph-Ansicht (lag vorher auf `/`) |
| `/traum` | die Traum-Ansicht (unverändert) |

Öffentlicher Hostname: `kollektivgedaechtnis.flashclash.de`.

Die beiden Reiter oben auf Graph- und Traum-Seite bleiben, damit man
zwischen den Ansichten wechseln kann, ohne über die Startseite zu gehen.
Dazu auf beiden Seiten ein unaufdringlicher Weg zurück zur Startseite.

## Die Startseite

Ruhig, kurz, in einem Blick erfassbar — sie wird im Stehen auf einem Flur
gelesen, nicht studiert. Kein Scrollen bis zu den beiden Knöpfen: die müssen
auf einem 390 × 660 px grossen Schirm ohne Wischen sichtbar sein. Der
Datenschutzhinweis darf darunter liegen.

Aufbau von oben nach unten:

1. Titel **Kollektivgedächtnis**
2. Ein bis zwei Sätze Willkommen und Kontext (Text unten, wörtlich übernehmen)
3. Zwei grosse Knöpfe nebeneinander bzw. untereinander:
   **Der Graph** → `/graph`, **Der Traum** → `/traum`.
   Jeder mit einer knappen Zeile darunter, was einen dort erwartet.
4. Der Datenschutz-Absatz (Text unten, wörtlich übernehmen)
5. Fusszeile mit zwei Links, in neuem Tab, `rel="noopener"`:
   [birkschmithuesen.com](https://birkschmithuesen.com) ·
   [artesmobiles.art](https://artesmobiles.art)

Gestaltung wie die anderen beiden Seiten: dunkler Grund, dieselbe Schrift,
keine neue Formensprache. Reduktion, kein Dashboard. Keine Logos, keine
Bilder, keine Animation — die Seite ist ein Wegweiser, keine Bühne.

## Texte — wörtlich übernehmen, nicht umformulieren

**Willkommen:**

> Während der Konferenz führen wir Interviews. Aus dem, was gesagt wird,
> wächst hier live ein gemeinsamer Graph — und daraus entsteht in Runden ein
> Traumbild. Beides läuft im Haus auf den Projektionen und ist auf dieser
> Seite auch von Ihrem Telefon aus zu sehen.
>
> Eine Arbeit von Birk Schmithüsen und ArtesMobiles.

**Knopf-Untertexte:**

> Der Graph — Wer was gesagt hat, und wie es zusammenhängt.

> Der Traum — Was die Maschine daraus gerade träumt.

**Datenschutz — DIESER ABSATZ IST NOCH NICHT FREIGEGEBEN.**

Der endgültige Wortlaut wird nachgereicht; Birk entscheidet ihn.
Setze bis dahin den folgenden Platzhalter ein, wörtlich:

> Diese Seite läuft auf einem Server in Deutschland. Sie setzt keine Cookies,
> misst keine Zugriffe und bindet nichts von Dritten ein.

Nichts darüber hinaus behaupten. Insbesondere **keine** Aussage darüber, wo
die Interviews verarbeitet werden — das ist eine andere Frage als das Hosting
dieser Seite, und sie ist noch offen. Eine unzutreffende Datenschutzaussage
auf einer öffentlichen Seite ist schlimmer als gar keine.

## Technisch

- Die Startseite ist statisch: keine Live-Verbindung, kein `EventSource`,
  keine Abhängigkeit von einer eingegangenen Aufnahme. Sie muss auch dann
  vollständig funktionieren, wenn die Station gar nicht verbunden ist.
- Kein externes CSS, keine Schrift von einem fremden Server, kein CDN —
  sonst stimmt der Satz „bindet nichts von Dritten ein" nicht mehr.
- Zwei zusätzliche Tests in `tests/test_mirror.py`:
  `GET /` liefert 200 und enthält beide Ziel-Pfade; `GET /graph` liefert die
  Graph-Seite. Beide auch ohne jede vorherige Aufnahme.
