"""Die Mindestschrift entscheidet, ob die Wand faehrt (Birk, 2026-09-02).

    „Die automatische Kamerafahrt sollte eigentlich erst einsetzen, wenn nicht
     mehr das ganze Netz darstellbar ist. Solange das ganze Netz darstellbar
     ist und es zu klein wird, brauchen wir gar keine Kamerafahrt."

Der Parameter dahinter ist eine Groesse, keine Vergroesserung: Cytoscape
skaliert `font-size` mit dem Zoom, die Schrift auf der Wand ist also
`--label-size x zoom`. Daraus folgt beides -- wie weit gefahren wird UND ob
ueberhaupt gefahren wird.

Diese Datei fasst nur den neuen Entscheid an. Wie sich die Fahrt selbst
bewegt, steht in test_camera.py und test_camera_ruhige_fahrt.py.
"""

import pytest

from tests.test_camera import CY_STUB

# Der Stub aus test_camera.py laesst `fit()` den Zoom immer auf 1 stehen -- er
# hat kein Netz, dessen Groesse sich aendern koennte. Genau das ist hier aber
# die Eingangsgroesse: Ein wachsendes Netz heisst ein SINKENDES Fit-Niveau.
# Also wird `fit()` steuerbar gemacht, statt einen zweiten Stub danebenzulegen.
# Als Funktion und nicht als nackte Anweisungsfolge: `page.evaluate` mit einem
# String wertet ihn als AUSDRUCK aus und serialisiert das Ergebnis -- eine
# zugewiesene Funktion laesst sich nicht serialisieren.
FIT_STEUERBAR = """() => {
  window.cyStub._fitLevel = 1;
  window.cyStub.fit = function (a, b) {
    this._zoom = this._fitLevel;
    this._pan = {x: 0, y: 0};
    if (b === undefined) this.calls.push(['fit', a]);
    else this.calls.push(['fit', a.stubName, b]);
  };
}"""

# 40 px Mindestschrift auf 26 Modelleinheiten Schriftgroesse -- die Vorgabe der
# Ausstellung. Das Fahrtniveau ist damit 40/26 = 1,538.
ZIEL = 40 / 26


@pytest.fixture()
def kamera(page, static_server):
    page.goto(f"{static_server}/frontend/static/test-harness.html")
    page.evaluate(CY_STUB)
    page.evaluate(FIT_STEUERBAR)
    page.evaluate(
        """async () => {
             const { Camera } = await import('./camera.js');
             window.cam = new Camera(window.cyStub, { panSpeed: 100 });
           }"""
    )
    return page


def _netzgroesse(kamera, fit_niveau):
    """Ein Netz dieser Groesse melden: hohes Fit-Niveau = kleines Netz."""
    kamera.evaluate(f"window.cyStub._fitLevel = {fit_niveau}")
    kamera.evaluate("window.cam.onGraphChanged()")


def test_die_vorgabe_ist_die_gemessene_kalibrierung(kamera):
    """40 px, rekonstruiert aus Birks Reglerstellung vom 2026-09-01."""
    assert kamera.evaluate("window.cam.minLabelPx") == 40
    assert kamera.evaluate("window.cam.labelSize") == 26


def test_passt_das_ganze_netz_lesbar_ins_bild_faehrt_die_kamera_nicht(kamera):
    """Ein Interview, wenige Begriffe: die Wand zeigt alles und haelt still."""
    _netzgroesse(kamera, 2.2)  # gemessen: 1 Interview auf der 4K-Wand
    kamera.evaluate("window.cam.setMode('pan')")
    assert kamera.evaluate("window.cam.fahrtNoetig") is False

    kamera.evaluate("window.cyStub.calls.length = 0")
    for _ in range(20):
        kamera.evaluate("window.cam.step(0.5)")
    assert kamera.evaluate("window.cyStub.calls") == [], (
        "im Stillstand darf dieser Modus den Viewport ueberhaupt nicht anfassen"
    )


def test_im_stillstand_steht_das_ganze_netz_im_bild(kamera):
    """Nicht bloss keine Bewegung -- der richtige Ausschnitt.

    `step()` schreibt im Stillstand nichts, also muss der Rahmen beim
    Zustandswechsel gesetzt worden sein. Ohne das bliebe der Fahrt-Ausschnitt
    stehen, den niemand mehr aufraeumt.
    """
    _netzgroesse(kamera, 1.0)
    kamera.evaluate("window.cam.setMode('pan')")
    kamera.evaluate("window.cam.step(9.0)")  # in die Fahrt hinein
    assert kamera.evaluate("window.cyStub._zoom") != 1.0

    _netzgroesse(kamera, 2.2)  # Begriffe fallen weg, alles passt wieder
    kamera.evaluate("window.cam.step(9.0)")  # Uebergabefahrt ausfahren
    kamera.evaluate("window.cam.step(9.0)")
    assert kamera.evaluate("window.cam.fahrtNoetig") is False
    assert kamera.evaluate("window.cyStub._zoom") == pytest.approx(2.2, rel=1e-3)


