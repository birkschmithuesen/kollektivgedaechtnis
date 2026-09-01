"""Das Ende des Traumgebiets wird gefahren, nicht geschnitten.

Birk, 2026-09-01, dritter Anlauf an demselben Sprung: „Das passiert
wesentlich seltener als alle zwölf Sekunden, und es passiert immer noch."
Und als Zielbild: „Ein harter Sprung soll es nie geben, es sollte immer ein
Fade sein."

🔴 GEMESSEN, Bild für Bild, an der echten Wand (render-harness.html, echtes
cytoscape, Replay-Graph 19c mit 60 Personen und 32 Begriffen, 1920×1080,
Zoomregler 1,55 — also so, wie die Station steht). Größte Änderung zwischen
zwei aufeinanderfolgenden Frames, gegen den Median aller Frames desselben
Laufs:

                                     vorher      nachher    Median (nachher)
  Traum verfällt, pan   Zoom        44,913 %      0,317 %       0,131 %
  Traum verfällt, fit   Zoom        43,843 %      0,317 %       0,128 %
                        Bildmitte  242,4 px       1,41 px       0,41 px
  Traum beginnt in der  Zoom         6,682 %      0,291 %       0,014 %
  laufenden Fahrt       Bildmitte  158,7 px       2,71 px       0,00 px

Vorher war der größte Sprung also rund das 3400-fache dessen, was ein Frame
sonst bewegt; nachher das 2,4-fache — und das liegt mitten in der Überblendung,
an ihrer steilsten Stelle. Es gibt keinen Frame mehr, in dem etwas anderes
passiert als Bewegung.

Warum es weder auf 12 s noch auf einen Reglertritt passte: `DREAM.holdMs`
sind vier Minuten, und kg2 startet alle 4-5 Minuten einen neuen Traum
(`min_interval_s: 240`). Der Sprung hing also am Ablauf der Haltezeit und
kam im Takt der Träume wieder — ganz ohne Zutun von Bedienpult oder
Touchscreen.

Diese Datei prüft die SPRUNGHÖHE, nicht die Zahlen oben: eine Schwelle weit
unter dem Defekt (44,9 %) und weit über der gesunden Bewegung (0,32 %). Ein
Test auf „max < 0,32 %" wäre eine Kopie der Messung und würde beim nächsten
Layout-Tuning rot, ohne dass etwas kaputt ist.
"""

import statistics

import pytest

# Dieselbe Wand wie dort: echtes cytoscape, echter Replay-Graph.
from test_camera_wand_haelt_durch import wand  # noqa: F401

# Ein Sprung ist mindestens hundertmal so groß gewesen. Diese Schwellen liegen
# rund eine Größenordnung unter dem Defekt und rund eine Größenordnung über
# dem, was die Überblendung selbst an ihrer steilsten Stelle bewegt.
MAX_ZOOM_PRO_FRAME = 5.0  # Prozent   (Defekt 44,9 | gesund 0,32)
MAX_MITTE_PRO_FRAME = 40.0  # Modellpixel (Defekt 242 | gesund 1,4)

# Bild-für-Bild-Sonde: kontrollierte Uhr, damit der Lauf reproduzierbar ist,
# und alles in EINEM synchronen evaluate(), damit der rAF-Tick der Projektion
# nicht dazwischenfährt.
SONDE = """
(opts) => {
  const view = window.kgView, cy = view.cy, cam = view.camera;

  // Das Traumgebiet, wie projection.js `dreamNodes()` es bildet: fünf
  // Begriffe EINER Person plus die Personen, die daran hängen.
  let bester = null, meiste = -1;
  cy.nodes('.person').forEach((p) => {
    const n = p.neighborhood().nodes('.term').length;
    if (n > meiste) { meiste = n; bester = p; }
  });
  const fuenf = bester.neighborhood().nodes('.term').slice(0, 5);
  const gebiet = fuenf.union(fuenf.neighborhood().nodes('.person'));

  const echteUhr = performance.now.bind(performance);
  let uhr = echteUhr();
  performance.now = () => uhr;
  try {
    cam.setMinLabel(40);  // Birks Kalibrierung: 40/26 = 1,54 -- wie das alte 1,55
    cam.setMode(opts.mode);
    cam.focusDream(gebiet);
    // Über die Haltezeit springen. Gemessen wird der ÜBERGANG, nicht die
    // Dauer -- vier Minuten Frames wären 15000 Schritte für dieselbe Aussage.
    cam._dream.until = uhr + opts.haltenMs;

    const bilder = [];
    for (let i = 0; i < opts.frames; i += 1) {
      uhr += 16;
      cam.step(0.016);
      const p = cy.pan(), z = cy.zoom();
      bilder.push({
        z,
        // Der Modellpunkt in der Bildmitte: wohin die Wand gerade zeigt.
        mx: (cy.width() / 2 - p.x) / z,
        my: (cy.height() / 2 - p.y) / z,
      });
    }
    return bilder;
  } finally { performance.now = echteUhr; }
}
"""


