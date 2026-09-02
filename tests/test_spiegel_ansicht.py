"""Die Spiegel-Ansicht am Handy — dieselbe Bildsprache wie der Plenarsaal.

Birk, 2026-09-02, mit der öffentlichen Seite in der Hand:

    „Die Ansicht ist irgendwie alt und komisch, und die Porträts werden gar
     nicht angezeigt. Die Ansicht soll im Prinzip dieselbe sein wie der
     Plenarsaal — mit geschwungenen Kanten und anklickbaren Zitaten."

Gemessen am 2026-09-02, bevor hier etwas geändert wurde (Empfänger lokal auf
:8899, echter Stand der Station über `mirror.uploader` eingespielt, Chromium
auf 390×844):

  * Kanten: `curve-style: straight` — schnurgerade Striche quer durchs Bild.
    Der Saal zeichnet seit theme-f Bögen (`unbundled-bezier` mit zwei
    Kontrollpunkten aus `edgeCurve()`, frontend/static/term-plate.js).
  * Ein Portrait maß **20,7 gerenderte Pixel** (Knoten p6, Zoom 0,345,
    56 Modelleinheiten). Das Bild WAR da — der Uploader hatte es übertragen,
    der Empfänger lieferte es mit 200 aus, Cytoscape hatte es als
    `background-image` gesetzt. Es war schlicht zu klein, um ein Gesicht zu
    sein. „Wird nicht angezeigt" heißt hier: nicht erkennbar, nicht: fehlt.
  * Begriffe: ein 7-px-Punkt mit Schrift daneben. Der Saal hat den Punkt
    ersatzlos gestrichen; dort IST der Begriff eine beschriftete Tafel.
  * Das Zitat kam ohne Namen. Der Saal zeigt beides (`quote-overlay.js`,
    `<figcaption class="quote-name">`).

Diese Datei misst am echten Bild im Browser, gegen einen echten Empfänger.
Bewusst nicht gegen die öffentliche Seite: die trägt fremde Portraits, und ein
Test darf nicht davon abhängen, was dort gerade steht.

Was hier NICHT geprüft wird: die Wand- und Saalansicht. Die wird kopiert, nicht
angefasst (`tests/test_foyer_unveraendert.py` bewacht sie).

Mutationsprobe (2026-09-02 durchgeführt):

  `curve-style` zurück auf `straight`
      → nur `test_die_kanten_sind_boegen_wie_im_saal` rot.
  `shape: round-rectangle` zurück auf `ellipse`
      → nur `test_die_begriffe_stehen_auf_tafeln_mit_runden_ecken` rot.
  `nameEl.textContent` auf `""`
      → nur `test_ein_tipp_auf_ein_gesicht_zeigt_zitat_und_name` rot.
  `ZIEL.personModell` und `ZIEL.personMin` zurück auf den Bestand (56 / 10)
      → `test_ein_portrait_ist_am_handy_gross_genug_fuer_ein_gesicht` und
        `test_eine_person_ohne_portrait_bleibt_eine_person` rot.
  `einpassen()` auf einen einzelnen `fit()` zurückgedreht
      → nur `test_einpassen_kommt_zur_ruhe` rot (8,1 % Abweichung zwischen
        zwei gleichen Gesten).

🔴 Ehrlich dazugesagt: JEDE der beiden Zahlen ALLEIN zurückzudrehen lässt die
Tests grün. 110 × 0,345 sind 38 px, und die Untergrenze 30 fängt die 56 ab —
erst beide zusammen ergeben wieder die gemessenen 20,7 px. Die Tests bewachen
also das Ergebnis (ein Gesicht ist ein Gesicht), nicht die einzelne Konstante.
Das ist Absicht: die Zahlen sind zwei Wege zum selben Ziel, und ein Test, der
eine davon festnagelt, verbietet die nächste Kalibrierung vor Ort.
"""

from __future__ import annotations

import io
import json
import re
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from PIL import Image

from mirror.receiver import create_app

VIEWPORT = {"width": 390, "height": 844}

