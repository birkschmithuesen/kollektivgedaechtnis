// The camera is its own component from the start, even if everything fits.
// Mode 'pan' IS the touch fallback: a non-interactive automatic animation.

const MODES = ['fit', 'manual', 'pan'];

// How the automatic mode moves. These are the aesthetic decisions, gathered in
// one place so they can be tuned without reading the traversal logic.
//
// The shape being avoided: a camera that slides left, hits the edge, and
// reverses in a single frame reads as a screensaver — the reversal is the
// moment the machine shows. So the automatic mode does not bounce off walls.
// It picks a term node, travels to it, rests, and picks another. Motion then
// carries meaning (it is going somewhere) and every direction change happens
// while the camera is standing still at a target, never mid-glide.
// Wieviel Luft der Fahrt-Ausschnitt jenseits der Knotenwolke behalten darf,
// als Anteil der Bildbreite bzw. -höhe (Birk, 2026-08-31, Punkt 8).
//
// Die Bremse in `_panForCentering()` schiebt einen Ausschnitt zurück, der zu
// weit ins Leere ragt. Ohne Luft klebte er exakt an der Wolke und läse sich
// als Anschlag; 8 % lassen einen Rand stehen, der wie ein gewollter Bildrand
// wirkt.
//
// Gemessen 2026-09-01, dichtes Testnetz (40 Personen, 60 Begriffe, 1920×1080)
// bei Zoomregler 2,5× — also so, wie die Wand im Betrieb steht:
//
//                        ohne Bremse   mit Bremse
//   schlechtester Fall        56 %         85 %
//   Median                    92 %         92 %
//
// Der Median rührt sich nicht, und das ist der Punkt: Die Bremse greift NUR
// dort, wo der Ausschnitt sonst ins Leere ragte. Ziele mitten im Netz bleiben
// unberührt, die Fahrt zeigt weiterhin unterschiedliche Ausschnitte
// (21 bis 32 von 100 Knoten je Ziel).
//
// Erster Messversuch lief in eine Falle und ist verworfen: bei Zoomregler 1
// passt die ganze Wolke ohnehin ins Bild, alle 60 Ziele lieferten identisch
// 82 % — gemessen wurde da nicht die Bremse, sondern dass es nichts zu
// klemmen gab.
const RAND_LUFT = 0.08;

/** Wie weit ein BESUCHER hineinzoomen darf: 8x enger als die Gesamtansicht.
 *
 * Weiter als der Regler des Operators (dort 1–4, gespiegelt an der
 * Serverschranke), und das ist Absicht: Der Operator kalibriert damit die
 * DAUERANSICHT der Wand, ein Besucher ersetzt damit eine Geste. In `manual`
 * gilt auch die Porträt-Schranke nicht, „dort darf ein Besucher in ein Gesicht
 * hineinzoomen, bis es formatfüllend ist" (operator.html). 8x sind auf 1920 px
 * rund ein Achtel der Netzbreite — nah genug für ein Gesicht oder ein langes
 * Begriffsschild.
 *
 * Steht hier und nicht in `touch-controls.js`, seit es zwei Bedienwege dorthin
 * gibt (Regler und Zwei-Finger-Geste, 2026-09-01). Zwei Anschläge wären zwei
 * Zahlen, die auseinanderlaufen können — und dann zöge die Geste in eine
 * Vergrößerung, aus welcher der Griff des Reglers nicht mehr herausholt. Die
 * Kamera ist die Stelle, die beide bedienen, also gehört die Schranke hierhin
 * und wird hier auch durchgesetzt (`setVisitorZoom`), nicht nur angezeigt. */
export const ZOOM_MAX = 8;

const ROAM = {
  // The FASTEST the tour ever goes (speed factor 1.0). Everything slower is
  // derived by dividing by the factor, so this pair stays the reference the
  // motion was tuned against and the operator only ever slows it down —
  // there is no setting that outruns what was judged on the wall.
  travelMs: 5200, // one leg, long enough to read as drifting rather than cutting
  dwellMs: 4200, // rest on the target — the beat that makes it feel deliberate
  // Zoom breathes around the calibrated level across a whole leg-plus-dwell.
  // Small on purpose: enough that the image is never frozen, not so much that
  // the visitor notices a zoom happening.
  breathAmplitude: 0.06,
  breathPeriodMs: 42000,
  // Prefer well-connected terms: the wall is about what people share, so the
  // traversal should dwell where sharing actually happened. Degree 1 nodes are
  // still reachable, just far less often.
  degreeBias: 2.0,
  // Handing the view back: how long the camera takes to travel from the
  // close-up a visitor left behind to the view the automatic mode wants.
  //
  // 5000 ms on Birk's call after watching it on the wall (2026-08-30). The
  // first value was 1500 ms, reasoned from the leg duration (5200 ms) -- the
  // handover should not read as part of the journey. Seen on the actual
  // projection that argument does not survive: at 1.5 s the takeover still
  // reads as a lurch rather than the wall calmly resuming, and this is the one
  // transition an audience watches from a standstill. Now essentially a full
  // leg, which is the point -- it should look like the tour simply carrying
  // on.
  //
  // NOT scaled by the operator's speed slider, unlike travel and dwell. The
  // slider sets the pace of the tour; a quarter-speed setting must not leave a
  // visitor's abandoned close-up on the wall for twenty seconds.
  handoverMs: 5000,
};

