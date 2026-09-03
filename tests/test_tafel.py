"""Die Tafel: der eigene Bereich neben dem Netz (`frontend/static/tafel.js`).

🔴 WARUM ES SIE GIBT (Birk, 2026-09-02, abends): „Bei Einblendung von Zitaten
soll dafür ein eigener Bereich auf dem Monitor sein, wo das Netz nicht
angezeigt wird, da aktuell gehighlightete Knoten von dem Zitatfenster
überdeckt werden."

Der Fehler entstand am selben Tag: Seit die Nachbarschaft beim Antippen
aufleuchtet, lag die Zitatkarte ausgerechnet über dem, was sie erklärt. Die
Tafel löst das, indem das NETZ ausweicht statt überdeckt zu werden — und genau
das prüft der erste Test hier. Alles Weitere ist Inhalt.
"""

from __future__ import annotations

import pytest

GRAPH = {
    "version": 1,
    "generated_at": 1000.0,
    "max_terms": 99,
    "nodes": [
        {"id": "p1", "type": "person", "name": "Steffen", "portrait": "/p1.png",
         "created_at": 1.0, "hidden": False, "x": -300, "y": 0},
        {"id": "p2", "type": "person", "name": "Marlen", "portrait": "/p2.png",
         "created_at": 2.0, "hidden": False, "x": 300, "y": 0},
        {"id": "p3", "type": "person", "name": "Reza", "portrait": None,
         "created_at": 3.0, "hidden": False, "x": 0, "y": 300},
        {"id": "t1", "type": "term", "label": "Entrümpeln statt Neubau", "mentions": 3,
         "created_at": 4.0, "hidden": False, "x": 0, "y": -200,
         "verwandt": ["Systeme nutzen", "Bestand pflegen"]},
        {"id": "t2", "type": "term", "label": "Lehmbau", "mentions": 1,
         "created_at": 5.0, "hidden": False, "x": 200, "y": 200, "verwandt": []},
    ],
    "edges": [
        {"id": "e1", "source": "p1", "target": "t1",
         "evidence": "lieber im Keller aufräumen"},
        {"id": "e2", "source": "p2", "target": "t1",
         "evidence": "die Systeme nutzen, die wir schon haben"},
        {"id": "e3", "source": "p3", "target": "t1", "evidence": "einfacher machen"},
        {"id": "e4", "source": "p1", "target": "t2", "evidence": "auch mit Lehm"},
    ],
    "quotes": [{"id": "q1", "person_id": "p1", "text": "Lieber im Keller aufräumen."}],
    "widersprueche": [
        {
            "titel": "Sanierung als Hoffnung und als Bedrohung",
            "eine": {"begriff": "Sanierung maroder Gebäude", "beleg": "mehr sanierte Gebäude"},
            "andere": {"begriff": "Wohnungszwangssanierung", "beleg": "Menschen fliegen raus"},
        }
    ],
}


@pytest.fixture()
def wand(page, static_server):
    page.goto(f"{static_server}/frontend/projection.html?theme=f&deterministisch=1")
    page.wait_for_function("window.kgView !== undefined", timeout=30000)
    return page


def _fuettern(page):
    """Den Graphen in die Seite geben — über denselben Weg, den der SSE-Strom
    nimmt. Ohne echten Kern gibt es keinen Strom, also direkt.

    🔴 Auf die LAYOUTRUHE warten, nicht auf eine feste Zeit. Eine Migration
    ist eine Rechnung plus 2,5 s Gleitflug; wer vorher tippt, misst eine
    Kamera, die noch unterwegs ist. Mit `wait_for_timeout(300)` stand hier
    genau das: Die Tafel ging auf, während das Layout noch lief, die Kamera
    fasste auf die alte Breite (Pan 960 statt 643), und 229 px des Netzes
    lagen danach unter der Tafel — ein echter, aber seltener Fehler, den der
    Test als Dauerzustand meldete.

    🔴 AUCH `kgQuotes` FUELLEN, und das ist keine Vollstaendigkeitsgeste
    (Mutationsprobe, 2026-09-02): projection.html reicht jeden Graph-Push an
    BEIDE weiter. Fuellte der Test nur die Tafel, haette die Zitatkarte keine
    Zitate — und `test_wo_die_tafel_steht_blendet_sich_keine_karte...` waere
    gruen, weil nichts da ist, das erscheinen koennte, statt weil `stumm`
    wirkt. Genau so ist er zuerst durch die Mutation `if (true)` gerutscht.
    """
    page.evaluate(
        "(g) => { window.kgView.update(g, 99); window.__tafelDaten.setGraph(g);"
        "         window.kgQuotes.setGraph(g); }",
        GRAPH,
    )
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)


def test_ein_tipp_waehrend_des_layoutlaufs_fasst_trotzdem_richtig(page, static_server):
    """🔴 Der Fall, der den Fehler zeigte, als Test (2026-09-02).

    Ein neues Interview kommt an, während jemand tippt: Die Migration läuft
    (2,5 s Gleitflug), und die Kamera fasste mitten in der Bewegung — mit dem
    Pan der ALTEN Breite. 229 px des Netzes lagen danach unter der Tafel.

    An einer Ausstellungswand ist das kein Randfall: Interviews kommen alle
    paar Minuten, und getippt wird dauernd.
    """
    page.goto(f"{static_server}/frontend/projection.html?theme=f&deterministisch=1")
    page.wait_for_function("window.kgView !== undefined", timeout=30000)
    # Füttern und SOFORT tippen — ohne auf die Layoutruhe zu warten.
    page.evaluate(
        "(g) => { window.kgView.update(g, 99); window.__tafelDaten.setGraph(g); }", GRAPH
    )
    page.evaluate("() => window.kgView.cy.$id('t1').emit('tap')")
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)
    # Die Tafel fasst erst nach der Layoutruhe neu; dann noch der Handover.
    page.wait_for_timeout(7000)

    kante = page.evaluate("() => document.getElementById('tafel').getBoundingClientRect().left")
    rechts = page.evaluate("""() => Math.max(...window.kgView.cy.nodes().map(n =>
      n.renderedBoundingBox({includeLabels: true}).x2))""")
    assert rechts <= kante + 1, f"ein Knoten ragt {rechts - kante:.0f} px unter die Tafel"


