"""Der Zoom-Regler auf der Touchfläche (Birk, 2026-09-01).

Am MacBook mit angeschlossenem Touchscreen: „Das funktioniert jetzt, aber ich
habe halt nur einen Mausklick, ich kann nicht irgendwie reinzoomen.
Zweifingergeste — ist das wegen Mac, geht das einfach nicht? Dann bräuchten wir
halt einen Regler an der Seite, einen Zoom-Regler."

Cytoscape rechnet seinen Pinch-Zoom hinter `t.touches[1]`
(static/vendor/cytoscape.min.js): Ein Digitizer, der nur EINEN Kontakt meldet,
kann dort per Konstruktion nie ankommen. Der Regler ist also nicht die
Notlösung, sondern der Weg. Ob der iiyama im Foyer einen oder zwei Kontakte
liefert, beantwortet `frontend/touchtest.html` am Gerät — für diese Datei ist
es egal, der Regler muss in beiden Fällen tragen.

Drei Eigenschaften tragen hier, und alle drei können still verlorengehen:

1. **Er postet nicht.** Was ein Besucher in der Vorhalle anfasst, darf die
   Wand im Plenarsaal nicht bewegen (`camera_min_label` ist globaler Zustand).
2. **Er zählt als Bedienung.** Sonst bliebe die Wand für immer auf dem
   Ausschnitt des letzten Besuchers stehen — die Bedienleiste ist von der
   Ruheuhr ausdrücklich AUSGENOMMEN, und der Regler braucht die umgekehrte
   Behandlung.
3. **Er hängt an `?touch=1`.** Die Wandansicht bekommt kein Bedienelement.
"""

import pytest

from test_camera import CY_STUB
from test_camera_ruhige_fahrt import WOLKE_STUB
from test_touch_autonomy import HARNESS, TOUCH_GRAPH

# Der rechte Anschlag, gespiegelt aus touch-controls.js (`ZOOM_MAX`).
ZOOM_MAX = 8


# --- Die Kamera: was der Regler an ihr auslöst -------------------------------


@pytest.fixture()
def kamera(page, static_server):
    page.goto(f"{static_server}/frontend/static/test-harness.html")
    page.evaluate(CY_STUB)
    page.evaluate(WOLKE_STUB)
    page.evaluate(
        """async () => {
             const { Camera } = await import('./camera.js');
             window.cam = new Camera(window.cyStub, { panSpeed: 100 });
           }"""
    )
    return page


def _basisniveau(kamera):
    """Der Zoom, bei dem das ganze Netz ins Bild passt — die Bezugsgröße."""
    return kamera.evaluate("window.cam._levelForBox(window.cyStub.elements())")


def test_ein_faktor_sitzt_genau_so_viel_enger_als_die_gesamtansicht(kamera):
    """`3` heisst am Besucherregler dasselbe wie am Regler des Operators.

    Sonst hiesse der linke Anschlag etwas anderes als „Übersicht", und die
    beiden Wege zurück landeten an verschiedenen Stellen.
    """
    basis = _basisniveau(kamera)
    kamera.evaluate("window.cam.setVisitorZoom(3)")
    assert kamera.evaluate("window.cyStub.zoom()") == pytest.approx(basis * 3, rel=1e-6)


def test_der_regler_ruehrt_die_kalibrierung_des_operators_nicht_an(kamera):
    """🔴 Die Isolationseigenschaft, in der Kamera selbst.

    `_minLabelPx` ist die Einstellung, die über `/events` von der Station
    kommt und auf ALLEN Flächen gilt. Ein Besucher schreibt in den Viewport
    dieser Seite, genau wie eine Zweifingergeste — nicht in die Kalibrierung.
    Ginge der Regler über `setMinLabel`, käme dazu, dass er im manuellen
    Modus (dem einzigen, in dem er bedient wird) gar nichts bewegte.
    """
    kamera.evaluate("window.cam.setVisitorZoom(4)")
    assert kamera.evaluate("window.cam.minLabelPx") == 40