// Die Kopplung an den Traum (Birk, 2026-08-31). Die Wand soll den Ausschnitt
// zeigen, aus dem das Bild gerade entsteht — „was an der Wand hängt, ist
// sichtbar aus DIESEM Teil des Netzes entstanden“.
//
// Zwei Auslöser, beide in Tool 1 sichtbar: das Portrait zu Interviewbeginn und
// die neuen Begriffe. Ein dritter („Bild fertig“) wurde am 2026-08-31 verworfen
// und das ist eine Entscheidung, keine Lücke: Tool 2 wählt seine fünf Begriffe
// zu Beginn des Zyklus und behält sie bis zum fertigen Bild, `in_dream` zeigt
// also während der ganzen Generierung schon dieselben fünf. Ein Schwenk zum
// Bildende führe dorthin, wo die Kamera längst steht — und wäre nur über einen
// Rückkanal von Tool 2 nach Tool 1 erreichbar, den `kg2/graph_client.py` per
// Konstruktion nicht hat und `tests/test_dream_contract.py` am Quelltext
// verbietet.
const DREAM = {
  // Wie weit der Ausschnitt gefasst wird: die fünf Begriffe PLUS die Personen,
  // die sie genannt haben. Gemessen am Replay-Stand (60 Personen, 110
  // Begriffe): die fünf allein sind 1240x346 groß und ergäben Zoom 1.45 — 1,6x
  // enger als die auf der Wand kalibrierte Ansicht (0.886) und für Labels wie
  // „Pseudo-Abstimmung vor Baubeginn“ zu wenig Fläche. Mit ihren 18 Personen
  // sind es 1685x884 und Zoom 1.07, also nah an dem, was schon als lesbar
  // beurteilt wurde. Und inhaltlich ist es die vollständigere Aussage: die
  // Begriffe sind das Material, die Portraits sind, wer es gesagt hat.
  withPersons: true,
  // Wie lange die Kamera nach einem Auslöser im Traumgebiet bleibt, bevor sie
  // wieder frei durchs ganze Netz wandert. Ein Traum entsteht alle 4-5 Minuten
  // (kg2 `min_interval_s: 240`), eine Runde aus Fahrt und Rast dauert 9,4 s —
  // in vier Minuten also rund 25 Stationen. Ohne Begrenzung sähe die Wand
  // stundenlang nur dieses eine Gebiet; ohne Bindung wäre sie nach zehn
  // Sekunden wieder irgendwo und die Kopplung praktisch wirkungslos.
  holdMs: 240000,
  // „Erst den Traum erklären, dann immer mehr Kontext geben“ (Birk,
  // 2026-08-31) — dieser Gedanke ist am 2026-09-01 an der Wand VERWORFEN
  // worden, nachdem Birk ihn im Betrieb gesehen hat:
  //
  //   „Mein Problem ist, dass es konstant immer weiter rauszieht. Das ist ja
  //    nicht die Idee der Sache, eigentlich sollte es immer identisch
  //    bleiben, den stelle ich einmal ein, so wie man gut sehen kann. Und
  //    dann soll die Kamerafahrt eigentlich nur über den ganzen Graphen hin
  //    und her fahren."
  //
  // Der Ausschnitt weitete sich über die vier Minuten Haltezeit von 1,0 auf
  // 2,1 — also auf mehr als das Doppelte — und begann beim nächsten Traum
  // wieder von vorn. Auf dem Papier eine Dramaturgie, an der Wand ein
  // Bildausschnitt, der nie da bleibt, wo er eingestellt wurde.
  //
  // BEIDE Werte stehen jetzt auf 1.0: der Traumausschnitt wird eins zu eins
  // gezeigt und bleibt es. Die Bildgröße bestimmt allein der Zoomregler des
  // Operators (`_zoomFactor`, siehe die Multiplikation in `_automaticView()`
  // und `_travelLevel()`) — „ich will das mit dem manuellen Zoomregler
  // machen" (Birk, 2026-09-01).
  //
  // Die Mechanik von `_dreamSpread()` bleibt absichtlich stehen, statt sie
  // herauszuoperieren: bei spreadFrom == spreadTo ist der Faktor konstant 1,0
  // und damit wirkungslos, und wenn das Aufziehen je wieder gewollt ist, ist
  // es eine Zahl statt eines Umbaus.
  spreadFrom: 1.0,
  spreadTo: 1.0,
};

/** Ease in and out — no abrupt starts, no arrivals that slam to a halt.
 *
 * cosine rather than a cubic: its derivative is zero at BOTH ends, so a leg
 * begins and ends at literally zero speed. That is what removes the visible
 * "start" of each leg; with a cubic ease the residual velocity at t=0 is small
 * but perceptible on a 65" screen at close range. */
function easeInOut(t) {
  return 0.5 - 0.5 * Math.cos(Math.PI * Math.min(1, Math.max(0, t)));
}

/** Interpolate a magnification: equal steps in RATIO, not in difference.
 *
 * Zoom is a factor, and the eye reads factors. A linear ramp from 4x to 1x
 * spends its first half between 4x and 2.5x — a sixth of the way back in
 * perceived terms — and then rushes the rest, which looks like the camera
 * hesitating and then falling. Falls back to linear for unusable levels
 * rather than producing NaN: a wall must degrade, never stop rendering. */
function lerpZoom(from, to, t) {
  if (!(from > 0) || !(to > 0)) return from + (to - from) * t;
  return from * Math.pow(to / from, t);
}

/** Die Uhr, auf der die Traumkopplung läuft.
 *
 * `performance.now()` und NICHT `Date.now()`, und das ist hier keine
 * Geschmacksfrage: `sim/prerender.py` installiert für seine Aufnahmen eine
 * kontrollierte Uhr (`_FRAME_CLOCK`), die `requestAnimationFrame` und
 * `performance.now` übernimmt, damit zwei kalte Läufe Bild für Bild
 * übereinstimmen. `Date.now()` fasst sie NICHT an — eine Kopplung, die daran
 * hinge, liefe also gegen die freie Wanduhr weiter, während der Rest der Seite
 * auf der kontrollierten steht.
 *
 * Gemessen 2026-08-31, nachdem genau das passiert war: zwei Läufe mit
 * identischen Knotenpositionen, aber Zoom 0.8053954 gegen 0.8050733 — die
 * Aufweitung war in beiden Läufen um Sekundenbruchteile verschieden weit
 * gelaufen. `tests/test_prerender.py::test_two_cold_runs_produce_the_same_motion`
 * hat es gefangen. Die Datei fuhr immer schon auf dieser Uhr (projection.js
 * differenziert `performance.now()` für `camera.step()`); die zweite
 * Zeitquelle war der Fremdkörper.
 *
 * Über eine Funktion und nicht als Vorgabewert im Parameter, damit es EINE
 * Stelle gibt, an der die Uhr steht — drei `now = performance.now()` in drei
 * Signaturen wären drei Stellen, an denen die nächste Änderung eine vergessen
 * kann. */
function jetzt() {
  return performance.now();
}

/** Keep a speed inside [0.25, 1], treating anything unusable as full speed.
 *
 * `Number(x) || 1` is the obvious spelling and is WRONG here: 0 is falsy, so a
 * zero would fall through to 1 — full speed — when it plainly means "as slow
 * as possible". Only NaN deserves the fallback.
 */
function clampRoamSpeed(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 1;
  // Untergrenze am 2026-09-01 von 0,25 auf 0,1 gesenkt. Birk stand beim
  // Einrichten vor Ort auf 0,25 -- also GENAU auf dem Anschlag -- und meldete
  // „der Tempo-Regler hat keinen Einfluss". Er hatte recht: langsamer ging
  // nicht mehr, der Regler war am Ende seines Wegs. Auf seine Rueckmeldung
  // („mach mal nach unten noch mehr headroom") dann bis 0,05 geoeffnet: eine
  // Etappe dauert dort 104 s statt 5,2 s.
  //
  // Nach oben bleibt es bei 1: das ist das Tempo, bei dem die Bewegung an der
  // Wand beurteilt wurde, und es soll keine Einstellung geben, die schneller
  // laeuft als je jemand gesehen hat.
  return Math.min(1, Math.max(0.05, n));
}

