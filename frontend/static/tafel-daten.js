// Was auf der Tafel steht, aus dem Graphen gelesen.
//
// Eigene Datei, damit `tafel.js` reine Ansicht bleibt: Sie weiss, wie eine
// Tafel aussieht, nicht wo die Zahlen herkommen. Beide zusammen ersetzen
// nichts — `quote-overlay.js` liest dieselben Felder für die Karte, die auf
// dem Handy und an der Touchfläche richtig ist.
//
// Alles hier kommt aus `graph.json` und kostet keinen zusätzlichen Aufruf:
// Namen und Portraits an den Personenknoten, Zitate im `quotes`-Feld, die
// BELEGSTELLEN an den Kanten (kg/export.py) — nur dort steht, wer einen
// Begriff wie gemeint hat.

export function createTafelDaten() {
  let personen = new Set();   // alle person_ids, auch die ohne Namen
  let namen = new Map();      // person_id -> Name
  let portraits = new Map();  // person_id -> Bildpfad
  let verwandte = new Map();  // term_id  -> [Label, …]
  let widersprueche = [];
  let zitate = new Map();     // person_id -> Text
  let etiketten = new Map();  // term_id  -> Label
  let belegeJeBegriff = new Map(); // term_id  -> [{person_id, evidence}]
  let begriffeJePerson = new Map(); // person_id -> [{term_id, evidence}]

  return {
    setGraph(graph) {
      personen = new Set();
      namen = new Map();
      portraits = new Map();
      etiketten = new Map();
      verwandte = new Map();
      widersprueche = Array.isArray(graph.widersprueche) ? graph.widersprueche : [];
      for (const knoten of graph.nodes || []) {
        if (knoten.type === 'person') {
          // 🔴 EIGENE MENGE und nicht `namen` als Ersatz: Dort landet nur, wer
          // einen Namen hat, und die Namenserkennung faellt regelmaessig aus
          // (STAND.md §2h). „Ohne Namen" ist ein gueltiger Mensch mit Tafel;
          // „nicht im Graphen" ist etwas anderes.
          personen.add(knoten.id);
          const name = (knoten.name || '').trim();
          if (name) namen.set(knoten.id, name);
          if (knoten.portrait) portraits.set(knoten.id, knoten.portrait);
        } else if (knoten.type === 'term') {
          etiketten.set(knoten.id, knoten.label || '');
          if (Array.isArray(knoten.verwandt)) verwandte.set(knoten.id, knoten.verwandt);
        }
      }

      zitate = new Map();
      for (const zitat of graph.quotes || []) {
        // Genau eines je Person (kg/export.py setzt das durch); ein älterer
        // Stand könnte mehrere tragen — dann gilt das erste, dieselbe
        // Regel wie dort.
        if (!zitate.has(zitat.person_id)) zitate.set(zitat.person_id, zitat.text);
      }

      belegeJeBegriff = new Map();
      begriffeJePerson = new Map();
      for (const kante of graph.edges || []) {
        if (!kante) continue;
        const zumBegriff = belegeJeBegriff.get(kante.target) || [];
        zumBegriff.push({ person_id: kante.source, evidence: kante.evidence || '' });
        belegeJeBegriff.set(kante.target, zumBegriff);

        const zurPerson = begriffeJePerson.get(kante.source) || [];
        zurPerson.push({ term_id: kante.target, evidence: kante.evidence || '' });
        begriffeJePerson.set(kante.source, zurPerson);
      }
    },

    person(id) {
      // Dieselbe Regel wie bei `begriff()`: Eine Person, die das Netz nicht
      // mehr zeigt (ausgeblendet, zusammengelegt), hat keine Tafel.
      if (!personen.has(id)) return null;
      const eigene = begriffeJePerson.get(id) || [];
      const meine = new Set(eigene.map((e) => e.term_id));

      // 🔴 „Teilt Themen mit" (Birk, 2026-09-02): Das macht die soziale Nähe
      // LESBAR, die das Layout nur andeutet. Wer im Graphen nebeneinander
      // steht, tut das ja genau deswegen — aber niemand sieht, mit WEM und
      // WORÜBER.
      const zaehler = new Map();
      const gemeinsam = new Map();
      for (const tid of meine) {
        for (const b of belegeJeBegriff.get(tid) || []) {
          if (b.person_id === id) continue;
          zaehler.set(b.person_id, (zaehler.get(b.person_id) || 0) + 1);
          const liste = gemeinsam.get(b.person_id) || [];
          liste.push(etiketten.get(tid) || '');
          gemeinsam.set(b.person_id, liste);
        }
      }
      const nahe = [...zaehler.entries()]
        // Bei Gleichstand der Name, damit zwei Aufrufe dasselbe zeigen.
        .sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])))
        .slice(0, 3)
        .map(([pid, anzahl]) => ({
          id: pid,
          name: namen.get(pid) || 'Ohne Namen',
          portrait: portraits.get(pid) || '',
          anzahl,
          themen: (gemeinsam.get(pid) || []).filter(Boolean),
        }));

      return {
        name: namen.get(id) || '',
        portrait: portraits.get(id) || '',
        zitat: zitate.get(id) || '',
        begriffe: eigene
          .map((e) => ({ kopf: etiketten.get(e.term_id) || '', unter: e.evidence }))
          .filter((e) => e.kopf),
        nahe,
      };
    },

    begriff(id) {
      // 🔴 NICHT MEHR DA HEISST NULL (gefunden 2026-09-03): Ohne diese Zeile
      // gab es fuer jede beliebige id ein Objekt zurueck — mit leerem Label
      // und leeren Stimmen. Beim Antippen kann das nicht vorkommen, beim
      // NACHZIEHEN schon: Begriffe werden automatisch zusammengelegt
      // (`fold_term`, kg/store.py). Die Tafel zeigte dann eine leere Seite mit
      // leerer Ueberschrift, statt zuzugehen.
      if (!etiketten.has(id)) return null;
      const belege = belegeJeBegriff.get(id) || [];
      return {
        label: etiketten.get(id) || '',
        // 🔴 Der eigentliche Gewinn dieser Fläche: dieselbe Sache in
        // verschiedenen Worten. Ein Begriff ist eine Verdichtung — was die
        // Menschen wirklich gesagt haben, steht nur hier.
        stimmen: belege
          .filter((b) => b.evidence)
          .map((b) => ({
            kopf: namen.get(b.person_id) || 'Ohne Namen',
            unter: b.evidence,
            portrait: portraits.get(b.person_id) || '',
          })),
        // Was inhaltlich danebenliegt, auch wenn es niemand zusammen gesagt
        // hat (kg/semantik.py, Kosinus über die vollen Embeddings).
        verwandt: verwandte.get(id) || [],
      };
    },

    /** Der Ruhezustand: die Widersprüche des Tages (kg/widerspruch.py). */
    widersprueche() {
      return widersprueche;
    },
  };
}