#: Ab wann ein Portrait am Telefon ein Gesicht ist und kein Punkt. 30 px ist
#: knapp unter dem, was ein Finger sicher trifft (--tap: 44px in mirror.css) —
#: also die Untergrenze, ab der etwas überhaupt als Bildinhalt und nicht als
#: Markierung gelesen wird. Vorher gemessen: 20,7 px.
PORTRAIT_MIN_PX = 30


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def png_bytes(farbe=(200, 150, 90)) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGBA", (512, 512), (*farbe, 255)).save(puffer, format="PNG")
    return puffer.getvalue()


def beispielgraph() -> dict:
    """Ein Stand, wie ihn `kg/export.py` schreibt.

    Die Koordinaten sind Modelleinheiten aus dem Layout der Wand — genau das
    ist die Lage, in die der Spiegel gerät: er bekommt Positionen, die für
    3840 px gerechnet sind, und muss sie auf 390 px lesbar machen.

    Eine Person OHNE Portrait ist Absicht und kein Füllmaterial: wer sich
    gegen ein Foto entscheidet, ist der Normalfall, nicht der Fehlerfall.
    """
    return {
        "version": 1,
        "generated_at": 1788300000.0,
        "max_terms": 20,
        "nodes": [
            {
                "id": "p1",
                "type": "person",
                "portrait": "/media/portraits/eins.png",
                "name": "Mira",
                "created_at": 1788290000.0,
                "hidden": False,
                "x": -400.0,
                "y": 120.0,
            },
            {
                "id": "p2",
                "type": "person",
                "portrait": "/media/portraits/zwei.png",
                "name": None,
                "created_at": 1788291000.0,
                "hidden": False,
                "x": 350.0,
                "y": -260.0,
            },
            {
                "id": "p3",
                "type": "person",
                "portrait": None,
                "name": "Jonas",
                "created_at": 1788292000.0,
                "hidden": False,
                "x": 60.0,
                "y": 420.0,
            },
            {
                "id": "t1",
                "type": "term",
                "label": "Genossenschaftliches Wohnen",
                "mentions": 4,
                "created_at": 1788290500.0,
                "hidden": False,
                "in_dream": True,
                "dream_role": "anchor",
                "x": -120.0,
                "y": -80.0,
            },
            {
                "id": "t2",
                "type": "term",
                "label": "Tiny House",
                "mentions": 3,
                "created_at": 1788291500.0,
                "hidden": False,
                "in_dream": False,
                "x": 240.0,
                "y": 200.0,
            },
            {
                "id": "t3",
                "type": "term",
                "label": "Rückbaubare Verbindungen",
                "mentions": 2,
                "created_at": 1788292500.0,
                "hidden": False,
                "in_dream": False,
                "x": -300.0,
                "y": -320.0,
            },
            # Vier weitere Begriffe mit langen Beschriftungen. Nicht Beiwerk:
            # DREI kurze Tafeln passen auf 390 px auch dann noch, wenn der
            # Ausschnitt schlecht gerechnet ist. Die reale Station stand am
            # 2026-09-02 bei sieben Begriffen mit genau solchen Wortlängen,
            # und erst dort ragte das Netz aus dem Bild
            # (`test_das_netz_passt_beim_aufschlagen_in_den_schirm`).
            {
                "id": "t4",
                "type": "term",
                "label": "Naturverbundenes Wohnen",
                "mentions": 2,
                "created_at": 1788292600.0,
                "hidden": False,
                "in_dream": False,
                "x": -420.0,
                "y": 20.0,
            },
            {
                "id": "t5",
                "type": "term",
                "label": "Gemeinschaftliche Erdgeschosszonen",
                "mentions": 2,
                "created_at": 1788292700.0,
                "hidden": False,
                "in_dream": False,
                "x": 420.0,
                "y": 60.0,
            },
            {
                "id": "t6",
                "type": "term",
                "label": "Bürgerräte für Stadtplanung",
                "mentions": 1,
                "created_at": 1788292800.0,
                "hidden": False,
                "in_dream": False,
                "x": 120.0,
                "y": -400.0,
            },
            {
                "id": "t7",
                "type": "term",
                "label": "Wiederverwendete Baustoffe",
                "mentions": 1,
                "created_at": 1788292900.0,
                "hidden": False,
                "in_dream": False,
                "x": -60.0,
                "y": 300.0,
            },
        ],
        "edges": [
            # 🔴 Zwei Menschen, EIN Begriff, je eigene Belegstelle (2026-09-02).
            # Genau der Fall, den Birk sehen will: „bei Begriffen, die von
            # mehreren Menschen genannt wurden, der jeweilige Kontext pro
            # Person mit dem Namen." p2 hat KEINEN Namen — auch das ist der
            # Normalfall und darf keinen Platzhalter erzeugen.
            {"id": "e1", "source": "p1", "target": "t1",
             "evidence": "Das Haus gehört allen zusammen"},
            {"id": "e2", "source": "p2", "target": "t1",
             "evidence": "Wir haben eine Genossenschaft gegründet"},
            {"id": "e3", "source": "p2", "target": "t2"},
            {"id": "e4", "source": "p3", "target": "t3"},
            {"id": "e5", "source": "p1", "target": "t3"},
            {"id": "e6", "source": "p1", "target": "t4"},
            {"id": "e7", "source": "p2", "target": "t5"},
            {"id": "e8", "source": "p3", "target": "t6"},
            {"id": "e9", "source": "p3", "target": "t7"},
        ],
        "quotes": [
            {"id": "q1", "person_id": "p1", "text": "Ich will mehr Grün zwischen den Häusern."},
            {"id": "q2", "person_id": "p3", "text": "Eigentum an Boden gehört überdacht."},
            # p2 hat ein Portrait, aber KEINEN Namen — der Normalfall: die
            # wenigsten stellen sich im Interview vor.
            {"id": "q3", "person_id": "p2", "text": "Höfe statt Parkplätze."},
        ],
    }


