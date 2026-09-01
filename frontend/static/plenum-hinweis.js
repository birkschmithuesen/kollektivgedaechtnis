/** Der Erklärungstext im Plenarsaal (Birk, 2026-09-01 vor Ort).
 *
 * Wörtlich bestellt: „Die Kamera fährt über den Graphen, und zwischendurch
 * erscheint ein kurzer Erklärungstext: was die Installation draußen ist, mit
 * dem QR-Code zum Scannen."
 *
 * Ausdrücklich NICHT bestellt: ein Traumbild dazwischen. Birk hält das selbst
 * für „wahrscheinlich too much" — also steht hier nur die eine Einblendung,
 * und wer sie erweitern will, muss das erst wieder besprechen.
 *
 * ## Warum ein Zeitgeber und keine Kopplung an die Kamerafahrt
 *
 * Der naheliegende Reflex wäre, die Einblendung an das Ende einer Etappe zu
 * hängen. Dagegen sprechen zwei Dinge: Die Fahrt läuft nur im Modus
 * „automatisch schwenken" (steht der Saal auf „alles zeigen", gäbe es nie
 * einen Erklärungstext), und ihre Etappenlänge hängt am Tempo-Regler — der
 * Rhythmus der Einblendung würde sich beim Verstellen des Tempos still mit
 * ändern. Beides sind Wege, auf denen die Einblendung im Saal ausbleibt,
 * ohne dass jemand einen Fehler sieht. Ein eigener Takt ist unabhängig davon,
 * und seine beiden Zahlen stehen als Regler im Bedienfeld.
 */

/** Der Erklärungstext. Von Birk freigegeben am 2026-09-01 (Vorschlag A, um
 * den Datenschutzsatz erweitert: „Ich nehme den Vorschlag auf, auch das ein.").
 *
 * Der Wortlaut nimmt bewusst die Sprache der Handyseite auf
 * (`mirror/web/start.html`, Absatz `.willkommen` und der Hinweis-Block
 * darunter). Saal und Telefon sollen dieselbe Arbeit gleich erklären — wer
 * hier liest und danach scannt, darf keine zweite, anders klingende Version
 * vorfinden. Wird der eine Text geändert, gehört der andere mit angesehen.
 *
 * Länge ist hier eine technische Grenze, keine Geschmacksfrage: die Karte
 * steht 25 Sekunden (`hinweis_dauer` in `kg/server.py`) und wird aus
 * Saalentfernung bei 42 px gelesen. Drei Sätze sind das Maß; ein vierter
 * drängt die Karte in die Höhe des QR-Codes. */
export const ERKLAERUNGSTEXT =
  'Draußen im Foyer führen wir Interviews. Aus dem, was gesagt wird, wächst ' +
  'dieses Netz — und daraus träumt die Maschine ein Bild. Es wird kein Ton ' +
  'aufgezeichnet, und nichts davon verlässt Europa.';

/** Die Zeile, die auf den QR-Code zeigt — getrennt vom Text darüber, weil sie
 * kleiner gesetzt ist (`.plenum-hinweis-scan` in plenum.css) und eine andere
 * Aufgabe hat: nicht erklären, sondern auf den Code rechts unten zeigen. */
export const SCANZEILE = 'Live auf Ihrem Telefon — Code rechts unten scannen.';

/** Vorgaben des Takts, in Millisekunden. Überschrieben vom Bedienfeld
 * (`plenum_hinweis_intervall` / `plenum_hinweis_dauer`), sobald der erste
 * Zustand über SSE ankommt — diese beiden Zahlen gelten also nur in der
 * Zeitspanne davor und auf einer Seite ohne Server. */
const INTERVALL_MS = 120000;
const DAUER_MS = 25000;

/** Wie lange nach dem Laden die Einblendung zum ersten Mal kommt.
 *
 * Nicht nach einem vollen Intervall: Wer die Saalfläche neu startet, muss
 * innerhalb von Sekunden sehen, DASS die Einblendung lebt. Sonst steht man im
 * Saal zwei Minuten vor einem schwarzen Bild und weiß nicht, ob man auf sie
 * wartet oder auf einen Fehler. Danach gilt der eingestellte Takt. */