export class Camera {
  constructor(
    cy,
    {
      panSpeed = 18,
      padding = 60,
      zoomFactor = 1,
      roamSpeed = 1,
      random = Math.random,
      fitWith = (fit) => fit(),
      onModeChanged = () => {},
    } = {},
  ) {
    this.cy = cy;
    this.panSpeed = panSpeed;
    this.padding = padding;
    // Called after every setMode(). The projection re-sizes its portrait discs
    // there: since 2026-08-30 the portrait ceiling applies to the DRIVEN modes
    // only (see portraitCapBlend), so a mode change is a size change, and it
    // has to land in the same synchronous breath as the mode itself rather
    // than on the next animation frame.
    this._onModeChanged = onModeChanged;
    // Every viewport fit this camera performs goes through here. The
    // projection passes a wrapper that first puts the portrait discs back to
    // their placement size: since 2026-08-29 a disc's model size is derived
    // from the zoom (projection.js), and a fit that measured THOSE discs
    // would be computing the zoom from a size that is computed from the zoom
    // — with a single portrait on the wall that has no solution at all. The
    // default is the plain call, so a Camera used on its own is unchanged.
    this._fitWith = fitWith;
    // 1 = the whole net in frame. >1 = that many times tighter, i.e. only
    // 1/factor of the net's width is on the wall. Fit-all is illegible at 50
    // persons (pre-render series, 2026-08-14), so the zoom level is a setting
    // of this component, not a second camera bolted on next to it.
    this._zoomFactor = 1;
    this._mode = 'fit';
    this._direction = -1;
    // Injected so a test can drive the traversal deterministically; production
    // passes nothing and gets Math.random.
    this._random = random;
    this._roam = null;
    // The way back out of a visitor's hands, see _startHandover().
    this._handover = null;
    // 1 = the tuned speed (ROAM.travelMs/dwellMs), 0.25 = a quarter of it, i.e.
    // four times as long per leg. Clamped rather than validated-and-thrown: a
    // bad value must slow the wall down, never stop it rendering.
    this._roamSpeed = clampRoamSpeed(roamSpeed);
    // Das Traumgebiet, solange eines gilt: `{ ids, until }`. `ids` friert die
    // Knotenmenge zum Zeitpunkt des Auslösers ein, statt sie bei jedem Zugriff
    // neu aus `.in-dream` zu lesen — sonst zöge ein Graph-Update mitten in
    // einer Fahrt das Ziel unter der laufenden Bewegung weg, und genau das
    // (ein Ruck mitten im Gleiten) ist das, was das Easing hier verhindern
    // soll. Ein neuer Auslöser ersetzt die Menge als Ganzes.
    this._dream = null;
    // At an unattended exhibition a stray touch/mouse must never be able to
    // pan the viewport off-frame or drag a node off its persisted position.
    // `manual` is the only mode where a visitor is meant to move anything;
    // apply that for the initial mode too, not just from setMode onward.
    this._applyInteractivity(this._mode);
    this.setZoomFactor(zoomFactor);
  }

  get mode() {
    return this._mode;
  }

  get zoomFactor() {
    return this._zoomFactor;
  }

  get roamSpeed() {
    return this._roamSpeed;
  }

  /** How fast the automatic tour travels, as a fraction of the tuned speed.
   *
   * Applied to the DURATIONS, not to a velocity: a leg always covers the
   * whole distance to its target with the same cosine ease, it just takes
   * longer. Changing a velocity instead would leave the camera short of its
   * target when the phase ends, and the arrival — the moment the motion is
   * built around — would land somewhere arbitrary.
   *
   * Takes effect on the NEXT phase. Rescaling a leg already in flight would
   * make the camera visibly jump, which is the one thing the easing exists to
   * prevent. */
  setRoamSpeed(speed) {
    this._roamSpeed = clampRoamSpeed(speed);
  }

  /** This leg's duration at the current speed. */
  _travelDuration() {
    return ROAM.travelMs / this._roamSpeed;
  }

  /** This rest's duration at the current speed. */
  _dwellDuration() {
    return ROAM.dwellMs / this._roamSpeed;
  }

  /** What the automatic traversal is doing right now — for tests and the
   * pre-render, which need to place frames inside a leg rather than guess. */
  get roamState() {
    if (!this._roam) return null;
    return { phase: this._roam.phase, targetId: this._roam.targetId, elapsed: this._roam.elapsed };
  }

  setMode(mode) {
    if (!MODES.includes(mode)) throw new Error(`unknown camera mode: ${mode}`);
    const previous = this._mode;
    this._mode = mode;
    // IMMER, auch wenn der Modus derselbe bleibt: Das ist die Zusicherung, dass
    // an einer unbeaufsichtigten Ausstellung keine Besucherhand den Viewport
    // verschieben oder einen Knoten aus der Anordnung ziehen kann, und sie wird
    // bei jedem Aufruf neu behauptet statt einmal gesetzt und gehofft
    // (tests/test_camera.py: „no sequence of modes ever makes a node
    // grabbable"). Idempotent, also kostet die Wiederholung nichts.
    this._applyInteractivity(mode);
    // Ab hier NUR bei einem echten Wechsel (gemessen 2026-08-31): `/events`
    // liefert nach jedem `graph` auch ein `state`, und projection.html reicht
    // dessen `camera_mode` ungeprüft durch — meist derselbe Wert wie eben.
    // Ohne diesen Ausstieg löschte jeder Graph-Push den gerade gestarteten
    // Handover und framte über `_frame()` wieder das ganze Netz: die
    // Traumkopplung startete korrekt und war einen Wimpernschlag später wieder
    // weg. Genau die Fehlerart aus dem Handoff — gebaut, plausibel,
    // wirkungslos, und nur am gerenderten Bild zu sehen.
    //
    // Die Trennlinie liegt zwischen „behaupten, was ohnehin gilt" (oben, immer)
    // und „die Ansicht neu werfen" (unten, nur bei Wechsel).
    if (mode === previous) return;
    // Entering pan starts a fresh traversal; leaving it drops the state so a
    // later return does not resume a leg whose target may no longer exist.
    this._roam = mode === 'pan' ? { phase: 'dwell', elapsed: 0, targetId: null, clock: 0 } : null;
    // Every mode change ends a handover in flight. The load-bearing case is a
    // visitor touching the wall while it is travelling back: `manual` has to
    // be theirs in that same frame, and a half-run handover still writing
    // pan/zoom would work against the hand that just grabbed it.
    this._handover = null;
    // Leaving manual is the one transition somebody is watching from a metre
    // away — it is their own view being taken back. Everywhere else the hard
    // framing stays: the operator's push, a graph change, and above all the
    // pre-render, which shoots a screenshot right after setting a view.
    //
    // Gilt ein Traumgebiet, ist auch der Weg nach `fit` eine Fahrt statt eines
    // harten Frames: `_frame()` zeigt das ganze Netz und risse die Kopplung
    // auf, `_startHandover()` fährt über `_automaticView()` auf das Gebiet.
    if (previous === 'manual' && mode !== 'manual') this._startHandover();
    else if (mode === 'fit') {
      if (this._dreamNodes()) this._startHandover();
      else this._frame();
    }
    this._onModeChanged(mode);
  }

  /** How much of the automatic portrait ceiling is in force right now, 0..1.
   *
   * The portrait size is an upper bound in the DRIVEN modes and no bound at
   * all in the visitor's (projection.js). The camera is the only component
   * that knows which of the two the wall is in — and, more to the point, that
   * there is a third state in between: the 1.5 s travel out of a close-up
   * somebody left behind. Switching the bound back on at either end of that
   * travel would be the snap the handover exists to remove, in the one element
   * that is ten times oversized at that moment, so it comes back on along the
   * handover's own cosine, together with the pan and the zoom.
   */
  get portraitCapBlend() {
    if (this._handover) return easeInOut(this._handover.elapsed / ROAM.handoverMs);
    return this._mode === 'manual' ? 0 : 1;
  }

  setZoomFactor(factor) {
    if (!(factor >= 1)) throw new Error(`zoom factor must be >= 1: ${factor}`);
    const changed = factor !== this._zoomFactor;
    this._zoomFactor = factor;
    // Manual is the visitor's mode: re-framing under their hands would fight
    // them. Every other mode is driven, so it re-frames at the new level.
    if (!changed || this._mode === 'manual') return;
    // A new level moves the destination. Steer the handover onto it instead of
    // framing hard underneath it — a hard frame mid-flight is the snap all
    // over again, and the next step() would drag the view back out of it.
    if (this._handover) this._handover.to = this._automaticView();
    else this._frame();
  }

