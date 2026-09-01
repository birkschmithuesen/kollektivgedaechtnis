"""Der Regler des Operators wirkt auch auf ein geltendes Traumgebiet.

Warum es diese Datei gibt (Birk, 2026-08-31: „Zoom und Portraitgröße im
Operator ändern an der Wand nichts"):

`_frame()` und der gecachte Zweig von `_travelLevel()` rechneten den Regler
ein, der Traum-Zweig — der Weg, den die Wand nimmt, sobald ein Traumgebiet
gilt — tat es nicht und verwarf die Reglerstellung damit stillschweigend.
Weil im Betrieb fast durchgehend ein Traumgebiet gilt (Haltezeit 4 Minuten),
war das an der Wand der Normalfall und nicht der Sonderfall.

Gemessen vor der Reparatur: Faktor 3 ergab am Traumgebiet 1,00× statt 3×.

Am 2026-09-02 hat der Regler die Einheit gewechselt — aus dem Zoomfaktor
wurde eine Mindestschriftgröße in gezeichneten Pixeln, und aus der
Multiplikation ein `max(Ausschnitt, Ziel)`. Die Frage dieser Datei bleibt
Wort für Wort dieselbe: Kommt der Regler im Traum-Zweig überhaupt an.

Der bestehende `tests/test_camera.py` deckt diesen Zweig nicht ab, weil sein
`cyStub` weder `collection()` noch `boundingBox()` kennt — beides ergänzt der
DREAM_STUB unten. Genau diese Lücke hat den Defekt so lange getragen.
"""

import pytest

from test_camera import CY_STUB

# Was der Stub der Hauptsuite nicht kann: eine Collection mit Bounding-Box,
# also das, worauf der Traum-Zweig seine Rechnung stützt.
DREAM_STUB = """
window.cyStub.collection = function (arr) {
  const c = arr.slice();
  c.empty = () => c.length === 0;
  c.boundingBox = () => {
    const xs = c.map((n) => n.position().x);
    const ys = c.map((n) => n.position().y);
    const x1 = Math.min(...xs) - 50, x2 = Math.max(...xs) + 50;
    const y1 = Math.min(...ys) - 50, y2 = Math.max(...ys) + 50;
    return {x1, y1, x2, y2, w: x2 - x1, h: y2 - y1};
  };
  return c;
};
const _stub = window.cyStub;
window.cyStub.getElementById = function (id) {
  const t = _stub._terms.find((x) => x.id === id);
  if (!t) return {length: 0, empty: () => true};
  return {
    length: 1,
    id: () => t.id,
    degree: () => t.degree,
    position: () => ({x: t.x, y: t.y}),
    empty: () => false,
  };
};
"""


@pytest.fixture()
def traumkamera(page, static_server):
    page.goto(f"{static_server}/frontend/static/test-harness.html")
    page.evaluate(CY_STUB)
    page.evaluate(DREAM_STUB)
    page.evaluate(
        """async () => {
             const { Camera } = await import('./camera.js');
             window.cam = new Camera(window.cyStub, { panSpeed: 100 });
           }"""
    )
    return page


def _traumgebiet_setzen(cam):
    # Zwei der drei Stub-Begriffe, also ein echter Ausschnitt und nicht das
    # ganze Netz — sonst wäre die Messung nicht vom Fit-Fall zu unterscheiden.
    cam.evaluate("window.cam.focusDream([{id: () => 't1'}, {id: () => 't3'}])")


def _zielzoom(cam):
    return cam.evaluate("window.cam._automaticView().zoom")


def test_die_mindestschrift_wirkt_auf_das_traumgebiet(traumkamera):
    """Reicht die Traumbox für sich, wird sie eins zu eins gezeigt — sonst
    zieht die Mindestschrift den Ausschnitt enger.

    Das ist dieselbe Regel wie für das ganze Netz (`max(Ausschnitt, Ziel)`),
    und sie muss es sein: Ein Traumgebiet, das anders gerechnet würde, wäre
    genau der stillschweigend verworfene Regler, gegen den diese Datei
    geschrieben ist.
    """
    traumkamera.evaluate("window.cam.setMode('fit')")
    # Klein genug, dass die Traumbox die Schrift von sich aus liefert.
    traumkamera.evaluate("window.cam.setMinLabel(8)")
    _traumgebiet_setzen(traumkamera)
    eins_zu_eins = _zielzoom(traumkamera)

    # Und jetzt eine Mindestschrift, die die Box nicht mehr hergibt.
    traumkamera.evaluate("window.cam.setMinLabel(104)")  # 104/26 = 4,0
    _traumgebiet_setzen(traumkamera)
    enger = _zielzoom(traumkamera)

    assert enger > eins_zu_eins, (
        f"die Mindestschrift muss den Traumausschnitt enger ziehen: {eins_zu_eins} -> {enger}"
    )
    assert enger == pytest.approx(4.0, rel=1e-3), (
        "und zwar genau bis zur Mindestschrift, nicht weiter"
    )