const ERSTER_AUFTRITT_MS = 8000;

/**
 * Hängt die Einblendung an `ziel` und startet ihren Takt.
 *
 * Die Zeitgeber sind einspeisbar, wie beim Zitat-Overlay: ein Test soll den
 * Rhythmus prüfen können, ohne zwei Minuten zu warten.
 *
 * Gibt ein Handle zurück mit `element`, `zeigen()`, `verbergen()`,
 * `setTakt({ intervallMs, dauerMs })` und `stoppen()`. `entfernen()` heißt
 * hier bewusst genauso wie bei der Legende — `sim/prerender.py` nimmt
 * Einblendungen vor der Aufnahme aus dem Bild und soll das für beide gleich
 * tun können.
 */
export function attachPlenumHinweis({
  ziel = document.body,
  intervallMs = INTERVALL_MS,
  dauerMs = DAUER_MS,
  ersterAuftrittMs = ERSTER_AUFTRITT_MS,
  setTimer = (fn, ms) => window.setTimeout(fn, ms),
  clearTimer = (id) => window.clearTimeout(id),
} = {}) {
  const karte = document.createElement('section');
  karte.className = 'plenum-hinweis';
  karte.id = 'plenum-hinweis';
  // Für Vorlesewerkzeuge unsichtbar, wie die anderen Einblendungen der Wand:
  // im Saal steht kein Gerät, das vorliest, und der Inhalt ist eine
  // Wandbeschriftung, kein Bedienelement.
  karte.setAttribute('aria-hidden', 'true');

  const text = document.createElement('p');
  text.className = 'plenum-hinweis-text';
  text.textContent = ERKLAERUNGSTEXT;
  karte.appendChild(text);

  const scan = document.createElement('p');
  scan.className = 'plenum-hinweis-scan';
  scan.textContent = SCANZEILE;
  karte.appendChild(scan);

  ziel.appendChild(karte);

  let takt = { intervallMs, dauerMs };
  let timer = null;

  function abbrechen() {
    if (timer !== null) clearTimer(timer);
    timer = null;
  }

  function verbergen() {
    karte.classList.remove('sichtbar');
  }

  function zeigen() {
    karte.classList.add('sichtbar');
  }

  /** Ein Auftritt: einblenden, nach `dauerMs` wieder ausblenden, nach
   * `intervallMs` von vorn.
   *
   * Der Wartezeitpunkt hängt am ANFANG des Auftritts, nicht an seinem Ende:
   * „alle zwei Minuten" soll zwei Minuten von Erscheinen zu Erscheinen heißen
   * und nicht zwei Minuten plus Standzeit — sonst verschiebt sich der Takt
   * jedesmal, wenn jemand die Dauer verstellt. Die Untergrenze schützt vor
   * einer Einstellung, in der die Einblendung nie verschwindet. */
  function auftritt() {
    zeigen();
    const stehzeit = Math.min(takt.dauerMs, Math.max(1000, takt.intervallMs - 1000));
    timer = setTimer(() => {
      verbergen();
      timer = setTimer(auftritt, Math.max(1000, takt.intervallMs - stehzeit));
    }, stehzeit);
  }

  timer = setTimer(auftritt, ersterAuftrittMs);

  return {
    element: karte,
    zeigen,
    verbergen,
    get sichtbar() {
      return karte.classList.contains('sichtbar');
    },
    /** Neuer Takt aus dem Bedienfeld. Wirkt ab dem NÄCHSTEN Auftritt und
     * schneidet keinen laufenden ab: Wer im Saal am Regler dreht, während der
     * Text gerade steht, will ihn nicht mitten im Satz wegblenden. */
    setTakt({ intervallMs: neuesIntervall, dauerMs: neueDauer } = {}) {
      if (neuesIntervall > 0) takt.intervallMs = neuesIntervall;
      if (neueDauer > 0) takt.dauerMs = neueDauer;
    },
    stoppen: abbrechen,
    entfernen() {
      abbrechen();
      karte.remove();
    },
  };
}
