// The one control a VISITOR may touch on surface A. Deliberately not the
// operator UI: no hiding, no camera modes, no zoom slider, no density.
//
// Why "Übersicht" is here: after a minute of pinching around, a visitor is
// lost, and the next visitor inherits a random close-up of one node. This is
// the way out of that with one press, and it is the ONLY way out other than
// waiting 30 s for the idle timeout (touch-autonomy.js).
//
// Why it is allowed to be here: it changes nothing beyond this screen. Like
// the camera's manual override it posts nothing — it points the local view
// back at the whole net.
//
// The density steps used to sit here too, and they posted `/api/min_mentions`.
// The reasoning was that "where the camera looks" is local while "what the wall
// means" holds everywhere. That is true of the OPERATOR, who has the dial
// anyway, and false of a stranger in the foyer: surface A is the touchscreen at
// the entrance and surface C the projection in the plenary room, so a guest
// pressing "häufig (ab 3)" was rewriting the wall in front of a seated
// audience. Removed 2026-08-26 (Birk). The density is the operator's, and the
// per-step term counts that used to sit on these buttons moved to the operator
// dropdown with it.

// Der Zoom-Regler kam am 2026-09-01 dazu. Birk am MacBook mit angeschlossenem
// Touchscreen: „ich habe halt nur einen Mausklick, ich kann nicht irgendwie
// reinzoomen. Zweifingergeste — ist das wegen Mac, geht das einfach nicht?
// Dann bräuchten wir halt einen Regler an der Seite, einen Zoom-Regler."
//
// Er darf hier stehen aus demselben Grund wie „Übersicht": Er postet nichts.
// Er schreibt in den Viewport DIESER Seite (`camera.setVisitorZoom`), genau
// das, was eine Zweifingergeste getan hätte. Die Wand im Plenarsaal merkt
// davon nichts.

// Der rechte Anschlag steht in camera.js, seit es zwei Bedienwege dorthin gibt
// (Regler und Zwei-Finger-Geste, Nachtrag 2026-09-01). Zwei Zahlen wären zwei
// Anschläge, die auseinanderlaufen können — und dann zöge die Geste in eine
// Vergrößerung, aus welcher der Griff hier nicht mehr herausholt.
import { ZOOM_MAX } from './camera.js';

/** Reglerweg (0…1) → Zoomfaktor. Gleicher Weg = gleiches VERHÄLTNIS.
 *
 * Nicht linear, und das ist dieselbe Begründung, aus der `lerpZoom` in
 * camera.js Zoomstufen geometrisch interpoliert: Das Auge liest Faktoren. Ein
 * linearer Weg von 1 bis 8 läge auf seiner ersten Hälfte zwischen 1x und 4,5x
 * — ein Drittel des Wegs in wahrgenommenen Stufen — und würde den Rest
 * überstürzen. Am Griff fühlt sich das an, als passiere zuerst nichts und
 * dann alles auf einmal. */
function zoomFaktor(weg) {
  return Math.pow(ZOOM_MAX, Math.min(1, Math.max(0, weg)));
}