# Die Gegenrichtung: das Traumgebiet BEGINNT, während eine Etappe läuft. Der
# häufigere der beiden Fälle -- eine Fahrt dauert 5,2 s, die Rast 4,2 s.
SONDE_EINTRITT = """
(opts) => {
  const view = window.kgView, cy = view.cy, cam = view.camera;
  let bester = null, meiste = -1;
  cy.nodes('.person').forEach((p) => {
    const n = p.neighborhood().nodes('.term').length;
    if (n > meiste) { meiste = n; bester = p; }
  });
  const fuenf = bester.neighborhood().nodes('.term').slice(0, 5);
  const gebiet = fuenf.union(fuenf.neighborhood().nodes('.person'));

  const echteUhr = performance.now.bind(performance);
  let uhr = echteUhr();
  performance.now = () => uhr;
  try {
    cam.setMinLabel(40);  // Birks Kalibrierung: 40/26 = 1,54 -- wie das alte 1,55
    cam.setMode('pan');

    // Bis MITTEN in eine Etappe fahren, statt eine Framenummer zu raten:
    // die Dauern sind Einstellungen und dürfen sich ändern.
    let sicherung = 0;
    while (cam.roamState.phase !== 'travel' && sicherung++ < 5000) {
      uhr += 16; cam.step(0.016);
    }
    const beginn = cam.roamState.elapsed;
    while (cam.roamState.phase === 'travel'
           && cam.roamState.elapsed < beginn + 1500 && sicherung++ < 5000) {
      uhr += 16; cam.step(0.016);
    }
    const mittenDrin = cam.roamState.phase === 'travel';

    cam.focusDream(gebiet);

    const bilder = [];
    for (let i = 0; i < opts.frames; i += 1) {
      uhr += 16;
      cam.step(0.016);
      const p = cy.pan(), z = cy.zoom();
      bilder.push({
        z,
        mx: (cy.width() / 2 - p.x) / z,
        my: (cy.height() / 2 - p.y) / z,
        ho: cam.handoverActive,
      });
    }
    return { mittenDrin, bilder };
  } finally { performance.now = echteUhr; }
}
"""


def _spruenge(bilder):
    """Zoom-Änderung in Prozent und Bewegung der Bildmitte in Modellpixeln,
    jeweils zwischen zwei aufeinanderfolgenden Frames."""
    zoom, mitte = [], []
    for a, b in zip(bilder, bilder[1:]):
        zoom.append(abs(b["z"] / a["z"] - 1) * 100)
        mitte.append(((b["mx"] - a["mx"]) ** 2 + (b["my"] - a["my"]) ** 2) ** 0.5)
    return zoom, mitte


# Ein Lauf je Modus, nicht je Test: die beiden Prüfungen unten stellen zwei
# Fragen an DIESELBE Messung (springt sie? und: bewegt sie sich überhaupt?),
# und 900 Frames auf dem echten Netz kosten rund zehn Sekunden. Am Aufbautag
# ist `-k camera` die Schleife, in der gearbeitet wird.
_LAEUFE = {}


def _fahre(wand, mode):
    # 8 s Haltezeit, dann 5 s Überblendung, dann Ruhe -- 900 Frames à 16 ms
    # sind 14,4 s und decken alle drei ab.
    if mode not in _LAEUFE:
        bilder = wand.evaluate(SONDE, {"mode": mode, "haltenMs": 8000, "frames": 900})
        assert len(bilder) == 900
        _LAEUFE[mode] = bilder
    return _LAEUFE[mode]