def test_das_netz_weicht_aus_statt_ueberdeckt_zu_werden(wand):
    """🔴 Der Kern des Auftrags. Ein Zitat, das über dem hervorgehobenen Knoten
    liegt, verdeckt genau das, was es erklärt."""
    _fuettern(wand)
    vorher = wand.evaluate("() => document.getElementById('cy').getBoundingClientRect().width")

    wand.evaluate("() => window.kgView.cy.$id('t1').emit('tap')")
    wand.wait_for_timeout(700)
    nachher = wand.evaluate("() => document.getElementById('cy').getBoundingClientRect().width")
    tafel = wand.evaluate("() => document.getElementById('tafel').getBoundingClientRect()")

    assert nachher < vorher, f"das Netz ist nicht schmaler geworden: {vorher} -> {nachher}"
    # Die Tafel beginnt genau dort, wo das Netz aufhört — kein Überlappen.
    assert abs(tafel["left"] - nachher) < 2, (tafel["left"], nachher)


def test_kein_knoten_liegt_hinter_der_tafel(wand):
    """🔴 Der eigentliche Zweck, und die erste Fassung dieses Tests hat ihn
    NICHT geprüft (gefunden durch eine Mutationsprobe, 2026-09-02).

    Sie verglich `cy.width()` mit der DOM-Breite — aber Cytoscape liest die
    live aus dem Container, also stimmten die beiden auch mit
    auskommentiertem `cy.resize()` überein. Der Test war grün, während das
    Netz halb unter der Tafel lag.

    Geprüft wird deshalb, was der Besucher sieht: Nachdem die Kamera neu
    gefasst hat, muss JEDER Knoten links von der Tafelkante stehen. Genau das
    war der Auftrag — das Netz weicht aus, statt überdeckt zu werden.
    """
    _fuettern(wand)
    wand.evaluate("() => window.kgView.cy.$id('t1').emit('tap')")
    # 🔴 Lange genug warten, und das ist keine Formalie: Die Kamera fährt den
    # Übergang als HANDOVER — fünf Sekunden Cosinus, damit an der Wand nichts
    # springt (camera.js, Birks Wert vom 2026-08-30). 440 ms Aufgehen plus
    # 5 s Fahrt; eine frühere Messung trifft die Kamera mitten in der
    # Bewegung und meldet einen Fehler, den es nach dem Ankommen nicht gibt.
    wand.wait_for_timeout(6500)

    kante = wand.evaluate("() => document.getElementById('tafel').getBoundingClientRect().left")
    rechts = wand.evaluate("""() => Math.max(...window.kgView.cy.nodes().map(n => {
      const b = n.renderedBoundingBox({includeLabels: true});
      return b.x2;
    }))""")
    assert rechts <= kante + 1, (
        f"ein Knoten ragt {rechts - kante:.0f} px unter die Tafel"
    )


def test_ein_begriff_zeigt_alle_stimmen_mit_ihren_eigenen_worten(wand):
    """🔴 Die stärkste Information, die es gibt und die vorher niemand sah:
    dieselbe Sache in verschiedenen Worten."""
    _fuettern(wand)
    wand.evaluate("() => window.kgView.cy.$id('t1').emit('tap')")
    wand.wait_for_timeout(700)

    text = wand.evaluate("() => document.getElementById('tafel').textContent")
    assert "Entrümpeln statt Neubau" in text
    assert "Von 3 Menschen gesagt" in text
    for wort in ["lieber im Keller aufräumen", "die Systeme nutzen", "einfacher machen"]:
        assert wort in text, wort
    for name in ["Steffen", "Marlen", "Reza"]:
        assert name in text, name


def test_ein_begriff_zeigt_die_inhaltlich_verwandten(wand):
    """Die Verbindung, die der Graph NICHT ziehen kann: Er verbindet nur, was
    dieselben Menschen gesagt haben."""
    _fuettern(wand)
    wand.evaluate("() => window.kgView.cy.$id('t1').emit('tap')")
    wand.wait_for_timeout(700)

    marken = wand.eval_on_selector_all(".tafel-chip", "els => els.map(e => e.textContent)")
    assert marken == ["Systeme nutzen", "Bestand pflegen"], marken


def test_eine_person_zeigt_portrait_zitat_und_ihre_begriffe(wand):
    _fuettern(wand)
    wand.evaluate("() => window.kgView.cy.$id('p1').emit('tap')")
    wand.wait_for_timeout(700)

    text = wand.evaluate("() => document.getElementById('tafel').textContent")
    assert "Steffen" in text
    assert "Lieber im Keller aufräumen." in text
    assert "Entrümpeln statt Neubau" in text and "Lehmbau" in text
    assert wand.eval_on_selector_all(".tafel-portrait", "e => e.length") == 1


def test_teilt_themen_mit_nennt_die_naechsten_menschen(wand):
    """🔴 Das macht die soziale Nähe lesbar, die das Layout nur andeutet:
    Wer im Netz nebeneinander steht, tut das genau deswegen — aber niemand
    sieht, mit WEM und WORÜBER."""
    _fuettern(wand)
    wand.evaluate("() => window.kgView.cy.$id('p1').emit('tap')")
    wand.wait_for_timeout(700)

    nahe = wand.eval_on_selector_all(
        ".tafel-nahe-eintrag", "els => els.map(e => e.textContent)"
    )
    # p1 teilt „Entrümpeln statt Neubau" mit p2 und p3, sonst nichts.
    assert len(nahe) == 2, nahe
    assert any("Marlen" in e and "Entrümpeln" in e for e in nahe), nahe
    assert any("Reza" in e for e in nahe), nahe


def test_eine_person_ohne_portrait_bekommt_keinen_platzhalter(wand):
    """Wer sich gegen ein Foto entschieden hat, ist kein FEHLENDES Foto —
    dieselbe Regel wie am Netz (kein Avatar, kein Fragezeichen)."""
    _fuettern(wand)
    wand.evaluate("() => window.kgView.cy.$id('p3').emit('tap')")
    wand.wait_for_timeout(700)

    ohne = wand.eval_on_selector_all(".tafel-portrait.ohne-bild", "e => e.length")
    assert ohne == 1
    stil = wand.eval_on_selector(".tafel-portrait", "e => getComputedStyle(e).backgroundImage")
    assert stil == "none", stil


def test_der_ruhezustand_zeigt_die_widersprueche(wand):
    """Ohne Auswahl fasst die Tafel den TAG zusammen statt eine Person — und
    erklaert zugleich, wofuer der Bereich da ist.

    🔴 ZWEIMAL GEDREHT AN EINEM TAG (2026-09-03): mittags entfernt („in der
    idle ansicht soll keine seitenleiste da sein"), nachmittags zurueckgeholt
    („ich will das zurueckgestellte Widerspruch im Idle-Mode wieder
    hochholen"). Deaktiviert war nur die ANZEIGE — `kg/widerspruch.py` rechnete
    durchgehend weiter, deshalb stand der Block sofort wieder mit dem Stand des
    Tages da.
    """
    _fuettern(wand)
    wand.evaluate("() => window.kgView.cy.$id('p1').emit('tap')")
    wand.wait_for_timeout(500)
    wand.evaluate("() => window.kgView.cy.emit('tap')")
    wand.wait_for_timeout(700)

    text = wand.evaluate("() => document.getElementById('tafel').textContent")
    assert "Konträre Positionen NewBauhaus 2026" in text
    assert "Sanierung als Hoffnung und als Bedrohung" in text
    assert "Menschen fliegen raus" in text
    # Zwei Seiten nebeneinander: Ein Widerspruch ist eine Gegenueberstellung,
    # und die Form soll das sagen, bevor jemand liest.
    assert wand.eval_on_selector_all(".tafel-seite", "e => e.length") == 2


