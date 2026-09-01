// Die Zwei-Finger-Geste auf der Touchfläche (Nachtrag Birk, 2026-09-01, 20:15).
//
// „Windows ruckelt, deswegen sind wir jetzt auf das MacBook gegangen. Jetzt
// läuft der Touchscreen auf meinem MacBook. Das heißt, wir müssen dort auch
// das Zoom hinbekommen, die Zwei-Finger-Geste. Oder wir brauchen den Regler,
// aber ich würde gerne das Zoom haben, das muss ja irgendwie gehen."
//
// Warum sie unter Windows wirkte und auf dem Mac nicht — zwei Ursachen, und
// beide muss dieses Modul aus dem Weg räumen.
//
// ERSTENS: DER KANAL.
// Ein Browser meldet eine Pinch-Geste auf drei verschiedenen Wegen (Dan
// Cătălin Burzo, „Pinch me, I'm zooming: gestures in the DOM",
// danburzo.ro/dom-gestures/):
//
//   Chrome/Brave/Firefox auf macOS  ->  wheel-Event mit ctrlKey: true
//   Safari                          ->  gesturestart/-change, fertiges scale
//   Mobile Browser                  ->  TouchEvent mit den Kontaktpunkten
//
// Cytoscape sucht von sich aus nur auf dem dritten: Seine Pinch-Rechnung steht
// hinter `t.touches[1]` (vendor/cytoscape.min.js). Reicht macOS die Geste des
// externen Digitizers stattdessen als `wheel` + ctrlKey durch — so, wie es
// Trackpad-Gesten tut —, sieht Cytoscape nie zwei Finger, und die Geste bleibt
// wirkungslos, obwohl das Gerät sie sauber meldet. Welcher Kanal am echten
// Schirm ankommt, zeigt `frontend/touchtest.html`; hier sind alle drei
// bedient, weil die Antwort erst vor Ort vorliegt und die Wand morgen in jedem
// Fall zoomen muss.
//
// ZWEITENS: DER MODUS — die Stelle, an der ein naiver Einbau LAUTLOS scheitert.
// Cytoscapes eigener Zoom-Zweig steht hinter
// `panningEnabled() && userPanningEnabled() && zoomingEnabled() &&
// userZoomingEnabled()`, und diese Schalter setzt `camera.js::_applyInteractivity`
// nur im Modus `manual`. In `pan` und `fit` folgt daraus dreierlei:
//
//   - es wird nicht gezoomt,
//   - es wird kein `preventDefault()` gerufen, also zoomt Brave die ganze
//     SEITE — die Ausstellungswand stünde für den Rest des Tages auf 150 %,
//   - und im Modus `pan` schreibt `camera.step()` in JEDEM Frame Zoom und Pan:
//     Ein Zoom, der die Kamera nicht vorher nach `manual` holt, wäre einen
//     Frame später wieder weg.
//
// Deshalb ist `onSteuern` kein Beiwerk, sondern das Erste, was jeder Handler
// hier tut. Auf der Wand hängt es an `autonomy.poke()` — derselben Tür, durch
// die auch eine Berührung des Graphen geht, samt der 30-Sekunden-Ruheuhr, die
// die Wand danach von selbst zurückholt.
//
// ARBEITSTEILUNG MIT CYTOSCAPE. Die beiden Kanäle, die Cytoscape nicht kennt
// (`wheel` + ctrlKey, `gesture*`), übernimmt dieses Modul ganz — und nimmt sie
// Cytoscape mit `stopPropagation()` aus der Hand, weil dessen Wheel-Handler auf
// demselben Ereignis sitzt und in `manual` sonst ein zweites Mal zoomte: Der
// Ausschlag käme im Quadrat an, die Geste liefe doppelt so schnell wie die
// Hand. Den Kanal, den Cytoscape kennt (zwei TouchEvent-Kontakte), lässt es
// unangetastet durch und stellt nur die Voraussetzung her — dort ist der
// eingebaute Weg der geprüfte, und ein zweiter daneben wäre derselbe
// Doppelzoom.

