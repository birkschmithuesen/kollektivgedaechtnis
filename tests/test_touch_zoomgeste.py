"""Die Zwei-Finger-Geste auf der Touchfläche (Nachtrag Birk, 2026-09-01, 20:15).

Die Lage hat sich umgekehrt: Die Ausstellung läuft nicht mehr auf dem
Windows-Rechner, sondern auf dem MacBook mit Brave — „Windows ruckelt, deswegen
sind wir jetzt auf das MacBook gegangen … wir müssen dort auch das Zoom
hinbekommen, die Zwei-Finger-Geste." Damit ist die Geste ausstellungskritisch
und der Regler (`test_touch_zoomregler.py`) der Rückfallweg.

🔴 Warum sie unter Windows wirkte und auf dem Mac nicht — die zwei Ursachen,
die diese Datei absichert:

1. **Der Kanal.** Ein Browser meldet eine Pinch-Geste auf drei verschiedenen
   Wegen (Dan Cătălin Burzo, „Pinch me, I'm zooming: gestures in the DOM"):
   Chromium auf macOS als `wheel` mit `ctrlKey: true`, Safari als
   `gesturechange` mit fertigem `scale`, mobile Browser als `TouchEvent` mit
   zwei Kontakten. Cytoscape sucht von sich aus nur auf dem dritten (seine
   Pinch-Rechnung steht hinter `t.touches[1]`). Kommt die Geste als `wheel` an,
   sieht Cytoscape nie zwei Finger — und die Geste bleibt wirkungslos, obwohl
   das Gerät sie sauber meldet.

2. **Der Modus.** Cytoscapes eigener Zoom-Zweig steht hinter
   `panningEnabled() && userPanningEnabled() && zoomingEnabled() &&
   userZoomingEnabled()` (vendor/cytoscape.min.js), und diese beiden Schalter
   setzt `camera.js::_applyInteractivity` NUR im Modus `manual`. In `pan` oder
   `fit` passiert deshalb zweierlei: Es wird nicht gezoomt, UND es wird kein
   `preventDefault()` gerufen — Brave zoomt dann die ganze Seite. Ausserdem
   schreibt `step()` im Modus `pan` in jedem Frame Zoom und Pan; ein Zoom, der
   die Kamera nicht vorher nach `manual` holt, wäre im nächsten Frame weg.
   **Das ist die Stelle, an der ein naiver Einbau lautlos scheitert**, und
   `test_die_fahrt_ueberschreibt_den_zoom_der_geste_nicht` ist der Test dafür.

Welcher der drei Kanäle am echten Gerät ankommt, beantwortet
`frontend/touchtest.html` — hier sind alle drei abgesichert, weil die Antwort
erst morgen vor Ort vorliegt und die Wand in jedem Fall zoomen muss.
"""

import pytest

from test_camera import CY_STUB
from test_camera_ruhige_fahrt import WOLKE_STUB
from test_touch_autonomy import TOUCH_GRAPH

# Der rechte Anschlag, gespiegelt aus camera.js (`ZOOM_MAX`).
ZOOM_MAX = 8


# --- Die Kamera: Zoom um einen Punkt statt um die Bildmitte -------------------


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


def test_der_punkt_unter_den_fingern_bleibt_stehen(kamera):
    """🔴 „Der Zoom muss um den Gestenmittelpunkt greifen, nicht um die
    Bildmitte — sonst fühlt es sich falsch an" (Nachtrag).

    Das ist der ganze Unterschied zwischen einer Geste und einem Regler: Wer
    zwei Finger auf ein Portrait legt und sie spreizt, erwartet, dass DIESES
    Portrait größer wird — nicht, dass es aus dem Bild wandert, weil die
    Vergrößerung um die Bildmitte lief.
    """
    lage = kamera.evaluate(
        """() => {
             const c = window.cam, cy = window.cyStub;
             c.setMode('manual');
             c.setVisitorZoom(4);
             const punkt = { x: 700, y: 500 };
             const z1 = cy.zoom(), p1 = cy.pan();
             const modell = { x: (punkt.x - p1.x) / z1, y: (punkt.y - p1.y) / z1 };
             c.setVisitorZoom(5, { renderedPosition: punkt });
             const z2 = cy.zoom(), p2 = cy.pan();
             return {
               modell,
               danach: { x: (punkt.x - p2.x) / z2, y: (punkt.y - p2.y) / z2 },
               z1, z2,
             };
           }"""
    )
    assert lage["z2"] > lage["z1"], "die Geste hat gar nicht gezoomt"
    assert lage["danach"]["x"] == pytest.approx(lage["modell"]["x"], abs=1.0), (
        f"der Punkt unter den Fingern ist waagerecht weggewandert: {lage}"
    )