def test_wird_das_netz_zu_gross_setzt_die_fahrt_ein(kamera):
    """Ab dem vierten Interview (gemessen) reicht die Vollansicht nicht mehr."""
    _netzgroesse(kamera, 2.2)
    kamera.evaluate("window.cam.setMode('pan')")
    assert kamera.evaluate("window.cam.fahrtNoetig") is False

    _netzgroesse(kamera, 1.25)  # gemessen: 4 Interviews
    assert kamera.evaluate("window.cam.fahrtNoetig") is True

    kamera.evaluate("window.cam.step(9.0)")
    kamera.evaluate("window.cyStub.calls.length = 0")
    kamera.evaluate("window.cam.step(1.0)")
    assert kamera.evaluate("window.cyStub.calls.length") > 0, "jetzt muss sie fahren"


def test_die_fahrt_zoomt_genau_bis_zur_mindestschrift(kamera):
    """Und keinen Schritt weiter -- der Regler ist eine Untergrenze, kein Faktor.

    Der alte Zoomfaktor multiplizierte das Fit-Niveau und fuhr auf einem
    kleinen Netz deshalb absurd nah heran. `max(Ausschnitt, Ziel)` kann das
    nicht: Es faehrt nur so weit, wie die Lesbarkeit es verlangt.
    """
    _netzgroesse(kamera, 1.0)
    kamera.evaluate("window.cam.setMode('pan')")
    # Ueber die Uebergabefahrt hinaus, dann steht das Fahrtniveau.
    for _ in range(20):
        kamera.evaluate("window.cam.step(0.5)")
    assert kamera.evaluate("window.cyStub._zoom") == pytest.approx(ZIEL, rel=0.07), (
        "das Fahrtniveau ist die Mindestschrift, plus/minus die Atembewegung"
    )


def test_der_uebergang_ins_fahren_ist_eine_fahrt_und_kein_sprung(kamera):
    """Der Wechsel ist die eine sichtbare Bewegung dieser ganzen Mechanik."""
    _netzgroesse(kamera, 2.2)
    kamera.evaluate("window.cam.setMode('pan')")
    _netzgroesse(kamera, 1.0)
    assert kamera.evaluate("window.cam.handoverActive") is True

    stufen = kamera.evaluate(
        """(() => {
             const z = [window.cyStub._zoom];
             for (let i = 0; i < 12; i++) { window.cam.step(0.4); z.push(window.cyStub._zoom); }
             return z;
           })()"""
    )
    schritte = [abs(b - a) for a, b in zip(stufen, stufen[1:])]
    spanne = abs(stufen[-1] - stufen[0])
    assert max(schritte) < spanne * 0.5, f"ein Frame nahm zu viel vorweg: {schritte}"


def test_an_der_schwelle_kippt_die_wand_nicht_hin_und_her(kamera):
    """Hysterese.

    Gemessen ueber die Interview-Leiter: bei 4 Interviews liefert die
    Vollansicht 32,6 px, bei 5 dann 35,8 px -- die Kurve ist nicht monoton,
    weil fcose das Netz jedes Mal neu ordnet. Ohne Luft im Rueckweg begaenne
    und endete die Fahrt im Wechsel, ohne dass sich etwas Sichtbares aenderte.
    """
    _netzgroesse(kamera, 1.0)
    kamera.evaluate("window.cam.setMode('pan')")
    assert kamera.evaluate("window.cam.fahrtNoetig") is True

    # Knapp UEBER der Schwelle -- das allein darf die Fahrt nicht beenden.
    _netzgroesse(kamera, ZIEL * 1.05)
    assert kamera.evaluate("window.cam.fahrtNoetig") is True

    # Mit Luft darueber: jetzt steht sie.
    _netzgroesse(kamera, ZIEL * 1.20)
    assert kamera.evaluate("window.cam.fahrtNoetig") is False

    # Und zurueck nach unten reicht das blosse Unterschreiten wieder.
    _netzgroesse(kamera, ZIEL * 0.99)
    assert kamera.evaluate("window.cam.fahrtNoetig") is True


def test_ein_hoeherer_regler_schickt_die_wand_auf_die_fahrt(kamera):
    """Der Operator dreht -- und die Entscheidung faellt sofort neu.

    Beide Eingangsgroessen der Schwelle koennen sich aendern, das Netz und der
    Regler. Ohne diese Neubewertung wirkte der Regler erst beim naechsten
    Interview, also unter Umstaenden minutenlang gar nicht.
    """
    _netzgroesse(kamera, 1.6)
    kamera.evaluate("window.cam.setMode('pan')")
    assert kamera.evaluate("window.cam.fahrtNoetig") is False

    kamera.evaluate("window.cam.setMinLabel(80)")  # 80/26 = 3,08
    assert kamera.evaluate("window.cam.fahrtNoetig") is True


def test_im_manuellen_modus_wird_gar_nichts_bewertet(kamera):
    """Dort hat der Besucher die Wand in der Hand -- auch die Messung kostet.

    `_fahrtZustandPruefen` misst ueber ein `cy.fit()`, das Pan und Zoom setzt
    und zuruecknimmt. In `manual` faellt es aus, damit diese Kamera dort
    wirklich keinen einzigen Schreibzugriff macht.
    """
    kamera.evaluate("window.cam.setMode('manual')")
    kamera.evaluate("window.cyStub.calls.length = 0")
    kamera.evaluate("window.cyStub._fitLevel = 0.5")
    kamera.evaluate("window.cam.onGraphChanged()")
    kamera.evaluate("window.cam.step(1.0)")
    assert kamera.evaluate("window.cyStub.calls") == []