import { ZOOM_MAX } from './camera.js';

/** Wieviel Zoom ein Ausschlag von `deltaY` bedeutet: Faktor = 10^(-deltaY/250).
 *
 * Exakt Cytoscapes eigene Rechnung (`s = t.deltaY / -250`, dann
 * `zoom * Math.pow(10, s)`, vendor/cytoscape.min.js). Bewusst abgeschrieben
 * und nicht neu gewählt: Auf demselben Schirm läuft im Modus `manual` auch
 * Cytoscapes Mausrad-Zoom, und zwei verschiedene Empfindlichkeiten für
 * dieselbe Handbewegung wären ein Unterschied, den niemand erklären kann. Und
 * es ist der Wert, gegen den die Geste in Chromium seit Jahren abgestimmt ist.
 */
const RAD_TEILER = 250;

export function attachZoomGeste(
  view,
  {
    target = document,
    // „Der Besucher steuert jetzt." Auf der Wand `autonomy.poke()`.
    onSteuern = () => {},
    // Der erreichte Faktor (1 = ganzes Netz). Der Regler stellt seinen Griff
    // darauf, damit er nicht etwas anderes anzeigt als das Bild.
    onZoom = () => {},
  } = {},
) {
  // Safaris `scale` ist ABSOLUT zum Gestenbeginn, nicht ein Schritt. Also muss
  // der Stand bei `gesturestart` festgehalten werden — sonst zoomten zwei
  // `gesturechange` mit demselben `scale` zweimal, und die Geste liefe davon.
  let gesteBasis = null;

  /** Der Punkt unter den Fingern, in Cytoscapes gerenderten Koordinaten.
   *
   * Über den Behälter und nicht über `clientX` direkt: Auf der Wand füllt
   * `#cy` zwar das Fenster, aber das ist eine Eigenschaft des Stylesheets und
   * keine Zusicherung — läge der Graph je in einem Rahmen, zoomte die Geste
   * sonst um einen um den Rahmenversatz verschobenen Punkt, und das fiele als
   * „zieht beim Zoomen leicht weg" auf, nicht als Fehler. */
  function mitte(event) {
    const behaelter = typeof view.cy.container === 'function' ? view.cy.container() : null;
    const kasten =
      behaelter && typeof behaelter.getBoundingClientRect === 'function'
        ? behaelter.getBoundingClientRect()
        : { left: 0, top: 0 };
    return { x: event.clientX - kasten.left, y: event.clientY - kasten.top };
  }

  /** Einen Zielfaktor anwenden und melden. Geklemmt wird in der Kamera —
   * dort steht der Anschlag, den auch der Regler meint (`ZOOM_MAX`). */
  function anwenden(faktor, renderedPosition) {
    view.camera.setVisitorZoom(faktor, { renderedPosition });
    // Den TATSÄCHLICHEN Stand melden, nicht den gewünschten: An der Schranke
    // sind das zwei verschiedene Zahlen, und der Griff des Reglers soll dem
    // Bild folgen, nicht dem Wunsch.
    onZoom(view.camera.visitorZoom);
  }

  // --- Chromium auf macOS: wheel + ctrlKey ------------------------------------
  const amRad = (event) => {
    // Ohne ctrlKey ist es ein gewöhnliches Mausrad und damit Cytoscapes Sache.
    // Griffe die Erkennung auch dort zu, zoomte auf dem Entwicklungsrechner
    // jedes Scrollen doppelt.
    if (!event.ctrlKey) return;
    event.preventDefault();
    event.stopPropagation();
    onSteuern();
    const schritt = Math.pow(10, -event.deltaY / RAD_TEILER);
    anwenden(view.camera.visitorZoom * schritt, mitte(event));
  };

  // --- Safari: gesturestart / gesturechange / gestureend ----------------------
  const gesteBeginnt = (event) => {
    event.preventDefault();
    event.stopPropagation();
    onSteuern();
    gesteBasis = view.camera.visitorZoom;
  };

  const gesteZieht = (event) => {
    event.preventDefault();
    event.stopPropagation();
    // Ein `gesturechange` ohne vorheriges `gesturestart` gibt es nicht — ausser
    // wenn die Seite mitten in einer Geste geladen wurde. Dann ist der
    // aktuelle Stand die einzig ehrliche Bezugsgrösse.
    if (gesteBasis === null) gesteBasis = view.camera.visitorZoom;
    onSteuern();
    const skala = Number(event.scale);
    anwenden(gesteBasis * (Number.isFinite(skala) && skala > 0 ? skala : 1), mitte(event));
  };

  const gesteEndet = (event) => {
    event.preventDefault();
    event.stopPropagation();
    gesteBasis = null;
  };

  // --- Der Weg, den Cytoscape schon kennt: zwei TouchEvent-Kontakte -----------
  //
  // Hier wird NICHT gezoomt. Cytoscapes Pinch-Zweig ist der eingebaute,
  // geprüfte Weg und macht nebenbei auch das Zwei-Finger-Schieben; was ihm
  // fehlt, ist allein die Voraussetzung. Also nur `poke()` — und zwar in der
  // Capture-Phase am `document`, damit der Modus steht, BEVOR Cytoscapes
  // eigener Handler am Behälter läuft und seine Wächterbedingung prüft.
  const zweiFingerAuf = (event) => {
    // Ein Finger ist eine Berührung, keine Geste: `touches.length` von 1
    // erreicht Cytoscapes Pinch-Rechnung hinter `t.touches[1]` nie. Und es
    // wäre die Rückkehr des Fehlers vom 2026-08-26 — jede Berührung der
    // Bedienleiste zählte als Steuern und „Übersicht" überschriebe sich selbst.
    if (!event.touches || event.touches.length < 2) return;
    onSteuern();
  };

  // Dieselbe Geste, aber in der Bubble-Phase: Da hat Cytoscape seinen Zoom
  // bereits geschrieben, und erst danach lässt sich der erreichte Faktor
  // ablesen und an den Griff des Reglers weitergeben.
  const zweiFingerZiehen = (event) => {
    if (!event.touches || event.touches.length < 2) return;
    onSteuern();
    onZoom(view.camera.visitorZoom);
  };

  // 🔴 `capture: true` und `passive: false` sind beide tragend: capture, damit
  // dieses Modul vor Cytoscapes Handlern am Behälter liegt (nur dort greift
  // `stopPropagation` überhaupt und nur dort steht der Modus rechtzeitig), und
  // `passive: false`, weil ein passiver Handler `preventDefault()` still
  // verwirft — und dann zoomt Brave die Seite.
  const fangen = { capture: true, passive: false };
  target.addEventListener('wheel', amRad, fangen);
  target.addEventListener('gesturestart', gesteBeginnt, fangen);
  target.addEventListener('gesturechange', gesteZieht, fangen);
  target.addEventListener('gestureend', gesteEndet, fangen);
  target.addEventListener('touchstart', zweiFingerAuf, { capture: true, passive: true });
  target.addEventListener('touchmove', zweiFingerZiehen, { capture: false, passive: true });

  return {
    detach() {
      target.removeEventListener('wheel', amRad, fangen);
      target.removeEventListener('gesturestart', gesteBeginnt, fangen);
      target.removeEventListener('gesturechange', gesteZieht, fangen);
      target.removeEventListener('gestureend', gesteEndet, fangen);
      target.removeEventListener('touchstart', zweiFingerAuf, { capture: true });
      target.removeEventListener('touchmove', zweiFingerZiehen, { capture: false });
    },
    /** Der Anschlag, gegen den die Geste läuft — für Tests und Sonden. */
    get max() {
      return ZOOM_MAX;
    },
  };
}