def test_derselbe_schritt_an_verschiedenen_stellen_fuehrt_woandershin(kamera):
    """Die Probe darauf, dass der Mittelpunkt überhaupt gelesen wird.

    Ein Einbau, der `renderedPosition` entgegennimmt und stillschweigend
    ignoriert, bestünde den Test darüber in einem Zustand, in dem die Bremse
    ohnehin zentriert — hier nicht.
    """
    links = kamera.evaluate(
        """() => {
             const c = window.cam, cy = window.cyStub;
             c.setMode('manual');
             c.setVisitorZoom(2);
             c.setVisitorZoom(3, { renderedPosition: { x: 100, y: 540 } });
             return cy.pan().x;
           }"""
    )
    rechts = kamera.evaluate(
        """() => {
             const c = window.cam, cy = window.cyStub;
             c.setVisitorZoom(2);
             c.setVisitorZoom(3, { renderedPosition: { x: 1820, y: 540 } });
             return cy.pan().x;
           }"""
    )
    assert links != rechts, (
        "derselbe Zoomschritt landet links wie rechts am selben Ort — "
        "der Gestenmittelpunkt wird nicht gelesen"
    )
    assert links > rechts, (
        "eine Geste am linken Rand muss den Ausschnitt weiter links stehen lassen "
        f"als dieselbe Geste am rechten: {links} vs {rechts}"
    )


def test_ohne_mittelpunkt_bleibt_es_beim_regler_verhalten(kamera):
    """Der Regler ruft dieselbe Methode ohne Punkt und muss unverändert um die
    Bildmitte zoomen — sonst hätte der Nachtrag den Rückfallweg beschädigt."""
    basis = kamera.evaluate("window.cam._levelForBox(window.cyStub.elements())")
    kamera.evaluate("window.cam.setVisitorZoom(3)")
    assert kamera.evaluate("window.cyStub.zoom()") == pytest.approx(basis * 3, rel=1e-6)


def test_der_gestenzoom_kennt_denselben_rechten_anschlag_wie_der_regler(kamera):
    """Sonst zieht ein Besucher mit zwei Fingern in eine Vergrößerung, aus der
    der Griff des Reglers ihn nicht mehr herausholt — und die beiden
    Bedienwege meinten verschiedene Dinge."""
    kamera.evaluate("window.cam.setMode('manual')")
    kamera.evaluate("window.cam.setVisitorZoom(500)")
    assert kamera.evaluate("window.cam.visitorZoom") == pytest.approx(ZOOM_MAX, rel=1e-6)


def test_die_kamera_sagt_wie_weit_hineingezoomt_ist(kamera):
    """Damit der Griff des Reglers einer Geste folgen kann.

    Gelesen und nicht gemerkt: Ein zweiter Zustand neben dem Viewport liefe
    auseinander, sobald eine Übergabefahrt, ein neuer Graph oder „Übersicht"
    den Zoom anfasst — und dann zeigte der Griff wieder etwas anderes an als
    das Bild.
    """
    kamera.evaluate("window.cam.setMode('manual')")
    kamera.evaluate("window.cam.setVisitorZoom(2.5)")
    assert kamera.evaluate("window.cam.visitorZoom") == pytest.approx(2.5, rel=1e-6)


# --- Das Modul: die drei Kanäle ----------------------------------------------