def test_ohne_widersprueche_geht_die_tafel_ganz_zu(wand):
    """Frueh am Tag gibt es keine — dann darf keine leere Flaeche stehenbleiben,
    die aussieht, als fehle etwas."""
    ohne = {**GRAPH, "widersprueche": []}
    wand.evaluate(
        "(g) => { window.kgView.update(g, 99); window.__tafelDaten.setGraph(g);"
        "         window.kgQuotes.setGraph(g); }",
        ohne,
    )
    wand.wait_for_timeout(300)
    wand.evaluate("() => window.kgView.cy.$id('p1').emit('tap')")
    wand.wait_for_timeout(500)
    wand.evaluate("() => window.kgView.cy.emit('tap')")
    wand.wait_for_timeout(900)

    assert wand.evaluate("() => window.__tafel.istOffen()") is False
    breite = wand.evaluate("() => document.getElementById('cy').getBoundingClientRect().width")
    fenster = wand.evaluate("() => window.innerWidth")
    assert abs(breite - fenster) < 2, (breite, fenster)


# --- Das grosse Netz: der Fall, den fuenf Knoten nicht zeigen ---------------

def _grosses_netz(knoten_paare: int = 36) -> dict:
    """Ein Netz in der Groesse der echten Wand, weit genug gespannt, dass die
    Kamera fahren MUSS.

    🔴 WOZU EIGENS GROSS: Bei den fuenf Knoten von `GRAPH` passt das ganze Netz
    lesbar ins Bild — `fahrtNoetig` ist falsch, die Wand zeigt immer alles, und
    „die Auswahl ist sichtbar" faellt mit „alles ist sichtbar" zusammen. Genau
    deshalb blieben die Tests oben gruen, waehrend an der Wand (gemessen
    2026-09-02: 76 Knoten) der angetippte Knoten bei x=1615 auf einer 1286 px
    breiten Flaeche lag, also ausserhalb. Erst ab dieser Groesse trennen sich
    die beiden Aussagen.
    """
    nodes, edges, quotes = [], [], []
    for i in range(knoten_paare):
        # Ein weiter Ring: Der Durchmesser ist das, was die Fahrt noetig macht.
        winkel = 6.28318 * i / knoten_paare
        import math
        rx, ry = 3600 * math.cos(winkel), 2400 * math.sin(winkel)
        nodes.append({"id": f"gp{i}", "type": "person", "name": f"Person {i}",
                      "portrait": "/p1.png", "created_at": float(i),
                      "hidden": False, "x": rx, "y": ry})
        nodes.append({"id": f"gt{i}", "type": "term", "label": f"Begriff {i}",
                      "mentions": 1 + i % 4, "created_at": float(i),
                      "hidden": False, "x": rx * 0.82, "y": ry * 0.82, "verwandt": []})
        edges.append({"id": f"ge{i}", "source": f"gp{i}", "target": f"gt{i}",
                      "evidence": f"Belegstelle {i}"})
        quotes.append({"id": f"gq{i}", "person_id": f"gp{i}", "text": f"Satz {i}."})
    # Eine Klammer quer durchs Netz, damit nicht lauter Inseln entstehen.
    for i in range(0, knoten_paare, 4):
        edges.append({"id": f"gx{i}", "source": f"gp{i}", "target": "gt0",
                      "evidence": f"Querbeleg {i}"})
    return {"version": 1, "generated_at": 1000.0, "max_terms": 99,
            "nodes": nodes, "edges": edges, "quotes": quotes, "widersprueche": []}


def _tippen_und_ruhen(wand, knoten_id: str, ruhe_ms: int = 2500) -> None:
    """Antippen wie eine Hand: erst den manuellen Modus, dann der Tipp.

    🔴 `setMode('manual')` GEHOERT DAZU und ist keine Testkruecke: An der Wand
    setzt `touch-autonomy.js` bei jedem `pointerdown` genau das (gemessen am
    laufenden Kern: nach einer echten Beruehrung steht der Modus auf 'manual').
    Ohne diese Zeile liefe der Test im Modus 'fit', und der rahmt WOERTLICH die
    Vollansicht — dann ist jeder Knoten im Bild, egal was die Tafel tut, und
    der Test koennte nichts mehr zeigen.

    🔴 `ruhe_ms` IST DER TEST, nicht nur eine Pause (Mutationsprobe,
    2026-09-02): Mit 2500 ms ueberlebte die Mutation `if (false)` — also der
    Rueckbau auf `uebersicht()` — unbemerkt. Der Grund ist die Reihenfolge:
    `uebersicht()` setzt `fit`, und das rahmt im ersten Moment noch das ganze
    Netz; erst die Fahrt danach traegt den Knoten aus dem Bild (gemessen am
    laufenden Kern: bei 2,5 s noch drin, bei 8,5 s draussen, 1 von 5 Nachbarn).
    Wer frueh misst, sieht den Fehler nicht.

    Die Frage ist ohnehin nicht „steht der Knoten im ersten Moment im Bild",
    sondern „bleibt er dort, solange jemand die Tafel liest" — und das sind an
    einer Ausstellungswand eher dreissig Sekunden als drei.
    """
    wand.evaluate("() => window.kgView.camera.setMode('manual')")
    wand.evaluate("(id) => window.kgView.cy.$id(id).emit('tap')", knoten_id)
    wand.wait_for_timeout(ruhe_ms)


def _sichtbarkeit(wand, knoten_id: str) -> dict:
    return wand.evaluate("""(id) => {
      const cy = window.kgView.cy, n = cy.getElementById(id);
      const w = cy.width(), h = cy.height();
      const drin = (x) => { const b = x.renderedBoundingBox({includeLabels: true});
        return b.x1 >= 0 && b.x2 <= w && b.y1 >= 0 && b.y2 <= h; };
      const nah = n.closedNeighborhood().nodes();
      return {drin: drin(n), sichtbar: nah.filter(drin).length, nachbarn: nah.length,
              modus: window.kgView.camera.mode, fahrt: window.kgView.camera.fahrtNoetig};
    }""", knoten_id)