@pytest.mark.parametrize("mode", ["pan", "fit"])
def test_der_ablauf_des_traumgebiets_hat_keinen_harten_frame(wand, mode):  # noqa: F811
    """Kein einzelner Frame darf den Ausschnitt umreißen.

    Gilt für BEIDE getriebenen Modi. `fit` ist die Vorgabe der Station
    (`camera_mode` in kg/server.py) und war der schlimmere Fall: dort stand
    das Bild zwischen den Graph-Pushes völlig still (Median 0,000 %), und
    der Ablauf riss es in EINEM Frame um 43,8 % Zoom und 242 Modellpixel.
    """
    zoom, mitte = _spruenge(_fahre(wand, mode))

    z_max, z_med = max(zoom), statistics.median(zoom)
    m_max, m_med = max(mitte), statistics.median(mitte)

    assert z_max < MAX_ZOOM_PRO_FRAME, (
        f"[{mode}] größte Zoomänderung in einem Frame: {z_max:.3f} % "
        f"(Median {z_med:.4f} %) — der Ablauf der Haltezeit wird geschnitten "
        f"statt gefahren"
    )
    assert m_max < MAX_MITTE_PRO_FRAME, (
        f"[{mode}] die Bildmitte springt {m_max:.1f} Modellpixel in einem "
        f"Frame (Median {m_med:.2f} px)"
    )


@pytest.mark.parametrize("mode", ["pan", "fit"])
def test_der_ausschnitt_wechselt_ueberhaupt_und_zwar_ueber_viele_frames(wand, mode):  # noqa: F811
    """Die Gegenprobe, ohne die der Test oben wertlos wäre.

    Eine Kamera, die nach dem Ablauf einfach im Traumausschnitt stehen bliebe,
    hätte auch keinen harten Frame — und wäre trotzdem falsch: der Rest des
    Netzes darf nicht dauerhaft unsichtbar bleiben, das ist der ganze Grund
    für `DREAM.holdMs`. Geprüft wird deshalb beides: dass der Wechsel
    STATTFINDET, und dass er sich über viele Frames verteilt.
    """
    bilder = _fahre(wand, mode)
    zoom, mitte = _spruenge(bilder)

    # NICHT erster gegen letzten Frame: der Lauf beginnt VOR der Einfahrt ins
    # Traumgebiet und endet nach der Ausfahrt, beide Enden liegen also auf der
    # Gesamtansicht und die Differenz wäre null. Verglichen wird der Stand, der
    # am weitesten vom Endstand entfernt ist (das gehaltene Traumgebiet), gegen
    # den Stand am Ende.
    #
    # 🔴 Gemessen wird der AUSSCHNITT und nicht mehr nur der Zoom (2026-09-02).
    # Seit die Mindestschrift den Zoomfaktor ersetzt hat, ist das Fahrtniveau
    # `max(Ausschnitt, Ziel)` — liegen sowohl die Traumbox als auch die
    # Vollansicht unter der Mindestschrift, laufen BEIDE auf demselben Niveau,
    # und der Wechsel zeigt sich allein im Schwenk. Das ist keine Schwäche,
    # sondern die Zusicherung, um die es geht: „eigentlich sollte es immer
    # identisch bleiben" (Birk, 2026-09-01) — die Wand behält ihre
    # Schriftgröße und wechselt den Ort. Ein Test, der weiter nur den Zoom
    # misst, würde genau diese Eigenschaft als Fehler melden.
    ende = bilder[-1]
    zoomwechsel = (max(b["z"] for b in bilder) / ende["z"] - 1) * 100
    weiteste = max(
        ((b["mx"] - ende["mx"]) ** 2 + (b["my"] - ende["my"]) ** 2) ** 0.5 for b in bilder
    )
    # Der weiteste Abstand, gemessen in Bildbreiten am Endstand — damit die
    # Schwelle nicht von der Netzgröße abhängt.
    ortswechsel = weiteste / (1920 / ende["z"]) * 100
    assert zoomwechsel > 20 or ortswechsel > 25, (
        f"[{mode}] der Ausschnitt wandert nur {ortswechsel:.1f} % einer Bildbreite "
        f"und der Zoom nur {zoomwechsel:.1f} % — das Traumgebiet läuft gar nicht ab"
    )

    # Der Wechsel muss sich auf eine Überblendung verteilen, nicht auf eine
    # Handvoll Frames. `ROAM.handoverMs` sind 5 s, also rund 300 Frames.
    bewegte = sum(1 for dz, dm in zip(zoom, mitte) if dz > 0.05 or dm > 1.0)
    assert bewegte > 150, (
        f"[{mode}] nur {bewegte} Frames bewegen den Ausschnitt nennenswert — "
        f"der Wechsel ist keine Fahrt"
    )


