"""Der Zoomregler des Operators wirkt auch auf ein geltendes Traumgebiet.

Warum es diese Datei gibt (Birk, 2026-08-31: „Zoom und Portraitgröße im
Operator ändern an der Wand nichts"):

`_frame()` und der gecachte Zweig von `_travelLevel()` multiplizieren das
Fit-Niveau mit `_zoomFactor`. Der Traum-Zweig — der Weg, den die Wand nimmt,
sobald ein Traumgebiet gilt — tat es nicht, und verwarf die Reglerstellung
damit stillschweigend. Weil im Betrieb fast durchgehend ein Traumgebiet gilt
(Haltezeit 4 Minuten), war das an der Wand der Normalfall und nicht der
Sonderfall.

Gemessen vor der Reparatur: Faktor 3 ergab am Traumgebiet 1,00× statt 3×.

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


def test_zoomregler_wirkt_auf_das_traumgebiet(traumkamera):
    traumkamera.evaluate("window.cam.setMode('fit')")
    _traumgebiet_setzen(traumkamera)
    eins = _zielzoom(traumkamera)

    traumkamera.evaluate("window.cam.setZoomFactor(3)")
    _traumgebiet_setzen(traumkamera)
    drei = _zielzoom(traumkamera)

    # Der Regler bedeutet „so viel enger als die Vollansicht" — auf dem
    # Traumgebiet dasselbe wie auf dem ganzen Netz.
    assert drei == pytest.approx(eins * 3, rel=1e-3), (
        f"Zoomfaktor 3 muss das Traumziel verdreifachen: {eins} -> {drei}"
    )


def test_die_fahrt_laeuft_auf_demselben_niveau_wie_ihr_ziel(traumkamera):
    # Handover-Ziel (_automaticView) und Fahrt (_travelLevel) müssen dasselbe
    # Niveau meinen, sonst zieht die Fahrt die Ansicht nach der Ankunft wieder
    # weg. Beide Zweige mussten repariert werden, also prüft das hier beide.
    traumkamera.evaluate("window.cam.setMode('pan')")
    traumkamera.evaluate("window.cam.setZoomFactor(2)")
    _traumgebiet_setzen(traumkamera)

    ziel = _zielzoom(traumkamera)
    fahrt = traumkamera.evaluate("window.cam._travelLevel()")
    assert fahrt == pytest.approx(ziel, rel=1e-3), (
        f"Fahrtniveau {fahrt} weicht vom Handover-Ziel {ziel} ab"
    )


def test_ohne_traumgebiet_bleibt_der_regler_wie_er_war(traumkamera):
    # Die Gegenprobe zur Reparatur: der Weg ohne Traumgebiet war nie defekt
    # und darf sich nicht mitverändert haben.
    traumkamera.evaluate("window.cam.setMode('fit')")
    traumkamera.evaluate("window.cam.setZoomFactor(3)")
    assert traumkamera.evaluate("window.cyStub._zoom") == 3