def test_der_regler_wirkt_auch_im_manuellen_modus(kamera):
    """Der Modus, in dem er IMMER bedient wird — die Berührung schaltet die
    Kamera über `attachTouchAutonomy` dorthin, bevor der erste `input` kommt.

    `setZoomFactor` steigt hier absichtlich aus, um dem Besucher nicht in die
    Hand zu fahren. Ein Regler, der denselben Weg nähme, setzte eine Zahl und
    bewegte auf dem Schirm nichts.
    """
    basis = _basisniveau(kamera)
    kamera.evaluate("window.cam.setMode('manual')")
    kamera.evaluate("window.cam.setVisitorZoom(2)")
    assert kamera.evaluate("window.cyStub.zoom()") == pytest.approx(basis * 2, rel=1e-6)


def test_unter_die_gesamtansicht_geht_es_nicht(kamera):
    """Weiter herausgezoomt wäre nur noch Rand."""
    basis = _basisniveau(kamera)
    kamera.evaluate("window.cam.setVisitorZoom(0.2)")
    assert kamera.evaluate("window.cyStub.zoom()") == pytest.approx(basis, rel=1e-6)


def test_ein_unbrauchbarer_wert_haelt_die_wand_nicht_an(kamera):
    """Wie `clampRoamSpeed`: Eine unbeaufsichtigte Wand muss abbauen, nie
    stehenbleiben."""
    basis = _basisniveau(kamera)
    kamera.evaluate("window.cam.setVisitorZoom(NaN)")
    assert kamera.evaluate("window.cyStub.zoom()") == pytest.approx(basis, rel=1e-6)


def test_der_ausschnitt_landet_nie_im_leeren(kamera):
    """Eine Hand am Regler darf nirgends im Schwarzen enden.

    Die Fahrt darf am Rand etwas Luft stehen lassen (`RAND_LUFT`, damit der
    Bildrand gewollt aussieht) — ein Besucher, der zieht, nicht. Nebenbei ist
    das der Rückweg für jemanden, der sich weggeschoben hat: Der Regler holt
    den Ausschnitt auf das Netz zurück.
    """
    lage = kamera.evaluate(
        """() => {
             const c = window.cam, cy = window.cyStub;
             // Absichtlich weit neben die Wolke geschoben, wie es eine Hand
             // im manuellen Modus kann.
             cy.pan({ x: 99999, y: 99999 });
             c.setVisitorZoom(8);
             const bb = cy.elements().boundingBox({ includeLabels: false });
             const z = cy.zoom(), pan = cy.pan();
             const links = -pan.x / z, oben = -pan.y / z;
             return { links, oben,
                      rechts: links + cy.width() / z,
                      unten: oben + cy.height() / z,
                      bb };
           }"""
    )
    bb = lage["bb"]
    assert lage["links"] >= bb["x1"] - 1 and lage["rechts"] <= bb["x2"] + 1, (
        f"der Ausschnitt ragt waagerecht aus der Knotenwolke heraus: {lage}"
    )
    assert lage["oben"] >= bb["y1"] - 1 and lage["unten"] <= bb["y2"] + 1, (
        f"der Ausschnitt ragt senkrecht aus der Knotenwolke heraus: {lage}"
    )


def test_ohne_messbare_wolke_wirft_der_regler_nicht(page, static_server):
    """Kein Graph, kein Zoom — aber auch kein Fehler.

    Der Regler steht auf der Wand, bevor das erste Interview da ist. Eine
    Ausnahme an dieser Stelle risse die Seite ab, bevor überhaupt jemand
    kommt.
    """
    page.goto(f"{static_server}/frontend/static/test-harness.html")
    page.evaluate(CY_STUB)  # ohne WOLKE_STUB: elements() hat keine boundingBox
    page.evaluate(
        """async () => {
             const { Camera } = await import('./camera.js');
             window.cam = new Camera(window.cyStub, { panSpeed: 100 });
             window.cam.setVisitorZoom(3);
           }"""
    )
    assert page.evaluate("window.cam.mode") == "fit"