@pytest.fixture()
def geste(page, static_server):
    """Die echte Kamera an einem Stub-Graphen, mit angehängter Gestenerkennung.

    `onSteuern` schaltet hier von Hand nach `manual` — auf der Wand macht das
    `autonomy.poke()`. Der echte Draht wird weiter unten an `projection.html`
    geprüft; hier geht es um die Erkennung der drei Kanäle.
    """
    page.goto(f"{static_server}/frontend/static/test-harness.html")
    page.evaluate(CY_STUB)
    page.evaluate(WOLKE_STUB)
    page.evaluate(
        """() => {
             const behaelter = document.createElement('div');
             behaelter.id = 'behaelter';
             behaelter.style.cssText = 'position:fixed;inset:0';
             document.body.appendChild(behaelter);
             window.cyStub.container = () => behaelter;
             // Ein Horcher AUF dem Behälter: Cytoscape hängt seine eigenen
             // Zoom-Handler genau dort auf. Was hier ankommt, käme dort auch an.
             window.durchgelassen = [];
             behaelter.addEventListener('wheel', (e) => window.durchgelassen.push(e.type));
             behaelter.addEventListener('gesturechange', (e) => window.durchgelassen.push(e.type));
           }"""
    )
    page.evaluate(
        """async () => {
             const { Camera } = await import('./camera.js');
             const { attachZoomGeste } = await import('./touch-zoom-geste.js');
             window.cam = new Camera(window.cyStub, { panSpeed: 100 });
             window.view = { camera: window.cam, cy: window.cyStub };
             window.gesteuert = 0;
             window.gemeldet = [];
             window.geste = attachZoomGeste(window.view, {
               onSteuern: () => { window.gesteuert += 1; window.cam.setMode('manual'); },
               onZoom: (f) => window.gemeldet.push(f),
             });
           }"""
    )
    return page


def _rad(page, *, strg=True, dy=-40.0, x=960.0, y=540.0):
    page.evaluate(
        """({strg, dy, x, y}) => document.getElementById('behaelter').dispatchEvent(
             new WheelEvent('wheel', {ctrlKey: strg, deltaY: dy, clientX: x, clientY: y,
                                      bubbles: true, cancelable: true}))""",
        {"strg": strg, "dy": dy, "x": x, "y": y},
    )


def _safari(page, art, skala=1.0, x=960.0, y=540.0):
    page.evaluate(
        """({art, skala, x, y}) => {
             const e = new Event(art, {bubbles: true, cancelable: true});
             e.scale = skala;
             e.clientX = x;
             e.clientY = y;
             document.getElementById('behaelter').dispatchEvent(e);
           }""",
        {"art": art, "skala": skala, "x": x, "y": y},
    )


def _finger(page, art, anzahl):
    page.evaluate(
        """({art, anzahl}) => {
             const ziel = document.getElementById('behaelter');
             const punkte = [];
             for (let i = 0; i < anzahl; i += 1) {
               punkte.push(new Touch({identifier: i, target: ziel,
                                      clientX: 400 + 200 * i, clientY: 540}));
             }
             ziel.dispatchEvent(new TouchEvent(art, {
               touches: punkte, targetTouches: punkte, changedTouches: punkte,
               bubbles: true, cancelable: true}));
           }""",
        {"art": art, "anzahl": anzahl},
    )


def test_ein_rad_mit_strgtaste_zoomt_hinein(geste):
    """🔴 Der Chromium-Weg auf macOS — der wahrscheinlichste Kanal morgen.

    Negatives `deltaY` heisst „Finger auseinander", also näher heran.
    """
    davor = geste.evaluate("window.cyStub.zoom()")
    _rad(geste, dy=-40)
    assert geste.evaluate("window.cyStub.zoom()") > davor


def test_ein_rad_in_die_andere_richtung_zoomt_heraus(geste):
    geste.evaluate("window.cam.setMode('manual'); window.cam.setVisitorZoom(4)")
    davor = geste.evaluate("window.cyStub.zoom()")
    _rad(geste, dy=+40)
    assert geste.evaluate("window.cyStub.zoom()") < davor


