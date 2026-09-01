"""Die Diagnoseseite, die Multitouch am Geraet in Sekunden beantwortet.

Der Anlass (Birk, 2026-09-01, am MacBook mit angeschlossenem Touchscreen):
„Zweifingergeste — ist das wegen Mac, geht das einfach nicht?" Die Frage war
nicht beantwortbar, weil nirgends stand, wieviele Kontakte der Schirm meldet.

🔴 Was diese Tests NICHT koennen: die Hardware pruefen. Ob der iiyama PL6568
zwei Finger meldet, entscheidet der Digitizer, und der haengt nicht an dieser
CI. Geprueft wird deshalb genau das, was pruefbar ist — dass die Seite die
Kontakte, die bei ihr ankommen, richtig zaehlt und richtig deutet. Die Messung
selbst macht ein Mensch mit zwei Fingern auf dem Glas.

Die Kontakte werden hier als synthetische PointerEvents zugestellt. Das ist
genau die Schnittstelle, an der auch der echte Digitizer haengt (Chromium
uebersetzt Touch nach Pointer, bevor die Seite etwas sieht) — der Unterschied
zum Ernstfall liegt allein davor, im Treiber.
"""

import pytest


@pytest.fixture()
def diagnose(page, static_server):
    page.goto(f"{static_server}/frontend/touchtest.html")
    page.wait_for_selector("#gleichzeitig")
    return page


def _auflegen(page, *ids, art="touch"):
    page.evaluate(
        """({ids, art}) => ids.forEach((id) => window.dispatchEvent(
             new PointerEvent('pointerdown', {pointerId: id, pointerType: art, bubbles: true})))""",
        {"ids": list(ids), "art": art},
    )


def _abheben(page, *ids):
    page.evaluate(
        """(ids) => ids.forEach((id) => window.dispatchEvent(
             new PointerEvent('pointerup', {pointerId: id, bubbles: true})))""",
        list(ids),
    )


def test_ohne_beruehrung_steht_die_seite_auf_null(diagnose):
    assert diagnose.text_content("#gleichzeitig") == "0"
    assert diagnose.text_content("#maximumwert") == "0"


def test_zwei_gleichzeitige_kontakte_werden_als_zwei_gezaehlt(diagnose):
    _auflegen(diagnose, 1, 2)
    assert diagnose.text_content("#gleichzeitig") == "2"


def test_ein_abgehobener_finger_verschwindet_wieder(diagnose):
    """Die Zahl muss der Wirklichkeit folgen, sonst ist sie wertlos."""
    _auflegen(diagnose, 1, 2)
    _abheben(diagnose, 2)
    assert diagnose.text_content("#gleichzeitig") == "1"


def test_das_maximum_bleibt_stehen(diagnose):
    """Der eigentliche Messwert.

    Zwei Finger landen nie im selben Moment auf dem Glas und werden nie im
    selben Moment abgehoben. Wer beim Ablesen schon einen abgehoben hat, saehe
    ohne das gemerkte Maximum wieder eine 1 — und zoege den falschen Schluss.
    """
    _auflegen(diagnose, 1, 2)
    _abheben(diagnose, 1, 2)
    assert diagnose.text_content("#gleichzeitig") == "0"
    assert diagnose.text_content("#maximumwert") == "2"


def test_zwei_kontakte_ergeben_das_urteil_multitouch_moeglich(diagnose):
    _auflegen(diagnose, 1, 2)
    assert diagnose.get_attribute("#urteil", "class") == "ja"
    assert "möglich" in diagnose.text_content("#urteil")


def test_ein_einziger_kontakt_ergeben_das_urteil_regler_noetig(diagnose):
    """Der Fall, um den es geht: ein Geraet ohne zweiten Kontakt.

    Cytoscape rechnet den Pinch-Zoom hinter `t.touches[1]` (vendor/
    cytoscape.min.js). Ein Schirm, der nur einen Kontakt liefert, kann dort
    per Konstruktion nie ankommen — dann ist der Regler die richtige Loesung
    und nicht die Notloesung.
    """
    _auflegen(diagnose, 7)
    assert diagnose.get_attribute("#urteil", "class") == "nein"
    assert "unmöglich" in diagnose.text_content("#urteil")


