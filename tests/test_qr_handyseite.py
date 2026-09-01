"""Ist der erzeugte QR-Code maschinell lesbar -- und zeigt er auf die richtige Seite?

Das ist der Test, der zaehlt. Ein QR-Code, der "aussieht wie ein QR-Code",
ist wertlos; entscheidend ist, ob ein Telefon ihn dekodiert und ob dabei die
Adresse herauskommt, die drinstehen soll.

Geprueft wird mit OpenCVs QRCodeDetector -- einem unabhaengigen DEKODIERER,
nicht mit derselben Bibliothek, die den Code erzeugt hat. Ein Test, der segno
gegen segno prueft, wuerde jeden Fehler mitmachen.

Zusaetzlich wird die ausgelieferte SVG-DATEI selbst geprueft: Sie ist das, was
auf der Wand landet, nicht die Matrix im Speicher.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SVG = Path("frontend/static/qr-handyseite.svg")
SKRIPT = Path("scripts/qr-erzeugen.py")
ADRESSE = "https://kollektivgedaechtnis.flashclash.de"


def test_die_datei_existiert_und_ist_ein_svg():
    """Erzeugt wird EINMAL per Skript; ausgeliefert wird die Datei. Fehlt sie,
    zeigt die Wand ein kaputtes Bild statt eines Codes."""
    assert SVG.exists(), f"{SVG} fehlt — 'uv run --with segno python {SKRIPT}' laufen lassen"
    wurzel = ET.fromstring(SVG.read_text(encoding="utf-8"))
    assert wurzel.tag.endswith("svg")


def test_die_adresse_ist_die_zertifizierte(monkeypatch):
    """🔴 Der teuerste denkbare Fehler an diesem Punkt.

    Birk nannte urspruenglich `kollektivtraum.flashclash.de`; live und
    zertifiziert ist `kollektivgedaechtnis.flashclash.de` (am 2026-09-01
    ausdruecklich bestaetigt). Ein QR-Code auf den anderen Namen ergaebe auf
    jedem Telefon einen Sicherheitswarn-Bildschirm statt der Seite -- und das
    faellt erst auf, wenn Besucher davorstehen.
    """
    quelle = SKRIPT.read_text(encoding="utf-8")
    treffer = re.search(r'^ADRESSE\s*=\s*"([^"]+)"', quelle, re.M)
    assert treffer, "die Adresse steht nicht mehr an der erwarteten Stelle"
    assert treffer.group(1) == ADRESSE, (
        f"der QR-Code zeigt auf {treffer.group(1)!r} statt auf {ADRESSE!r}"
    )
    assert "kollektivtraum.flashclash.de" not in treffer.group(1), (
        "kollektivtraum.flashclash.de hat kein Zertifikat"
    )


def test_der_code_ist_maschinell_lesbar_und_fuehrt_zur_richtigen_seite():
    """Der eigentliche Nachweis: ein unabhaengiger Dekodierer liest ihn.

    Gerendert wird aus der Matrix in derselben Groesse und Ruhezone wie in der
    SVG-Datei. OpenCVs Detektor steht hier stellvertretend fuer die Kamera
    eines Telefons.
    """
    segno = pytest.importorskip("segno", reason="nur zum Erzeugen noetig")
    cv2 = pytest.importorskip("cv2", reason="unabhaengiger Dekodierer")
    np = pytest.importorskip("numpy")

    qr = segno.make(ADRESSE, error="m", micro=False)
    matrix = [[bool(v) for v in zeile] for zeile in qr.matrix]

    rand, skala = 4, 10
    n = len(matrix)
    gesamt = (n + 2 * rand) * skala
    bild = np.full((gesamt, gesamt), 255, dtype=np.uint8)
    for y, zeile in enumerate(matrix):
        for x, dunkel in enumerate(zeile):
            if dunkel:
                y0, x0 = (y + rand) * skala, (x + rand) * skala
                bild[y0 : y0 + skala, x0 : x0 + skala] = 0

    detektor = cv2.QRCodeDetector()
    gelesen, _punkte, _rest = detektor.detectAndDecode(bild)
    assert gelesen == ADRESSE, (
        f"dekodiert wurde {gelesen!r}, erwartet {ADRESSE!r}"
    )


def test_die_svg_datei_zeigt_denselben_code_wie_die_matrix():
    """Die Datei ist das Auslieferungsstueck — sie muss den Code enthalten,
    den der Encoder gemeint hat, und nicht etwa einen leeren Rahmen."""
    segno = pytest.importorskip("segno")

    inhalt = SVG.read_text(encoding="utf-8")
    qr = segno.make(ADRESSE, error="m", micro=False)
    module = sum(1 for zeile in qr.matrix for wert in zeile if wert)

    # segno zeichnet die dunklen Module als Pfad(e). Grober, aber wirksamer
    # Test gegen eine leere oder abgeschnittene Datei: die Pfaddaten muessen
    # ungefaehr zur Anzahl dunkler Module passen.
    pfade = re.findall(r'\sd="([^"]+)"', inhalt)
    assert pfade, "die SVG enthaelt keinen Pfad — der Code fehlt"
    kommandos = sum(len(re.findall(r"[Mmhv]", p)) for p in pfade)
    assert kommandos > module * 0.3, (
        f"die SVG wirkt leer: {kommandos} Zeichenbefehle bei {module} dunklen Modulen"
    )


def test_die_ruhezone_ist_vorhanden():
    """Vier Module Rand sind Vorschrift. Ohne sie finden viele Leser den Code
    auf einer gemusterten Projektion nicht — der haeufigste Grund, warum ein
    technisch korrekter QR-Code an einer Wand nicht funktioniert."""
    segno = pytest.importorskip("segno")

    inhalt = SVG.read_text(encoding="utf-8")
    qr = segno.make(ADRESSE, error="m", micro=False)
    n = len(qr.matrix)

    treffer = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', inhalt)
    if treffer is None:
        treffer = re.search(r'width="([\d.]+)"[^>]*height="([\d.]+)"', inhalt)
    assert treffer, "die SVG nennt weder viewBox noch Groesse"

    breite = float(treffer.group(1))
    # Bei Skalierung 1 entspricht eine Einheit einem Modul.
    rand_gesamt = breite - n
    assert rand_gesamt >= 8, (
        f"Ruhezone zu klein: {rand_gesamt / 2:.1f} Module je Seite, noetig sind 4"
    )


# --- Die Einbindung an der Wand ---------------------------------------------


@pytest.fixture()
def wand(page, static_server):
    page.goto(f"{static_server}/frontend/projection.html?theme=f")
    page.wait_for_function("() => window.kgLegende !== undefined", timeout=30000)
    return page


def test_der_code_haengt_sichtbar_an_der_wand(wand):
    """Er nuetzt nur etwas, wenn man ihn sieht — und er muss gross genug sein,
    um aus einigen Metern erfasst zu werden."""
    masse = wand.evaluate(
        """() => {
             const bild = document.querySelector('.qr-bild');
             if (!bild) return null;
             const r = bild.getBoundingClientRect();
             const s = getComputedStyle(document.querySelector('.qr-hinweis'));
             const sb = getComputedStyle(bild);
             return {breite: r.width, hoehe: r.height, pointer: s.pointerEvents,
                     deckkraft: parseFloat(sb.opacity),
                     hintergrund: s.backgroundColor,
                     geladen: bild.complete && bild.naturalWidth > 0};
           }"""
    )
    assert masse is not None, "der QR-Code ist nicht in der Wandseite eingebunden"
    assert masse["geladen"], "die SVG-Datei wird nicht geladen (falscher Pfad?)"
    assert masse["breite"] >= 100, f"der Code ist nur {masse['breite']}px breit"
    assert masse["pointer"] == "none", "der Code faengt Beruehrungen ab"


def test_der_code_haengt_ohne_kasten_und_ohne_text(wand):
    """Birk, 2026-09-01: „Der qr code ohne Text so unauffaellig wie moeglich.
    Ecke ist OK. Hintergrund mit transparenz."

    Geprueft wird beides: keine Beschriftung, und die Flaeche darum traegt
    keinen eigenen Hintergrund mehr (die alte Fassung hatte eine helle Karte
    mit Schatten und dem Text „Am eigenen Telefon mitlesen")."""
    befund = wand.evaluate(
        """() => {
             const kasten = document.querySelector('.qr-hinweis');
             const s = getComputedStyle(kasten);
             return {text: kasten.textContent.trim(),
                     hintergrund: s.backgroundColor,
                     schatten: s.boxShadow,
                     kindElemente: kasten.children.length};
           }"""
    )
    assert befund["text"] == "", f"der Code traegt noch Text: {befund['text']!r}"
    assert befund["kindElemente"] == 1, "neben dem Bild haengt noch etwas daran"
    # rgba(0,0,0,0) = transparent; alles andere waere wieder ein Kasten.
    assert "rgba(0, 0, 0, 0)" in befund["hintergrund"] or befund["hintergrund"] == "transparent", (
        f"die Flaeche hat wieder einen Hintergrund: {befund['hintergrund']}"
    )
    assert befund["schatten"] in ("none", ""), f"der Schatten ist zurueck: {befund['schatten']}"


def test_die_deckkraft_bleibt_ueber_der_gemessenen_lesegrenze(wand):
    """🔴 Die Zahl, die diesen Code lesbar haelt.

    Ein QR-Code lebt vom Kontrast zwischen hellen und dunklen Modulen. Wird er
    durchsichtig, sinkt der helle Anteil gegen die fast schwarze Wand ab
    (gemessene Wandhelligkeit 6.7 von 255). Am 2026-09-01 auf dem echten
    Wandbild mit OpenCVs Dekodierer durchgemessen:

        100 % .. 46 %      lesbar
        44 % und darunter  NICHT mehr lesbar

    Gesetzt sind 70 %: Birks „so unauffaellig wie moeglich" mit Abstand zur
    Grenze. Der Abstand ist noetig, weil eine Handykamera schlechter sieht als
    ein Dekodierer auf einem perfekten Rendering — Schraeglage, Bewegung,
    Beamer-Gamma, Streulicht.

    Dieser Test ist die Bremse gegen ein spaeteres „mach ihn noch dezenter":
    Unter 50 % darf niemand gehen, ohne neu zu messen.
    """
    deckkraft = wand.evaluate(
        "() => parseFloat(getComputedStyle(document.querySelector('.qr-bild')).opacity)"
    )
    assert deckkraft >= 0.5, (
        f"Deckkraft {deckkraft:.0%} liegt zu nah an der gemessenen Lesegrenze von 46 % — "
        "vor einer weiteren Absenkung neu messen (siehe Docstring)"
    )
    assert deckkraft <= 1.0


def test_der_code_verdeckt_weder_zitat_noch_legende(wand):
    """Drei Einblendungen teilen sich den unteren Rand: Legende links, Zitat
    mittig, QR rechts. Ueberschneiden sie sich, verdeckt die kleinere Sache
    die groessere Aussage."""
    wand.evaluate(
        """() => {
             const q = document.querySelector('.quote-overlay');
             q.hidden = false;
             q.querySelector('.quote-text').textContent =
               'Ein Satz von der Laenge, wie ihn die Wand an einem vollen Tag wirklich zeigt, mit Umbruch.';
             q.classList.add('visible');
           }"""
    )
    ueberschneidungen = wand.evaluate(
        """() => {
             const r = (s) => {
               const e = document.querySelector(s);
               return e ? e.getBoundingClientRect() : null;
             };
             const paare = [['.qr-hinweis', '.quote-overlay'], ['.qr-hinweis', '.dream-legende']];
             const treffer = [];
             for (const [a, b] of paare) {
               const ra = r(a), rb = r(b);
               if (!ra || !rb || ra.width === 0 || rb.width === 0) continue;
               const schneidet = !(ra.right < rb.left || rb.right < ra.left ||
                                   ra.bottom < rb.top || rb.bottom < ra.top);
               if (schneidet) treffer.push(a + ' / ' + b);
             }
             return treffer;
           }"""
    )
    assert ueberschneidungen == [], f"Einblendungen ueberlappen: {ueberschneidungen}"


def test_der_prerender_nimmt_den_code_aus_dem_bild():
    """`sim/prerender.py` schiesst definierte Aufnahmen des Graphen; eine
    Einblendung darin verfaelscht Bildeindruck und Ueberlappungszaehlung."""
    quelle = Path("sim/prerender.py").read_text(encoding="utf-8")
    assert "qr-hinweis" in quelle, "der Prerender entfernt den QR-Code nicht"