@pytest.fixture()
def spiegel(tmp_path):
    """Ein echter Empfänger auf einem echten Port, mit echten Bilddateien.

    Kein `TestClient`: der Browser muss die Seite wirklich über HTTP holen,
    sonst sagt der Test nichts über das, was am Telefon ankommt.
    """
    daten = tmp_path / "mirror-data"
    (daten / "portraits").mkdir(parents=True)
    for name in ("eins.png", "zwei.png"):
        (daten / "portraits" / name).write_bytes(png_bytes())
    (daten / "graph.json").write_text(
        json.dumps({"received_at": time.time(), "payload": beispielgraph()}),
        encoding="utf-8",
    )

    port = freier_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(data_dir=daten, token="unbenutzt"),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    faden = threading.Thread(target=server.run, daemon=True)
    faden.start()
    frist = time.time() + 20
    while not server.started and time.time() < frist:
        time.sleep(0.05)
    assert server.started, "der Empfänger kam nicht hoch"
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        faden.join(timeout=10)


@pytest.fixture()
def handy(browser, spiegel):
    """Die Graphseite, so wie sie auf einem Telefon aufschlägt."""
    seite = browser.new_page(viewport=VIEWPORT)
    fehler: list[str] = []
    seite.on("pageerror", lambda e: fehler.append(str(e)))
    seite.goto(f"{spiegel}/graph")
    seite.wait_for_function(
        "() => window.kgSpiegel && window.kgSpiegel.cy.nodes('.person').length > 0",
        timeout=30000,
    )
    # Ein Frame Ruhe: `ersteAnsicht()` zoomt und skaliert per
    # requestAnimationFrame, und ohne diese Pause misst der Test die Größen
    # von VOR der Skalierung.
    seite.wait_for_timeout(700)
    assert not fehler, f"die Seite hat Fehler geworfen: {fehler}"
    yield seite
    seite.close()


# --- Geschwungene Kanten -----------------------------------------------------