def test_die_fahrt_laeuft_auf_demselben_niveau_wie_ihr_ziel(traumkamera):
    # Handover-Ziel (_automaticView) und Fahrt (_travelLevel) müssen dasselbe
    # Niveau meinen, sonst zieht die Fahrt die Ansicht nach der Ankunft wieder
    # weg. Beide Zweige mussten repariert werden, also prüft das hier beide.
    traumkamera.evaluate("window.cam.setMode('pan')")
    traumkamera.evaluate("window.cam.setMinLabel(78)")  # 78/26 = 3,0
    _traumgebiet_setzen(traumkamera)

    ziel = _zielzoom(traumkamera)
    fahrt = traumkamera.evaluate("window.cam._travelLevel()")
    assert fahrt == pytest.approx(ziel, rel=1e-3), (
        f"Fahrtniveau {fahrt} weicht vom Handover-Ziel {ziel} ab"
    )


def test_ohne_traumgebiet_faehrt_der_regler_auf_dasselbe_niveau(traumkamera):
    # Die Gegenprobe zur Reparatur: der Weg ohne Traumgebiet muss dieselbe
    # Rechnung fahren wie der mit, sonst sind es wieder zwei Rechnungen.
    traumkamera.evaluate("window.cam.setMode('pan')")
    traumkamera.evaluate("window.cam.setMinLabel(78)")  # 78/26 = 3,0
    assert traumkamera.evaluate("window.cam._travelLevel()") == pytest.approx(3.0, rel=1e-3)


def test_der_traumausschnitt_zieht_sich_nicht_ueber_die_zeit_auf(traumkamera):
    """Der Bildausschnitt bleibt, wo der Regler ihn hinstellt.

    Birk am 2026-09-01 an der Wand: „Mein Problem ist, dass es konstant immer
    weiter rauszieht. Das ist ja nicht die Idee der Sache, eigentlich sollte
    es immer identisch bleiben, den stelle ich einmal ein."

    Bis dahin weitete `_dreamSpread()` den Ausschnitt über die vier Minuten
    Haltezeit linear von 1,0 auf 2,1 — der Ausschnitt war also nach vier
    Minuten mehr als doppelt so weit wie eingestellt und sprang beim nächsten
    Traum zurück auf eins. Gemeint war eine Dramaturgie („erst den Traum
    erklären, dann Kontext geben"), an der Wand war es ein Bild, das nie
    stehenbleibt.

    Geprüft wird der Faktor über die volle Haltezeit, nicht nur der Endwert:
    ein Test auf `spreadTo == 1.0` allein wäre eine Wiederholung der
    Konstanten und würde jede andere Aufziehmechanik durchlassen.
    """
    traumkamera.evaluate("window.cam.setMode('pan')")
    _traumgebiet_setzen(traumkamera)

    # 0 s, 2 min, 4 min, 8 min nach dem Auslöser -- die Haltezeit sind 4 min.
    faktoren = traumkamera.evaluate(
        """() => {
             const seit = window.cam.dreamState.since;
             return [0, 120000, 240000, 480000].map(
               (ms) => window.cam._dreamSpread(seit + ms));
           }"""
    )
    assert all(f == pytest.approx(1.0, rel=1e-6) for f in faktoren), (
        f"Der Traumausschnitt darf sich nicht aufziehen, gemessen: {faktoren}"
    )


def test_das_fahrtniveau_bleibt_ueber_die_haltezeit_konstant(traumkamera):
    """Die Gegenprobe am ECHTEN Wert, nicht an der Hilfsfunktion.

    `_dreamSpread()` könnte konstant 1,0 liefern und der Ausschnitt sich
    trotzdem bewegen, wenn ihn noch etwas anderes aufzieht. Deshalb hier das,
    was die Wand tatsächlich sieht: das Fahrtniveau zu Beginn und am Ende der
    Haltezeit.
    """
    traumkamera.evaluate("window.cam.setMode('pan')")
    traumkamera.evaluate("window.cam.setMinLabel(78)")  # 78/26 = 3,0
    _traumgebiet_setzen(traumkamera)

    niveaus = traumkamera.evaluate(
        """() => {
             const cam = window.cam;
             const seit = cam.dreamState.since;
             const echt = cam._dreamSpread.bind(cam);
             const messe = (ms) => {
               cam._dreamSpread = () => echt(seit + ms);
               const v = cam._travelLevel();
               cam._dreamSpread = echt;
               return v;
             };
             return [messe(0), messe(240000)];
           }"""
    )
    anfang, ende = niveaus
    assert ende == pytest.approx(anfang, rel=1e-6), (
        f"Das Fahrtniveau driftet über die Haltezeit: {anfang} -> {ende}"
    )
