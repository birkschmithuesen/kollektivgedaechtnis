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
const MAX_MINIATUREN = 40;

// ---------------------------------------------------------------------------
// Die Slideshow (Birk, 2026-09-02, am Abend des Ausstellungstags)
// ---------------------------------------------------------------------------
// 🔴 „Die Träume sollten als Slideshow mit Überblendung durchlaufen."
//
// Der Anlass: Am Abend werden keine Interviews mehr geführt, es entsteht also
// kein neuer Traum mehr. Die Seite zeigte dann stundenlang EIN Bild — den
// letzten Traum von 16:59. Die Slideshow macht aus dem Bestand des Tages
// wieder etwas, das läuft.
//
// Sie greift NUR, wenn nichts Neues mehr kommt: Sobald die Station einen
// frischen Traum schickt, springt die Anzeige dorthin und beginnt von vorn.
// Ein Abend ohne Interviews ist der Regelfall dieser Schleife, ein Abend mit
// welchen unterbricht sie ohne Zutun.

/** Wie lange ein Bild steht, bevor das nächste aufblendet. Birks Vorgabe. */
const BILD_DAUER_MS = 8000;

/** Die Blende. Dieselbe Länge wie an der Wand (`default_fade_ms` in kg2) —
 *  wer beides an einem Abend sieht, soll denselben Rhythmus erkennen.
 *  Muss zur `transition` in dream.css passen. */
const BLENDE_MS = 1200;

export function createTraumAnsicht(wurzel = document) {
  const bild = wurzel.getElementById('bild');
  const bildBlende = wurzel.getElementById('bild-blende');
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

  // --- Die Slideshow -------------------------------------------------------
  //
  // `alleTraeume` ist der Vorrat in der Reihenfolge, in der die Träume
  // entstanden sind — der aktuelle zuletzt. `stelle` zeigt auf das gerade
  // Sichtbare, `oben` sagt, welche der beiden Bildebenen vorn liegt.
  let alleTraeume = [];
  let stelle = 0;
  let oben = bild;
  let unten = bildBlende;
  let uhr = null;

  /** Ein Bild einblenden, das andere darunter stehen lassen.
   *
   * Der Kern der Blende: Das NEUE Bild wird unsichtbar geladen, erst nach
   * `load` sichtbar geschaltet und dann eingeblendet. Ohne das Warten auf
   * `load` blendet die Seite auf ein Bild, das noch gar nicht da ist — über
   * ein Konferenz-WLAN sieht man dann eine Sekunde lang nichts. */
  function blendeAuf(traum) {
    if (!traum || !traum.image) return;
    satz.textContent = traum.sentence || '';
    unten.alt = traum.sentence || '';

    const zeigen = () => {
      unten.hidden = false;
      unten.style.opacity = '0';
      // Ein Frame Pause, sonst fasst der Browser Setzen und Ändern zu einem
      // Schritt zusammen und es gibt keine Blende, sondern einen Schnitt.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          unten.style.opacity = '1';
          oben.style.opacity = '0';
        });
      });
      window.setTimeout(() => {
        oben.hidden = true;
        const merk = oben;
        oben = unten;
        unten = merk;
      }, BLENDE_MS);
    };

    if (unten.src.endsWith(traum.image) && unten.complete) {
      zeigen();
    } else {
      unten.hidden = true;
      unten.onload = zeigen;
      unten.src = traum.image;
    }
  }

  function weiter() {
    if (alleTraeume.length < 2) return;
    stelle = (stelle + 1) % alleTraeume.length;
    blendeAuf(alleTraeume[stelle]);
  }

  function starteSchleife() {
    if (uhr !== null) window.clearInterval(uhr);
    // Unter zwei Bildern gibt es nichts durchzublättern — dann bleibt die
    // Seite genau so stehen, wie sie es vor der Slideshow tat.
    if (alleTraeume.length < 2) {
      uhr = null;
      return;
    }
    uhr = window.setInterval(weiter, BILD_DAUER_MS);
  }

  return {
    schliesseLupe,
    /** Für Tests und für den Fall, dass die Seite im Hintergrund liegt. */
    stoppeSchleife() {
      if (uhr !== null) window.clearInterval(uhr);
      uhr = null;
    },
    applyState(zustand) {
      const aktuell = zustand && zustand.current ? zustand.current : null;

      // 🔴 Der Vorrat für die Slideshow: die Historie in ihrer Entstehungs-
      // reihenfolge, der aktuelle Traum zuletzt. `history` kommt ältestes
      // zuerst (kg2/server.py), also ist die Reihenfolge schon richtig.
      const vorrat = ((zustand && zustand.history) || [])
        .filter((tr) => tr && tr.image)
        .concat(aktuell && aktuell.image ? [aktuell] : []);
      const vorratSchluessel = vorrat.map((tr) => tr.id).join(',');
      if (vorratSchluessel !== alleTraeume.map((tr) => tr.id).join(',')) {
        alleTraeume = vorrat;
        starteSchleife();
      }

      if (aktuell && aktuell.image) {
        if (aktuell.image !== gezeigt) {
          gezeigt = aktuell.image;
          // 🔴 Ein NEUER Traum unterbricht die Schleife und wird gezeigt: Was
          // gerade entstanden ist, hat Vorrang vor dem Durchblättern. Danach
          // läuft die Slideshow von dieser Stelle aus weiter.
          stelle = Math.max(0, alleTraeume.length - 1);
          blendeAuf(aktuell);
          starteSchleife();
        }
      } else {
        gezeigt = null;
        bild.hidden = true;
        bildBlende.hidden = true;
        bild.removeAttribute('src');
        bildBlende.removeAttribute('src');
      }

      satz.textContent = aktuell ? aktuell.sentence || '' : '';
      warten.hidden = Boolean(aktuell);

      // Neueste zuerst: `history` kommt ältestes zuerst (kg2/server.py), und am
      // Handy wischt man von links nach rechts in die Vergangenheit.
      // 🔴 Mehr Miniaturen (Birk, 2026-09-02): „du kannst die anzahl erhöhen
      // sodass sie die komplette untere breite ausfüllt." Der Streifen ist
      // waagerecht wischbar und traegt sie ohnehin; die Grenze schuetzt nur
      // ein schwaches Telefon vor zwei Dutzend gleichzeitigen Ladungen —
      // und die Miniaturen laden `lazy`, also kosten die hinteren nichts,
      // solange niemand dorthin wischt.
      const verlauf = ((zustand && zustand.history) || [])
        .filter((t) => t && t.image && (!aktuell || t.id !== aktuell.id))
        .slice(-MAX_MINIATUREN)
        .reverse();
      zeichneStreifen(verlauf);
    },
  };
}