def test_die_art_des_kontakts_wird_angezeigt(diagnose):
    """Ein Digitizer, der sich als `mouse` meldet, erreicht Cytoscapes
    Touch-Zweig ueberhaupt nicht — auch mit zwei Kontakten nicht."""
    _auflegen(diagnose, 3, art="pen")
    assert "pen" in diagnose.text_content("#arten")


def test_zuruecksetzen_loescht_auch_das_gemerkte_maximum(diagnose):
    _auflegen(diagnose, 1, 2)
    _abheben(diagnose, 1, 2)
    diagnose.click("#zuruecksetzen")
    assert diagnose.text_content("#maximumwert") == "0"
    assert diagnose.get_attribute("#urteil", "class") == "nein"


def test_die_seite_nennt_was_das_geraet_von_sich_behauptet(diagnose):
    """Neben dem gemessenen Wert, weil beide luegen koennen — und weil
    `TouchEvent` entscheidet, welchen Eingabepfad Cytoscape bindet."""
    text = diagnose.text_content("#geraet")
    assert "maxTouchPoints" in text
    assert "TouchEvent" in text


def test_die_flaeche_gibt_keine_beruehrung_an_den_browser_ab(diagnose):
    """🔴 Ohne `touch-action: none` misst die Seite den Browser statt den Schirm.

    Chrome verschluckt Mehrfinger-Gesten sonst fuer Scrollen und Seitenzoom und
    stellt sie nie als Pointer-Events zu: ein Geraet, das zwei Kontakte kann,
    saehe hier trotzdem nur einen. Der Messfehler ginge also in genau die
    Richtung, in der wir uns nicht irren duerfen.
    """
    assert (
        diagnose.evaluate("getComputedStyle(document.body).touchAction") == "none"
    ), "die Seite laesst den Browser Gesten abfangen und misst dann sich selbst"


# --- Welcher der drei Zoom-Wege kommt an? ------------------------------------
#
# Die Frage des Nachtrags vom 2026-09-01, 20:15, und der eigentliche Grund,
# warum die Geste auf dem MacBook nicht wirkt, obwohl sie unter Windows wirkte.
# Ein Browser meldet eine Pinch-Geste auf DREI verschiedene Arten (Dan Cătălin
# Burzo, „Pinch me, I'm zooming: gestures in the DOM", danburzo.ro/dom-gestures/):
#
#   Chrome/Brave/Firefox auf macOS  ->  wheel-Event mit ctrlKey: true
#   Safari                          ->  gesturestart/-change mit fertigem scale
#   Mobile Browser                  ->  TouchEvent mit den Kontaktpunkten
#
# Die Zahl der Pointer allein (oben) beantwortet also nur die halbe Frage: Ein
# Geraet kann zwei Kontakte melden und die Geste trotzdem auf einem Kanal
# ausliefern, auf dem Cytoscape sie nie sucht. Diese Haelfte der Seite zeigt,
# welcher Kanal tatsaechlich feuert.


def _rad(page, *, strg, dy=-40.0, dx=0.0):
    """Ein `wheel`-Event, wie es eine Trackpad-/Touchpad-Pinch ausloest."""
    page.evaluate(
        """({strg, dy, dx}) => window.dispatchEvent(new WheelEvent('wheel', {
             ctrlKey: strg, deltaY: dy, deltaX: dx, bubbles: true, cancelable: true }))""",
        {"strg": strg, "dy": dy, "dx": dx},
    )


def _geste(page, skala):
    """Safaris `gesturechange`. In Chromium gibt es die Klasse `GestureEvent`
    nicht, also wird ein gleichnamiges Event mit `scale` zugestellt — die Seite
    liest genau diese Eigenschaft, mehr braucht es fuer die Ablesung nicht."""
    page.evaluate(
        """(skala) => {
             const e = new Event('gesturechange', {bubbles: true, cancelable: true});
             e.scale = skala;
             window.dispatchEvent(e);
           }""",
        skala,
    )


def _tippen(page, anzahl):
    """Ein `touchstart` mit `anzahl` gleichzeitigen Beruehrungen."""
    page.evaluate(
        """(anzahl) => {
             const ziel = document.body;
             const punkte = [];
             for (let i = 0; i < anzahl; i += 1) {
               punkte.push(new Touch({identifier: i, target: ziel, clientX: 100 * i, clientY: 100}));
             }
             ziel.dispatchEvent(new TouchEvent('touchstart', {
               touches: punkte, targetTouches: punkte, changedTouches: punkte,
               bubbles: true, cancelable: true }));
           }""",
        anzahl,
    )