def test_die_fahrt_nimmt_nach_der_uebergabe_dort_auf_wo_sie_gelandet_ist(wand):  # noqa: F811
    """Die andere Hälfte desselben Sprungs — beim EINTRITT ins Traumgebiet.

    🔴 Gemessen 2026-09-01: Beginnt ein Traum mitten in einer Etappe, hält
    `step()` die Fahrt an und übergibt fünf Sekunden lang an den Handover.
    Danach lief die Etappe auf ihrer alten Bahn weiter — `roam.from` und
    `roam.elapsed` hatten die Übergabe überlebt — und riss das Bild in dem
    einen Frame, in dem der Handover landete, dorthin zurück:

        Bildmitte   158,7 Modellpixel in einem Frame   (Median 0,40 px)
        Zoom        1,693 -> 1,806 = 6,7 %             (Median 0,013 %)

    Der Zoomanteil kam aus `roam.clock`: `_automaticView()` misst sein Ziel
    bei clock 0, wo die Atembewegung genau null ist, die weiterlaufende Uhr
    setzte den ersten `step()` danach aber irgendwo auf der Welle ab.

    Das passiert im selben Takt wie der Ablauf — alle vier bis fünf Minuten,
    und häufiger als nicht, weil eine Etappe (5,2 s) länger dauert als eine
    Rast (4,2 s).
    """
    ergebnis = wand.evaluate(SONDE_EINTRITT, {"frames": 900})
    assert ergebnis["mittenDrin"], (
        "der Traum wurde nicht mitten in einer Etappe ausgelöst — dieser Test "
        "misst dann nicht den Fall, um den es geht"
    )
    zoom, mitte = _spruenge(ergebnis["bilder"])

    m_max, m_med = max(mitte), statistics.median(mitte)
    z_max, z_med = max(zoom), statistics.median(zoom)
    assert m_max < MAX_MITTE_PRO_FRAME, (
        f"die Bildmitte springt {m_max:.1f} Modellpixel in einem Frame "
        f"(Median {m_med:.2f} px) — die Etappe setzt ihre alte Bahn fort, "
        f"statt dort aufzunehmen, wo die Übergabe gelandet ist"
    )
    assert z_max < MAX_ZOOM_PRO_FRAME, (
        f"größte Zoomänderung in einem Frame: {z_max:.3f} % "
        f"(Median {z_med:.4f} %) beim Landen der Übergabe"
    )


def test_die_uebergabe_landet_ohne_letzten_schritt(wand):  # noqa: F811
    """Der Frame, in dem die Fahrt ankommt, gehört noch zur Fahrt.

    🔴 Gemessen 2026-09-01: Die Übergabe misst ihr Ziel beim Start und fuhr
    es fünf Sekunden lang unverändert an. Das Ziel bleibt aber nicht stehen —
    `projection.js` leitet die Größe der Portraitscheiben aus dem Zoom ab, und
    `_levelForBox()` misst diese Scheiben mit. Während die Fahrt ins
    Traumgebiet hineinzoomt, schrumpfen die Scheiben, das Gebiet schrumpft
    mit, und das richtige Fahrtniveau wandert davon:

        Frame  Zoom     Fahrtniveau   Handover-Ziel   Scheibe (Modellpixel)
          401  0,9958     1,69299        1,69299            121,42
          650  1,6118     1,71730        1,69299             78,57
          712  1,6930     1,72151        1,69299             71,28   <- Landung

    Die Fahrt landete also auf einem 1,7 % veralteten Wert, und der nächste
    `step()` holte ihn in EINEM Frame nach.

    Geprüft wird eine RELATION und keine Schwelle: der Schritt beim Landen
    darf nicht größer sein als der größte Schritt, den die Fahrt selbst
    unterwegs macht. Gemessen sind das 0,014 % gegen 0,293 % — die Landung
    ist unauffälliger als die Fahrt. Mit eingefrorenem Ziel waren es 1,708 %
    gegen 0,269 %, also das 6,4-fache.
    """
    ergebnis = wand.evaluate(SONDE_EINTRITT, {"frames": 900})
    bilder = ergebnis["bilder"]
    zoom, _ = _spruenge(bilder)

    landung = next(
        i for i in range(1, len(bilder)) if bilder[i - 1]["ho"] and not bilder[i]["ho"]
    )
    unterwegs = [
        zoom[i] for i in range(len(zoom)) if bilder[i]["ho"] and bilder[i + 1]["ho"]
    ]
    assert unterwegs, "es lief gar keine Übergabefahrt — der Test misst nichts"

    schritt = zoom[landung]
    steilste = max(unterwegs)
    assert schritt <= steilste, (
        f"beim Landen bewegt sich der Zoom um {schritt:.4f} %, die Fahrt "
        f"selbst höchstens um {steilste:.4f} % — die Übergabe kommt auf einem "
        f"veralteten Ziel an und der nächste Frame holt den Rest nach"
    )