def test_ein_gewoehnliches_scrollrad_bleibt_unangetastet(geste):
    """Ohne `ctrlKey` ist es keine Geste, sondern ein Mausrad — und das ist
    Cytoscapes eigene Sache. Griffe die Erkennung auch dort zu, zoomte auf dem
    Entwicklungsrechner jedes Scrollen doppelt."""
    davor = geste.evaluate("window.cyStub.zoom()")
    _rad(geste, strg=False, dy=-40)
    assert geste.evaluate("window.cyStub.zoom()") == davor
    assert geste.evaluate("window.gesteuert") == 0
    assert geste.evaluate("window.durchgelassen") == ["wheel"]


def test_die_geste_wird_dem_browser_weggenommen(geste):
    """🔴 Ohne `preventDefault` zoomt Brave die ganze SEITE statt des Graphen.

    Cytoscape ruft es selbst — aber erst hinter seiner Wächterbedingung, also
    nur im Modus `manual`. In `pan` und `fit` fiele die allererste Geste damit
    an den Browser, und die Ausstellungswand stünde für den Rest des Tages auf
    150 % Seitenzoom.
    """
    verschluckt = geste.evaluate(
        """() => {
             const e = new WheelEvent('wheel', {ctrlKey: true, deltaY: -40,
                                                clientX: 960, clientY: 540,
                                                bubbles: true, cancelable: true});
             document.getElementById('behaelter').dispatchEvent(e);
             return e.defaultPrevented;
           }"""
    )
    assert verschluckt is True


def test_cytoscape_sieht_die_geste_nicht_mehr(geste):
    """🔴 Sonst zoomt es zweimal: einmal hier, einmal in Cytoscapes eigenem
    Wheel-Zweig, der auf demselben Ereignis sitzt und im Modus `manual`
    ebenfalls zugreift. Der Ausschlag käme im Quadrat an — die Geste führe
    doppelt so schnell wie die Hand.
    """
    _rad(geste, dy=-40)
    assert geste.evaluate("window.durchgelassen") == []


def test_ein_gesturechange_zoomt_ueber_scale(geste):
    """Der Safari-Weg. Chromium kennt ihn nicht, aber er kostet zehn Zeilen,
    und die Frage „testet Birk vielleicht doch in Safari" ist morgen früh
    keine, die jemand noch beantworten will."""
    _safari(geste, "gesturestart", 1.0)
    davor = geste.evaluate("window.cyStub.zoom()")
    _safari(geste, "gesturechange", 2.0)
    danach = geste.evaluate("window.cyStub.zoom()")
    assert danach == pytest.approx(davor * 2, rel=0.02)


def test_scale_gilt_gegen_den_stand_bei_gestenbeginn(geste):
    """Safaris `scale` ist absolut zum Gestenbeginn, nicht ein Schritt: zwei
    `gesturechange` mit demselben `scale` dürfen nicht zweimal zoomen."""
    _safari(geste, "gesturestart", 1.0)
    _safari(geste, "gesturechange", 2.0)
    einmal = geste.evaluate("window.cyStub.zoom()")
    _safari(geste, "gesturechange", 2.0)
    assert geste.evaluate("window.cyStub.zoom()") == pytest.approx(einmal, rel=1e-6)


def test_zwei_finger_zaehlen_als_bedienung(geste):
    """Der Weg, den Cytoscape schon kennt — er braucht nur den Modus.

    Hier wird NICHT selbst gezoomt: Cytoscapes Pinch-Zweig ist der eingebaute,
    geprüfte Weg, und ein zweiter daneben zoomte im Quadrat. Was fehlt, ist
    allein die Voraussetzung — `userZoomingEnabled` ist nur in `manual` wahr.
    """
    _finger(geste, "touchstart", 2)
    assert geste.evaluate("window.gesteuert") == 1
    assert geste.evaluate("window.cam.mode") == "manual"


def test_ein_finger_allein_ist_keine_geste(geste):
    """Sonst zählte jede Berührung der Bedienleiste als Steuern und
    „Übersicht" überschriebe sich wieder selbst (der Fehler vom 2026-08-26)."""
    _finger(geste, "touchstart", 1)
    assert geste.evaluate("window.gesteuert") == 0