def test_ohne_geste_nennt_die_seite_noch_keinen_weg(diagnose):
    assert "Noch kein" in diagnose.text_content("#wegurteil")


def test_ein_rad_mit_strgtaste_wird_als_pinch_erkannt(diagnose):
    """🔴 Der Weg, auf dem Chromium eine Pinch-Geste auf macOS ausliefert.

    Genau hier wird sich entscheiden, warum die Geste unter Windows wirkte und
    auf dem MacBook nicht: Cytoscapes Pinch-Pfad erwartet zwei TouchEvent-
    Kontakte, und wenn macOS die Geste stattdessen als `wheel` + `ctrlKey`
    durchreicht, sieht Cytoscape nie zwei Finger.
    """
    _rad(diagnose, strg=True, dy=-40)
    assert diagnose.get_attribute("#wegwheel", "class").split()[-1] == "an"
    assert "wheel + ctrlKey" in diagnose.text_content("#wegurteil")


def test_ein_rad_ohne_strgtaste_ist_kein_pinch(diagnose):
    """Ein gewoehnliches Scrollrad darf den Befund nicht faelschen — sonst
    meldete die Seite „Pinch kommt an", sobald jemand eine Maus dreht."""
    _rad(diagnose, strg=False, dy=-40)
    assert diagnose.get_attribute("#wegwheel", "class").split()[-1] != "an"
    assert "Noch kein" in diagnose.text_content("#wegurteil")


def test_die_seite_zeigt_die_ausschlaege_des_rads(diagnose):
    """`deltaY` ist der Skalierungsschritt. Die Zahl mit anzuzeigen ist der
    Unterschied zwischen „es kommt etwas an" und „es kommt DAS an": Ein
    Ausschlag von 0 waere ein Ereignis ohne Wirkung."""
    _rad(diagnose, strg=True, dy=-12.5, dx=3.0)
    text = diagnose.text_content("#wegwheel")
    assert "-12.5" in text and "3" in text


def test_ein_gestureevent_wird_als_safariweg_erkannt(diagnose):
    """Fuer den Fall, dass Birk doch Safari oeffnet: Dort gibt es weder das
    `wheel`+ctrlKey noch TouchEvents, sondern `scale` fix und fertig."""
    _geste(diagnose, 1.5)
    assert diagnose.get_attribute("#weggeste", "class").split()[-1] == "an"
    assert "gesture" in diagnose.text_content("#wegurteil")
    assert "1.5" in diagnose.text_content("#weggeste")


def test_zwei_touchkontakte_werden_als_cytoscapeweg_erkannt(diagnose):
    """Der einzige der drei Wege, den Cytoscape von sich aus kennt."""
    _tippen(diagnose, 2)
    assert diagnose.get_attribute("#wegtouch", "class").split()[-1] == "an"
    assert "TouchEvent" in diagnose.text_content("#wegurteil")


def test_ein_einzelner_touchkontakt_ist_noch_kein_zoomweg(diagnose):
    """Ein Finger ist eine Berührung, keine Geste — `touches.length` von 1
    erreicht Cytoscapes Pinch-Rechnung (hinter `t.touches[1]`) nie."""
    _tippen(diagnose, 1)
    assert diagnose.get_attribute("#wegtouch", "class").split()[-1] != "an"


def test_die_seite_schluckt_die_pinch_statt_die_seite_zu_zoomen(diagnose):
    """🔴 Ohne `preventDefault` zoomt Brave die ganze SEITE statt zu messen —
    und dann ist die Schrift verzerrt, waehrend die Zahl abgelesen werden
    soll. Dieselbe Vorkehrung, die der Zoom auf der Wand braucht."""
    diagnose.evaluate(
        """() => {
             const e = new WheelEvent('wheel', {ctrlKey: true, deltaY: -40,
                                                bubbles: true, cancelable: true});
             window.dispatchEvent(e);
             window.geschluckt = e.defaultPrevented;
           }"""
    )
    assert diagnose.evaluate("window.geschluckt") is True


def test_zuruecksetzen_loescht_auch_die_gemeldeten_wege(diagnose):
    _rad(diagnose, strg=True)
    diagnose.click("#zuruecksetzen")
    assert diagnose.get_attribute("#wegwheel", "class").split()[-1] != "an"
    assert "Noch kein" in diagnose.text_content("#wegurteil")