def test_die_kanten_sind_boegen_wie_im_saal(handy):
    """Birks erster Punkt wörtlich: „mit geschwungenen Kanten".

    Der Saal zeichnet `unbundled-bezier` mit zwei gegenläufigen
    Kontrollpunkten (frontend/static/projection.js, `styleSchwarzplan()`).
    Ein Bogen ohne Kontrollpunkte wäre wieder eine Gerade — deshalb wird
    beides geprüft, der Stil UND die Daten, aus denen er seine Form nimmt.
    """
    kanten = handy.evaluate(
        """() => window.kgSpiegel.cy.edges().map((e) => ({
             id: e.id(),
             stil: e.style('curve-style'),
             cpd: e.data('cpd'),
             cpw: e.data('cpw'),
           }))"""
    )
    assert kanten, "keine Kanten im Bild"
    for kante in kanten:
        assert kante["stil"] == "unbundled-bezier", f"{kante['id']} ist eine Gerade"
        assert kante["cpd"], f"{kante['id']} hat keine Kontrollpunkt-Abstände"
        assert kante["cpw"], f"{kante['id']} hat keine Kontrollpunkt-Gewichte"

    # Zwei Kontrollpunkte mit GEGENLÄUFIGEM Vorzeichen: das ist die flache
    # S-Kurve des Saals und nicht der eine gleichmäßige Bauch, den ein
    # einzelner Punkt ergäbe.
    for kante in kanten:
        a, b = (float(x) for x in kante["cpd"].split())
        assert a * b < 0, f"{kante['id']} schwingt nur in eine Richtung: {kante['cpd']}"


def test_der_bogen_einer_kante_bleibt_ueber_die_zeit_gleich(handy):
    """Der Bogen kommt aus der Kanten-ID, nicht aus dem Zufall.

    Sonst zappelt das Netz bei jedem Push — und der Spiegel bekommt alle drei
    Sekunden einen. Dieselbe Begründung wie in `term-plate.js::edgeCurve`.
    """
    boegen = "() => Object.fromEntries(window.kgSpiegel.cy.edges().map((e) => [e.id(), e.data('cpd')]))"
    vorher = handy.evaluate(boegen)
    # Denselben Stand noch einmal einspielen, genau wie der Uploader es alle
    # drei Sekunden tut.
    handy.evaluate(
        """async () => {
             const daten = await fetch('/api/graph', { cache: 'no-store' }).then((a) => a.json());
             window.kgSpiegel.update(daten, 20);
           }"""
    )
    nachher = handy.evaluate(boegen)
    assert vorher == nachher
    assert len(vorher) == 9


# --- Die Porträts ------------------------------------------------------------


def test_ein_portrait_ist_am_handy_gross_genug_fuer_ein_gesicht(handy):
    """Der gemessene Grund für „die Porträts werden gar nicht angezeigt".

    Vorher: 20,7 px bei drei Personen auf 390×844. Das Bild war da und wurde
    gezeichnet — man konnte nur nichts darauf erkennen.
    """
    groessen = handy.evaluate(
        """() => window.kgSpiegel.cy.nodes('.person').map((n) => ({
             id: n.id(),
             breite: n.renderedBoundingBox().w,
           }))"""
    )
    assert groessen, "keine Personen im Bild"
    for eintrag in groessen:
        assert eintrag["breite"] >= PORTRAIT_MIN_PX, (
            f"{eintrag['id']} ist {eintrag['breite']:.1f} px breit — "
            f"unter {PORTRAIT_MIN_PX} px ist das ein Punkt, kein Gesicht"
        )


def test_ein_portrait_wird_wirklich_geladen_und_nicht_nur_gesetzt(handy, spiegel):
    """Gesetzt ist nicht geladen.

    Ein `background-image` auf einen 404 sieht im Stil genauso aus wie eines
    auf ein Bild. Deshalb wird die Antwort des Empfängers geprüft, nicht die
    Absicht der Seite.
    """
    bilder = handy.evaluate(
        """async () => {
             const cy = window.kgSpiegel.cy;
             const quellen = cy.nodes('.person')
               .map((n) => n.data('portrait'))
               .filter(Boolean);
             const ergebnis = [];
             for (const quelle of quellen) {
               const antwort = await fetch(quelle, { cache: 'no-store' });
               ergebnis.push({ quelle, status: antwort.status,
                               typ: antwort.headers.get('content-type') });
             }
             return ergebnis;
           }"""
    )
    assert len(bilder) == 2, f"erwartet zwei Portraits, bekommen: {bilder}"
    for bild in bilder:
        assert bild["status"] == 200, bild
        assert bild["typ"].startswith("image/"), bild