# --- Die Autonomie: wer am Regler zieht, steuert ------------------------------


@pytest.fixture()
def autonomie(page, static_server):
    """Die Autonomie mit einer nachgebauten Leiste — Knopf UND Regler."""
    page.goto(f"{static_server}/frontend/static/test-harness.html")
    page.evaluate(HARNESS)
    page.evaluate(
        """() => {
             window.freigaben = [];
             const bar = document.createElement('div');
             bar.className = 'touch-controls';
             const knopf = document.createElement('button');
             knopf.id = 'knopf';
             const huelle = document.createElement('div');
             huelle.id = 'huelle';
             huelle.dataset.autonomie = 'steuern';
             const regler = document.createElement('input');
             regler.id = 'regler';
             regler.type = 'range';
             huelle.appendChild(regler);
             bar.append(knopf, huelle);
             document.body.appendChild(bar);
           }"""
    )
    page.evaluate(
        """async () => {
             const { attachTouchAutonomy } = await import('./touch-autonomy.js');
             window.autonomy = attachTouchAutonomy(window.fakeView, {
               setTimer: window.fakeSetTimer,
               clearTimer: window.fakeClearTimer,
               onRelease: () => window.freigaben.push('frei'),
             });
           }"""
    )
    return page


def test_wer_den_regler_anfasst_steuert(autonomie):
    """🔴 Die umgekehrte Behandlung.

    Die Bedienleiste ist von der Ruheuhr ausgenommen, weil „Übersicht" sich
    sonst selbst überschriebe (2026-08-26). Der Regler braucht das Gegenteil:
    Wer ihn zieht, navigiert — sonst zählt die Wand die 30 s nie an und bleibt
    für immer auf dem Ausschnitt des letzten Besuchers stehen.
    """
    autonomie.evaluate(
        "document.getElementById('regler').dispatchEvent("
        "new PointerEvent('pointerdown', {bubbles: true}))"
    )
    assert autonomie.evaluate("window.fakeCamera.mode") == "manual"
    assert autonomie.evaluate("window.autonomy.manual") is True


def test_der_knopf_daneben_zaehlt_weiterhin_nicht(autonomie):
    """Die Ausnahme darf nicht durch die neue Regel verlorengehen.

    Genau das ist der Fehler, der hier schon einmal passiert ist: „Übersicht"
    stellte die Kamera zurück, und dieselbe Berührung schaltete sie sofort
    wieder auf manuell — der Knopf sah tot aus.
    """
    autonomie.click("#knopf")
    assert autonomie.evaluate("window.fakeCamera.mode") == "pan"
    assert autonomie.evaluate("window.autonomy.manual") is False


def test_ein_langer_zug_haelt_die_ruheuhr_am_laufen(autonomie):
    """Ein Regler liefert nach dem ersten `pointerdown` nur noch `input`.

    Ohne das liefe die 30-s-Uhr während des Ziehens weiter und könnte mitten
    in der Bewegung ablaufen — die Wand risse sich die Ansicht unter der Hand
    des Besuchers zurück.
    """
    autonomie.evaluate(
        "document.getElementById('regler').dispatchEvent("
        "new PointerEvent('pointerdown', {bubbles: true}))"
    )
    autonomie.evaluate("window.pendingTimer = null")
    autonomie.evaluate(
        "document.getElementById('regler').dispatchEvent(new Event('input', {bubbles: true}))"
    )
    assert autonomie.evaluate("window.pendingTimer") is not None, (
        "ein `input` am Regler stösst die Ruheuhr nicht an"
    )


