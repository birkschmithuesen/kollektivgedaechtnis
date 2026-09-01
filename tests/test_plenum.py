"""Die Plenar-Ansicht und ihr eigenes Bedienfeld (Birk, 2026-09-01 vor Ort).

    „Für den Ausspieler im Plenarsaal brauchen wir ein eigenes Design, das
    kann doch nicht dasselbe wie draußen sein. Erstens ist es hier nur Full
    HD, die Leute sitzen weiter entfernt."

Die beiden Flächen sind gemessen verschieden: 3840×2160 aus Armlänge mit
Touch gegen 1920×1080 aus Saalbreite ohne Bedienung. Diese Datei sichert die
sieben Punkte seiner Liste — und vor allem die Trennung, ohne die keiner von
ihnen etwas wert wäre: Was im Saal eingestellt wird, darf im Foyer nichts
verstellen.

Der Gegentest dazu (das Foyer ist unverändert) steht in
`tests/test_foyer_unveraendert.py`; die Architektur und ihre Begründung in
`docs/plenum-entwurf.md`.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from kg.bus import EventBus
from kg.config import Config
from kg.server import PLENUM_REGLER, create_app
from kg.store import Store


@pytest.fixture()
def client(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    bus = EventBus()
    app = create_app(store, cfg, bus)
    with TestClient(app) as test_client:
        test_client.store = store
        test_client.bus = bus
        yield test_client
    store.close()


# --- Die Adressen ------------------------------------------------------------


def test_der_saal_hat_eine_eigene_kurze_adresse(client):
    """`/plenum` ist die Adresse, die im Kiosk-Start des Saal-Laptops steht.

    Sie leitet auf dieselbe Wandseite mit gesetztem Schalter um — eine zweite
    HTML-Datei hätte den Theme-Ladevertrag, die Bundle-Reihenfolge und die
    Zustandsanwendung wiederholt und wäre von der ersten weggelaufen.
    """
    antwort = client.get("/plenum", follow_redirects=False)
    assert antwort.status_code in (302, 307)
    assert antwort.headers["location"] == "/projection?plenum=1"

    seite = client.get("/plenum").text
    assert "static/projection.js" in seite, "die Umleitung landet nicht auf der Wandseite"


def test_der_saal_hat_ein_eigenes_bedienfeld(client):
    seite = client.get("/operator-plenum").text
    assert "static/operator-plenum.js" in seite
    # Der Satz, der verhindert, dass jemand am falschen Feld dreht.
    assert "/operator" in seite and "Foyer" in seite


# --- Getrennt gespeicherte Werte ---------------------------------------------


def test_der_zustand_traegt_beide_saetze_nebeneinander(client):
    """Rein additiv: die Foyer-Schlüssel stehen unverändert, wo sie standen,
    und der Saal kommt als eigener Block dazu. Jeder bestehende Leser
    (Foyer-Wand, /operator, Spiegel) sieht damit weiter seins."""
    zustand = client.get("/api/state").json()
    for schluessel in (
        "max_terms",
        "camera_mode",
        "camera_min_label",
        "camera_speed",
        "portrait_size",
        "stt_connected",
        "mic_on",
        "interview",
    ):
        assert schluessel in zustand, f"der Foyer-Schlüssel {schluessel} fehlt im Zustand"

    saal = zustand["plenum"]
    assert set(saal) == {regler["key"] for regler in PLENUM_REGLER}
    # Die Vorgaben für den Saal sind absichtlich andere als die des Foyers.
    assert saal["camera_mode"] == "pan", "im Saal ist die Fahrt die Vorgabe"
    assert saal["qr_size"] > 132, "der QR-Code im Saal muss deutlich größer sein"
    # 🔴 Die Begriffszahl ist KEIN Saalregler mehr (Birk, 2026-09-02): „die
    # anzahl der begriffe soll bei plenar genau so sein wie auf dem touch
    # screen, nur die schriftgröße ggf anders". Bis dahin standen dort 20 gegen
    # 32 im Foyer, beide Flächen zeigten also verschiedene Begriffe.
    assert "max_terms" not in saal, "der Saal hat keine eigene Begriffszahl mehr"
    assert "camera_min_label" in saal, "die Schriftgröße bleibt je Fläche eigen"


def test_ein_saalregler_veraendert_die_foyerwerte_nicht(client):
    """🔴 Die Kernforderung. Heute lag alles in einer `setting`-Tabelle und
    beide Flächen lasen dieselben Werte."""
    vorher = client.get("/api/state").json()

    assert (
        client.post("/api/plenum", json={"key": "camera_min_label", "value": 64}).status_code == 200
    )
    assert client.post("/api/plenum", json={"key": "portrait_size", "value": 120}).status_code == 200

    nachher = client.get("/api/state").json()
    assert nachher["plenum"]["camera_min_label"] == 64
    assert nachher["plenum"]["portrait_size"] == 120
    # Und das Foyer steht Zeichen für Zeichen, wo es stand.
    assert {k: v for k, v in nachher.items() if k != "plenum"} == {
        k: v for k, v in vorher.items() if k != "plenum"
    }
    # Auch in der Datenbank: eigene Schlüssel, nicht dieselben.
    assert client.store.get_setting("plenum_camera_min_label", "-") == "64.0"
    assert client.store.get_setting("camera_min_label", "40") == "40"


def test_ein_foyerregler_veraendert_die_saalwerte_nicht(client):
    """Die Gegenrichtung, und sie ist die wahrscheinlichere: Am Foyer-Pult
    wird den ganzen Tag gedreht."""
    vorher = client.get("/api/state").json()["plenum"]

    assert client.post("/api/camera_min_label", json={"pixels": 26}).status_code == 200
    assert client.post("/api/max_terms", json={"value": 80}).status_code == 200
    assert client.post("/api/portrait_size", json={"pixels": 640}).status_code == 200

    zustand = client.get("/api/state").json()
    assert zustand["camera_min_label"] == 26
    assert zustand["plenum"] == vorher, "ein Foyer-Regler hat in den Saal durchgeschlagen"


def test_ein_saalwert_wird_gemeldet_und_nicht_nur_gespeichert(client):
    """Der Zustandsweg darf nicht brechen: Wer am Saalregler dreht, muss die
    Fläche im Saal erreichen — und die hängt am SSE-Push, nicht an einer
    Abfrage."""
    warteschlange = client.bus.subscribe()
    assert client.post("/api/plenum", json={"key": "camera_speed", "value": 0.1}).status_code == 200
    meldung = warteschlange.get_nowait()
    assert meldung["type"] == "state"
    assert meldung["state"]["plenum"]["camera_speed"] == 0.1


# --- Schranken ---------------------------------------------------------------


def test_ein_unbekannter_regler_wird_abgewiesen(client):
    antwort = client.post("/api/plenum", json={"key": "gibt_es_nicht", "value": 1})
    assert antwort.status_code == 400
    assert "gibt_es_nicht" in antwort.json()["detail"]
    # Und nichts ist gespeichert worden.
    assert client.store.get_setting("plenum_gibt_es_nicht", "-") == "-"


@pytest.mark.parametrize(
    ("key", "wert"),
    [
        ("camera_min_label", 2.0),  # unter der Untergrenze
        ("camera_min_label", 400.0),  # über der Obergrenze
        ("camera_speed", 0.0),
        ("qr_size", 5000),
        ("portrait_size", 0),
        ("hinweis_dauer", 1),
        ("camera_mode", "rueckwaerts"),  # keine gültige Auswahl
        ("camera_min_label", "sehr gross"),  # gar keine Zahl
    ],
)
def test_werte_ausserhalb_der_schranke_werden_abgewiesen(client, key, wert):
    """Die Fläche im Saal steht unbeaufsichtigt vor Publikum. Was hier
    durchkäme, bliebe bis zum nächsten Morgen stehen."""
    vorher = client.get("/api/state").json()["plenum"][key]
    assert client.post("/api/plenum", json={"key": key, "value": wert}).status_code == 400
    assert client.get("/api/state").json()["plenum"][key] == vorher


def test_die_reglertabelle_ist_in_sich_stimmig():
    """Die Vorgabe jedes Reglers muss innerhalb seiner eigenen Schranke
    liegen. Sonst zeigte das Bedienfeld beim ersten Aufruf einen Wert an, den
    es selbst nicht posten dürfte."""
    for regler in PLENUM_REGLER:
        if regler["typ"] == "auswahl":
            assert regler["default"] in regler["auswahl"], regler["key"]
            assert len(regler["beschriftungen"]) == len(regler["auswahl"]), regler["key"]
            continue
        assert regler["min"] <= regler["default"] <= regler["max"], regler["key"]
        assert regler["schritt"] > 0, regler["key"]
        assert regler["hinweis"], f"{regler['key']} hat keinen Hinweis für den Saal"


def test_die_reglertabelle_wird_der_oberflaeche_ausgeliefert(client):
    """Das Bedienfeld baut sich daraus — damit steht jede Schranke genau
    einmal im Code und die Oberfläche kann keinen Wert anbieten, den der
    Server ablehnt."""
    tabelle = client.get("/api/plenum/regler").json()["regler"]
    assert [r["key"] for r in tabelle] == [r["key"] for r in PLENUM_REGLER]
    assert all("label" in r and "typ" in r for r in tabelle)


def test_ein_unlesbarer_gespeicherter_wert_haelt_die_wand_nicht_an(client):
    """Von Hand editiert, halb geschriebene Datei, ältere Fassung: Ein
    kaputter Eintrag darf die Saalwand nicht ausfallen lassen. Sie zeigt dann
    die Vorgabe."""
    client.store.set_setting("plenum_camera_min_label", "ganz gross")
    client.store.set_setting("plenum_portrait_size", "-4")
    saal = client.get("/api/state").json()["plenum"]
    assert saal["camera_min_label"] == 40.0
    assert saal["portrait_size"] == 260.0


# --- Die Fläche selbst -------------------------------------------------------


GRAPH = {
    "version": 1,
    "generated_at": 1.0,
    "max_terms": 32,
    "nodes": [
        {"id": "p1", "type": "person", "portrait": None, "created_at": 1.0,
         "hidden": False, "x": 0, "y": 0},
        {"id": "t1", "type": "term", "label": "Pseudo-Abstimmung vor Baubeginn",
         "mentions": 16, "created_at": 2.0, "hidden": False, "x": 200, "y": 0,
         "in_dream": True, "dream_role": "anchor"},
        {"id": "t2", "type": "term", "label": "Normen-Inventur",
         "mentions": 7, "created_at": 3.0, "hidden": False, "x": 400, "y": 0,
         "in_dream": True, "dream_role": "neighbour"},
        {"id": "t3", "type": "term", "label": "Grün gegen Parkplätze",
         "mentions": 1, "created_at": 4.0, "hidden": False, "x": 600, "y": 0,
         "in_dream": True, "dream_role": "recent"},
        {"id": "t4", "type": "term", "label": "Ruhender Begriff",
         "mentions": 2, "created_at": 5.0, "hidden": False, "x": 800, "y": 0,
         "in_dream": False, "dream_role": ""},
    ],
    "edges": [{"id": "e1", "source": "p1", "target": "t1"}],
    "quotes": [],
}


@pytest.fixture()
def saal(page, static_server):
    """Die Saalfläche, wie `/plenum` sie aufruft — 1920×1080 wie im echten Raum."""
    page.goto(f"{static_server}/frontend/projection.html?theme=f&plenum=1")
    page.wait_for_function("() => window.kgView !== undefined", timeout=30000)
    return page


def zeige(page, graph=None):
    page.evaluate("(g) => window.kgView.update(g)", graph or GRAPH)
    page.wait_for_timeout(400)
    return page


def test_die_saal_auflage_liegt_ueber_dem_theme(saal):
    """Sie ist kein Theme, sondern eine Auflage: Das Theme ist geladen (und
    liefert alles Unveränderte), die Auflage steht danach und gewinnt."""
    blaetter = saal.evaluate(
        "() => [...document.styleSheets].map((s) => s.href || '').filter(Boolean)"
    )
    namen = [h.rsplit("/", 1)[-1] for h in blaetter]
    assert "theme-f.css" in namen, namen
    assert "plenum.css" in namen, namen
    assert namen.index("plenum.css") > namen.index("theme-f.css"), (
        f"die Auflage steht vor dem Theme und verliert damit: {namen}"
    )


def test_die_schrift_ist_im_saal_groesser(saal):
    """Birks Punkt 1. Gemessen am Knoten, nicht an der Variable: dazwischen
    liegt `cssVar()` in projection.js, und genau dort fiele eine Auflage aus,
    die zu spät geladen wird."""
    zeige(saal)
    groesse = saal.evaluate("() => Number(window.kgView.cy.$id('t1').style('font-size').replace('px',''))")
    assert groesse >= 34, f"die Schrift steht auf {groesse}px statt auf der Saalgröße"


def test_die_begriffe_tragen_im_saal_keine_achsenfarbe(saal):
    """Birks Punkt 3: „Im Foyer tragen die drei Achsenfarben Bedeutung; im
    Saal ohne Legende sind sie sinnlose Dekoration."

    Geprüft am gezeichneten Knoten. Die Hervorhebung als solche darf bleiben
    (heller, kräftiger Ring) — verschwinden muss die FARBcodierung, also die
    Unterscheidbarkeit der drei Rollen.
    """
    zeige(saal)
    farben = saal.evaluate(
        """() => ({
             anker: window.kgView.cy.$id('t1').style('border-color'),
             nachbar: window.kgView.cy.$id('t2').style('border-color'),
             juengst: window.kgView.cy.$id('t3').style('border-color'),
           })"""
    )
    assert farben["anker"] == farben["nachbar"] == farben["juengst"], (
        f"die drei Rollen sind im Saal noch unterscheidbar gefärbt: {farben}"
    )
    # Und es ist keine der drei Bauhaus-Farben mehr.
    for bauhaus in ("rgb(214, 40, 40)", "rgb(29, 78, 156)", "rgb(244, 195, 0)"):
        assert farben["anker"] != bauhaus, farben


def test_im_saal_gibt_es_keine_legende(saal):
    """Birks Punkt 4."""
    assert saal.evaluate("() => document.querySelector('.dream-legende') === null")
    assert saal.evaluate("() => window.kgLegende === null")


def test_der_qr_code_ist_im_saal_deutlich_groesser_und_voll_deckend(saal):
    """Birks Punkt 2: „QR-Code ist nicht scanbar, zu klein." 132 px waren für
    4K aus 2–3 m gesetzt; im Saal muss ihn eine Handykamera aus vielen Metern
    erfassen, auf einer Fläche mit halb so vielen Pixeln."""
    masse = saal.evaluate(
        """() => {
             const s = getComputedStyle(document.querySelector('.qr-bild'));
             const r = document.querySelector('.qr-bild').getBoundingClientRect();
             return { breite: r.width, deckkraft: Number(s.opacity) };
           }"""
    )
    # Anteil der Bildbreite statt einer nackten Pixelzahl: das ist die Größe,
    # die eine Kamera aus dem Saal sieht. Im Foyer sind es 3,4 %.
    anteil = masse["breite"] / 1920
    assert anteil > 0.15, f"der Code nimmt nur {anteil:.1%} der Bildbreite ein"
    # Birks Messreihe (base.css): 100 %..46 % lesbar. Für die Erfassung aus
    # dem Saal ist mehr Kontrast immer besser.
    assert masse["deckkraft"] == 1.0, masse


def test_die_zitatkarte_hat_im_saal_keine_helle_kante(saal):
    """Birks Punkt 5, soweit er ohne Verlust erfüllbar ist — der volle Befund
    steht in `docs/plenum-entwurf.md`. Die weiße Ruhezone des QR-Codes bleibt:
    sie ist Teil des Codes, und ohne sie erfüllte Punkt 5 sich auf Kosten von
    Punkt 2."""
    schatten = saal.evaluate(
        "() => getComputedStyle(document.querySelector('.quote-overlay')).boxShadow"
    )
    assert "rgba(255, 255, 255" not in schatten, schatten


# --- Der Erklärungstext ------------------------------------------------------


def test_der_erklaerungstext_haengt_im_saal_und_ist_als_platzhalter_lesbar(saal):
    """Birks Punkt 7. Der Inhalt ist seine Sache — bis er dasteht, muss die
    Wand selbst sagen, dass sie unfertig ist."""
    befund = saal.evaluate(
        """async () => {
             const modul = await import('./static/plenum-hinweis.js');
             const karte = document.querySelector('.plenum-hinweis');
             return {
               vorhanden: karte !== null,
               text: karte ? karte.querySelector('.plenum-hinweis-text').textContent : '',
               scan: karte ? karte.querySelector('.plenum-hinweis-scan').textContent : '',
               erwartet: modul.ERKLAERUNGSTEXT,
               erwarteteScanzeile: modul.SCANZEILE,
             };
           }"""
    )
    assert befund["vorhanden"], "die Einblendung hängt nicht an der Saalwand"
    # Gegen die Konstante geprüft, nicht gegen einen Wortlaut: Birk ersetzt den
    # Text, und dieser Test darf dabei nicht rot werden.
    assert befund["text"] == befund["erwartet"]
    assert befund["scan"] == befund["erwarteteScanzeile"]


def test_der_erklaerungstext_kommt_und_geht_wieder(page, static_server):
    """Er blendet ein und wieder aus — eine Einblendung, die stehen bliebe,
    verdeckte den Graphen für den Rest des Tages."""
    page.goto(f"{static_server}/frontend/projection.html?theme=f&plenum=1")
    page.wait_for_function("() => window.kgView !== undefined", timeout=30000)
    verlauf = page.evaluate(
        """async () => {
             const { attachPlenumHinweis } = await import('./static/plenum-hinweis.js');
             const h = attachPlenumHinweis({ intervallMs: 300, dauerMs: 100, ersterAuftrittMs: 50 });
             const schlaf = (ms) => new Promise((r) => setTimeout(r, ms));
             const gesehen = [];
             for (let i = 0; i < 20; i += 1) {
               gesehen.push(h.sichtbar);
               await schlaf(30);
             }
             h.entfernen();
             return gesehen;
           }"""
    )
    assert any(verlauf), "die Einblendung ist nie erschienen"
    assert not all(verlauf), "die Einblendung verschwindet nie wieder"


def test_der_erklaerungstext_verdeckt_den_qr_code_nicht(saal):
    """Er fordert zum Scannen auf — er darf nicht verdecken, worauf er zeigt.
    Geprüft bei aufgedrehtem QR-Regler, also im ungünstigsten Fall."""
    ueberschneidung = saal.evaluate(
        """() => {
             document.documentElement.style.setProperty('--qr-size', '720px');
             window.kgPlenumHinweis.zeigen();
             const a = document.querySelector('.plenum-hinweis').getBoundingClientRect();
             const b = document.querySelector('.qr-hinweis').getBoundingClientRect();
             return !(a.right < b.left || b.right < a.left || a.bottom < b.top || b.bottom < a.top);
           }"""
    )
    assert ueberschneidung is False, "Erklärungstext und QR-Code überschneiden sich"


# --- Das Bedienfeld ----------------------------------------------------------


@pytest.fixture()
def pult(page, static_server):
    """Das Saal-Bedienfeld mit der ECHTEN Reglertabelle des Servers.

    Die Tabelle wird nicht nachgebaut, sondern aus `kg.server` genommen und
    der Seite untergeschoben — sonst prüfte dieser Test eine Oberfläche gegen
    eine erfundene Tabelle und genau die Drift bliebe unbemerkt, gegen die die
    Tabelle da ist.
    """
    tabelle = json.dumps({"regler": [dict(r) for r in PLENUM_REGLER]}, default=list)
    page.add_init_script(
        """window.kgPosts = [];
           window.fetch = (url, opts) => {
             if (String(url).includes('/api/plenum/regler')) {
               return Promise.resolve({ ok: true, json: () => Promise.resolve(TABELLE) });
             }
             window.kgPosts.push([String(url), JSON.parse(opts.body)]);
             return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
           };""".replace("TABELLE", tabelle)
    )
    page.goto(f"{static_server}/frontend/operator-plenum.html")
    page.wait_for_function("() => document.querySelectorAll('.regler-zeile').length > 0")
    return page


def test_das_pult_baut_sich_aus_der_reglertabelle_des_servers(pult):
    """Damit kann es keinen Wert anbieten, den die API ablehnt."""
    zeilen = pult.evaluate(
        """() => [...document.querySelectorAll('.regler-zeile')].map((z) => {
             const f = z.querySelector('input, select');
             return { key: z.dataset.key, typ: f.tagName.toLowerCase(),
                      min: f.min || null, max: f.max || null };
           })"""
    )
    assert [z["key"] for z in zeilen] == [r["key"] for r in PLENUM_REGLER]
    nach_key = {z["key"]: z for z in zeilen}
    for regler in PLENUM_REGLER:
        zeile = nach_key[regler["key"]]
        if regler["typ"] == "auswahl":
            assert zeile["typ"] == "select"
            continue
        assert zeile["typ"] == "input"
        assert float(zeile["min"]) == regler["min"], regler["key"]
        assert float(zeile["max"]) == regler["max"], regler["key"]


def test_die_regler_sind_gross_genug_fuer_einen_finger(pult):
    """Birk: „Eigenes Operator-Panel mit großen Slidern." Bedient wird das
    Feld im Halbdunkel neben dem Beamer, oft im Stehen. 48 px ist die
    Untergrenze für ein Bedienelement, das ohne Zielen getroffen werden soll
    — dieselbe Zahl, die die Bedienleiste im Foyer trägt (base.css)."""
    hoehen = pult.evaluate(
        """() => [...document.querySelectorAll('.regler-zeile input[type=range]')]
                   .map((f) => f.getBoundingClientRect().height)"""
    )
    assert hoehen, "es gibt gar keine Schieberegler"
    assert min(hoehen) >= 44, f"zu flach für einen Finger: {hoehen}"


def test_ein_regler_postet_erst_beim_loslassen(pult):
    """`input` feuert bei jedem Pixel des Ziehens; ein Post pro Pixel schickte
    an jede angeschlossene Fläche eine Zustandsmeldung. Gepostet wird bei
    `change`, angezeigt schon vorher."""
    pult.evaluate(
        """() => {
             const f = document.getElementById('regler-camera_min_label');
             f.value = '52';
             f.dispatchEvent(new Event('input', { bubbles: true }));
           }"""
    )
    assert pult.evaluate("() => window.kgPosts") == []
    assert "52" in pult.evaluate(
        "() => document.querySelector('[data-wert-fuer=camera_min_label]').textContent"
    )

    pult.evaluate(
        """() => {
             const f = document.getElementById('regler-camera_min_label');
             f.dispatchEvent(new Event('change', { bubbles: true }));
           }"""
    )
    assert pult.evaluate("() => window.kgPosts") == [
        ["/api/plenum", {"key": "camera_min_label", "value": "52"}]
    ]


def test_das_pult_zeigt_den_zustand_des_saals_und_nicht_den_des_foyers(pult):
    """Der Zustand trägt beide Sätze. Griffe das Pult den falschen ab, drehte
    man im Saal an Zahlen, die dort gar nicht gelten — und merkte es erst,
    wenn die Wand nicht reagiert."""
    pult.evaluate(
        """() => window.kgOperatorPlenum.anzeigen({ camera_min_label: 52, portrait_size: 300 })"""
    )
    werte = pult.evaluate(
        """() => ({
             zoom: document.getElementById('regler-camera_min_label').value,
             begriffe: document.getElementById('regler-portrait_size').value,
           })"""
    )
    # 300 und nicht 302: der Porträt-Schieber hat Schrittweite 5 (PLENUM_REGLER
    # in kg/server.py), ein Zwischenwert rastet auf das nächste Vielfache. Eine
    # frühere Fassung prüfte hier mit einem Wert, den der Regler gar nicht
    # annehmen KANN — sie prüfte damit nicht den Zustandsweg, sondern die
    # Rasterung des Schiebers, und scheiterte daran. Korrigiert am 2026-09-01,
    # nachdem der Auftrag im Turn-Limit abbrach und der Test unfertig liegen
    # blieb; der Begriffe-Schieber, an dem das auffiel, ist am 2026-09-02 aus
    # dem Saalpult verschwunden (die Begriffszahl gilt jetzt für beide Flächen).
    assert werte == {"zoom": "52", "begriffe": "300"}


# --- Was die Saalfläche NICHT tun darf ---------------------------------------


def test_die_saalflaeche_schreibt_keine_positionen_zurueck(page, static_server, fetch_mitschnitt):
    """🔴 Der eine Weg, auf dem die Saalfläche das Foyer trotz getrennter
    Regler doch verändert hätte.

    Beide Flächen lesen aus derselben `position`-Tabelle. Der Saal rechnet mit
    größerer Schrift und größerem Tafelpolster, fcose kommt für neue Knoten
    also auf ein anderes Ergebnis — und `/api/positions` schriebe es dorthin,
    wo das Foyer beim nächsten Neuladen sein mühsam kalibriertes Netz herholt.
    """
    page.goto(f"{static_server}/frontend/projection.html?theme=f&plenum=1")
    page.wait_for_function("() => window.kgView !== undefined", timeout=30000)
    page.evaluate(
        "(g) => window.kgView.update(g)",
        {**GRAPH, "nodes": [{**n, "x": None, "y": None} for n in GRAPH["nodes"]]},
    )
    page.wait_for_function("() => window.kgView.layoutPending === false", timeout=30000)
    page.wait_for_timeout(1500)

    positionen = [u for u in fetch_mitschnitt() if "/api/positions" in u]
    assert positionen == [], f"die Saalfläche schreibt Positionen zurück: {positionen}"