@pytest.fixture()
def grosse_wand(page, static_server):
    page.goto(f"{static_server}/frontend/projection.html?theme=f&deterministisch=1")
    page.wait_for_function("window.kgView !== undefined", timeout=30000)
    # 🔴 Der kalibrierte Wert der Wand (aus `/api/state` des laufenden Kerns
    # gelesen, 2026-09-02: `camera_min_label` = 14). Ohne Kern laedt die Seite
    # ihren Standardwert, und der ist so klein, dass selbst dieses Netz noch
    # lesbar ins Bild passt — dann faehrt die Kamera nicht, und die Tests
    # darunter pruefen nichts. Die Schwelle GEHOERT also zum Aufbau.
    page.evaluate("() => window.kgView.camera.setMinLabel(14)")
    netz = _grosses_netz()
    page.evaluate(
        "(g) => { window.kgView.update(g, 99); window.__tafelDaten.setGraph(g); }", netz
    )
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)
    # 🔴 Der Operator-Modus der Wand (aus `/api/state`, 2026-09-02:
    # `camera_mode` = 'pan') — und er GEHOERT hierher, nicht nur der Echtheit
    # wegen: `_fahrtZustandPruefen()` laeuft bewusst nur in `pan` (camera.js:
    # in `fit` zeigt die Wand ohnehin alles, in `manual` fasst sie den Viewport
    # gar nicht an). Ohne diese Zeile bliebe `fahrtNoetig` auf dem Wert vom
    # LEEREN Graphen stehen, also falsch, und der Test darunter faellt zu
    # Recht. Erst das Betreten von 'pan' bewertet die Fahrt neu.
    page.evaluate("() => window.kgView.camera.setMode('pan')")
    page.wait_for_timeout(200)
    return page


@pytest.fixture()
def beruehrbare_wand(page, static_server):
    """Dasselbe grosse Netz, aber auf der Flaeche MIT Bedienung.

    🔴 `touch=1` ist hier kein Detail: Ohne diesen Schalter baut die Seite gar
    keine `touch-autonomy` auf (projection.html), es gibt also weder einen
    Rueckfall noch ein `window.__autonomy` — und der Fehler, den die Tests
    darunter meinen, kann dort nicht entstehen. Auf einer Wand ohne Beruehrung
    waehlt niemand etwas aus.
    """
    page.goto(f"{static_server}/frontend/projection.html?theme=f&touch=1&deterministisch=1")
    page.wait_for_function("window.kgView !== undefined", timeout=30000)
    page.evaluate("() => window.kgView.camera.setMinLabel(14)")
    page.evaluate(
        "(g) => { window.kgView.update(g, 99); window.__tafelDaten.setGraph(g); }",
        _grosses_netz(),
    )
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)
    page.evaluate("() => window.kgView.camera.setMode('pan')")
    page.wait_for_timeout(200)
    return page


def test_im_grossen_netz_muss_die_kamera_ueberhaupt_fahren(grosse_wand):
    """Die Vorbedingung aller folgenden Tests — sonst pruefen sie nichts.

    Faellt dieser Test, ist das Testnetz zu klein oder zu eng geworden: Dann
    passt wieder alles ins Bild, und „die Auswahl ist sichtbar" waere keine
    Aussage mehr ueber die Tafel, sondern nur ueber die Groesse des Graphen.
    """
    assert grosse_wand.evaluate("() => window.kgView.camera.fahrtNoetig") is True


def test_der_angetippte_knoten_bleibt_im_bild(grosse_wand):
    """🔴 DER FEHLER, DEN DIE WAND HATTE (gemessen 2026-09-02, 76 Knoten).

    `neuFassen()` rief `uebersicht()` — also das GANZE Netz. Passt das nicht
    lesbar ins Feld, zeigt die Wand einen Ausschnitt, und der angetippte
    Knoten lag gemessen bei x=1615 auf 1286 px Flaeche: Die Tafel erklaerte
    einen Knoten, den niemand sehen konnte. Genau das Gegenteil des Auftrags.

    🔴 EHRLICH VERMERKT (Mutationsprobe, 2026-09-02): Dieser Test faengt den
    Rueckbau auf `uebersicht()` NICHT — er blieb gruen, auch nach zwoelf
    Sekunden Wartezeit. Der Grund liegt im Aufbau: Ohne Kern gibt es keinen
    `state`-Push, die Wand bleibt nach `uebersicht()` in der Vollansicht, und
    dort ist ohnehin jeder Knoten im Bild. An der Wand kam der Push, die Fahrt
    lief an, und der Knoten war weg.

    Er steht trotzdem hier, weil er die ANFORDERUNG festhaelt und jede kuenftige
    Aenderung an ihr messen wird. Bewiesen wird der Fix von den drei Tests
    darunter: `..._fasst_auf_die_auswahl_und_nicht_auf_das_ganze_netz` (die
    Entscheidung selbst), `..._aendert_den_modus_nicht` und
    `..._ins_leere_tippen...` — die fallen bei der Mutation zuverlaessig.
    """
    _tippen_und_ruhen(grosse_wand, "gt9", ruhe_ms=12000)
    s = _sichtbarkeit(grosse_wand, "gt9")
    assert s["drin"], f"der angetippte Knoten liegt ausserhalb des Feldes: {s}"


def test_die_hervorgehobene_nachbarschaft_ist_vollstaendig_zu_sehen(grosse_wand):
    """Was leuchtet, muss im Bild sein.

    `nachbarschaft.js` hebt die geschlossene Nachbarschaft hervor, und die
    Tafel erklaert sie — beide meinen dieselbe Menge. Waere nur der Knoten
    selbst gefasst, stuenden seine Verbindungen halb ausserhalb, und der Blick
    von der Tafel zurueck ins Netz ginge ins Leere.

    Dieselbe Grenze wie beim Test darueber: haelt die Anforderung fest, faengt
    den Rueckbau aber nicht allein.
    """
    _tippen_und_ruhen(grosse_wand, "gt9", ruhe_ms=12000)
    s = _sichtbarkeit(grosse_wand, "gt9")
    assert s["sichtbar"] == s["nachbarn"], (
        f"nur {s['sichtbar']} von {s['nachbarn']} hervorgehobenen Knoten sind im Bild"
    )


def test_der_zweite_tipp_fasst_auch_nach(grosse_wand):
    """Wer einmal tippt, tippt weiter — und dann aendert sich die BREITE nicht
    mehr.

    🔴 Der Zweig, den das prueft, fehlte zuerst: `oeffne()` liess das Nachfassen
    `breiteSetzen()` erledigen, und das laeuft nur beim Aufgehen. Beim zweiten
    Tipp blieb die Kamera also beim ERSTEN Knoten stehen, waehrend die Tafel
    schon den zweiten erklaerte. An einer Ausstellungswand ist das der
    Normalfall, nicht der Randfall.
    """
    _tippen_und_ruhen(grosse_wand, "gt9")
    ferner = "gt27"  # auf der gegenueberliegenden Seite des Rings
    _tippen_und_ruhen(grosse_wand, ferner, ruhe_ms=12000)
    s = _sichtbarkeit(grosse_wand, ferner)
    assert s["drin"], f"nach dem zweiten Tipp steht die Kamera noch beim ersten: {s}"