def test_der_rueckfall_in_die_automatik_wird_gemeldet(autonomie):
    """Damit der Griff mitgeht, wenn die Wand sich selbst zurücknimmt.

    Ein Regler, der 4x anzeigt, während die Wand die Übersicht zeigt, ist
    schlimmer als keiner: Die nächste Hand bewegt ihn um eine Kleinigkeit und
    das Bild springt um vier Stufen.
    """
    autonomie.evaluate(
        "document.getElementById('regler').dispatchEvent("
        "new PointerEvent('pointerdown', {bubbles: true}))"
    )
    assert autonomie.evaluate("window.freigaben") == []
    autonomie.evaluate("window.fireIdle()")
    assert autonomie.evaluate("window.freigaben") == ["frei"]


# --- Die echte Fläche: projection.html?touch=1 -------------------------------


@pytest.fixture()
def flaeche(page, static_server):
    page.goto(f"{static_server}/frontend/projection.html?touch=1")
    page.wait_for_function("window.kgTouch !== undefined")
    page.evaluate(
        "window.kgFetches = [];"
        " window.fetch = (url) => { window.kgFetches.push(url);"
        " return Promise.resolve({ok: true, json: () => Promise.resolve({})}); };"
        " void 0;"
    )
    page.evaluate("(g) => window.kgView.update(g, 1)", TOUCH_GRAPH)
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)
    return page


def _ziehen(page, weg):
    """Den Griff auf `weg` (0…1) setzen, wie eine Hand es täte."""
    page.eval_on_selector(
        "#touch-zoom",
        """(el, w) => {
             el.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
             el.value = String(w);
             el.dispatchEvent(new Event('input', {bubbles: true}));
           }""",
        weg,
    )


def test_die_wandansicht_bekommt_keinen_regler(page, static_server):
    """🔴 Alles Neue hängt an `?touch=1`, wie die bestehende Bedienleiste.

    Fläche C im Plenarsaal lädt dieselbe Seite ohne die Fahne und bleibt eine
    reine Anzeige: kein Bedienelement, keine lokale Übersteuerung, den ganzen
    Tag genau die Einstellung des Operators.
    """
    page.goto(f"{static_server}/frontend/projection.html")
    page.wait_for_function("window.kgView !== undefined")
    assert page.evaluate("document.getElementById('touch-zoom') === null")
    assert page.evaluate("document.querySelector('.touch-controls') === null")
    assert page.evaluate("window.kgTouch === undefined")


def test_der_regler_zoomt_den_ausschnitt_dieser_seite(flaeche):
    davor = flaeche.evaluate("window.kgView.cy.zoom()")
    _ziehen(flaeche, 0.5)
    danach = flaeche.evaluate("window.kgView.cy.zoom()")
    assert danach > davor, "der Regler bewegt den Ausschnitt nicht"


def test_gleicher_weg_bedeutet_gleiches_verhaeltnis(flaeche):
    """Der Weg ist geometrisch, nicht linear — dieselbe Begründung, aus der
    `lerpZoom` in camera.js Zoomstufen als Faktoren interpoliert: Das Auge
    liest Verhältnisse. Linear läge die halbe Strecke bei 4,5x statt bei
    2,83x, und am Griff fühlte es sich an, als passiere zuerst nichts und
    dann alles auf einmal."""
    _ziehen(flaeche, 0)
    ganz_raus = flaeche.evaluate("window.kgView.cy.zoom()")
    _ziehen(flaeche, 0.5)
    halb = flaeche.evaluate("window.kgView.cy.zoom()")
    _ziehen(flaeche, 1)
    ganz_rein = flaeche.evaluate("window.kgView.cy.zoom()")

    assert halb / ganz_raus == pytest.approx(ZOOM_MAX**0.5, rel=0.02)
    assert ganz_rein / halb == pytest.approx(ZOOM_MAX**0.5, rel=0.02)
    assert ganz_rein / ganz_raus == pytest.approx(ZOOM_MAX, rel=0.02)


