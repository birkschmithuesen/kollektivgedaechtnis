"""Die Zeichenschalter fuer die bewegte Kamera — und wie weit sie reichen.

Birk hat am 2026-09-01 vor Ort gemessen (Stufe 60, 138 Knoten, 302 Kanten,
zwei Bildschirme, Brave im Vollbild):

                        GPU 3D    CPU brave
    Stillstand (fit)     10,6 %      49,4 %
    Kamerafahrt (pan)    61,4 %     144,4 %     -> 5,8x GPU, 2,9x CPU

Alle Python-Dienste zusammen bleiben dabei konstant bei ~12 %. Der Engpass ist
das Zeichnen im Browser, nicht die Dienste.

`createGraphView` setzt deshalb zwei Schalter, die Cytoscape von sich aus auf
`false` stehen laesst — im vendorierten Bundle nachgesehen, nicht aus dem
Gedaechtnis:

    textureOnViewport    waehrend einer Bewegung ein fertiges Bild schieben
    hideEdgesOnViewport  waehrend einer Bewegung keine Kanten zeichnen

Ein dritter, `pixelRatio: 1`, war am selben Tag kurz drin und ist wieder raus
(dd22a5a): Birk sah am Bild „die ganzen Graphen sehen sehr schlecht aufgeloest
aus, das sieht so aus wie Full HD, die festen Texte sehen gut aus" — genau die
Signatur dieses Schalters auf dem 4K-Schirm.
`test_pixelratio_bleibt_ungesetzt` haelt ihn draussen.

Zurueckgeschaltet wird ohne neuen Build ueber `?schnell=0`; das Urteil faellt
am Bild, nicht an der Zahl.

WIE WEIT DIE SCHALTER REICHEN. Der Renderer weckt sie NUR bei einer Geste des
Besuchers — im Bundle:

    I = pinching || hoverData.dragging || swipePanning || wheelZooming
        || hoverData.draggingEles || cy.animated()
    A = hideEdgesOnViewport && I          (textureOnViewport ohne cy.animated())

Die automatische Kamerafahrt der Wand schreibt `cy.pan()`/`cy.zoom()` direkt
aus ihrer eigenen `step()`-Schleife und benutzt bewusst KEIN `cy.animate()`
(`camera.js`, „a second writer on this viewport"). Fuer den Renderer ist der
Modus `pan` damit gar keine Bewegung. Von den drei Schaltern wirkt dort nur
`pixelRatio`; die anderen beiden treffen die Interaktion am Touchscreen. Das
ist die eine Haelfte der Klage, nicht beide —
`test_die_automatische_kamerafahrt_laesst_die_kanten_stehen` haelt genau das
fest, damit die Annahme nicht unbemerkt kippt.
"""

from __future__ import annotations

import io

import pytest

GRAPH = {
    "version": 1,
    "generated_at": 1.0,
    "max_terms": 32,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": None, "created_at": 1.0,
         "hidden": False, "x": -300, "y": 0},
        {"id": "t1", "type": "term", "label": "Bodenpreise", "mentions": 3,
         "created_at": 2.0, "hidden": False, "x": 300, "y": 0},
    ],
    "edges": [{"id": "e1", "source": "p1", "target": "t1"}],
    "quotes": [],
}


def wand(page, static_server, query=""):
    page.goto(f"{static_server}/frontend/projection.html?theme=f{query}")
    page.wait_for_function("window.kgView !== undefined", timeout=15000)
    return page


def schalter(page):
    """Was der Renderer wirklich uebernommen hat — nicht, was uebergeben wurde.

    Cytoscape legt die drei Werte beim Bau des Renderers ab; `pixelRatio`
    landet dort als `forcedPixelRatio` und ist `null`, wenn nichts erzwungen
    wird. Am Renderer abgelesen und nicht an den Optionen, damit ein Tippfehler
    im Optionsnamen — der folgenlos durchginge — hier auffliegt."""
    return page.evaluate(
        """() => {
             const r = window.kgView.cy.renderer();
             return { textur: r.textureOnViewport, kantenAus: r.hideEdgesOnViewport,
                      pixel: r.forcedPixelRatio };
           }"""
    )


def test_die_wand_zeichnet_ohne_sparschalter(page, static_server):
    """🔴 UMGEDREHT AM 2026-09-02. Vorher galt der schnelle Weg ohne Parameter.

    Birk am Geraet: „Wenn ich beim Touchscreen mit der Maus das Bild bewege,
    dann bauen sich die neuen Ausschnitte erst auf, nachdem ich die Maus
    losgelassen hab. Ausserdem sind beim Beruehren alle Kanten verschwunden."

    Genau das tun die zwei Schalter. Und die Messung im Modulkopf sagt, dass
    sie AUSSCHLIESSLICH bei Benutzergesten greifen — ihr Preis faellt also
    genau dort an, wo jemand die Wand anfasst, ihr Nutzen an einer Stelle, an
    der die Wand die meiste Zeit gar nicht ist.
    """
    wand(page, static_server)

    assert schalter(page) == {"textur": False, "kantenAus": False, "pixel": None}


