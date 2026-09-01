"""🔴 Die Foyer-Ansicht darf sich durch die Plenar-Arbeit NICHT verändert haben.

Am 2026-09-01 ist die Touchfläche im Foyer vor Ort kalibriert worden: Zoom
1,55, Porträtgröße, Zitatkarte auf 40 %, QR-Deckkraft gemessen. Diese Werte
sind teuer erarbeitet und stehen morgen in der Ausstellung. Die Saal-Ansicht
ist daneben gebaut worden und teilt sich mit ihr **eine Seite, ein Regelwerk
und eine Datenbank** — es gibt also drei Wege, auf denen sie das Foyer
verändert haben könnte, und alle drei sind still:

 1. **Die Auflage** (`static/plenum.css`) könnte auch ohne `?plenum=1`
    geladen werden. Dann stünde im Foyer das Saal-Design.
 2. **Die neuen Variablen** in `base.css` (`--qr-size`, `--qr-opacity`,
    `--quote-ring`) könnten eine andere Vorgabe tragen als die festen Werte,
    die vorher an ihrer Stelle standen.
 3. **Die Positionen.** Beide Flächen lesen aus derselben `position`-Tabelle.
    Schriebe die Saalfläche ihr eigenes Layout zurück (sie rechnet mit
    größerer Schrift und größerem Tafelpolster, fcose kommt also auf ein
    anderes Ergebnis), stünde das Foyer nach dem nächsten Neuladen anders da.

Diese Datei misst alle drei am echten Bild im Browser, statt sie zu
behaupten. Die Zahlen darin sind aus dem Bestand ÜBERNOMMEN, nicht neu
gewählt: Sie sind die Werte, die vor dieser Änderung galten.

Mutationsprobe (2026-09-01 durchgeführt, siehe Bericht): `plenum.css`
unbedingt laden lassen → `test_die_saal_auflage_ist_im_foyer_nicht_geladen`
und die Maßtests werden rot; `--qr-size` auf einen anderen Vorgabewert setzen
→ `test_der_qr_code_hat_unveraenderte_masse` wird rot.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def foyer(page, static_server):
    """Die Foyerfläche, genau wie sie im Haus aufgerufen wird."""
    page.goto(f"{static_server}/frontend/projection.html?theme=f")
    page.wait_for_function("() => window.kgLegende !== undefined", timeout=30000)
    return page


@pytest.fixture()
def foyer_touch(page, static_server):
    """Dieselbe Fläche mit dem Touch-Schalter — so läuft sie in der Ausstellung."""
    page.goto(f"{static_server}/frontend/projection.html?theme=f&touch=1")
    page.wait_for_function("() => window.kgLegende !== undefined", timeout=30000)
    return page


def _variablen(page, namen):
    return page.evaluate(
        """(namen) => {
             const s = getComputedStyle(document.documentElement);
             return Object.fromEntries(namen.map((n) => [n, s.getPropertyValue(n).trim()]));
           }""",
        namen,
    )


# --- 1. Die Auflage ist nicht da ---------------------------------------------


def test_die_saal_auflage_ist_im_foyer_nicht_geladen(foyer):
    """Kein `<link>`, kein Stylesheet, keine Anfrage.

    Nicht „ist wirkungslos", sondern „ist nicht vorhanden": Ein deaktiviertes
    oder überschriebenes Stylesheet wäre eine Zusicherung über die Kaskade,
    die beim nächsten Umsortieren kippt. Ein Element, das gar nicht entsteht,
    kann nichts überschreiben.
    """
    befund = foyer.evaluate(
        """() => ({
             link: document.getElementById('plenum') !== null,
             blaetter: [...document.styleSheets].map((s) => s.href || '').filter(Boolean),
           })"""
    )
    assert befund["link"] is False, "die Saal-Auflage hängt im Foyer im Dokument"
    saal = [h for h in befund["blaetter"] if "plenum" in h]
    assert saal == [], f"das Foyer lädt die Saal-Auflage: {saal}"
    # Und die beiden, die es laden MUSS, sind noch da.
    assert any(h.endswith("base.css") for h in befund["blaetter"])
    assert any(h.endswith("theme-f.css") for h in befund["blaetter"])


def test_im_foyer_gibt_es_keinen_erklaerungstext(foyer):
    """Die periodische Einblendung gehört dem Saal. Im Foyer stünde sie vor
    einer Fläche, an der jemand steht und liest — und verdeckte den Graphen,
    den er gerade erkundet."""
    assert foyer.evaluate("() => document.querySelector('.plenum-hinweis') === null")
    assert foyer.evaluate("() => window.kgPlenumHinweis === null")
    # Und erst recht kein Vollbild-Code: der legte sich schwarz über den
    # gesamten Graphen, mitten in der Erkundung durch einen Besucher.
    assert foyer.evaluate("() => document.querySelector('.plenum-qr-voll') === null")


def test_die_legende_steht_im_foyer_weiter(foyer):
    """Sie ist im Saal abgeschaltet — hier muss sie geblieben sein, mit ihren
    drei Einträgen (Birk, 2026-09-01)."""
    eintraege = foyer.evaluate(
        "() => [...document.querySelectorAll('.dream-legende-eintrag')].map((e) => e.textContent.trim())"
    )
    assert eintraege == ["oft genannt", "Nachbarn", "vor Kurzem gesagt"]


# --- 2. Die Maße sind unverändert --------------------------------------------


def test_der_qr_code_hat_unveraenderte_masse(foyer):
    """132 px und 70 % Deckkraft — beide Zahlen sind gemessen (base.css) und
    stehen seit dieser Änderung in Variablen. Die Vorgabe der Variable muss
    exakt der frühere feste Wert sein."""
    masse = foyer.evaluate(
        """() => {
             const s = getComputedStyle(document.querySelector('.qr-bild'));
             const aussen = getComputedStyle(document.querySelector('.qr-hinweis'));
             return {
               breite: s.width,
               hoehe: s.height,
               deckkraft: s.opacity,
               anzeige: aussen.display,
             };
           }"""
    )
    assert masse["breite"] == "132px", masse
    assert masse["hoehe"] == "132px", masse
    assert float(masse["deckkraft"]) == pytest.approx(0.7), masse
    # 🔴 Seit 2026-09-01 ist `display` eine Variable, weil der Saal den
    # Eck-Code abschaltet. Der Vorgabewert muss im Foyer weiter `block` sein —
    # genau hier könnte die Saal-Änderung dem Foyer den Code wegnehmen, und
    # niemand fiele es auf, bis jemand vor der Wand steht und nichts findet.
    assert masse["anzeige"] == "block", masse


def test_die_zitatkarte_behaelt_ihre_helle_kante(foyer):
    """Die haarfeine Kante ist einer der Kandidaten für Birks „der weiße Rand
    soll weg" und ist im Saal entfernt. Im Foyer ist sie Teil des Schattens,
    der die Karte von der Wand abhebt — sie muss stehen bleiben, bis Birk
    entschieden hat, dass er genau diese meinte."""
    schatten = foyer.evaluate(
        "() => getComputedStyle(document.querySelector('.quote-overlay')).boxShadow"
    )
    assert "rgba(255, 255, 255, 0.12) 0px 0px 0px 1px" in schatten, schatten


def test_die_gemessenen_theme_werte_stehen_unveraendert(foyer):
    """Die Werte, an denen das Bild im Foyer hängt — jeder einzelne mit einer
    Begründung in `theme-f.css` bzw. `base.css` hinterlegt."""
    werte = _variablen(
        foyer,
        [
            "--person-size",
            "--label-size",
            "--label-max-width",
            "--label-outline-width",
            "--plate-pad",
            "--plate-radius",
            "--term-ring-width",
            "--edge-width",
            "--edge-opacity",
            "--quote-scale",
        ],
    )
    assert werte == {
        "--person-size": "56",
        "--label-size": "26",
        "--label-max-width": "220px",
        "--label-outline-width": "4",
        "--plate-pad": "8",
        "--plate-radius": "18",
        "--term-ring-width": "1.5",
        "--edge-width": "2",
        "--edge-opacity": "0.55",
        "--quote-scale": "0.4",
    }


def test_die_drei_achsenfarben_tragen_im_foyer_weiter_bedeutung(foyer):
    """Im Saal stehen sie alle drei auf demselben neutralen Licht (Birk:
    „Begriffe nicht farbig markieren"). Im Foyer tragen sie den Code, ohne den
    die Markierung an der Wand nur ein Ja/Nein wäre — sie müssen dort
    verschieden und die drei Bauhaus-Farben sein."""
    farben = _variablen(
        foyer, ["--dream-anchor-color", "--dream-neighbour-color", "--dream-recent-color"]
    )
    assert farben == {
        "--dream-anchor-color": "#D62828",
        "--dream-neighbour-color": "#1D4E9C",
        "--dream-recent-color": "#F4C300",
    }


def test_die_bedienleiste_der_touchflaeche_ist_unveraendert(foyer_touch):
    """Die Foyerfläche läuft mit `?touch=1`. Der Knopf trägt einen weißen
    Rahmen (`rgba(255,255,255,0.22)`) — die Zeile, die der Auftrag als
    „weißer Rand" verdächtigt hat. Er steht noch, weil das Foyer sich nicht
    ändern darf; das ist im Bericht vermerkt."""
    befund = foyer_touch.evaluate(
        """() => {
             const k = document.querySelector('.touch-button');
             if (!k) return null;
             const s = getComputedStyle(k);
             return { rand: s.borderTopColor, breite: s.borderTopWidth, text: k.textContent.trim() };
           }"""
    )
    assert befund is not None, "die Bedienleiste der Touchfläche fehlt"
    assert befund["rand"] == "rgba(255, 255, 255, 0.22)", befund
    assert befund["breite"] == "1px", befund


# --- 3. Das Foyer schreibt seine Positionen weiter ----------------------------


GRAPH = {
    "version": 1,
    "generated_at": 1.0,
    "max_terms": 32,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": None, "created_at": 1.0, "hidden": False},
        {"id": "t1", "type": "term", "label": "Holzbau", "mentions": 3, "created_at": 2.0,
         "hidden": False, "in_dream": False, "dream_role": ""},
        {"id": "t2", "type": "term", "label": "Normen-Inventur", "mentions": 2, "created_at": 3.0,
         "hidden": False, "in_dream": False, "dream_role": ""},
    ],
    "edges": [{"id": "e1", "source": "p1", "target": "t1"}],
    "quotes": [],
}


def test_das_foyer_schreibt_seine_positionen_weiter_zurueck(
    page, static_server, fetch_mitschnitt
):
    """🔴 Der Weg, auf dem die Saalfläche das Foyer trotz getrennter Regler
    hätte verändern können — hier von der anderen Seite geprüft: Das Foyer
    muss weiter speichern, sonst hätte ich beim Abschalten für den Saal aus
    Versehen beide abgeschaltet."""
    page.goto(f"{static_server}/frontend/projection.html?theme=f")
    page.wait_for_function("() => window.kgView !== undefined", timeout=30000)
    page.evaluate("(g) => window.kgView.update(g)", GRAPH)
    # Das Zurückschreiben passiert am Ende des Layouts, nicht beim Einspielen.
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=30000)
    page.wait_for_timeout(1500)

    aufrufe = fetch_mitschnitt()
    positionen = [u for u in aufrufe if "/api/positions" in u]
    assert positionen, f"das Foyer speichert keine Positionen mehr: {aufrufe}"