def test_der_regler_erreicht_den_server_nicht(flaeche):
    """🔴 Die tragende Regel dieser Fläche: „whatever a visitor presses on
    surface A must stay on surface A".

    `camera_min_label` ist globaler Zustand und wird über `/events` an jede Fläche
    verteilt. Ein POST von hier zöge die Projektion im Plenarsaal vor
    sitzendem Publikum mit — ohne dass dort jemand etwas angefasst hätte.
    """
    _ziehen(flaeche, 0.3)
    _ziehen(flaeche, 0.9)
    _ziehen(flaeche, 0.0)
    assert flaeche.evaluate("window.kgFetches") == []


def test_der_regler_laesst_die_kalibrierung_der_station_stehen(flaeche):
    """Auch lokal nicht: `camera_min_label` bleibt, was der Operator gesetzt hat.

    Sonst widerspräche die Vorhalle für den Rest des Tages der Einstellung
    der Station, ohne dass es jemand bemerkt — dasselbe Argument, aus dem die
    Dichtestufen am 2026-08-26 hier verschwunden sind.
    """
    vorher = flaeche.evaluate("window.kgView.camera.minLabelPx")
    _ziehen(flaeche, 0.7)
    assert flaeche.evaluate("window.kgView.camera.minLabelPx") == vorher


def test_wer_am_regler_zieht_steuert_auch_auf_der_echten_flaeche(flaeche):
    _ziehen(flaeche, 0.4)
    assert flaeche.evaluate("window.kgView.camera.mode") == "manual"
    assert flaeche.evaluate("window.kgTouch.autonomy.manual") is True


def test_uebersicht_ist_weiterhin_der_ganze_rueckweg(flaeche):
    """🔴 Nach einer Reglerbedienung muss „Übersicht" alles zurücksetzen.

    Drei Dinge auf einmal, weil es für den Besucher eine Sache ist: raus aus
    meinem Zoom, zurück auf das ganze Netz — und der Griff des Reglers steht
    wieder da, wo das Bild steht.
    """
    _ziehen(flaeche, 0.8)
    assert flaeche.evaluate("window.kgView.camera.mode") == "manual"

    flaeche.click("#touch-overview")

    assert flaeche.evaluate("window.kgView.camera.mode") == "fit"
    # Der Weg zurueck ist eine FAHRT und kein Sprung (siehe `_startHandover`).
    assert flaeche.evaluate("window.kgView.camera.handoverActive") is True
    # Und die Kalibrierung der Station ist dabei nicht angefasst worden.
    assert flaeche.evaluate("window.kgView.camera.minLabelPx") == 40
    assert flaeche.evaluate("document.getElementById('touch-zoom').value") == "0"
    assert flaeche.evaluate("window.kgTouch.autonomy.manual") is False
    assert flaeche.evaluate("window.kgFetches") == []


def test_der_griff_ist_fuer_einen_finger_gebaut(flaeche):
    """Kein Formular, sondern ein Ausstellungs-Touchscreen.

    Der Knopf daneben hält 48 px, das übliche Mindestziel. Der Regler bekommt
    mehr, weil ein Finger dort nicht einmal treffen, sondern während einer
    ziehenden Bewegung auf der Bahn bleiben muss — auf einem IR-Panel, das
    Kontakte über dem Glas meldet, die schwerere Aufgabe.
    """
    masse = flaeche.eval_on_selector(
        "#touch-zoom",
        """(el) => {
             const kasten = el.getBoundingClientRect();
             return { hoehe: kasten.height, breite: kasten.width };
           }""",
    )
    assert masse["hoehe"] >= 48, f"die Trefferzone ist zu flach: {masse}"
    assert masse["breite"] >= 240, f"der Reglerweg ist zu kurz: {masse}"


def test_der_regler_liegt_in_der_bestehenden_bedienleiste(flaeche):
    """Stil und Platzierung von „Übersicht", nicht ein zweites Bedienfeld
    daneben: Die Fläche soll eine Leiste haben, nicht zwei."""
    assert flaeche.evaluate(
        "document.getElementById('touch-zoom').closest('.touch-controls') !== null"
    )