  /** Der Zoom eines BESUCHERS — von der Zwei-Finger-Geste wie vom Regler.
   *
   * Birk, 2026-09-01 am Touchscreen: „ich habe halt nur einen Mausklick, ich
   * kann nicht irgendwie reinzoomen … dann bräuchten wir halt einen Regler an
   * der Seite."
   *
   * Der Nachtrag desselben Abends dreht die Rangfolge um: Die Ausstellung
   * läuft jetzt auf dem MacBook mit Brave, die Geste ist ausstellungskritisch
   * und der Regler der Rückfallweg. Beide landen hier — und das ist der Grund,
   * warum diese Methode einen optionalen Mittelpunkt kennt statt zwei
   * Methoden nebeneinander zu stehen: Der rechte Anschlag, die Bremse am
   * Bildrand und die Bedeutung von „3x" müssen für beide dieselben sein, sonst
   * holt der eine Weg nicht mehr aus dem heraus, was der andere angerichtet
   * hat. `touch-zoom-geste.js` ruft mit Punkt, `touch-controls.js` ohne.
   *
   * 🔴 Und deshalb NICHT `setZoomFactor`, so naheliegend das aussieht: Der
   * Regler wird im Modus `manual` bedient (die Berührung schaltet die Kamera
   * über `attachTouchAutonomy` dorthin), und `setZoomFactor` steigt in genau
   * diesem Modus absichtlich aus, um dem Besucher nicht in die Hand zu
   * fahren. Der Regler hätte also eine Zahl gesetzt und auf dem Schirm nichts
   * bewegt — gebaut, plausibel, wirkungslos. Ausserdem ist `_zoomFactor` die
   * Kalibrierung des Operators, die über `/events` hereinkommt; ein Besucher
   * schreibt nicht daran, er schreibt in den Viewport DIESER Seite, genau wie
   * eine Geste es täte.
   *
   * `faktor` bedeutet dasselbe wie am Regler des Operators: 1 = das ganze Netz
   * im Bild, 3 = dreimal enger. So heisst der linke Anschlag dasselbe wie
   * „Übersicht", und beide Wege zurück landen an derselben Stelle.
   *
   * Geklemmt wird OHNE Luft (0 statt `RAND_LUFT`): Eine Fahrt darf am Rand
   * etwas Schwarz stehen lassen, damit der Bildrand gewollt aussieht; eine
   * Hand am Regler darf nirgends im Leeren landen. Nebenbei ist das der
   * Rückweg für einen Besucher, der sich weggeschoben hat — der Regler holt
   * den Ausschnitt auf das Netz zurück. */
  setVisitorZoom(faktor, { renderedPosition = null } = {}) {
    const alle = this.cy.elements();
    if (typeof alle?.boundingBox !== 'function') return;
    const basis = this._levelForBox(alle);
    if (!(basis > 0)) return;
    const n = Number(faktor);
    // Wie `clampRoamSpeed`: ein unbrauchbarer Wert darf die Wand nie anhalten.
    // Nach unten bei 1, weil weiter herausgezoomt nur noch Rand wäre; nach
    // oben bei ZOOM_MAX, damit Regler und Geste denselben Anschlag meinen.
    const eng = Number.isFinite(n) ? Math.min(ZOOM_MAX, Math.max(1, n)) : 1;
    // Ohne Punkt um die Bildmitte — das ist der Regler, der gar keinen Ort
    // hat. Mit Punkt um die Finger: Wer zwei Finger auf ein Portrait legt und
    // sie spreizt, erwartet, dass DIESES Portrait größer wird und nicht, dass
    // es aus dem Bild wandert (Nachtrag 2026-09-01).
    if (renderedPosition) this._zoomeUmPunkt(basis * eng, renderedPosition);
    else this._applyZoom(basis * eng);
    // Erst zoomen, dann klemmen: Die Bremse rechnet gegen den Ausschnitt, der
    // nach dem Zoom gilt, nicht gegen den davor.
    this.cy.pan(this._klemmeAufWolke(this.cy.pan(), 0));
  }

  /** Wie weit der Besucher gerade hineingezoomt ist, in derselben Einheit, die
   * `setVisitorZoom` entgegennimmt: 1 = das ganze Netz im Bild.
   *
   * GELESEN und nicht gemerkt. Ein zweiter Zustand neben dem Viewport liefe
   * auseinander, sobald eine Übergabefahrt, ein neuer Graph oder „Übersicht"
   * den Zoom anfasst — und dann zeigte der Griff des Reglers wieder etwas
   * anderes an als das Bild, also genau den Fehler, gegen den `resetZoom`
   * gebaut ist. Gebraucht von der Geste: Sie rechnet relativ („anderthalbmal
   * so nah wie eben") und muss dafür wissen, wo sie steht. */
  get visitorZoom() {
    const alle = this.cy.elements();
    if (typeof alle?.boundingBox !== 'function') return 1;
    const basis = this._levelForBox(alle);
    if (!(basis > 0)) return 1;
    const jetzt = this.cy.zoom() / basis;
    return Number.isFinite(jetzt) && jetzt > 0 ? jetzt : 1;
  }

  /** Zoomen, ohne den Modellpunkt unter `renderedPosition` zu verschieben.
   *
   * Von Hand gerechnet statt über `cy.zoom({level, renderedPosition})`, weil
   * der Pan hier hinterher ohnehin durch die Bremse läuft: Ginge der Punkt
   * durch Cytoscape und die Bremse schriebe danach einen anderen Pan, stünden
   * zwei Rechnungen hintereinander, von denen nur die zweite zählt. So ist es
   * eine — und sie ist an derselben Stelle nachlesbar wie ihre Umkehrung in
   * `_klemmeAufWolke`. */
  _zoomeUmPunkt(level, renderedPosition) {
    const vorher = this.cy.zoom();
    const pan = this.cy.pan();
    if (!(vorher > 0)) {
      this._applyZoom(level);
      return;
    }
    // Der Modellpunkt, der gerade unter den Fingern liegt …
    const modell = {
      x: (renderedPosition.x - pan.x) / vorher,
      y: (renderedPosition.y - pan.y) / vorher,
    };
    this.cy.zoom(level);
    // … und der Pan, bei dem er nach dem Zoom wieder genau dort liegt.
    this.cy.pan({
      x: renderedPosition.x - modell.x * level,
      y: renderedPosition.y - modell.y * level,
    });
  }

  /** Point the camera at a subset — one cluster instead of the whole net.
   *
   * This is the framing an automatic traversal dwells on, and what the
   * pre-render shoots for the close view. It deliberately does not change the
   * mode: the interaction rules stay whatever the operator set. */
  focus(eles, padding = this.padding) {
    this._fitWith(() => this.cy.fit(eles, padding));
  }