def test_der_touchweg_bleibt_bei_cytoscape(geste):
    """Weder verschluckt noch gestoppt: Cytoscape braucht dieselben Ereignisse
    für seinen Pinch UND für das Zwei-Finger-Schieben."""
    durch = geste.evaluate(
        """() => {
             const ziel = document.getElementById('behaelter');
             let gesehen = false;
             ziel.addEventListener('touchstart', () => { gesehen = true; }, {once: true});
             const punkte = [0, 1].map((i) => new Touch({identifier: i, target: ziel,
                                                         clientX: 400 + 200 * i, clientY: 540}));
             const e = new TouchEvent('touchstart', {touches: punkte, targetTouches: punkte,
                                                     changedTouches: punkte,
                                                     bubbles: true, cancelable: true});
             ziel.dispatchEvent(e);
             return { gesehen, verschluckt: e.defaultPrevented };
           }"""
    )
    assert durch["gesehen"] is True, "Cytoscape bekäme die Geste nicht mehr zu sehen"
    assert durch["verschluckt"] is False


def test_die_geste_meldet_den_erreichten_faktor(geste):
    """Damit der Griff des Reglers mitgeht. Ein Griff, der etwas anderes
    anzeigt als das Bild, ist schlimmer als keiner (touch-controls.js)."""
    _rad(geste, dy=-120)
    gemeldet = geste.evaluate("window.gemeldet")
    assert gemeldet, "die Geste meldet keinen Faktor"
    assert gemeldet[-1] == pytest.approx(geste.evaluate("window.cam.visitorZoom"), rel=1e-6)


def test_abhaengen_loest_die_geste_wieder(geste):
    """Wie `attachTouchAutonomy.detach()` — ein Modul, das sich nicht lösen
    lässt, ist in einem Test nicht isolierbar."""
    geste.evaluate("window.geste.detach()")
    davor = geste.evaluate("window.cyStub.zoom()")
    _rad(geste, dy=-40)
    assert geste.evaluate("window.cyStub.zoom()") == davor


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


def _pinch(page, dy=-60.0, x=600.0, y=400.0):
    page.evaluate(
        """({dy, x, y}) => document.getElementById('cy').dispatchEvent(
             new WheelEvent('wheel', {ctrlKey: true, deltaY: dy, clientX: x, clientY: y,
                                      bubbles: true, cancelable: true}))""",
        {"dy": dy, "x": x, "y": y},
    )


def test_eine_geste_zoomt_den_ausschnitt_dieser_seite(flaeche):
    davor = flaeche.evaluate("window.kgView.cy.zoom()")
    _pinch(flaeche)
    assert flaeche.evaluate("window.kgView.cy.zoom()") > davor


def test_wer_eine_geste_macht_steuert(flaeche):
    """Die Kopplung an `manual` — über `autonomy.poke()`, dieselbe Tür, durch
    die eine Berührung des Graphen geht."""
    _pinch(flaeche)
    assert flaeche.evaluate("window.kgView.camera.mode") == "manual"
    assert flaeche.evaluate("window.kgTouch.autonomy.manual") is True


def test_die_fahrt_ueberschreibt_den_zoom_der_geste_nicht(flaeche):
    """🔴 Die Stelle, an der ein naiver Einbau LAUTLOS scheitert (Nachtrag).

    Im Modus `pan` schreibt `step()` in jedem Frame Zoom und Pan. Eine Geste,
    die die Kamera nicht vorher nach `manual` holt, zoomt sichtbar für genau
    einen Frame und ist im nächsten wieder weg — auf der Wand sieht das aus,
    als täte die Geste gar nichts.
    """
    flaeche.evaluate("window.kgView.camera.setMode('pan')")
    _pinch(flaeche, dy=-120)
    nach_geste = flaeche.evaluate("window.kgView.cy.zoom()")
    flaeche.evaluate("window.kgView.camera.step(0.1)")
    assert flaeche.evaluate("window.kgView.cy.zoom()") == pytest.approx(
        nach_geste, rel=1e-6
    ), "die Kamerafahrt hat den Zoom der Geste im nächsten Frame überschrieben"


