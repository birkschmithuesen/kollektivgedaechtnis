# Vendored browser libraries (mobiler Spiegel)

Eine **Kopie**, kein Link auf `frontend/static/vendor/`. An der Wand wird
parallel weitergebaut; ein gemeinsamer Pfad würde bedeuten, dass ein Austausch
der Bibliothek an der Wand gleichzeitig die öffentliche Handyansicht verändert
— zwei Baustellen, ein Auslöser. Der Preis (373 KB doppelt im Repo) ist
gegenüber dieser Kopplung der günstigere.

| File | Package | Version | Global | Licence |
|---|---|---|---|---|
| `cytoscape.min.js` | cytoscape | 3.x | `cytoscape` | MIT |

**Nur Cytoscape selbst, keine Layout-Erweiterung.** Die Wand lädt zusätzlich
`layout-base` + `cose-base` + `fcose` + `layout-utilities` (zusammen weitere
710 KB), weil sie einen Graphen ohne gespeicherte Positionen frisch legen
können muss. Hier ist das nicht nötig: `graph.json` bringt die an der Wand
berechneten und gespeicherten Positionen (`x`/`y`) mit, und für den seltenen
Fall, dass sie fehlen (frische Station, noch nie gerendert), reicht Cytoscapes
eingebautes `cose`. Über ein Konferenz-WLAN auf ein Handy sind 710 KB
gesparter Download mehr wert als das schönere Layout in einem Randfall.

Auffrischen wie bei der Wand: `npm pack cytoscape`, `package/dist/cytoscape.min.js`
aus dem Tarball kopieren.