  /** Der Ausschnitt, aus dem das Bild gerade entsteht (Birk, 2026-08-31).
   *
   * Gerufen von der Projektion bei den beiden Auslösern, die Tool 1 sieht: ein
   * Portrait erscheint (Interviewbeginn) und neue Begriffe kommen dazu. Beide
   * enden im selben Graph-Push, deshalb genügt EIN Einstieg.
   *
   * Bewegt hier NICHTS sofort. Der Sprung wäre genau der Ruck, gegen den die
   * ganze Datei gebaut ist; stattdessen wird das Gebiet gemerkt und die
   * laufende Fahrt zieht von selbst dorthin — im `pan`-Modus über die
   * Zielauswahl in `_pickTarget`, im Übergang aus `manual` über den Handover.
   *
   * Wirkt NICHT im manuellen Modus: dort hat der Besucher die Wand in der
   * Hand, und eine Kamera, die ihm alle vier Minuten wegspringt, wäre
   * unbrauchbar (Birk). Gemerkt wird das Gebiet trotzdem — beim Rückfall in
   * den Automatik-Modus ist es das Erste, was die Wand zeigt. Genau dafür
   * fragt `_automaticView()` es ab. */
  focusDream(nodes, { now = jetzt() } = {}) {
    if (!nodes || nodes.length === 0) return;
    // Die Menge einfrieren, nicht die Collection halten: Cytoscape-Collections
    // sind an die Elemente gebunden, und ein Knoten, den das nächste Update
    // entfernt, machte jede spätere Messung an dieser Menge unbrauchbar.
    const ids = nodes.map((n) => n.id());
    this._dream = { ids, until: now + DREAM.holdMs, since: now };
    // Im manuellen Modus bleibt die Ansicht, wie sie ist — aber gemerkt ist
    // gemerkt. Sonst ist ein laufender Handover auf das neue Gebiet
    // umzulenken, aus demselben Grund wie in setZoomFactor: ein hartes Framing
    // mitten im Flug ist der Ruck, den der Handover gerade vermeidet.
    if (this._mode === 'manual') return;
    // Kein hartes Framing, sondern eine Fahrt: der Handover ist bereits die
    // Bewegung, die genau dafür gebaut wurde — 5 s Cosinus, von Birk am
    // 2026-08-30 an der Wand auf diesen Wert gesetzt, weil 1,5 s „als Ruck
    // ankamen". Ein Traum entsteht alle vier Minuten, also ist eine
    // Fünf-Sekunden-Fahrt reichlich selten, und sie ist das Erzählmoment: das
    // Netz wandert sichtbar dorthin, wo das nächste Bild herkommt.
    //
    // Gilt für BEIDE getriebenen Modi. In `fit` gäbe `_frame()` sonst wieder
    // das ganze Netz, und `fit` ist die Vorgabe der Station (`camera_mode`
    // default in kg/server.py) — die Kopplung wäre dort also wirkungslos.
    if (this._handover) this._handover.to = this._automaticView();
    else this._startHandover();
  }

  /** Das Traumgebiet vergessen — die Wand rahmt wieder das ganze Netz.
   *
   * Für Werkzeuge, die eine DEFINIERTE Ansicht brauchen statt der Ansicht, die
   * die Station gerade erzählt: `sim/prerender.py` setzt einen Modus und
   * schießt im nächsten Atemzug den Screenshot („fit mode, the whole net in
   * frame — the reference view"). Eine Kamera, die stattdessen auf das
   * Traumgebiet FÄHRT, liefert dort ein Bild mitten in der Bewegung, und die
   * Referenzaufnahme wäre keine Referenz mehr.
   *
   * Öffentlich und nicht als Sonderfall in `setMode`: „ich will die
   * Gesamtansicht" ist eine Absicht des Aufrufers, keine Eigenschaft eines
   * Modus. Die Wand ruft das nie. */
  clearDream() {
    this._dream = null;
    // Auch einen LAUFENDEN Handover beenden, nicht nur das Gebiet vergessen.
    // Das war der zweite Teil des Fehlers und der Grund, warum das Vergessen
    // allein nicht reichte (gemessen: 0.931 -> 0.966 statt 1.0): Die Fahrt
    // aufs Traumgebiet startet schon beim ersten Graph-Push, also WÄHREND
    // `_open_projection` auf `layoutPending === false` wartet. Sie dauert 5 s,
    // der Prerender schießt nach 200 ms — er erwischt also die Fahrt, egal wie
    // gründlich das Gebiet vergessen wurde. `step()` gibt dem Handover den
    // Vorrang vor allem anderen, deshalb muss er hier wirklich weg sein.
    //
    // Ohne Neu-Rahmen: Der Aufrufer setzt unmittelbar danach die Ansicht, die
    // er haben will (`setMode`/`setZoomFactor`/`focus`). Hier zusätzlich zu
    // rahmen hieße, sie zweimal zu werfen.
    this._handover = null;
  }

  /** Die Knoten des Traumgebiets, oder null wenn gerade keines gilt.
   *
   * Läuft die Haltezeit ab, verfällt das Gebiet und die Wand wandert wieder
   * frei — der Rest des Netzes darf nicht stundenlang unsichtbar bleiben.
   * Knoten, die inzwischen aus dem Graphen verschwunden sind, fallen dabei
   * heraus (`.filter` auf der Collection, nicht auf den ids): eine Auswahl,
   * die auf einen entfernten Knoten zeigt, strandete die Fahrt im Nichts. */
  _dreamNodes(now = jetzt()) {
    if (!this._dream) return null;
    if (now >= this._dream.until) {
      this._dream = null;
      return null;
    }
    const live = this.cy.collection(
      this._dream.ids.map((id) => this.cy.getElementById(id)).filter((n) => n.length > 0),
    );
    if (live.empty()) {
      this._dream = null;
      return null;
    }
    return live;
  }

  /** Wie weit der Traumausschnitt gerade aufgezogen ist, 1 = eins zu eins.
   *
   * „Erst den Traum erklären, dann immer mehr Kontext geben" (Birk): der
   * Faktor wächst über die Haltezeit von spreadFrom auf spreadTo. Linear und
   * nicht über easeInOut: das hier ist kein Bewegungsabschnitt mit Anfang und
   * Ende, den jemand als eine Geste sieht, sondern ein vier Minuten langes
   * Driften — eine Kurve mit weichen Enden ließe es zwischendurch schneller
   * laufen als am Rand, und genau das würde als Bewegung auffallen. */
  _dreamSpread(now = jetzt()) {
    if (!this._dream) return DREAM.spreadFrom;
    const t = Math.min(1, Math.max(0, (now - this._dream.since) / DREAM.holdMs));
    return DREAM.spreadFrom + (DREAM.spreadTo - DREAM.spreadFrom) * t;
  }

  /** Ob die Kamera gerade an einen Traum gebunden ist — für Tests und Sonden. */
  get dreamState() {
    if (!this._dream) return null;
    return { ids: [...this._dream.ids], until: this._dream.until, since: this._dream.since };
  }

  _frame() {
    this._fitWith(() => this.cy.fit(this.padding));
    if (this._zoomFactor === 1) return;
    // Zoom about the middle of the viewport, so the net stays centred on the
    // wall instead of drifting towards the model origin.
    this.cy.zoom({
      level: this.cy.zoom() * this._zoomFactor,
      renderedPosition: { x: this.cy.width() / 2, y: this.cy.height() / 2 },
    });
  }

  _applyInteractivity(mode) {
    const interactive = mode === 'manual';
    this.cy.userPanningEnabled(interactive);
    this.cy.userZoomingEnabled(interactive);
    // NOT gated on the mode, unlike the two above. Birk, 2026-08-30, live at
    // the station: in manual mode a visitor's hand pulled portraits and terms
    // out of the arrangement and left them there. Moving the VIEW is what
    // manual mode is for; the arrangement belongs to the layout, always.
    //
    // `autoungrabify` and not `autolock`, and not a `grabbable: false` in the
    // stylesheet, because it is the one of the three that draws the line
    // exactly where Birk drew it — between user input and everything else.
    // Cytoscape gates only its two input handlers on grabbability
    // (`nodeIsDraggable = !locked() && grabbable()`, checked by the mouse
    // handler and again by the separate touch handler, which is the one the
    // foyer's HID digitizer goes through). `locked()` is checked in two more
    // places: by `position()` itself (`canSet: (e) => !e.locked()`) and by the
    // preset layout the migration glide runs on — so `autolock` would take
    // sim/prerender.py, the crash-recovery path and every position-writing
    // test down with the visitor's hand. Both halves of that are measured in
    // tests/test_projection.py rather than left as a claim.
    this.cy.autoungrabify(true);
  }