def test_eine_geste_erreicht_den_server_nicht(flaeche):
    """🔴 Die tragende Regel dieser Fläche: „whatever a visitor presses on
    surface A must stay on surface A". Auch eine Geste ist ein Druck."""
    _pinch(flaeche, dy=-60)
    _pinch(flaeche, dy=+30)
    assert flaeche.evaluate("window.kgFetches") == []
    # Und die Kalibrierung der Station steht, wo sie stand.
    assert flaeche.evaluate("window.kgView.camera.minLabelPx") == 40


def test_der_griff_des_reglers_folgt_der_geste(flaeche):
    """Sonst stünde der Griff auf dem linken Anschlag, während die Wand eine
    Nahaufnahme zeigt — und die nächste Hand risse das Bild um vier Stufen."""
    _pinch(flaeche, dy=-200)
    faktor = flaeche.evaluate("window.kgView.camera.visitorZoom")
    weg = float(flaeche.evaluate("document.getElementById('touch-zoom').value"))
    assert faktor > 1.05, "die Geste hat kaum gezoomt — der Test misst nichts"
    assert ZOOM_MAX**weg == pytest.approx(faktor, rel=0.02), (
        f"der Griff steht auf {weg} und zeigt damit {ZOOM_MAX**weg:.2f}x, "
        f"während das Bild auf {faktor:.2f}x steht"
    )


def test_uebersicht_holt_auch_aus_einer_geste_zurueck(flaeche):
    """Der Rückweg muss für beide Bedienwege derselbe sein.

    🔴 ANGEPASST AM 2026-09-02. Vorher stand hier `value == "0"` DIREKT nach
    dem Druck. Seit der Regler ein Anzeiger ist (Birk: „Der Zoomregler soll
    sich dynamisch mitbewegen"), zeigt er, wo die Kamera IST — und die gleitet
    fünf Sekunden lang zur Übersicht, statt zu springen. Gemessen unmittelbar
    nach dem Druck: 0,87.

    Die alte Sofortstellung auf 0 war während dieser Fahrt eine Falschangabe:
    Der Griff stand am linken Anschlag, während die Wand noch nah dran war.
    Genau der Fehler, gegen den `showZoom` ursprünglich gebaut wurde, nur
    andersherum.

    Geprüft wird jetzt das Ende der Fahrt — dort muss der Griff wirklich unten
    stehen, sonst reißt die nächste Hand das Bild um Stufen zurück."""
    _pinch(flaeche, dy=-200)
    flaeche.click("#touch-overview")
    assert flaeche.evaluate("window.kgView.camera.mode") == "fit"
    # Die Etappe ist 5 s, die Nachführung läuft mit 10 Hz.
    flaeche.wait_for_timeout(6500)
    griff = float(flaeche.evaluate("document.getElementById('touch-zoom').value"))
    assert griff < 0.02, f"der Griff steht nach der Fahrt nicht unten: {griff}"
    assert flaeche.evaluate("window.kgFetches") == []


def test_die_wandansicht_bekommt_keine_gestenerkennung(page, static_server):
    """🔴 Alles Neue hängt an `?touch=1`.

    Fläche C im Plenarsaal lädt dieselbe Seite ohne die Fahne. Dort greift die
    Erkennung nicht — es steht ja auch niemand davor, und ein `preventDefault`
    auf `wheel` wäre dort eine Nebenwirkung ohne Anlass.
    """
    page.goto(f"{static_server}/frontend/projection.html")
    page.wait_for_function("window.kgView !== undefined")
    verschluckt = page.evaluate(
        """() => {
             const e = new WheelEvent('wheel', {ctrlKey: true, deltaY: -40,
                                                clientX: 600, clientY: 400,
                                                bubbles: true, cancelable: true});
             document.getElementById('cy').dispatchEvent(e);
             return e.defaultPrevented;
           }"""
    )
    assert verschluckt is False
    assert page.evaluate("window.kgTouch === undefined")