# Während der Graph umzieht, setzt die Wand die Kamera aus: `projection.js`,
# tick() ruft `camera.step()` nicht, solange `umbauend` gilt und keine
# Übergabe läuft. Ein Umzug dauert 2,5 s, ein Graph-Push kommt alle ~12 s —
# rund ein Fünftel der Zeit läuft also KEIN step(). Läuft die Haltezeit
# ausgerechnet dann ab, ist `onGraphChanged()` der Erste, der es bemerkt.
ABLAUF_IM_UMZUG = """
(opts) => {
  const view = window.kgView, cy = view.cy, cam = view.camera;
  let bester = null, meiste = -1;
  cy.nodes('.person').forEach((p) => {
    const n = p.neighborhood().nodes('.term').length;
    if (n > meiste) { meiste = n; bester = p; }
  });
  const fuenf = bester.neighborhood().nodes('.term').slice(0, 5);
  const gebiet = fuenf.union(fuenf.neighborhood().nodes('.person'));

  const echteUhr = performance.now.bind(performance);
  let uhr = echteUhr();
  performance.now = () => uhr;
  try {
    cam.setMinLabel(40);  // Birks Kalibrierung: 40/26 = 1,54 -- wie das alte 1,55
    cam.setMode('fit');
    cam.focusDream(gebiet);
    cam._dream.until = uhr + 100000;
    // Erst sauber im Traumgebiet ankommen.
    for (let i = 0; i < 400; i += 1) { uhr += 16; cam.step(0.016); }
    const vorher = cy.zoom();

    // Jetzt die Haltezeit ablaufen lassen, OHNE dass ein Frame läuft --
    // genau das tut der Umzug. Dann kommt der Graph-Push.
    uhr += 200000;
    cam.onGraphChanged();
    const nachPush = cy.zoom();

    // Und danach nimmt die Bildschleife den Betrieb wieder auf.
    const bilder = [];
    for (let i = 0; i < opts.frames; i += 1) {
      uhr += 16; cam.step(0.016);
      const p = cy.pan(), z = cy.zoom();
      bilder.push({z, mx: (cy.width() / 2 - p.x) / z, my: (cy.height() / 2 - p.y) / z});
    }
    return { vorher, nachPush, bilder };
  } finally { performance.now = echteUhr; }
}
"""


def test_ablauf_waehrend_eines_umzugs_wird_auch_gefahren(wand):  # noqa: F811
    """Läuft die Haltezeit ab, während kein Frame läuft, zählt der Graph-Push.

    `projection.js` setzt `camera.step()` während des Layout-Umzugs aus (2,5 s
    je Push, also rund ein Fünftel der Betriebszeit). Fällt der Ablauf der
    Haltezeit in dieses Fenster, ist `onGraphChanged()` die erste Stelle, die
    davon erfährt — und die rahmte im `fit`-Modus über `_frame()` hart auf das
    ganze Netz. Derselbe Sprung wie im Bildtakt, nur über einen anderen Weg.
    """
    ergebnis = wand.evaluate(ABLAUF_IM_UMZUG, {"frames": 500})

    sprung = abs(ergebnis["nachPush"] / ergebnis["vorher"] - 1) * 100
    assert sprung < MAX_ZOOM_PRO_FRAME, (
        f"der Graph-Push nach dem Ablauf reißt den Zoom um {sprung:.1f} % um "
        f"({ergebnis['vorher']:.4f} -> {ergebnis['nachPush']:.4f}) — der "
        f"Ablauf wird hier geschnitten statt gefahren"
    )

    zoom, mitte = _spruenge(ergebnis["bilder"])
    assert max(zoom) < MAX_ZOOM_PRO_FRAME, (
        f"nach dem Push springt der Zoom um {max(zoom):.3f} % in einem Frame"
    )
    assert max(mitte) < MAX_MITTE_PRO_FRAME, (
        f"nach dem Push springt die Bildmitte um {max(mitte):.1f} Modellpixel"
    )
    # Und das Netz kommt danach auch wirklich wieder ins Bild.
    weitester = min(b["z"] for b in ergebnis["bilder"])
    assert (ergebnis["vorher"] / weitester - 1) * 100 > 20, (
        "der Ausschnitt hat sich nach dem Ablauf nicht geweitet"
    )