  onGraphChanged() {
    // Das gecachte Fahrtniveau gilt für eine Knotenwolke, die es nicht mehr
    // gibt (Birk, 2026-08-31, Punkt 7: „springt immer mal wieder").
    //
    // 🔴 Gemessen 2026-09-01 auf dem dichten Testnetz: `_roamBaseLevel` wurde
    // beim ERSTEN Aufruf berechnet und nie wieder — es gab keinen einzigen
    // Weg, den Cache zu verwerfen, außer einer Änderung am Zoomregler. Wächst
    // der Graph, wird der gemerkte Wert falsch:
    //
    //     25 Personen (Wolke 3476px):  gecacht 0.4919, korrekt 0.4919   0 %
    //     35 Personen (Wolke 3807px):  gecacht 0.4919, korrekt 0.4489   9,6 %
    //     45 Personen (Wolke 3934px):  gecacht 0.4919, korrekt 0.4350  13,1 %
    //     55 Personen (Wolke 4515px):  gecacht 0.4919, korrekt 0.3783  30,0 %
    //
    // Und weil `_travelLevel()` den Cache neu füllt, sobald er fehlt, führte
    // das zu einem harten Zoomwechsel mitten im Betrieb — gemessen als
    // Pan-Sprung von bis zu 961 Modellpixeln in EINEM Frame, gegen einen
    // Median von 6 px. Genau Birks „springt von Zeit zu Zeit".
    //
    // Hier verworfen und nicht neu berechnet: Der nächste `_travelLevel()`
    // holt ihn sich, und der läuft ohnehin in jedem Frame. Ein Neuberechnen
    // an dieser Stelle wäre ein `cy.fit()` mitten in einem Frame, in dem
    // gerade das Layout schreibt.
    this._roamBaseLevel = undefined;

    // Same reason as in setZoomFactor: an interview arriving during the 1.5 s
    // handover moves the destination, so the handover is redirected rather
    // than overwritten.
    if (this._handover) this._handover.to = this._automaticView();
    // `_frame()` zeigt das GANZE Netz. Gilt ein Traumgebiet, wäre das der
    // Rückschritt hinter die Kopplung: jeder Graph-Push (also genau der
    // Moment, in dem ein neuer Traum entsteht) risse die Wand wieder auf die
    // Gesamtansicht auf. Dann fährt sie stattdessen auf das Gebiet — dieselbe
    // Fahrt, die focusDream() auslöst.
    else if (this._mode === 'fit') {
      if (this._dreamNodes()) this._startHandover();
      else this._frame();
    }
    // A target that just left the graph (density raised, term hidden) must not
    // strand the traversal mid-leg pointing at nothing.
    if (this._roam && this._roam.targetId && this.cy.getElementById(this._roam.targetId).empty()) {
      this._roam = { phase: 'dwell', elapsed: 0, targetId: null, clock: this._roam.clock };
    }
  }

  /** The level the roaming camera travels at: the operator's calibrated zoom,
   * breathing gently so the image is never completely static. */
  _breathingZoom(baseLevel, clockMs) {
    const wave = Math.sin((2 * Math.PI * clockMs) / ROAM.breathPeriodMs);
    return baseLevel * (1 + ROAM.breathAmplitude * wave);
  }

  /** Pick the next term to travel to.
   *
   * Weighted by degree so the traversal favours shared concepts, and never
   * returns the node it is already sitting on — revisiting immediately would
   * look like the camera got stuck.
   *
   * Gilt ein Traumgebiet, wird NUR daraus gewählt (Birk, 2026-08-31, Variante
   * C): die Kamera wandert weiter — die Wand soll nie einfrieren, dafür gibt
   * es sogar die Atembewegung — aber sie bleibt dort, wo das Bild entsteht.
   * Ohne das wäre der Ausschnitt nach einer Fahrt von 5,2 s wieder verlassen
   * und die Kopplung bei einem Traum alle vier Minuten praktisch wirkungslos.
   *
   * Fällt auf das ganze Netz zurück, sobald das Gebiet abgelaufen ist oder aus
   * einem einzigen Knoten besteht — aus dem einen Knoten wäre kein Ziel mehr
   * wählbar, das nicht der aktuelle ist, und die Fahrt bliebe stehen. */
  _pickTarget() {
    const dream = this._dreamNodes();
    const pool = dream ? dream.nodes('.term') : this.cy.nodes('.term');
    let candidates = pool.filter((n) => n.id() !== this._roam?.targetId);
    if (candidates.empty()) {
      candidates = this.cy.nodes('.term').filter((n) => n.id() !== this._roam?.targetId);
    }
    if (candidates.empty()) return null;
    const weights = candidates.map((n) => Math.pow(n.degree(false) || 1, ROAM.degreeBias));
    const total = weights.reduce((a, b) => a + b, 0);
    let roll = this._random() * total;
    for (let i = 0; i < weights.length; i += 1) {
      roll -= weights[i];
      if (roll <= 0) return candidates[i];
    }
    return candidates[candidates.length - 1];
  }

  /** The view a handover is travelling to, or null when none is in flight. */
  get handoverTarget() {
    return this._handover ? { ...this._handover.to } : null;
  }

  /** Begin the travel from the view the visitor left to the automatic one. */
  _startHandover() {
    const from = { x: this.cy.pan().x, y: this.cy.pan().y, zoom: this.cy.zoom() };
    // In flight BEFORE the target is measured, and provisionally aimed at the
    // view it starts from. _automaticView() performs the hard framing and so
    // writes the zoom three times before putting it back, and the projection
    // sizes its portrait discs off portraitCapBlend on every one of those
    // writes. With the handover not yet in flight the blend would read 1 —
    // the mode has already flipped — and those writes would size the discs as
    // if the ceiling were fully back on, i.e. exactly the snap this travel
    // exists to remove, one frame before it starts.
    this._handover = { elapsed: 0, from, to: { ...from } };
    this._handover.to = this._automaticView();
  }