def test_eine_person_ohne_portrait_bleibt_eine_person(handy):
    """Kein Platzhalter-Avatar, kein Fragezeichen — eine eigene, ruhige Fläche.

    Wörtlich die Regel der Wand (`styleSchwarzplan()`, node.person): „Wer sich
    gegen ein Bild entscheidet, ist kein fehlendes Bild." Der Knoten muss also
    da sein, gleich groß wie die anderen, und darf kein Bild tragen.
    """
    ohne = handy.evaluate(
        """() => {
             const n = window.kgSpiegel.cy.getElementById('p3');
             if (!n.length) return null;
             return {
               klassen: n.classes(),
               bild: n.style('background-image'),
               breite: n.renderedBoundingBox().w,
               farbe: n.style('background-color'),
             };
           }"""
    )
    assert ohne is not None, "die Person ohne Portrait fehlt im Bild"
    assert "mit-bild" not in ohne["klassen"]
    assert ohne["bild"] in ("none", "", None), ohne["bild"]
    assert ohne["breite"] >= PORTRAIT_MIN_PX


# --- Die Begriffe ------------------------------------------------------------


def test_die_begriffe_stehen_auf_tafeln_mit_runden_ecken(handy):
    """Der Punkt am Begriff ist im Saal ersatzlos weg; der Begriff IST die Tafel.

    Er trug nie Bedeutung (Kantenanker und Labelanker) und kostete den Blick
    einen Sprung — die Begründung steht in `styleSchwarzplan()`. Am Telefon
    wiegt sie schwerer, nicht leichter: dort ist die Beschriftung die
    Hauptsache.
    """
    begriffe = handy.evaluate(
        """() => window.kgSpiegel.cy.nodes('.term').map((n) => ({
             id: n.id(),
             form: n.style('shape'),
             radius: n.style('corner-radius'),
             breite: n.renderedBoundingBox().w,
             hoehe: n.renderedBoundingBox().h,
           }))"""
    )
    assert begriffe, "keine Begriffe im Bild"
    for begriff in begriffe:
        assert begriff["form"] == "round-rectangle", f"{begriff['id']}: {begriff['form']}"
        assert float(str(begriff["radius"]).replace("px", "")) > 0, begriff
        # Die Tafel trägt ihre Beschriftung: sie muss breiter sein als der
        # 7-px-Punkt, den sie ersetzt, sonst steht die Schrift wieder daneben.
        assert begriff["breite"] > 40, begriff


def test_einpassen_kommt_zur_ruhe(handy):
    """„Alles zeigen" muss ein FIXPUNKT sein, nicht ein Schritt in die Richtung.

    🔴 Die Tafelgrösse und der Ausschnitt hängen VONEINANDER ab, und das ist
    der Preis dafür, dass die Schrift am Telefon bei jedem Zoom lesbar bleibt:
    eine Tafel misst `Mass / Zoom` Modelleinheiten, und `cy.fit()` bestimmt
    den Zoom aus eben diesen Modelleinheiten. Ein einzelnes `fit()`
    beantwortet also eine Frage, die sich durch die Antwort ändert.

    Gemessen am 2026-09-02 (390×844, sieben Begriffe, Chromium): ein
    Durchgang landete bei Zoom 0,260, der zweite bei 0,229 — 12 % Unterschied
    für dieselbe Geste. Am Telefon heisst das: der Doppeltipp springt beim
    zweiten Mal noch einmal, obwohl sich nichts geändert hat.

    Die Wand hat das Problem nicht: dort steht die Schrift in Modelleinheiten
    und wächst mit dem Zoom mit.

    Gemessen wird die Stabilität und nicht „alles ist im Bild": die Seite
    schlägt bewusst auf einem AUSSCHNITT auf (`ersteAnsicht()` zoomt auf ein
    lesbares Mass und zentriert auf die Traumbegriffe), da liegt also zurecht
    etwas ausserhalb.
    """
    zoome = handy.evaluate(
        """() => {
             const cy = window.kgSpiegel.cy;
             window.kgSpiegel.einpassen();
             const erste = cy.zoom();
             window.kgSpiegel.einpassen();
             const zweite = cy.zoom();
             return { erste, zweite };
           }"""
    )
    abweichung = abs(zoome["zweite"] - zoome["erste"]) / zoome["erste"]
    assert abweichung < 0.01, (
        f"zweimal dieselbe Geste, zwei Ausschnitte: {zoome['erste']:.4f} → "
        f"{zoome['zweite']:.4f} ({abweichung:.1%})"
    )