def test_schnell_1_holt_die_sparschalter_zurueck(page, static_server):
    """Der Weg fuer ein schwaecheres Geraet, ohne neuen Build."""
    wand(page, static_server, "&schnell=1")

    assert schalter(page) == {"textur": True, "kantenAus": True, "pixel": None}


def test_jeder_andere_wert_bleibt_beim_ruhigen_weg(page, static_server):
    """Nur die ausdrueckliche 1 schaltet die Sparschalter ein. Ein Tippfehler
    in der Adresse darf die Wand nicht versehentlich waehrend jeder Geste
    ihre Kanten verlieren lassen — das sah am 2026-09-02 wie ein Defekt aus."""
    wand(page, static_server, "&schnell=ja")

    assert schalter(page) == {"textur": False, "kantenAus": False, "pixel": None}


def test_pixelratio_bleibt_ungesetzt(page, static_server):
    """Die teuerste Wache dieser Datei, und die einzige, die um ein AUSSEHEN
    kaempft statt um Leistung.

    `pixelRatio: 1` war am 2026-09-01 fuer wenige Minuten drin — als
    vermeintlich groesster Hebel eingebaut, dann nach einem Blick in die
    Windows-Registry als „wirkungslos, Skalierung steht auf 100 %"
    abgeschrieben. Beide Urteile waren falsch, und zwar auf dieselbe Weise:
    `devicePixelRatio` ist nicht die Desktop-Skalierung.

    Was zaehlte, sah Birk am Bild: „die ganzen Graphen sehen sehr schlecht
    aufgeloest aus, das sieht so aus wie Full HD, die festen Texte sehen gut
    aus." Genau die Signatur — der HTML-Text daneben bleibt scharf, nur
    Cytoscapes Zeichenflaeche faellt auf ein Viertel der Pixel. Auf dem
    4K-Schirm, der die Anzeigeflaeche IST.

    `forcedPixelRatio is None` heisst: der Bildschirm entscheidet. Jede Zahl
    hier waere eine zweite Entscheidung, und die faellt nicht im Code."""
    wand(page, static_server)

    assert schalter(page)["pixel"] is None, (
        "pixelRatio ist wieder gesetzt — auf dem 4K-Schirm sieht das Netz dann "
        "aus wie Full HD, waehrend die Schrift daneben scharf bleibt"
    )


# --- Die Kanten, gemessen am Bild -----------------------------------------
#
# In theme-f („Schwarzplan") tragen die Kanten Bedeutung, und
# `hideEdgesOnViewport` nimmt sie weg. Also wird hier nicht der Stilwert
# geprueft, sondern was auf dem Schirm steht.
#
# Die Messstelle: ein 12 px breiter, 120 px hoher Streifen bei einem Viertel
# der Strecke zwischen Scheibe und Tafel. Weit weg von beiden Knoten und von
# jeder Schrift — GEMESSEN liegen dort 66 helle von 1440 Pixeln, wenn die
# Kante da ist, und 0, wenn nicht. Der Streifen muss hoch sein, weil theme-f
# die Kante schwingen laesst: auf der geraden Verbindungslinie selbst
# (± 25 px) liegt kein einziges Pixel von ihr.
STREIFEN_HALBE_HOEHE = 60


def _kantenpixel(page):
    from PIL import Image

    stelle = page.evaluate(
        """() => {
             const cy = window.kgView.cy;
             const a = cy.$id('p1').renderedPosition();
             const b = cy.$id('t1').renderedPosition();
             return { x: Math.round(a.x + (b.x - a.x) * 0.25),
                      y: Math.round(a.y + (b.y - a.y) * 0.25) };
           }"""
    )
    bild = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
    aus = bild.crop(
        (stelle["x"] - 6, stelle["y"] - STREIFEN_HALBE_HOEHE,
         stelle["x"] + 6, stelle["y"] + STREIFEN_HALBE_HOEHE)
    )
    # tobytes() statt getdata(): dasselbe Ergebnis, aber ohne die
    # Pillow-14-Verfallswarnung, die den Testlauf sonst zumuellt.
    roh = aus.tobytes()
    return sum(1 for i in range(0, len(roh), 3) if roh[i] + roh[i + 1] + roh[i + 2] > 60)