def test_der_tipp_aendert_den_modus_nicht(grosse_wand):
    """`focus()` statt `uebersicht()` — und das ist der Unterschied, an dem der
    Fehler sichtbar wurde.

    `uebersicht()` setzt `setMode('fit')` und nimmt der Wand damit still die
    Bedienbarkeit, die der Operator eingestellt hat. Beim Messen am laufenden
    Kern war genau dieser Moduswechsel die Spur: ohne Fix stand danach 'fit',
    mit Fix bleibt 'manual'.
    """
    _tippen_und_ruhen(grosse_wand, "gt9", ruhe_ms=12000)
    assert _sichtbarkeit(grosse_wand, "gt9")["modus"] == "manual"


def test_ins_leere_tippen_gibt_das_ganze_netz_zurueck(grosse_wand):
    """Der Weg zurueck: Ohne Auswahl gilt wieder die Uebersicht.

    Sonst bliebe die Wand fuer immer auf dem letzten angetippten Knoten
    stehen — eine Ausstellungswand, die nach einer Beruehrung nie wieder das
    Ganze zeigt.
    """
    _tippen_und_ruhen(grosse_wand, "gt9")
    eng = grosse_wand.evaluate("() => window.kgView.cy.zoom()")
    grosse_wand.evaluate("() => window.kgView.cy.emit('tap')")
    grosse_wand.wait_for_timeout(7000)
    weit = grosse_wand.evaluate("() => window.kgView.cy.zoom()")
    assert weit < eng, f"die Wand ist nicht wieder herausgefahren: {eng} -> {weit}"


def test_die_tafel_fasst_auf_die_auswahl_und_nicht_auf_das_ganze_netz(grosse_wand):
    """🔴 DER BEWEIS DES FIXES — die Entscheidung selbst, nicht ihre Folge.

    Die beiden Tests oben halten fest, was der Besucher sehen soll, koennen den
    Rueckbau aber nicht fangen: Ohne Kern bleibt die Wand nach `uebersicht()`
    in der Vollansicht, und dort ist ohnehin alles im Bild (Mutationsprobe,
    2026-09-02). Hier wird deshalb gemessen, WORAUF die Tafel die Kamera
    richtet — und das ist der Unterschied zwischen dem Fehler und dem Fix:

        vorher:  camera.uebersicht()                  -> das ganze Netz
        nachher: camera.focus(closedNeighborhood())   -> die Auswahl

    Ein Spion auf beiden Methoden, weil kein gerendertes Mass die beiden im
    Testaufbau auseinanderhaelt. Er prueft zusaetzlich die GROESSE der
    uebergebenen Menge: `focus(alleKnoten)` waere derselbe Fehler mit dem
    richtigen Methodennamen.
    """
    grosse_wand.evaluate("""() => {
      const c = window.kgView.camera;
      window.__spion = {focus: [], uebersicht: 0};
      const f = c.focus.bind(c), u = c.uebersicht.bind(c);
      c.focus = (eles, p) => { window.__spion.focus.push(eles ? eles.length : 0); return f(eles, p); };
      c.uebersicht = () => { window.__spion.uebersicht += 1; return u(); };
    }""")
    _tippen_und_ruhen(grosse_wand, "gt9")
    spion = grosse_wand.evaluate("() => window.__spion")
    erwartet = grosse_wand.evaluate(
        "() => window.kgView.cy.$id('gt9').closedNeighborhood().length"
    )

    assert spion["uebersicht"] == 0, (
        "die Tafel hat auf das ganze Netz gefasst statt auf die Auswahl"
    )
    assert spion["focus"], "die Tafel hat die Kamera gar nicht gerichtet"
    assert spion["focus"][-1] == erwartet, (
        f"gefasst wurde auf {spion['focus'][-1]} Elemente, die Nachbarschaft "
        f"hat {erwartet} — gefasst werden soll genau das, was auch leuchtet"
    )


def test_beim_rueckfall_bleibt_keine_auswahl_stehen(beruehrbare_wand):
    """🔴 Derselbe Fehler, nur zeitversetzt (2026-09-02).

    Nach 30 s ohne Beruehrung nimmt die Wand sich zurueck (`touch-autonomy.js`)
    und faehrt wieder von selbst. Eine Tafel, die dann noch einen bestimmten
    Knoten erklaert, zeigt binnen Sekunden auf etwas, das aus dem Bild gefahren
    ist — genau die Trennung, gegen die diese Datei gebaut ist: Was erklaert
    wird, muss zu sehen sein.

    Das grosse Netz hat keine Widersprueche, also geht die Tafel ganz zu. Mit
    Widerspruechen tritt der Ruhezustand an die Stelle der Auswahl; der meint
    den ganzen Tag und haelt eine fahrende Kamera aus.
    """
    _tippen_und_ruhen(beruehrbare_wand, "gt9")
    assert beruehrbare_wand.evaluate("() => window.__tafel.istOffen()") is True

    beruehrbare_wand.evaluate("() => window.__autonomy.releaseNow()")
    beruehrbare_wand.wait_for_timeout(700)

    assert beruehrbare_wand.evaluate("() => window.__tafel.istOffen()") is False, (
        "die Auswahl steht noch, waehrend die Wand schon wieder faehrt"
    )


def test_beim_rueckfall_tritt_der_ruhezustand_an_die_stelle_der_auswahl(page, static_server):
    """Gibt es Widersprueche, geht die Tafel nicht zu, sondern wechselt.

    Eine Flaeche, die alle halbe Minute auf- und zuklappt, waere Unruhe an
    einer Wand, die sonst ruhig steht — und der Ruhezustand ist ohnehin das,
    was ohne Auswahl dort stehen soll.
    """
    page.goto(f"{static_server}/frontend/projection.html?theme=f&touch=1&deterministisch=1")
    page.wait_for_function("window.kgView !== undefined", timeout=30000)
    _fuettern(page)
    page.evaluate("() => window.kgView.cy.$id('p1').emit('tap')")
    page.wait_for_timeout(700)
    assert page.eval_on_selector("#tafel h2", "e => e.textContent") == "Steffen"

    page.evaluate("() => window.__autonomy.releaseNow()")
    page.wait_for_timeout(900)

    assert page.evaluate("() => window.__tafel.istOffen()") is True, (
        "die Tafel geht ganz zu, statt in den Ruhezustand zu wechseln"
    )
    assert page.eval_on_selector("#tafel h2", "e => e.textContent") == "Konträre Positionen NewBauhaus 2026"


