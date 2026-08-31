// Das Traumbild am Telefon.
//
// Eigenständig, nichts aus frontend2/: die Wand ist eine Fläche, auf der Satz
// und Streifen ÜBER dem formatfüllenden Bild liegen (Umbau 2026-08-30). Am
// Handy im Hochformat geht das nicht — ein 16:9-Traumbild auf 9:16 gelegt und
// beschnitten verliert die halbe Fläche. Hier liegen die drei Dinge deshalb
// untereinander, und das Bild wird eingepasst statt beschnitten (Birks
// Entscheidung 2026-08-26 gilt am Handy erst recht).

/** Wie viele Miniaturen der Streifen höchstens trägt. Die Station schickt
 *  ihren eigenen Wert mit (`strip_max`); dies ist die Obergrenze fürs Handy —
 *  jede Miniatur ist ein Bild, das über ein Konferenz-WLAN geladen wird. */
const MAX_MINIATUREN = 24;

export function createTraumAnsicht(wurzel = document) {
  const bild = wurzel.getElementById('bild');
  const satz = wurzel.getElementById('satz');
  const streifen = wurzel.getElementById('streifen');
  const warten = wurzel.getElementById('warten');
  const lupe = wurzel.getElementById('lupe');
  const lupeBild = wurzel.getElementById('lupe-bild');
  const lupeSatz = wurzel.getElementById('lupe-satz');

  let gezeigt = null; // Bildpfad auf der Bühne, um unnötige Neuladungen zu sparen
  let streifenSchluessel = '';

  // Ein Bild kann fehlen, obwohl der Traumsatz schon da ist: der Uploader
  // schickt erst den Zustand und dann die Datei, und dazwischen liegen ein paar
  // Sekunden Konferenz-WLAN. Ohne das hier zeigt das Telefon in dieser Lücke
  // ein kaputtes Bildsymbol mit dem Alternativtext daneben — das sieht nach
  // Fehler aus, obwohl es nur „gleich" heisst.
  bild.addEventListener('error', () => {
    bild.hidden = true;
  });
  bild.addEventListener('load', () => {
    bild.hidden = false;
  });

  function schliesseLupe() {
    lupe.hidden = true;
    // src leeren, damit ein grosses Bild nicht im Speicher eines schwachen
    // Telefons liegen bleibt, während der Rest der Seite weiterläuft.
    lupeBild.removeAttribute('src');
  }

  function oeffneLupe(traum) {
    if (!traum || !traum.image) return;
    lupeBild.src = traum.image;
    lupeSatz.textContent = traum.sentence || '';
    lupe.hidden = false;
  }

  wurzel.getElementById('lupe-zu').addEventListener('click', schliesseLupe);
  lupe.addEventListener('click', (ereignis) => {
    // Tipp auf den Hintergrund schliesst ebenfalls — auf dem Bild selbst nicht,
    // sonst schliesst sich die Lupe beim Versuch, das Bild anzusehen.
    if (ereignis.target === lupe) schliesseLupe();
  });

  function zeichneStreifen(traeume) {
    // Ein Schlüssel aus den IDs: der Zustand kommt alle paar Sekunden
    // vollständig, und den Streifen jedes Mal neu zu bauen würde einen Wisch
    // mitten in der Bewegung zurücksetzen.
    const schluessel = traeume.map((t) => t.id).join(',');
    if (schluessel === streifenSchluessel) return;
    streifenSchluessel = schluessel;
    streifen.replaceChildren();
    for (const traum of traeume) {
      const eintrag = document.createElement('li');
      const knopf = document.createElement('button');
      knopf.type = 'button';
      knopf.setAttribute('aria-label', traum.sentence || 'Traum');
      const miniatur = document.createElement('img');
      miniatur.src = traum.image;
      miniatur.alt = '';
      // Erst laden, wenn die Miniatur in die Nähe des Sichtfensters gewischt
      // wird: der Streifen kann zwei Dutzend Bilder tragen.
      miniatur.loading = 'lazy';
      miniatur.decoding = 'async';
      knopf.appendChild(miniatur);
      knopf.addEventListener('click', () => oeffneLupe(traum));
      eintrag.appendChild(knopf);
      streifen.appendChild(eintrag);
    }
    streifen.hidden = traeume.length === 0;
  }

  return {
    schliesseLupe,
    applyState(zustand) {
      const aktuell = zustand && zustand.current ? zustand.current : null;

      if (aktuell && aktuell.image) {
        if (aktuell.image !== gezeigt) {
          gezeigt = aktuell.image;
          // Der Traumsatz IST die Bildbeschreibung — dasselbe, was daneben
          // steht, aber für den, der das Bild nicht sieht.
          bild.alt = aktuell.sentence || '';
          bild.src = aktuell.image;
        }
      } else {
        gezeigt = null;
        bild.hidden = true;
        bild.removeAttribute('src');
      }

      satz.textContent = aktuell ? aktuell.sentence || '' : '';
      warten.hidden = Boolean(aktuell);

      // Neueste zuerst: `history` kommt ältestes zuerst (kg2/server.py), und am
      // Handy wischt man von links nach rechts in die Vergangenheit.
      const verlauf = ((zustand && zustand.history) || [])
        .filter((t) => t && t.image && (!aktuell || t.id !== aktuell.id))
        .slice(-MAX_MINIATUREN)
        .reverse();
      zeichneStreifen(verlauf);
    },
  };
}