@pytest.fixture()
def wand_mit_kante(page, static_server):
    """Die Wand im Modus `manual` — nur dort darf eine Hand die Ansicht
    schieben (`camera.js:_applyInteractivity`), und nur dann setzt der
    Renderer ueberhaupt `swipePanning`.

    🔴 MIT `&schnell=1`, seit die Sparschalter am 2026-09-02 vorgabemaessig
    AUS sind. Die Tests an dieser Vorrichtung messen, WIE die Schalter sich
    verhalten — dass eine Geste sie weckt, die Kamerafahrt nicht, und dass die
    Kanten danach von selbst zurueckkommen. Diese Messung ist die Begruendung
    fuer die neue Vorgabe und muss deshalb weiter laufen; sie braucht die
    Schalter nur ausdruecklich statt stillschweigend.
    """
    wand(page, static_server, "&schnell=1")
    page.evaluate("(g) => window.kgView.update(g)", GRAPH)
    page.evaluate("() => window.kgView.camera.setMode('manual')")
    page.wait_for_timeout(600)
    return page


def test_die_kanten_sind_nach_der_geste_wieder_da(wand_mit_kante):
    """Die Nebenwirkung, auf die es ankommt. `hideEdgesOnViewport` nimmt die
    Kanten waehrend der Geste weg — danach muessen sie von selbst
    zurueckkommen und nicht erst bei der naechsten Beruehrung. Cytoscape
    faehrt am Ende der Geste `redrawHint('eles', true); redraw()`; hier steht,
    dass das mit unseren Schaltern auch wirklich ankommt.

    Gezogen wird mit echten Maus-Ereignissen: ein `cy.pan()` aus dem Test
    heraus wuerde `swipePanning` gar nicht setzen und die Schalter nie wecken.

    Waehrend der Geste wird bewusst NICHT gemessen: die Knotenpositionen im
    Modell laufen dem gezeichneten Bild dann um eine Bildfolge voraus, ein
    Streifen an der gerechneten Stelle trifft also auch dann nichts, wenn
    gezeichnet wurde. Das haette rot ausgesehen, ohne etwas zu zeigen."""
    assert _kantenpixel(wand_mit_kante) > 0, "Messstelle trifft die Kante nicht — Test kaputt"

    wand_mit_kante.mouse.move(1500, 900)
    wand_mit_kante.mouse.down()
    for i in range(6):
        wand_mit_kante.mouse.move(1500 - (i + 1) * 12, 900 - (i + 1) * 6)
        wand_mit_kante.wait_for_timeout(30)
    wand_mit_kante.mouse.up()
    wand_mit_kante.wait_for_timeout(300)

    assert wand_mit_kante.evaluate("() => window.kgView.cy.pan().x") != 0, "es wurde gar nicht gezogen"
    assert _kantenpixel(wand_mit_kante) > 0, "die Kante ist nach der Geste nicht zurueckgekommen"


def _bewegungsflaggen(page):
    """Woran der Renderer „es bewegt sich" festmacht — und ob er die Textur
    tatsaechlich benutzt. `textureCache` ist genau dann gesetzt, wenn der
    Texturweg gerade laeuft; sonst raeumt der Renderer ihn selbst ab."""
    return page.evaluate(
        """() => {
             const r = window.kgView.cy.renderer();
             return { textur: r.textureCache != null,
                      bewegt: !!(r.pinching || r.swipePanning || r.data.wheelZooming
                                 || r.hoverData.dragging || r.hoverData.draggingEles
                                 || window.kgView.cy.animated()) };
           }"""
    )


