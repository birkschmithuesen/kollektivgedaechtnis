"""Der öffentliche Spiegel der beiden Stationen (Konferenz-Handyansicht).

Zwei Hälften, die sich nie gegenseitig importieren:

* `mirror.receiver` läuft auf herkules und ist von aussen erreichbar,
* `mirror.uploader` läuft auf dem Ausstellungsrechner und schiebt hoch.

Nichts hier importiert aus `kg`, `kg2`, `frontend` oder `frontend2`. Der
Spiegel ist eine eigene, schlanke Ansicht auf dieselben Daten — an der Wand
wird parallel weitergebaut, und eine gemeinsame Datei würde beide Baustellen
aneinander binden.
"""