# --- Die Weiche: Tafel ODER Karte, nie beides ------------------------------

def _klick(page, knoten_id: str) -> None:
    """Dort klicken, wo der Knoten gezeichnet ist — ein echtes Zeigereignis.

    🔴 BEWUSST NICHT `emit('tap')`, und das ist hier keine Stiltreue: Die
    Zitatkarte wird nach einem synthetischen Tipp aus einem TIMER wieder
    versteckt (gemessen 2026-09-02: `show()` setzt sichtbar, Millisekunden
    spaeter setzt `hide()` ohne Aufrufer im Stack zurueck). Ein Test darauf ist
    nicht nur unzuverlaessig, sondern misst etwas anderes als die Wand tut.
    `tests/test_quote_overlay.py` haelt denselben Grund fest — dort bringt der
    synthetische Tipp diesen Chromium-Build sogar zum Absturz.

    Ein Finger auf dem iiyama ist ohnehin genau das hier.
    """
    pos = page.evaluate(
        "(id) => { const p = window.kgView.cy.getElementById(id).renderedPosition();"
        " return {x: p.x, y: p.y}; }",
        knoten_id,
    )
    page.mouse.click(pos["x"], pos["y"])
    page.wait_for_timeout(700)


def test_wo_die_tafel_steht_blendet_sich_keine_karte_ueber_das_netz(wand):
    """🔴 GEFUNDEN AM GERENDERTEN BILD (2026-09-02), nicht von einem Test.

    Die Option `stumm` war in `quote-overlay.js` deklariert und wurde von
    projection.html auch gesetzt — aber nirgends gelesen. Die Karte hoerte also
    weiter auf Tipps mit, und beim Antippen standen BEIDE da: die Tafel rechts
    und die Zitatkarte quer ueber dem Netz, beide zum selben Knoten.

    Damit war der Auftrag genau nicht erfuellt: „bei einblendung von zitaten
    soll dafuer ein eigener bereich auf dem monitor sein, da aktuell
    gehighlightete Knoten von dem Zitatfenster ueberdeckt werden."

    Ein Fehler, den nur ein Blick auf das Bild zeigt — und deshalb steht er ab
    jetzt hier.
    """
    _fuettern(wand)
    _klick(wand, "p1")

    assert wand.eval_on_selector("#tafel h2", "e => e.textContent") == "Steffen"
    assert wand.evaluate("window.kgQuotes.visible") is False, (
        "die Zitatkarte liegt trotz Tafel wieder ueber dem Netz"
    )


def test_ohne_tafel_bleibt_die_karte_der_weg_zum_zitat(page, static_server):
    """Die Gegenrichtung, und sie ist der wichtigere Teil des Tests.

    Im Plenarsaal gibt es keine Tafel — dort IST die Karte die Zitatanzeige.
    Wer `stumm` zu breit setzt, nimmt dieser Flaeche ihre einzige Moeglichkeit,
    ein Zitat zu zeigen, und niemand merkt es, weil auf der Wand alles stimmt.
    """
    page.goto(f"{static_server}/frontend/projection.html?theme=f&plenum=1&deterministisch=1")
    page.wait_for_function("window.kgView !== undefined", timeout=30000)
    page.evaluate(
        "(g) => { window.kgView.update(g, 99); window.kgQuotes.setGraph(g); }", GRAPH
    )
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)
    _klick(page, "p1")

    assert page.evaluate("window.kgQuotes.visible") is True, (
        "im Plenarsaal zeigt niemand mehr ein Zitat"
    )
    assert page.eval_on_selector(".quote-text", "e => e.textContent").startswith(
        "Lieber im Keller"
    )


# --- Lesbarkeit: die Grenze, auf die die Wand kalibriert ist ----------------

def test_nichts_auf_der_tafel_steht_unter_der_grenze_der_wand(wand):
    """🔴 GEMESSEN AM LAUFENDEN KERN (2026-09-02), nicht geschaetzt.

    Die Wand ist auf `camera_min_label` = 14 kalibriert — das ist Birks Wert
    dafuer, wie klein Schrift auf dieser Flaeche werden darf, bevor sie keine
    Schrift mehr ist. Ihre Knoten standen damit bei 14,6 px auf dem Schirm.

    Die Tafel daneben stand bei 6,8 px (Belegstellen) und 5,2 px
    (Abschnittsmarken): weniger als die Haelfte, auf derselben Flaeche, aus
    demselben Abstand gelesen. Die Ursache war dieselbe wie am 2026-09-02 bei
    der Zitatkarte — alles hing an `--quote-scale`, und der steht auf 0,4, weil
    die KARTE zu viel Flaeche nahm. Die Tafel nimmt keine: sie hat ihre eigene.

    Der Test prueft die GERECHNETE Groesse im Browser, nicht die Regel im
    Stylesheet. Nur so faellt er auch, wenn jemand die Regler verstellt oder
    eine neue Regel dazwischenschiebt.
    """
    GRENZE = 14.0
    _fuettern(wand)
    wand.evaluate("() => window.kgView.cy.$id('p1').emit('tap')")
    wand.wait_for_timeout(700)

    zu_klein = wand.evaluate("""(grenze) => {
      const raus = [];
      for (const e of document.querySelectorAll('#tafel *')) {
        if (!e.textContent.trim()) continue;          // Bilder und leere Huellen
        const px = parseFloat(getComputedStyle(e).fontSize);
        if (px < grenze) raus.push([e.className || e.tagName, Math.round(px * 10) / 10]);
      }
      return raus;
    }""", GRENZE)

    assert not zu_klein, (
        f"unter {GRENZE} px und damit unter der Lesbarkeitsgrenze der Wand: {zu_klein}"
    )


def test_auch_der_ruhezustand_bleibt_lesbar(wand):
    """Die Widersprueche stehen am laengsten da — sie sind der Normalzustand
    der Flaeche, wenn niemand tippt."""
    GRENZE = 14.0
    _fuettern(wand)
    assert wand.evaluate("() => window.__tafel.zeigeWidersprueche()") is True
    wand.wait_for_timeout(700)

    zu_klein = wand.evaluate("""(grenze) => {
      const raus = [];
      for (const e of document.querySelectorAll('#tafel *')) {
        if (!e.textContent.trim()) continue;
        const px = parseFloat(getComputedStyle(e).fontSize);
        if (px < grenze) raus.push([e.className || e.tagName, Math.round(px * 10) / 10]);
      }
      return raus;
    }""", GRENZE)

    assert not zu_klein, f"im Ruhezustand unter {GRENZE} px: {zu_klein}"


