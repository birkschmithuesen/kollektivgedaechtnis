# Offen: Deckt das Bild den Satz, der darüber steht?

**Aufgeworfen von Birk am 2026-08-30**, an einem realen Bild
(`out/vgl-F-massstab/5-60personen.jpg`). Noch **nicht entschieden** — hier
festgehalten, damit die Frage nicht in einem Chatverlauf verschwindet.

## Der Befund

Wandsatz:

> Anwohner und Fachleute mauern Abbruchschutt ins Dorfhaus vor den
> ausgehobenen Kellergruben am Ortsrand.

Birk am Bild: Anwohner und Fachleute sind zu sehen — aber sie mauern **eine
Mauer, nicht das Dorfhaus**, und **ausgehobene Kellergruben sind nicht zu
sehen**. Zwei von drei Aussagen des Satzes stehen nicht im Bild.

Das ist etwas anderes als die bisherigen Bildbefunde. Bisher ging es darum, ob
ein Bild gut ist. Hier geht es darum, dass **Satz und Bild nebeneinander an der
Wand hängen** und der Satz etwas behauptet, das die Besucherin im Bild nicht
findet. Der Satz ist das Textstück der Arbeit; wenn er danebengreift, sieht das
nicht nach einem Traum aus, sondern nach einem Fehler.

## Warum das passiert (Vermutung, NICHT belegt)

Stufe 1 schreibt Satz und `image_description` in einem Zug, beide aus demselben
Material. Stufe 2 rendert nur die `image_description`. Zwischen der
Beschreibung und dem fertigen Bild liegt aber das Bildmodell, das weglässt,
zusammenzieht und umdeutet — und niemand prüft danach, ob vom Satz noch etwas
übrig ist. Der Prompt verlangt ausdrücklich, dass Satz und Beschreibung
DIESELBE Szene meinen; ob das Ergebnis das einhält, wird nie gemessen.

## Die eigentliche Frage (Birk)

> „Das wirft die Frage auf, ob wir diesen Feedbacktest, den du jetzt zur
> Selbstoptimierung gemacht hast, auch in der realen Installation machen, dass
> das Bild noch mal geprüft wird."

Also: Der Rückkopplungs-Test (`sim/probes/rueckkopplung.py`) ist bisher ein
Werkzeug für die Prompt-Entwicklung. Soll er zur **Laufzeit** laufen?

## Was dabei zu bedenken ist (Material für die Entscheidung, keine Empfehlung)

**Dafür:**
- Es ist die einzige Stelle, an der ein Fehler auffällt, bevor er an der Wand
  hängt. Alles andere ist Stichprobe.
- Der Test existiert bereits und misst genau diese Eigenschaft.

**Dagegen / zu klären:**
- **Was passiert bei Nichtbestehen?** Ein zweiter Renderversuch kostet Geld und
  Zeit; Spec §8 sagt ausdrücklich, dass es KEINEN Retry gibt („ride it out"),
  weil ein WLAN-Ausfall sonst die Rechnung verdreifacht. Ein Prüf-Retry wäre
  eine Ausnahme von dieser Regel und muss als solche entschieden werden.
- **Wer entscheidet über „durchgefallen"?** Eine Modellbewertung, die ein Bild
  verwirft, ist ein Automat, der über das Werk urteilt. Das ist genau die
  Rolle, die Birk am 2026-08-30 ausdrücklich für sich behalten hat („Beurteilung
  ab jetzt nur durch mich von Bildern").
- **Ein billigerer Weg:** Nicht das Bild verwerfen, sondern den SATZ nach dem
  Bild wählen. Stufe 1 könnte zwei bis drei Satzfassungen liefern, und nach dem
  Rendern wird die genommen, die das entstandene Bild am ehesten deckt. Kostet
  keinen zweiten Bildaufruf, dreht aber die Reihenfolge um — und der Satz ist
  bisher das Primäre, das Bild folgt ihm.
- **Oder gar nicht zur Laufzeit:** Stattdessen den Prompt so schärfen, dass die
  Deckung von vornherein hoch ist, und die Messung als Entwicklungswerkzeug
  behalten.

## Nächster Schritt

Vor der Entscheidung fehlt eine Zahl: **Wie oft weicht das Bild überhaupt vom
Satz ab?** Ein Befund an einem Bild ist ein Verdacht, keine Häufigkeit. Die
Messung dafür ist klein — die blinde Bildbeschreibung aus
`sim/probes/rueckkopplung.py` liegt schon vor, sie muss nur gegen den SATZ
gehalten werden statt gegen die Begriffe.