def test_die_schalter_wecken_die_geste_und_nicht_die_fahrt(wand_mit_kante):
    """Die Reichweite der beiden Ansichtsschalter, gemessen statt angenommen.

    Cytoscape schaltet `textureOnViewport` und `hideEdgesOnViewport` nicht ein,
    weil sich `pan` oder `zoom` aendern, sondern weil eine GESTE laeuft
    (`pinching || hoverData.dragging || swipePanning || wheelZooming`, bei den
    Kanten zusaetzlich `cy.animated()`). Die automatische Fahrt der Wand
    schreibt `cy.pan()`/`cy.zoom()` frame-fuer-frame aus `camera.step()` und
    benutzt bewusst kein `cy.animate()` — fuer den Renderer ist das keine
    Bewegung.

    Ergebnis, hier festgehalten: die beiden Schalter helfen der Interaktion am
    Touchscreen und NICHT dem Dauerbetrieb im Modus `pan`. Wer die 61,4 % GPU
    der Fahrt senken will, braucht dafuer etwas anderes."""
    ruhe = _bewegungsflaggen(wand_mit_kante)
    assert ruhe == {"textur": False, "bewegt": False}

    wand_mit_kante.mouse.move(1500, 900)
    wand_mit_kante.mouse.down()
    for i in range(6):
        wand_mit_kante.mouse.move(1500 - (i + 1) * 12, 900 - (i + 1) * 6)
        wand_mit_kante.wait_for_timeout(40)
    waehrend_der_geste = _bewegungsflaggen(wand_mit_kante)
    wand_mit_kante.mouse.up()
    wand_mit_kante.wait_for_timeout(300)

    assert waehrend_der_geste == {"textur": True, "bewegt": True}, (
        "die Geste weckt die Schalter nicht mehr — dann sparen sie gar nichts"
    )

    # Eine Mindestschrift, die dieses kleine Testnetz nicht von selbst liefert
    # (2026-09-02): Sonst steht die Wand still, weil ohnehin alles lesbar im
    # Bild ist -- richtig im Betrieb, aber dann misst dieser Test nichts ueber
    # die Fahrt. 120 px ist der obere Anschlag des Reglers.
    wand_mit_kante.evaluate("() => window.kgView.camera.setMinLabel(120)")
    wand_mit_kante.evaluate("() => window.kgView.camera.setMode('pan')")
    wand_mit_kante.evaluate(
        "() => { for (let i = 0; i < 100; i++) window.kgView.camera.step(0.05); }"
    )
    waehrend_der_fahrt = []
    for _ in range(4):
        wand_mit_kante.evaluate(
            "() => { for (let i = 0; i < 8; i++) window.kgView.camera.step(0.05); }"
        )
        wand_mit_kante.wait_for_timeout(120)
        waehrend_der_fahrt.append(_bewegungsflaggen(wand_mit_kante))

    assert waehrend_der_fahrt == [{"textur": False, "bewegt": False}] * 4, (
        "die Fahrt gilt dem Renderer ploetzlich als Bewegung — dann greifen die "
        "Schalter dort, die Kanten flackern im Betrieb, und Birks Messung "
        "(61,4 % GPU bei `pan`) muss neu gemacht werden"
    )


def test_die_automatische_kamerafahrt_laesst_die_kanten_stehen(wand_mit_kante):
    """Die Gegenprobe fuer den Dauerbetrieb — und die Aussage, die am meisten
    wert ist: Im Modus `pan` verschwinden die Kanten ueberhaupt nicht, weil
    der Renderer diese Fahrt nicht als Bewegung sieht. Wer diese Zeile rot
    sieht, hat die Kamera auf `cy.animate()` umgestellt; dann greifen die
    Schalter dort ploetzlich, die Kanten flackern im Betrieb, und Birks
    Messung von oben muss neu gemacht werden.

    Gefahren wird ueber `camera.step()` statt ueber Warten: die Kamera ruht
    nach dem Moduswechsel erst 4,2 s (`ROAM.dwellMs`), und ein Test, der lange
    genug schlaeft, um daran vorbeizukommen, misst am Ende die Uhr."""
    # Eine Mindestschrift, die dieses kleine Testnetz nicht von selbst liefert
    # (2026-09-02): Sonst steht die Wand still, weil ohnehin alles lesbar im
    # Bild ist -- richtig im Betrieb, aber dann misst dieser Test nichts ueber
    # die Fahrt. 120 px ist der obere Anschlag des Reglers.
    wand_mit_kante.evaluate("() => window.kgView.camera.setMinLabel(120)")
    wand_mit_kante.evaluate("() => window.kgView.camera.setMode('pan')")
    # Ueber die Ruhephase hinweg, ohne zu zeichnen — hier ist nichts zu sehen.
    wand_mit_kante.evaluate(
        "() => { for (let i = 0; i < 100; i++) window.kgView.camera.step(0.05); }"
    )

    bewegt = False
    for _ in range(5):
        vorher = wand_mit_kante.evaluate("() => ({ ...window.kgView.cy.pan(), z: window.kgView.cy.zoom() })")
        wand_mit_kante.evaluate(
            "() => { for (let i = 0; i < 8; i++) window.kgView.camera.step(0.05); }"
        )
        wand_mit_kante.wait_for_timeout(120)
        nachher = wand_mit_kante.evaluate("() => ({ ...window.kgView.cy.pan(), z: window.kgView.cy.zoom() })")
        bewegt = bewegt or nachher != vorher

        assert _kantenpixel(wand_mit_kante) > 0, f"Kante weg bei {nachher}"

    assert bewegt, "die Kamera stand still — dann sagt der Test nichts ueber die Fahrt"