# --- Anklickbare Zitate ------------------------------------------------------


def test_ein_tipp_auf_ein_gesicht_zeigt_zitat_und_name(handy):
    """Birks zweiter Punkt: „anklickbare Zitate".

    Der Saal zeigt Name UND Zitat (`quote-overlay.js`: eine `<figcaption>`
    über dem `<blockquote>`, weil ein Name IM Zitattext zwischen den
    Anführungszeichen stünde, als hätte die Person ihren eigenen Namen
    gesagt). Der Spiegel zeigte bis 2026-09-02 nur den Text.
    """
    zustand = handy.evaluate(
        """() => {
             const cy = window.kgSpiegel.cy;
             cy.getElementById('p1').emit('tap');
             return {
               offen: document.getElementById('blatt').classList.contains('offen'),
               zitat: document.getElementById('blatt-zitat').textContent,
               name: document.getElementById('blatt-name').textContent,
               nameVersteckt: document.getElementById('blatt-name').hidden,
               bild: document.getElementById('blatt-bild').getAttribute('src'),
             };
           }"""
    )
    assert zustand["offen"], "das Blatt ist nicht aufgegangen"
    assert zustand["zitat"] == "Ich will mehr Grün zwischen den Häusern."
    assert zustand["name"] == "Mira"
    assert zustand["nameVersteckt"] is False
    assert zustand["bild"] == "/media/portraits/eins.png"


def test_eine_person_ohne_namen_zeigt_das_zitat_allein(handy):
    """Die meisten stellen sich nicht vor.

    Eine leere Zeile über dem Zitat wäre dann eine Lücke bei fast jedem —
    deshalb versteckt, nicht nur leer (dieselbe Begründung wie in
    `quote-overlay.js::showName`).
    """
    zustand = handy.evaluate(
        """() => {
             window.kgSpiegel.cy.getElementById('p2').emit('tap');
             const name = document.getElementById('blatt-name');
             return { text: name.textContent, versteckt: name.hidden,
                      zitat: document.getElementById('blatt-zitat').textContent };
           }"""
    )
    assert zustand["zitat"] == "Höfe statt Parkplätze."
    assert zustand["versteckt"] is True
    assert zustand["text"] == ""


def test_ein_tipp_auf_den_hintergrund_schliesst_das_blatt_wieder(handy):
    """Ein Zitat, das stehen bleibt, verdeckt das Netz, das man sehen wollte."""
    zu = handy.evaluate(
        """() => {
             const cy = window.kgSpiegel.cy;
             cy.getElementById('p1').emit('tap');
             const offen = document.getElementById('blatt').classList.contains('offen');
             cy.emit('tap');
             return { offen, danach: document.getElementById('blatt').classList.contains('offen') };
           }"""
    )
    assert zu["offen"] is True
    assert zu["danach"] is False


# --- Was der Spiegel NICHT tun darf ------------------------------------------