  /** Where the automatic mode wants the viewport — measured, not derived.
   *
   * It performs the HARD framing this mode does, reads the result off the
   * viewport and puts the visitor's view straight back. Computing the numbers
   * a second time instead would be a second implementation of _frame() and of
   * the traversal's opening zoom, free to drift away from the ones the wall
   * actually uses; this way the handover can only ever land where the old
   * jump landed. */
  _automaticView() {
    const before = { pan: { ...this.cy.pan() }, zoom: this.cy.zoom() };
    // Gilt ein Traumgebiet, ist DAS das Ziel — auch und gerade beim Rückfall
    // aus dem manuellen Modus (Birk, 2026-08-31: „wenn's dann auf den
    // automatischen Modus geht, dann ist das Erste, wo es hinfährt, auch der
    // Bereich, der jetzt gerade für das Bild verantwortlich ist"). Der Besucher
    // hat die Wand vielleicht minutenlang gehalten, während zwei Interviews
    // liefen; sie kehrt dorthin zurück, wo das aktuelle Bild herkommt, nicht
    // zur Gesamtansicht.
    const dream = this._dreamNodes();
    if (dream) {
      // Mal `_zoomFactor`, genau wie `_frame()` und `_travelLevel()` es tun:
      // der Regler bedeutet „so viel enger als die Vollansicht" und muss auf
      // dem Traumgebiet dasselbe bedeuten wie auf dem ganzen Netz. Ohne diese
      // Multiplikation verwarf jedes geltende Traumgebiet die Reglerstellung
      // stillschweigend — gemessen 2026-09-01: Faktor 3 ergab 1,00x statt 3x,
      // und weil im Betrieb fast immer ein Traumgebiet gilt, wirkte der Regler
      // an der Wand gar nicht (Birk, 2026-08-31).
      const level = this._levelForBox(dream, this._dreamSpread()) * this._zoomFactor;
      if (level > 0) {
        const centre = this._dreamCentre(dream);
        return {
          x: this.cy.width() / 2 - centre.x * level,
          y: this.cy.height() / 2 - centre.y * level,
          zoom: level,
        };
      }
    }
    if (this._mode === 'fit') {
      this._frame();
    } else {
      // Pan mode does not re-frame: its opening dwell holds the pan where it
      // is and puts the zoom on the calibrated travel level, about the
      // viewport centre — which carries the pan with it. Reproduced by simply
      // doing it, at clock 0, where the breathing wave is exactly zero and the
      // first step() will therefore continue from the same level.
      this._applyZoom(this._breathingZoom(this._travelLevel(), 0));
    }
    const to = { x: this.cy.pan().x, y: this.cy.pan().y, zoom: this.cy.zoom() };
    this.cy.zoom(before.zoom);
    this.cy.pan(before.pan);
    return to;
  }

  /** One frame of the handover, on the same clock as the tour.
   *
   * Cytoscape's cy.animate() was the obvious alternative and is the wrong tool
   * here: it drives itself from its own requestAnimationFrame, so it would be
   * a second writer on this viewport next to the step() loop that is already
   * running — and the traversal's breathing zoom writes every single frame.
   * Two writers per frame is the kind of bug that surfaces later as jitter.
   * Sharing step()'s dt also means a test can drive the handover, and that a
   * visitor's touch cancels it by dropping one object. */
  _advanceHandover(dtMs) {
    const handover = this._handover;
    handover.elapsed += dtMs;
    const t = Math.min(1, handover.elapsed / ROAM.handoverMs);
    // The same cosine as a leg of the tour, so the handover and the travel it
    // hands over to feel like one movement.
    const eased = easeInOut(t);
    const { from, to } = handover;
    this.cy.zoom(t >= 1 ? to.zoom : lerpZoom(from.zoom, to.zoom, eased));
    this.cy.pan(
      t >= 1
        ? { x: to.x, y: to.y }
        : { x: from.x + (to.x - from.x) * eased, y: from.y + (to.y - from.y) * eased },
    );
    if (t >= 1) this._handover = null;
  }

  step(dtSeconds) {
    const dtMs = dtSeconds * 1000;
    // The handover owns the viewport until it lands: letting the traversal
    // write pan and zoom in the same frame is exactly the two-writer problem
    // the handover avoids by not being a cy.animate().
    if (this._handover) {
      this._advanceHandover(dtMs);
      return;
    }
    if (this._mode !== 'pan') return;
    if (!this._roam) this._roam = { phase: 'dwell', elapsed: 0, targetId: null, clock: 0 };
    const roam = this._roam;
    roam.clock += dtMs;
    roam.elapsed += dtMs;

    if (roam.phase === 'dwell') {
      // Hold still (bar the breathing) until the beat is over, then choose.
      this._applyZoom(this._breathingZoom(this._travelLevel(), roam.clock));
      if (roam.elapsed < (roam.duration ?? this._dwellDuration())) return;
      const target = this._pickTarget();
      if (!target) return; // empty wall: keep waiting rather than throwing
      roam.phase = 'travel';
      roam.elapsed = 0;
      // Frozen for the whole leg: reading the live speed every frame would
      // rescale a glide already in progress, and the eased position would
      // jump the moment the operator touched the slider.
      roam.duration = this._travelDuration();
      roam.targetId = target.id();
      roam.from = { ...this.cy.pan() };
      roam.to = this._panForCentering(target);
      return;
    }

    // travel
    const t = Math.min(1, roam.elapsed / (roam.duration ?? this._travelDuration()));
    const eased = easeInOut(t);
    this._applyZoom(this._breathingZoom(this._travelLevel(), roam.clock));
    // Das Ziel wird JEDEN Frame neu vermessen, nicht beim Start eingefroren.
    //
    // 🔴 Gemessen 2026-09-01 (Birk, Punkt 7: „springt immer mal wieder"): Eine
    // Fahrt dauert rund fünf Sekunden. Kommt in dieser Zeit ein Interview
    // dazu, ordnet fcose das Netz neu und der Zielknoten steht am Ende
    // woanders — die Fahrt landete gemessen 244 bis 536 Modellpixel neben
    // ihm. Sichtbar wurde das nicht während der Fahrt (die läuft ja weich),
    // sondern beim Übergang in die Standzeit: Der nächste Abschnitt beginnt
    // an der falschen Stelle und reißt das Bild dorthin.
    //
    // `roam.from` bleibt eingefroren — es ist der Startpunkt und darf sich
    // nicht bewegen, sonst würde die Fahrt in sich selbst zurücklaufen. Nur
    // das ZIEL wird nachgeführt. Wandert es, verformt sich die Bahn weich,
    // statt am Ende zu springen: `eased` ist beim Nachführen bereits nahe 1,
    // die Korrektur also klein und über die Restzeit verteilt.
    const ziel = roam.targetId ? this.cy.getElementById(roam.targetId) : null;
    if (ziel && ziel.length && !ziel.empty()) roam.to = this._panForCentering(ziel);
    this.cy.pan({
      x: roam.from.x + (roam.to.x - roam.from.x) * eased,
      y: roam.from.y + (roam.to.y - roam.from.y) * eased,
    });
    if (t >= 1) {
      roam.phase = 'dwell';
      roam.elapsed = 0;
      roam.duration = this._dwellDuration();
    }
  }

  /** The zoom level the traversal travels at, derived from the calibrated
   * factor the same way `_frame` derives it — so "1.8×" means the same thing
   * whether the operator is in fit or in pan.
   *
   * Gilt ein Traumgebiet, wird stattdessen DESSEN Box vermessen und über die
   * Haltezeit aufgezogen (`_dreamSpread`) — „erst den Traum eins zu eins, dann
   * immer mehr Kontext". Dieser Zweig wird bewusst NICHT gecacht: der Faktor
   * ändert sich per Definition jede Sekunde, ein Cache wäre hier genau das
   * Gegenteil dessen, was er sonst leistet. Der Cache bleibt für den
   * ungebundenen Fall, wo `cy.fit()` sonst in jedem Frame liefe. */
  _travelLevel() {
    const dream = this._dreamNodes();
    if (dream) {
      // Mal `_zoomFactor` aus demselben Grund wie in `_automaticView()`: der
      // gecachte Zweig unten multipliziert ihn ebenfalls (`* this._zoomFactor`),
      // und die Fahrt darf nicht auf einem anderen Niveau laufen als das Ziel,
      // auf das der Handover sie setzt.
      const level = this._levelForBox(dream, this._dreamSpread()) * this._zoomFactor;
      if (level > 0) return level;
    }
    if (this._roamBaseLevel === undefined || this._roamBaseFactor !== this._zoomFactor) {
      const before = { pan: { ...this.cy.pan() }, zoom: this.cy.zoom() };
      this._fitWith(() => this.cy.fit(this.padding));
      this._roamBaseLevel = this.cy.zoom() * this._zoomFactor;
      this._roamBaseFactor = this._zoomFactor;
      this.cy.zoom(before.zoom);
      this.cy.pan(before.pan);
    }
    return this._roamBaseLevel;
  }