def test_die_tafel_folgt_dem_schriftregler_und_nicht_dem_flaechenregler(wand):
    """🔴 Die Entscheidung selbst, damit sie nicht unbemerkt zurueckfaellt.

    Zwei Regler, weil es zwei Fragen sind (base.css, Birk am 2026-09-02): Wie
    viel FLAECHE darf eine Einblendung nehmen (`--quote-scale`), und wie gross
    muss der TEXT sein, damit man ihn von dort liest, wo man steht
    (`--quote-schrift`). Wer die Karte kleiner stellt, will selten auch
    schlechter lesen.

    Gemessen wird an der Wirkung: Der Flaechenregler allein darf die Schrift
    der Tafel nicht mehr veraendern.
    """
    _fuettern(wand)
    wand.evaluate("() => window.kgView.cy.$id('p1').emit('tap')")
    wand.wait_for_timeout(700)
    vorher = wand.eval_on_selector("#tafel .tafel-zitat", "e => getComputedStyle(e).fontSize")

    wand.evaluate("() => document.documentElement.style.setProperty('--quote-scale', '0.1')")
    wand.wait_for_timeout(200)
    nachher = wand.eval_on_selector("#tafel .tafel-zitat", "e => getComputedStyle(e).fontSize")
    assert nachher == vorher, (
        f"der Flaechenregler zieht die Schrift mit: {vorher} -> {nachher}"
    )

    wand.evaluate("() => document.documentElement.style.setProperty('--quote-schrift', '1.6')")
    wand.wait_for_timeout(200)
    groesser = wand.eval_on_selector("#tafel .tafel-zitat", "e => getComputedStyle(e).fontSize")
    assert parse_px(groesser) > parse_px(vorher), (
        f"der Schriftregler wirkt nicht: {vorher} -> {groesser}"
    )


def parse_px(wert: str) -> float:
    return float(wert.removesuffix("px"))


# --- Neue Interviews, waehrend jemand liest --------------------------------

def _spaeter() -> dict:
    """Der Graph, nachdem ein weiteres Interview gelaufen ist.

    Drei Dinge auf einmal, weil sie an der Wand auch zusammen kommen: eine neue
    Person, ein neuer Begriff, und p1 (dessen Tafel offen steht) haengt selbst
    am neuen Begriff und teilt ein Thema mit der neuen Person.
    """
    import copy
    g = copy.deepcopy(GRAPH)
    g["nodes"] += [
        {"id": "p9", "type": "person", "name": "Neu Angekommen", "portrait": "/p9.png",
         "created_at": 9.0, "hidden": False, "x": 400, "y": -300},
        {"id": "t9", "type": "term", "label": "Ganz neuer Begriff", "mentions": 1,
         "created_at": 9.0, "hidden": False, "x": 300, "y": -350, "verwandt": []},
    ]
    g["edges"] += [
        {"id": "e9", "source": "p9", "target": "t9", "evidence": "was ganz Neues"},
        {"id": "e10", "source": "p1", "target": "t9", "evidence": "sagt Steffen auch"},
        {"id": "e11", "source": "p9", "target": "t1", "evidence": "teilt ein Thema"},
    ]
    return g


def _nachschub(page, graph: dict) -> None:
    """Ein Graph-Push auf dem Weg, den projection.html nimmt — einschliesslich
    `tafel.aktualisiere()`. Ohne diesen letzten Schritt misst der Test die
    Verdrahtung nicht mit; die prueft
    `test_die_seite_zieht_die_tafel_bei_jedem_graphen_nach`."""
    page.evaluate(
        "(g) => { window.kgView.update(g, 99); window.__tafelDaten.setGraph(g);"
        "         window.kgQuotes.setGraph(g); window.__tafel.aktualisiere(); }",
        graph,
    )
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)
    page.wait_for_timeout(800)


def test_ein_neues_interview_erreicht_die_offene_tafel(wand):
    """🔴 BIRK, 2026-09-03: „hast du geprueft, dass es mit neu hinzukommenden
    interviews auch alles richtig einsortiert und auch die zusatzinfo pro
    knoten in der seitenleiste aktualisiert?"

    Hatte ich nicht — und beim Nachmessen stand genau der Fehler da: Der Graph
    wuchs von 5 auf 7 Knoten, die offene Tafel blieb unveraendert stehen.
    `oeffne()` lief nur beim Antippen.

    An einer Wand, an der alle paar Minuten ein Interview ankommt und Menschen
    minutenlang lesen, ist das kein Randfall.
    """
    _fuettern(wand)
    wand.evaluate("() => window.kgView.cy.$id('p1').emit('tap')")
    wand.wait_for_timeout(800)
    vorher = wand.eval_on_selector_all("#tafel > div > ul li b", "e => e.map(x => x.textContent)")
    assert "Ganz neuer Begriff" not in vorher

    _nachschub(wand, _spaeter())

    nachher = wand.eval_on_selector_all("#tafel > div > ul li b", "e => e.map(x => x.textContent)")
    assert "Ganz neuer Begriff" in nachher, (
        f"der neue Begriff erreicht die offene Tafel nicht: {nachher}"
    )


def test_teilt_themen_mit_waechst_mit(wand):
    """Die Zusatzinfo pro Knoten — nicht nur die eigenen Begriffe.

    „Teilt Themen mit" wird aus dem GANZEN Graphen berechnet: Wer neu dazukommt
    und ein Thema mit der gezeigten Person teilt, gehoert dort hin. Genau das
    blieb vorher stehen.
    """
    _fuettern(wand)
    wand.evaluate("() => window.kgView.cy.$id('p1').emit('tap')")
    wand.wait_for_timeout(800)
    _nachschub(wand, _spaeter())

    namen = wand.eval_on_selector_all(".tafel-nahe-text b", "e => e.map(x => x.textContent)")
    assert "Neu Angekommen" in namen, f"die neue Person fehlt bei „Teilt Themen mit\": {namen}"


def test_ein_begriff_bekommt_die_neue_stimme_dazu(wand):
    """Dieselbe Frage von der anderen Seite: Steht ein BEGRIFF offen und sagt
    jemand Neues dasselbe, gehoert die Stimme dazu — das ist der eigentliche
    Gewinn dieser Flaeche."""
    _fuettern(wand)
    wand.evaluate("() => window.kgView.cy.$id('t1').emit('tap')")
    wand.wait_for_timeout(800)
    vorher = wand.eval_on_selector_all(".tafel-stimmen li", "e => e.length")

    _nachschub(wand, _spaeter())

    nachher = wand.eval_on_selector_all(".tafel-stimmen li", "e => e.length")
    assert nachher == vorher + 1, (
        f"die neue Stimme fehlt am offenen Begriff: {vorher} -> {nachher}"
    )
    namen = wand.eval_on_selector_all(".tafel-stimmen li b", "e => e.map(x => x.textContent)")
    assert "Neu Angekommen" in namen, namen