def test_der_spiegel_haengt_weiterhin_an_nichts_aus_frontend():
    """Die Bildsprache wird KOPIERT, nicht geteilt.

    Der Spiegel liegt auf einem anderen Rechner und wird ohne `frontend/`
    ausgeliefert (`test_mirror.py::test_die_seiten_haengen_an_nichts_aus_frontend`).
    Ein Import von dort wäre am Ausstellungstag ein 404 statt eines Netzes.
    """
    # Nur echte Verweise, nicht die Prosa: die Kommentare in `graph.css`
    # NENNEN `frontend/static/quote-overlay.js` als Vorbild, und genau das
    # sollen sie — nachgebaut heisst, dass die Herkunft dokumentiert ist.
    verweis = re.compile(
        r"""(?:src|href)\s*=\s*["'][^"']*frontend|from\s+["'][^"']*frontend|url\(\s*["']?[^)"']*frontend""",
        re.IGNORECASE,
    )
    geprueft = 0
    for pfad in sorted(Path("mirror/web").rglob("*")):
        if pfad.suffix not in (".html", ".js", ".css"):
            continue
        geprueft += 1
        text = pfad.read_text(encoding="utf-8")
        treffer = verweis.search(text)
        assert treffer is None, f"{pfad} lädt aus frontend/: {treffer.group(0) if treffer else ''}"
    assert geprueft >= 8, f"nur {geprueft} Dateien geprüft — der Suchpfad stimmt nicht"


# --- Ein Tipp auf einen BEGRIFF (Birk, 2026-09-02) --------------------------
#
# „Guck mal, ob man da auch auf die Nodes draufklicken kann, wie man die
# Zitate sieht."
#
# Gemessen VOR dieser Änderung, am echten Stand auf 390x844: Ein Fingertipp
# auf ein Porträt landete auf `t25` — vier Knoten (p6, t23, t24, t25) lagen an
# derselben Stelle übereinander. Begriffe waren gar nicht anklickbar, also
# passierte nichts. Die Wand kann das seit heute (quote-overlay.js), der
# Spiegel nicht.


def test_ein_tipp_auf_einen_begriff_zeigt_die_belegstellen(handy):
    handy.evaluate("() => window.kgSpiegel.cy.getElementById('t1').emit('tap')")
    handy.wait_for_timeout(400)

    zustand = handy.evaluate(
        """() => ({
             offen: document.getElementById('blatt').classList.contains('offen'),
             text: document.getElementById('blatt').innerText,
           })"""
    )
    assert zustand["offen"], "das Blatt bleibt zu"
    assert "Das Haus gehört allen zusammen" in zustand["text"]
    assert "Wir haben eine Genossenschaft gegründet" in zustand["text"]


def test_die_belegstelle_traegt_den_namen_wo_es_einen_gibt(handy):
    handy.evaluate("() => window.kgSpiegel.cy.getElementById('t1').emit('tap')")
    handy.wait_for_timeout(400)

    text = handy.evaluate("() => document.getElementById('blatt').innerText")
    # Das Blatt setzt Namen per CSS in Versalien — deshalb ohne Ruecksicht auf
    # Gross-/Kleinschreibung pruefen, sonst haengt die Wache an einer
    # Gestaltungsentscheidung statt am Inhalt.
    assert "mira" in text.lower(), "der Name der Person fehlt an ihrer Stelle"
    # p2 hat keinen Namen — dort darf nichts Erfundenes stehen.
    assert "null" not in text.lower()
    assert "undefined" not in text.lower()


def test_ein_begriff_ohne_belegstelle_oeffnet_kein_leeres_blatt(handy):
    """t2 hat nur eine Kante ohne `evidence` — wie jede Kante von vor dem
    2026-09-02. Lieber nichts als ein Blatt, das kaputt aussieht."""
    handy.evaluate("() => window.kgSpiegel.cy.getElementById('t2').emit('tap')")
    handy.wait_for_timeout(400)

    assert not handy.evaluate(
        "() => document.getElementById('blatt').classList.contains('offen')"
    )


def test_ein_tipp_auf_ein_gesicht_zeigt_weiter_das_zitat(handy):
    """Die Gegenrichtung: der bestehende Weg darf nicht kaputtgehen."""
    handy.evaluate("() => window.kgSpiegel.cy.getElementById('p1').emit('tap')")
    handy.wait_for_timeout(400)

    text = handy.evaluate("() => document.getElementById('blatt').innerText")
    assert "Ich will mehr Grün zwischen den Häusern." in text
    assert "mira" in text.lower()