  /** Der Zoom, bei dem `eles` ins Fenster passt, geteilt durch `spread`.
   *
   * Gemessen wie `cy.fit()` es rechnet, statt fit() aufzurufen und das
   * Ergebnis abzulesen: fit() schreibt Pan UND Zoom, und diese Funktion läuft
   * in JEDEM Frame der Fahrt. Ein Schreiben-und-Zurücksetzen pro Frame wäre
   * ein zweiter Schreiber auf dem Viewport neben step() — dieselbe Falle, die
   * der Handover mit dem Verzicht auf cy.animate() umgeht. */
  _levelForBox(eles, spread = 1) {
    const bb = eles.boundingBox({ includeLabels: false });
    if (!(bb.w > 0) || !(bb.h > 0)) return 0;
    const w = this.cy.width() - 2 * this.padding;
    const h = this.cy.height() - 2 * this.padding;
    if (!(w > 0) || !(h > 0)) return 0;
    const level = Math.min(w / bb.w, h / bb.h) / Math.max(1, spread);
    return level > 0 && Number.isFinite(level) ? level : 0;
  }

  /** Die Mitte des Traumgebiets, oder null. Ziel des Handovers aus `manual`. */
  _dreamCentre(nodes) {
    const bb = nodes.boundingBox({ includeLabels: false });
    return { x: (bb.x1 + bb.x2) / 2, y: (bb.y1 + bb.y2) / 2 };
  }

  /** Ob gerade eine Übergabefahrt läuft — für die Wand, die während des
   * Layout-Umzugs alles andere aussetzt (`projection.js`, tick()).
   *
   * Der Handover behält dort Vorrang: Er ist eine gewollte, kurze Bewegung
   * (1,5 s) und würde beim Aussetzen mitten in der Luft stehenbleiben. */
  get handoverActive() {
    return this._handover !== null;
  }

  _applyZoom(level) {
    // Around the viewport centre, so breathing does not also drift the frame.
    this.cy.zoom({
      level,
      renderedPosition: { x: this.cy.width() / 2, y: this.cy.height() / 2 },
    });
  }

  /** The pan that puts `node` in the middle of the viewport at current zoom.
   *
   * Mit einer Bremse am Rand: Der sichtbare Ausschnitt darf die Knotenwolke
   * nicht wesentlich verlassen (Birk, 2026-08-31, Punkt 8 — „die Hälfte des
   * Bildes liegt außerhalb des Graphen, viel schwarze Fläche, wenig Inhalt").
   *
   * 🔴 Gemessen 2026-09-01, dichtes Testnetz (40 Personen, 60 Begriffe,
   * 1920×1080), Zoomregler 2,5×: Der schlechteste Ausschnitt deckte nur 56 %
   * des Bildes mit Knotenwolke ab — der Rest war schwarz. Ursache ist keine
   * Fehlrechnung: Ein Ziel am Rand HAT nun einmal nur auf einer Seite
   * Nachbarschaft. Mit der Bremse sind es 85 %.
   *
   * Die Bremse verschiebt den Ausschnitt zurück auf die Wolke, statt Ziele am
   * Rand seltener zu wählen — die frisch gesagten Begriffe liegen naturgemäß
   * außen, und genau die soll die Fahrt zeigen (Handoff, Punkt 8). Der
   * Zielknoten wandert dabei aus der Mitte, bleibt aber im Bild.
   *
   * `RAND_LUFT` ist bewusst nicht 0: Ein Ausschnitt, der exakt an der Wolke
   * klebt, sieht aus wie ein Anschlag. Ein Rest Luft ringsum liest sich als
   * gewollter Bildrand. */
  _panForCentering(node) {
    const zoom = this.cy.zoom();
    const pos = node.position();
    const mitte = {
      x: this.cy.width() / 2 - pos.x * zoom,
      y: this.cy.height() / 2 - pos.y * zoom,
    };
    return this._klemmeAufWolke(mitte, RAND_LUFT);
  }

  /** Schiebt einen Ausschnitt zurück auf die Knotenwolke.
   *
   * Herausgelöst aus `_panForCentering`, weil der Zoom-Regler der Touchfläche
   * dieselbe Bremse braucht (`setVisitorZoom`) — mit einer anderen Luft, aber
   * derselben Rechnung. Zwei Kopien dieser Klemmung wären zwei Orte, an denen
   * die Bildkante anders definiert ist, und die gemessenen Zahlen im Kommentar
   * über `RAND_LUFT` gälten dann nur noch für eine davon.
   *
   * `luftAnteil` ist der Rand, den der Ausschnitt jenseits der Wolke behalten
   * darf, als Anteil der Bildbreite bzw. -höhe. */
  _klemmeAufWolke(pan, luftAnteil) {
    const zoom = this.cy.zoom();
    const alle = this.cy.elements();
    // Ohne messbare Wolke gibt es nichts zu klemmen: Cytoscape liefert immer
    // eine Bounding-Box, ein schlanker Test-Stub nicht. Die Bremse ist eine
    // Verbesserung des Bildaufbaus, kein Muss — fehlt die Messung, bleibt es
    // beim übergebenen Ausschnitt, statt hier zu werfen und die Fahrt
    // anzuhalten.
    if (typeof alle?.boundingBox !== 'function') return pan;
    const bb = alle.boundingBox({ includeLabels: false });
    if (!(bb.w > 0) || !(bb.h > 0)) return pan;

    // Der sichtbare Modellbereich bei diesem Pan, in Modellkoordinaten.
    const sichtbarB = this.cy.width() / zoom;
    const sichtbarH = this.cy.height() / zoom;

    // Passt die Wolke in eine Richtung ohnehin ganz ins Bild, wird dort
    // zentriert statt geklemmt: Sonst zöge die Bremse an einem Netz, das
    // kleiner als das Fenster ist, den Ausschnitt an eine Kante.
    const luftX = sichtbarB * luftAnteil;
    const luftY = sichtbarH * luftAnteil;

    let x = pan.x;
    if (bb.w + 2 * luftX <= sichtbarB) {
      x = this.cy.width() / 2 - ((bb.x1 + bb.x2) / 2) * zoom;
    } else {
      // Linke Bildkante darf höchstens `luftX` links der Wolke liegen …
      const maxX = -(bb.x1 - luftX) * zoom;
      // … und die rechte höchstens `luftX` rechts davon.
      const minX = this.cy.width() - (bb.x2 + luftX) * zoom;
      x = Math.min(maxX, Math.max(minX, x));
    }

    let y = pan.y;
    if (bb.h + 2 * luftY <= sichtbarH) {
      y = this.cy.height() / 2 - ((bb.y1 + bb.y2) / 2) * zoom;
    } else {
      const maxY = -(bb.y1 - luftY) * zoom;
      const minY = this.cy.height() - (bb.y2 + luftY) * zoom;
      y = Math.min(maxY, Math.max(minY, y));
    }

    return { x, y };
  }
}