def test_beim_nachziehen_bleibt_die_rollposition(wand):
    """🔴 Wer liest, soll nicht an den Anfang zurueckgeworfen werden.

    Ein Graph-Push kommt an der Wand alle paar Sekunden. Wuerde jeder davon die
    Tafel an den Anfang scrollen, waere sie fuer einen langen Text unbenutzbar
    — und lange Texte sind genau das, wofuer sie gebaut ist (Birk: „wenn ich
    auf ein Note klicke und die ganzen Zitate sehe, muss das scrollbar sein").
    """
    _fuettern(wand)
    wand.evaluate("() => window.kgView.cy.$id('p1').emit('tap')")
    wand.wait_for_timeout(800)
    # Weit genug herunterrollen, dass ein Ruecksprung auffiele. Bleibt der
    # Inhalt kuerzer als die Flaeche, klemmt der Browser auf 0 — dann prueft
    # dieser Test nichts, und das soll er sagen.
    wand.evaluate("() => { document.getElementById('tafel-inhalt').scrollTop = 400; }")
    wand.wait_for_timeout(200)
    stand = wand.evaluate("() => document.getElementById('tafel-inhalt').scrollTop")
    if stand == 0:
        pytest.skip("Inhalt passt ohne Rollen auf die Flaeche — nichts zu pruefen")

    _nachschub(wand, _spaeter())

    danach = wand.evaluate("() => document.getElementById('tafel-inhalt').scrollTop")
    assert danach == stand, f"die Tafel springt beim Nachziehen an den Anfang: {stand} -> {danach}"


def test_beim_nachziehen_faehrt_die_kamera_nicht(wand):
    """Ein Graph-Push darf niemandem das Bild wegziehen, waehrend er liest.

    Das Nachfassen gehoert zum Antippen (dort waehlt jemand aus), nicht zum
    Zugang eines Interviews.
    """
    _fuettern(wand)
    wand.evaluate("() => window.kgView.cy.$id('p1').emit('tap')")
    wand.wait_for_timeout(2500)
    wand.evaluate("""() => {
      const c = window.kgView.camera;
      window.__spion = {focus: 0, uebersicht: 0};
      const f = c.focus.bind(c), u = c.uebersicht.bind(c);
      c.focus = (e, p) => { window.__spion.focus += 1; return f(e, p); };
      c.uebersicht = () => { window.__spion.uebersicht += 1; return u(); };
    }""")

    _nachschub(wand, _spaeter())

    spion = wand.evaluate("() => window.__spion")
    assert spion == {"focus": 0, "uebersicht": 0}, (
        f"der Graph-Push zieht die Kamera mit: {spion}"
    )


def test_ein_verschwundener_knoten_schliesst_die_tafel(wand):
    """🔴 Begriffe werden automatisch zusammengelegt (`fold_term`, kg/store.py).

    Steht ausgerechnet der offen, den es nach dem naechsten Interview nicht mehr
    gibt, waere Stehenbleiben das Falsche: Die Tafel erklaerte dann einen
    Knoten, den das Netz daneben nicht mehr zeigt.
    """
    _fuettern(wand)
    wand.evaluate("() => window.kgView.cy.$id('t2').emit('tap')")
    wand.wait_for_timeout(800)
    assert wand.evaluate("() => window.__tafel.istOffen()") is True

    ohne_t2 = {
        **GRAPH,
        "nodes": [n for n in GRAPH["nodes"] if n["id"] != "t2"],
        "edges": [e for e in GRAPH["edges"] if e["target"] != "t2"],
    }
    _nachschub(wand, ohne_t2)

    assert wand.evaluate("() => window.__tafel.istOffen()") is False, (
        "die Tafel erklaert einen Knoten weiter, den es nicht mehr gibt"
    )


def test_die_seite_zieht_die_tafel_bei_jedem_graphen_nach(wand):
    """Die VERDRAHTUNG, und sie ist der Teil, der zuerst fehlte.

    Die Tafel kann noch so gut nachziehen — wenn projection.html sie beim
    Graph-Push nicht ruft, passiert nichts. Genau so stand es beim ersten
    Messen da (2026-09-03): `aktualisiere()` war gebaut und wurde nirgends
    gerufen.

    Geprueft wird ueber den Aufruf, den die Seite selbst tut, mit einem Spion
    auf der Tafel — der SSE-Strom laesst sich ohne Kern nicht ausloesen.
    """
    quelle = wand.evaluate(
        "() => fetch('projection.html').then(r => r.text())"
    )
    assert "tafel.aktualisiere()" in quelle, (
        "projection.html ruft die Tafel beim Graph-Push nicht nach"
    )
    # Und der Aufruf steht im Graph-Zweig, nicht irgendwo.
    zweig = quelle.split("tafelDaten.setGraph(payload.graph);")[1][:300]
    assert "tafel.aktualisiere()" in zweig, (
        "der Aufruf steht nicht im Graph-Zweig des SSE-Stroms"
    )


def test_eine_person_ohne_namen_bekommt_trotzdem_eine_tafel(wand):
    """🔴 Die Falle beim Fix von oben (2026-09-03).

    „Nicht mehr im Graphen" liefert seit heute `null`, damit die Tafel bei
    einem zusammengelegten Knoten zugeht. Die naheliegende Pruefung waere
    `namen.has(id)` gewesen — und haette jede Person ohne erkannten Namen
    mitgenommen. Die Namenserkennung faellt regelmaessig aus (STAND.md §2h);
    „Ohne Namen" ist ein gueltiger Mensch, der etwas gesagt hat.
    """
    namenlos = {
        **GRAPH,
        "nodes": [
            {**n, "name": ""} if n["id"] == "p1" else n for n in GRAPH["nodes"]
        ],
    }
    wand.evaluate(
        "(g) => { window.kgView.update(g, 99); window.__tafelDaten.setGraph(g);"
        "         window.kgQuotes.setGraph(g); }",
        namenlos,
    )
    wand.wait_for_function("() => window.kgView.layoutPending === false", timeout=60000)
    wand.evaluate("() => window.kgView.cy.$id('p1').emit('tap')")
    wand.wait_for_timeout(800)

    assert wand.evaluate("() => window.__tafel.istOffen()") is True, (
        "eine Person ohne erkannten Namen bekommt keine Tafel mehr"
    )
    assert wand.eval_on_selector("#tafel h2", "e => e.textContent") == "Ohne Namen"