export function createTouchControls(container, { onOverview, onZoom } = {}) {
  const bar = document.createElement('div');
  bar.className = 'touch-controls';
  bar.id = 'touch-controls';
  // 🔴 Die Leiste sagt selbst, wie hoch sie ist (Birk, 2026-09-02: die
  // Zitatkarte erschien UNTER dem Zoomregler).
  //
  // Die Karte stand auf `bottom: calc(104px * var(--quote-scale))`. Bei einem
  // Massstab von 0,4 sind das 41,6 px — die Leiste ist aber 88 px hoch
  // (12 + 64 + 12). Der Fehler ist nicht die Zahl, sondern dass der Abstand,
  // der die Leiste freihalten soll, MIT DER KARTE MITSCHRUMPFT: je kleiner
  // das Zitat gestellt wird, desto tiefer verschwindet es.
  //
  // GEMESSEN statt aus dem CSS abgeschrieben: Wer dort das Polster oder die
  // Trefferzone aendert, soll das nicht an einer zweiten Stelle nachtragen
  // muessen. Der ResizeObserver haelt den Wert nach, wenn sich die Leiste
  // spaeter noch aendert (Drehung, andere Schirmbreite).
  //
  // Nur im Touch-Modus: `createTouchControls` wird ausschliesslich unter
  // `?touch=1` aufgerufen (projection.html). Auf der Wand und im Saal bleibt
  // die Variable ungesetzt, und die Karte sitzt dort unveraendert.

  const overview = document.createElement('button');
  overview.id = 'touch-overview';
  overview.className = 'touch-button';
  // Not "Zoom 1x": the visitor is not thinking in zoom factors, they are
  // thinking "show me everything again".
  overview.textContent = 'Übersicht';
  bar.appendChild(overview);

  // Der Regler sitzt in einer Hülle mit den beiden Marken − und +. Keine
  // Beschriftung „Zoom": Zwei Zeichen an den Enden sagen dasselbe in jeder
  // Sprache und nehmen der Leiste keine Ruhe.
  const zoomHuelle = document.createElement('div');
  zoomHuelle.className = 'touch-zoom';
  // 🔴 Hier steht die Ausnahme von der Ausnahme (touch-autonomy.js): Die
  // Bedienleiste zählt sonst NICHT als „der Besucher steuert" — sonst hätte
  // „Übersicht" sich selbst überschrieben (Fehler vom 2026-08-26). Wer aber am
  // Zoom-Regler zieht, steuert die Ansicht wie mit einer Geste am Graphen und
  // muss die 30-s-Ruheuhr anstossen, damit die Wand von selbst zurückfindet.
  // Die Erklärung steht AN dem Bedienelement, das sie betrifft; die Regel, die
  // sie liest, steht an genau einer Stelle in touch-autonomy.js.
  zoomHuelle.dataset.autonomie = 'steuern';

  const raus = document.createElement('span');
  raus.className = 'touch-zoom-marke';
  raus.setAttribute('aria-hidden', 'true');
  raus.textContent = '−';

  const regler = document.createElement('input');
  regler.id = 'touch-zoom';
  regler.className = 'touch-zoom-regler';
  regler.type = 'range';
  // Der Regler läuft in WEG (0…1), nicht in Faktoren — `zoomFaktor()` rechnet
  // um. Ein `min="1" max="8"` wäre der lineare Weg, den der Kommentar dort
  // verwirft. 0,01 sind hundert Stufen: auf einem 65-Zoll-Schirm feiner als
  // ein Finger je trifft, also nie stufig.
  regler.min = '0';
  regler.max = '1';
  regler.step = '0.01';
  regler.value = '0';
  regler.setAttribute('aria-label', 'Zoom');

  const rein = document.createElement('span');
  rein.className = 'touch-zoom-marke';
  rein.setAttribute('aria-hidden', 'true');
  rein.textContent = '+';

  zoomHuelle.append(raus, regler, rein);
  bar.appendChild(zoomHuelle);

  // `input` und nicht `change`: Der Ausschnitt soll der Hand folgen, solange
  // sie zieht. Der Operator-Regler macht es andersherum (dort erst beim
  // Loslassen), weil er ein POST pro Schritt auslösen würde — hier geht nichts
  // ins Netz, es wird nur der eigene Viewport geschrieben.
  regler.addEventListener('input', () => onZoom && onZoom(zoomFaktor(Number(regler.value))));

  /** Den Griff auf den linken Anschlag zurückstellen — ohne `input` auszulösen.
   *
   * Ein Regler, der 4x anzeigt, während die Wand die Übersicht zeigt, ist
   * schlimmer als keiner: Die nächste Hand bewegt ihn um eine Kleinigkeit und
   * das Bild springt um vier Stufen. Gerufen von „Übersicht" und von der
   * Autonomie, wenn die Wand sich nach 30 s Ruhe selbst zurücknimmt. */
  const reglerZuruecksetzen = () => {
    regler.value = '0';
  };

  /** Den Griff auf einen Zoomfaktor stellen — die Umkehrung von `zoomFaktor`.
   *
   * Gerufen von der Zwei-Finger-Geste (Nachtrag 2026-09-01): Wer mit zwei
   * Fingern auf 4x zieht, muss den Griff danach bei 4x finden. Sonst steht er
   * auf dem linken Anschlag, während die Wand eine Nahaufnahme zeigt — und die
   * nächste Hand bewegt ihn um eine Kleinigkeit und reisst das Bild um vier
   * Stufen zurück. Genau der Fall, für den es `reglerZuruecksetzen` gibt, nur
   * andersherum.
   *
   * Löst KEIN `input` aus (eine Zuweisung an `.value` tut das nie): Sonst
   * riefe das Setzen des Griffs `onZoom` und damit `setVisitorZoom` — die
   * Geste zoomte über ihre eigene Rückmeldung ein zweites Mal. */
  const reglerAnzeigen = (faktor) => {
    const n = Number(faktor);
    if (!Number.isFinite(n) || !(n > 0)) return;
    const weg = Math.log(n) / Math.log(ZOOM_MAX);
    regler.value = String(Math.min(1, Math.max(0, weg)));
  };

  overview.addEventListener('click', () => {
    reglerZuruecksetzen();
    if (onOverview) onOverview();
  });

  container.appendChild(bar);

  // Erst nach dem Einhaengen messbar. `--touch-leiste-hoehe` liest base.css,
  // damit die Zitatkarte ueber der Leiste landet statt darunter.
  const meldeHoehe = () => {
    const h = Math.round(bar.getBoundingClientRect().height);
    document.documentElement.style.setProperty('--touch-leiste-hoehe', `${h}px`);
  };
  meldeHoehe();
  if (typeof ResizeObserver === 'function') {
    new ResizeObserver(meldeHoehe).observe(bar);
  }

  return {
    element: bar,
    zoom: regler,
    resetZoom: reglerZuruecksetzen,
    showZoom: reglerAnzeigen,
  };
}
