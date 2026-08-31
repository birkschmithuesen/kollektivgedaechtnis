"""Der mobile Spiegel: Empfänger und Uploader (Auftrag 2026-08-31).

Kein Netz, keine Schlafbefehle. Der Empfänger läuft über FastAPIs `TestClient`,
der Uploader gegen einen vorgetäuschten `httpx.Client`, der die Anfragen an die
Station beantwortet und die Uploads in genau diesen TestClient schiebt — damit
ist die ganze Kette geprüft, ohne dass eine Verbindung aufgemacht wird.

Kein Token steht in dieser Datei. Jeder Test würfelt sich eins; das echte kommt
ausschliesslich aus der Prozessumgebung (Auftrag, „Keine Geheimnisse im Repo").
"""

from __future__ import annotations

import json
import re
import secrets

import httpx
import pytest
from fastapi.testclient import TestClient

from mirror.receiver import STALE_AFTER_S, create_app, leerer_graph
from mirror.uploader import Aenderungswache, Uploader, bildnamen, kurz, stabiler_hash

GRAPH = {
    "version": 1,
    "generated_at": 1700000000.0,
    "max_terms": 12,
    "nodes": [
        {
            "id": "p1",
            "type": "person",
            "portrait": "/media/portraits/p1.png",
            "created_at": 1.0,
            "hidden": False,
            "x": 10.0,
            "y": 20.0,
        },
        {
            "id": "t1",
            "type": "term",
            "label": "Holzbau",
            "mentions": 3,
            "created_at": 2.0,
            "hidden": False,
            "x": 30.0,
            "y": 40.0,
        },
    ],
    "edges": [{"id": "e1", "source": "p1", "target": "t1"}],
    "quotes": [{"id": "q1", "person_id": "p1", "text": "Aus Holz, aber ernsthaft."}],
}

TRAUM = {
    "question": "Wie wollen wir bauen?",
    "current": {
        "id": "d2",
        "created_at": 1700000200.0,
        "sentence": "Ein Haus, das seinen Wald noch kennt.",
        "image": "/media/images/d2.png",
    },
    "history": [
        {"id": "d1", "created_at": 1700000100.0, "sentence": "Erster Traum", "image": "/media/images/d1.png"},
        {"id": "d2", "created_at": 1700000200.0, "sentence": "Ein Haus, das seinen Wald noch kennt.", "image": "/media/images/d2.png"},
    ],
}


@pytest.fixture()
def token() -> str:
    return secrets.token_urlsafe(24)


@pytest.fixture()
def daten(tmp_path):
    return tmp_path / "mirror-data"


@pytest.fixture()
def client(tmp_path, daten, token):
    with TestClient(create_app(data_dir=daten, token=token)) as test_client:
        yield test_client


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def dateien(wurzel) -> set:
    return {p.relative_to(wurzel).as_posix() for p in wurzel.rglob("*")}


# --------------------------------------------------------------------------
# 1. Die Grenze: von aussen kommt nichts hinein
# --------------------------------------------------------------------------


def test_aufnahme_ohne_token_wird_abgewiesen(client):
    assert client.post("/ingest/graph", json=GRAPH).status_code == 401
    assert client.post("/ingest/dream", json=TRAUM).status_code == 401
    assert client.post("/ingest/media/portraits/p1.png", content=b"png").status_code == 401


def test_aufnahme_mit_falschem_token_wird_abgewiesen(client, token):
    falsch = {"Authorization": f"Bearer {token}x"}
    assert client.post("/ingest/graph", json=GRAPH, headers=falsch).status_code == 401
    # Auch die Formen, die knapp danebenliegen: ohne „Bearer", leer, nur der
    # Präfix. Alles 401, und nichts davon darf durchrutschen.
    for kopf in ({"Authorization": token}, {"Authorization": "Bearer "}, {"Authorization": "Bearer"}):
        assert client.post("/ingest/graph", json=GRAPH, headers=kopf).status_code == 401
    assert client.get("/api/graph").json()["nodes"] == []


def test_ohne_konfiguriertes_token_nimmt_der_spiegel_nichts_an(daten):
    """Ein vergessenes EnvironmentFile darf nicht bedeuten: alles darf rein."""
    with TestClient(create_app(data_dir=daten, token=None)) as offen:
        assert offen.post("/ingest/graph", json=GRAPH).status_code == 401
        assert offen.post("/ingest/graph", json=GRAPH, headers=auth("")).status_code == 401
        # Die öffentliche Seite lebt trotzdem — der Dienst geht nicht mit unter.
        assert offen.get("/healthz").json()["ok"] is True
        assert offen.get("/").status_code == 200


def test_das_token_kommt_aus_der_umgebung(daten, monkeypatch):
    aus_der_umgebung = secrets.token_urlsafe(24)
    monkeypatch.setenv("KG_MIRROR_TOKEN", aus_der_umgebung)
    with TestClient(create_app(data_dir=daten)) as umgebungs_client:
        assert umgebungs_client.post("/ingest/graph", json=GRAPH).status_code == 401
        assert (
            umgebungs_client.post("/ingest/graph", json=GRAPH, headers=auth(aus_der_umgebung)).status_code
            == 200
        )


def test_es_gibt_keinen_schreibweg_richtung_station(client):
    """Die Sicherheitsgrenze dieses Aufbaus, als Test.

    Es gibt bewusst keinen Login. Das trägt nur, solange von aussen ausser der
    Aufnahme NICHTS geschrieben werden kann — kein `/api/pause`, kein
    `/api/discard`, nichts, was an der Station ankäme. Ein neuer Endpunkt, der
    das aufweicht, wird hier rot.
    """
    schreibend = [
        (weg, sorted(methoden))
        for weg, methoden in (
            (route.path, route.methods) for route in client.app.routes if hasattr(route, "methods")
        )
        if set(methoden) - {"GET", "HEAD"}
    ]
    assert all(weg.startswith("/ingest/") for weg, _ in schreibend), schreibend


# --------------------------------------------------------------------------
# 2.-4. Aufnahme, Wiedergabe, leerer Anfangszustand
# --------------------------------------------------------------------------


def test_der_aufgenommene_graph_kommt_unveraendert_wieder_heraus(client, token):
    assert client.post("/ingest/graph", json=GRAPH, headers=auth(token)).status_code == 200
    assert client.get("/api/graph").json() == GRAPH


def test_der_aufgenommene_traum_kommt_unveraendert_wieder_heraus(client, token):
    assert client.post("/ingest/dream", json=TRAUM, headers=auth(token)).status_code == 200
    assert client.get("/api/dream").json() == TRAUM


def test_eine_zweite_aufnahme_ersetzt_die_erste_vollstaendig(client, token):
    """Kein Delta, kein Mischen: `kg/export.py` schreibt immer den ganzen
    Graphen, und ein Knoten, den der Operator ausgeblendet hat, muss auch am
    Handy verschwinden."""
    client.post("/ingest/graph", json=GRAPH, headers=auth(token))
    kleiner = {**GRAPH, "nodes": GRAPH["nodes"][:1], "edges": [], "quotes": []}
    client.post("/ingest/graph", json=kleiner, headers=auth(token))
    assert client.get("/api/graph").json() == kleiner


def test_vor_der_ersten_aufnahme_gibt_es_einen_leeren_aber_gueltigen_graphen(client):
    daten = client.get("/api/graph")
    assert daten.status_code == 200
    assert daten.json()["nodes"] == []
    assert daten.json()["edges"] == []
    # `generated_at is None` ist das Merkmal, an dem die Seite „noch nichts da"
    # von „ein Graph ohne Knoten" unterscheidet.
    assert daten.json()["generated_at"] is None

    traum = client.get("/api/dream")
    assert traum.status_code == 200
    assert traum.json()["current"] is None
    assert traum.json()["history"] == []


def test_kaputte_koerper_sind_ein_klientenfehler_kein_absturz(client, token):
    assert client.post("/ingest/graph", content=b"{kein json", headers=auth(token)).status_code == 400
    assert client.post("/ingest/graph", content=b"[1, 2]", headers=auth(token)).status_code == 400
    # Und der Bestand ist unberührt.
    assert client.get("/api/graph").json() == leerer_graph()


def test_der_stand_ueberlebt_einen_neustart(daten, token):
    """systemd startet den Dienst nach jedem Absturz neu. Ohne Platte stünde
    danach eine Wartemeldung, obwohl die Station längst weiterläuft."""
    with TestClient(create_app(data_dir=daten, token=token)) as erster:
        erster.post("/ingest/graph", json=GRAPH, headers=auth(token))
        erster.post("/ingest/dream", json=TRAUM, headers=auth(token))
        erster.post("/ingest/media/portraits/p1.png", content=b"\x89PNG-Bild", headers=auth(token))

    with TestClient(create_app(data_dir=daten, token=token)) as zweiter:
        assert zweiter.get("/api/graph").json() == GRAPH
        assert zweiter.get("/api/dream").json() == TRAUM
        assert zweiter.get("/media/portraits/p1.png").content == b"\x89PNG-Bild"
        # Und das Alter ist NICHT auf null zurückgesetzt: der Stand ist so alt,
        # wie er ist, auch wenn der Dienst jünger ist.
        assert zweiter.get("/healthz").json()["graph_age_s"] is not None


# --------------------------------------------------------------------------
# 3. Bilder: der Name aus dem Netz wird zu einem Pfad
# --------------------------------------------------------------------------


def test_ein_bild_geht_hoch_und_kommt_wieder_heraus(client, token, daten):
    antwort = client.post(
        "/ingest/media/portraits/p1.png", content=b"\x89PNG\r\n", headers=auth(token)
    )
    assert antwort.status_code == 200
    assert (daten / "portraits" / "p1.png").read_bytes() == b"\x89PNG\r\n"

    geholt = client.get("/media/portraits/p1.png")
    assert geholt.status_code == 200
    assert geholt.content == b"\x89PNG\r\n"
    assert geholt.headers["content-type"].startswith("image/png")
    assert client.get("/media/portraits/gibtesnicht.png").status_code == 404


def test_ein_pfad_ausbruch_beim_hochladen_schreibt_nichts(client, token, tmp_path, daten):
    """Der teuerste denkbare Fehler dieses Dienstes: hier wird ein Name aus dem
    NETZ zu einem Pfad auf der Platte des Servers.

    Die Wege stehen prozentkodiert da, weil httpx `..`-Segmente schon beim
    Bauen der URL wegkürzt — die unkodierte Form käme also gar nicht erst als
    Ausbruchsversuch am Server an. Prozentkodiert überlebt sie httpx, wird von
    Starlette (und genauso von uvicorn im Betrieb) dekodiert und landet als
    `../…` im Namen. Das ist der Weg, den ein Angriff tatsächlich nimmt.
    """
    (tmp_path / "etc").mkdir()
    vorher = dateien(tmp_path)

    for weg in (
        "/ingest/media/portraits/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "/ingest/media/portraits/..%2Fpasswd",
        "/ingest/media/images/..%2F..%2Fgraph.json",
        "/ingest/media/portraits/%2e%2e",
        "/ingest/media/portraits/%2Fabsolut.png",
        "/ingest/media/portraits/unter%2Fverzeichnis.png",
        "/ingest/media/portraits/",
    ):
        antwort = client.post(weg, content=b"boese", headers=auth(token))
        assert antwort.status_code == 400, f"{weg} ergab {antwort.status_code}"

    # Der Nachweis: nirgends unter tmp_path ist etwas entstanden — weder
    # ausserhalb von mirror-data noch darin.
    assert dateien(tmp_path) == vorher
    assert not (tmp_path / "etc" / "passwd").exists()


def test_eine_unbekannte_medienart_wird_abgewiesen(client, token, tmp_path):
    vorher = dateien(tmp_path)
    assert client.post("/ingest/media/geheim/x.png", content=b"x", headers=auth(token)).status_code == 400
    assert dateien(tmp_path) == vorher


def test_ein_pfad_ausbruch_beim_lesen_wird_ebenso_abgewiesen(client, daten):
    """Dieselbe Prüfung in der Gegenrichtung — sonst wäre `/media/…` ein
    öffentliches Leserohr in das Dateisystem des Servers."""
    (daten.parent / "geheim.txt").write_text("nicht fuer die oeffentlichkeit")
    assert client.get("/media/portraits/..%2Fgeheim.txt").status_code == 400
    assert client.get("/media/portraits/..%2F..%2Fgeheim.txt").status_code == 400
    assert client.get("/media/geheim/x.png").status_code == 400


def test_eine_leere_datei_ist_ein_klientenfehler(client, token):
    assert client.post("/ingest/media/portraits/p1.png", content=b"", headers=auth(token)).status_code == 400


# --------------------------------------------------------------------------
# 5. Alter und Gesundheit
# --------------------------------------------------------------------------


def test_healthz_meldet_das_alter_der_letzten_aufnahme(client, token):
    frisch = client.get("/healthz").json()
    assert frisch["ok"] is True
    # Noch nie etwas empfangen heisst `null`, nicht 0 — ein Alter von null
    # Sekunden hiesse „gerade eben", und das wäre eine Lüge.
    assert frisch["graph_age_s"] is None
    assert frisch["dream_age_s"] is None
    assert frisch["stale_after_s"] == STALE_AFTER_S

    client.post("/ingest/graph", json=GRAPH, headers=auth(token))
    nach = client.get("/healthz").json()
    assert 0.0 <= nach["graph_age_s"] < 5.0
    # Die beiden Werkzeuge fallen unabhängig voneinander aus: eine Aufnahme von
    # Tool 1 darf den Traumstand nicht jünger aussehen lassen, als er ist.
    assert nach["dream_age_s"] is None

    client.post("/ingest/dream", json=TRAUM, headers=auth(token))
    assert client.get("/healthz").json()["dream_age_s"] is not None


def test_ein_alter_stand_wird_als_alt_gemeldet(daten, token):
    """Der Stand bleibt stehen, aber die Seite bekommt die Wahrheit über ihn.

    Ohne Schlafbefehl geprüft: die Aufnahmezeit wird künstlich zurückgesetzt,
    genau wie sie es nach einem Ausfall der Station im Betrieb wäre.
    """
    app = create_app(data_dir=daten, token=token)
    with TestClient(app) as alt:
        alt.post("/ingest/graph", json=GRAPH, headers=auth(token))
        app.state.spiegel.graph_at -= 10 * 60
        gesundheit = alt.get("/healthz").json()
        assert gesundheit["graph_age_s"] > gesundheit["stale_after_s"]
        # Der Graph selbst wird weiter ausgeliefert — ein ehrlicher alter Stand
        # ist besser als eine leere Seite.
        assert alt.get("/api/graph").json() == GRAPH


# --------------------------------------------------------------------------
# Die Seiten und der Ereignisstrom
# --------------------------------------------------------------------------


def test_beide_seiten_und_ihre_dateien_werden_ausgeliefert(client):
    for weg in ("/graph", "/traum"):
        antwort = client.get(weg)
        assert antwort.status_code == 200
        assert "viewport-fit=cover" in antwort.text
        # Beide Reiter stehen auf beiden Seiten — seit der Startseite auf der
        # Wurzel liegt, zeigt der Netz-Reiter auf /graph.
        assert 'href="/graph"' in antwort.text and 'href="/traum"' in antwort.text
        # Und von beiden geht es zurück zur Startseite und zur Transparenz.
        assert 'href="/"' in antwort.text and 'href="/transparenz"' in antwort.text
    for datei in (
        "/static/mirror.css",
        "/static/seite.css",
        "/static/mirror.js",
        "/static/graph.js",
        "/static/dream.js",
        "/static/vendor/cytoscape.min.js",
    ):
        assert client.get(datei).status_code == 200, datei


def test_die_seiten_haengen_an_nichts_aus_frontend(client):
    """Der Spiegel ist eigenständig (Auftrag): an der Wand wird parallel
    gebaut, und ein Pfad nach frontend/ würde beide Baustellen verkoppeln."""
    for weg in ("/", "/graph", "/traum", "/transparenz"):
        text = client.get(weg).text
        assert "frontend" not in text
        assert client.get(f"{weg.rstrip('/')}/../frontend/projection.html").status_code in (400, 404)


# --------------------------------------------------------------------------
# Die beiden stillen Seiten: Startseite und Transparenz
# --------------------------------------------------------------------------


def test_die_wurzel_ist_die_startseite_und_zeigt_auf_beide_ansichten(client):
    """Ohne jede Aufnahme. Die Startseite ist der Wegweiser im Flur — sie muss
    dastehen, auch wenn die Station gar nicht verbunden ist."""
    antwort = client.get("/")
    assert antwort.status_code == 200
    assert "viewport-fit=cover" in antwort.text
    assert 'href="/graph"' in antwort.text
    assert 'href="/traum"' in antwort.text
    assert "Der Graph" in antwort.text and "Der Traum" in antwort.text
    # Der Weg zum langen Text ist von hier aus da.
    assert 'href="/transparenz"' in antwort.text
    # Und der Graph liegt jetzt woanders, nicht mehr auf der Wurzel.
    assert "cytoscape" not in antwort.text


def test_die_graphansicht_liegt_auf_graph(client):
    antwort = client.get("/graph")
    assert antwort.status_code == 200
    assert 'id="cy"' in antwort.text
    assert "/static/vendor/cytoscape.min.js" in antwort.text


def test_die_transparenzseite_steht_ohne_jede_aufnahme(client):
    antwort = client.get("/transparenz")
    assert antwort.status_code == 200
    assert "Was wo läuft" in antwort.text
    # Die vier Dienste stehen an einer Stelle; dass sie überhaupt dastehen, ist
    # der Sinn der Seite.
    for dienst in ("Spracherkennung", "Ähnlichkeitsvergleich", "Black Forest Labs"):
        assert dienst in antwort.text, dienst
    # Der Abschnitt über die eigenen Lücken wird nicht wegoptimiert — er ist
    # der Grund, warum der Rest glaubwürdig ist (Nachtrag 3).
    assert "Was dabei offen bleibt" in antwort.text
    assert "Die Schweiz gehört nicht zur EU" in antwort.text
    assert "Telegram" in antwort.text
    # Kein Datum auf der Seite: ein sichtbarer Stand, der nicht nachgepflegt
    # wird, ist schlechter als keiner.
    assert not re.search(r"\b20\d\d-\d\d-\d\d\b", antwort.text)


def test_die_stillen_seiten_binden_nichts_von_dritten_ein(client):
    """Beide behaupten das über sich selbst. Eine Schrift von einem fremden
    Server oder ein nachgeladenes Skript würde die Aussage zur Unwahrheit
    machen — und das auf der Seite, auf der es am meisten zählt."""
    for weg in ("/", "/transparenz"):
        # Ohne die Kommentare: dort steht (als Begründung) genau das, was hier
        # verboten wird, und der Browser holt daraus nichts.
        text = re.sub(r"<!--.*?-->", "", client.get(weg).text, flags=re.S)
        assert "<script" not in text, weg
        assert "EventSource" not in text, weg
        # Alles, was der Browser von woanders HOLEN würde: nichts davon zeigt
        # nach draussen. Die einzigen fremden URLs sind Ziele zum Anklicken.
        for url in re.findall(r'(?:src|href)="(https?://[^"]*)"', text):
            assert url.rstrip("/") in (
                "https://birkschmithuesen.com",
                "https://artesmobiles.art",
            ), (weg, url)


def test_die_beiden_ausseren_links_oeffnen_sicher(client):
    """`target=_blank` ohne `rel=noopener` gibt der fremden Seite Zugriff auf
    das eigene `window.opener` (Auftrag: „in neuem Tab, rel=noopener")."""
    for weg in ("/", "/transparenz"):
        text = client.get(weg).text
        for anker in re.findall(r"<a\s[^>]*https?://[^>]*>", text):
            assert 'target="_blank"' in anker, (weg, anker)
            assert 'rel="noopener"' in anker, (weg, anker)


async def test_der_ereignisstrom_beginnt_mit_dem_aktuellen_stand(daten, token):
    """Der Strom wird über die Route selbst geprüft, nicht über den TestClient.

    Derselbe Grund wie in tests/test_dream_server.py: httpx' ASGI-Transport
    liest den ganzen Antwortkörper leer, bevor er irgendetwas herausgibt — und
    `/events` endet nie, das ist der Sinn der Sache. Also wird hier die echte
    Routen-Koroutine gefahren und ihr `body_iterator` gelesen.
    """
    app = create_app(data_dir=daten, token=token)
    with TestClient(app) as vorbereiten:
        vorbereiten.post("/ingest/graph", json=GRAPH, headers=auth(token))

    route = next(r for r in app.routes if getattr(r, "path", None) == "/events")
    antwort = await route.endpoint()
    assert antwort.media_type == "text/event-stream"
    # nginx puffert sonst — die Kopfzeile ist der Gürtel zum Hosenträger in
    # mirror/nginx-kg-mirror.conf.
    assert antwort.headers["x-accel-buffering"] == "no"

    erstes = json.loads((await antwort.body_iterator.__anext__())[len("data: "):])
    zweites = json.loads((await antwort.body_iterator.__anext__())[len("data: "):])
    await antwort.body_iterator.aclose()

    assert erstes["type"] == "graph"
    assert erstes["graph"] == GRAPH
    assert erstes["age_s"] is not None
    assert zweites["type"] == "dream"
    # Noch nie ein Traum eingegangen: kein Alter, aber ein gültiger Zustand.
    assert zweites["age_s"] is None
    assert zweites["dream"]["current"] is None


async def test_eine_stille_minute_schickt_ein_keep_alive_statt_aufzulegen(daten, token):
    """15 s Stille ist der Normalfall. Ohne den Herzschlag macht ein Proxy die
    Leitung zu, und die Seite steht still, ohne dass irgendwo etwas rot wird —
    dasselbe Muster und dieselbe Frist wie in kg/server.py und kg2/server.py."""
    import asyncio

    app = create_app(data_dir=daten, token=token)
    route = next(r for r in app.routes if getattr(r, "path", None) == "/events")
    antwort = await route.endpoint()
    await antwort.body_iterator.__anext__()
    await antwort.body_iterator.__anext__()

    echtes_wait_for = asyncio.wait_for

    async def sofort_ablaufen(awaitable, timeout):
        assert timeout == 15.0
        awaitable.close()
        raise TimeoutError

    asyncio.wait_for = sofort_ablaufen
    try:
        chunk = await antwort.body_iterator.__anext__()
    finally:
        asyncio.wait_for = echtes_wait_for
        await antwort.body_iterator.aclose()

    assert chunk == ": keep-alive\n\n"


async def test_eine_aufnahme_erreicht_die_offenen_seiten(daten, token):
    """Der ganze Zweck des Stroms: die Seite am Handy aktualisiert sich, ohne
    dass jemand nachlädt."""
    app = create_app(data_dir=daten, token=token)
    route = next(r for r in app.routes if getattr(r, "path", None) == "/events")
    antwort = await route.endpoint()
    await antwort.body_iterator.__anext__()
    await antwort.body_iterator.__anext__()

    with TestClient(app) as sender:
        sender.post("/ingest/dream", json=TRAUM, headers=auth(token))

    chunk = json.loads((await antwort.body_iterator.__anext__())[len("data: "):])
    await antwort.body_iterator.aclose()

    assert chunk["type"] == "dream"
    assert chunk["dream"] == TRAUM
    assert chunk["age_s"] == 0.0


# --------------------------------------------------------------------------
# 6. Der Uploader
# --------------------------------------------------------------------------


def test_die_aenderungserkennung_schickt_unveraendertes_kein_zweites_mal():
    """Ohne sie liefe der Uploader alle drei Sekunden mit demselben Graphen
    los — den ganzen Tag, über ein Konferenz-WLAN."""
    wache = Aenderungswache()

    assert wache.geaendert("graph", GRAPH) is True
    wache.bestaetige("graph", GRAPH)
    assert wache.geaendert("graph", GRAPH) is False

    # Eine umsortierte, inhaltlich gleiche Antwort ist KEINE Änderung: der
    # Graph kommt frisch aus einem JSON-Parser, und die Schlüsselreihenfolge
    # ist keine Zusage.
    umsortiert = dict(reversed(list(GRAPH.items())))
    assert wache.geaendert("graph", umsortiert) is False

    # Eine echte Änderung dagegen schon — auch eine winzige.
    assert wache.geaendert("graph", {**GRAPH, "generated_at": 1700000001.0}) is True

    # Und die beiden Werkzeuge zählen getrennt.
    assert wache.geaendert("dream", TRAUM) is True
    wache.bestaetige("dream", TRAUM)
    assert wache.geaendert("dream", TRAUM) is False
    assert wache.geaendert("graph", GRAPH) is False


def test_der_hash_haengt_nur_am_inhalt():
    assert stabiler_hash({"a": 1, "b": 2}) == stabiler_hash({"b": 2, "a": 1})
    assert stabiler_hash({"a": 1}) != stabiler_hash({"a": 2})
    assert stabiler_hash([1, 2]) != stabiler_hash([2, 1])


def test_bildnamen_findet_portraits_und_traumbilder():
    assert bildnamen(GRAPH, "/media/portraits/") == ["p1.png"]
    assert bildnamen(TRAUM, "/media/images/") == ["d2.png", "d1.png"]
    # Nichts Fremdes, keine Doppelten, kein Verzeichnis.
    assert bildnamen({"a": "/media/images/x/y.png", "b": None, "c": 7}, "/media/images/") == []


class StationsAttrappe:
    """Ein `httpx.Client`, der die Station spielt und die Uploads in den
    TestClient des Empfängers schiebt. Kein Socket, kein Port, kein Warten."""

    def __init__(self, empfaenger: TestClient, ziel: str, antworten: dict):
        self.empfaenger = empfaenger
        self.ziel = ziel
        self.antworten = antworten
        self.geholt: list[str] = []
        self.geschickt: list[str] = []

    def get(self, url: str, **_):
        self.geholt.append(url)
        wert = self.antworten.get(url)
        if wert is None:
            raise httpx.ConnectError(f"nicht erreichbar: {url}")
        if isinstance(wert, Exception):
            raise wert
        if isinstance(wert, bytes):
            return httpx.Response(200, content=wert, request=httpx.Request("GET", url))
        return httpx.Response(200, json=wert, request=httpx.Request("GET", url))

    def post(self, url: str, content=None, headers=None, **_):
        self.geschickt.append(url)
        weg = url[len(self.ziel):]
        return self.empfaenger.post(weg, content=content, headers=headers)


def test_der_uploader_schiebt_beide_werkzeuge_und_ihre_bilder_hoch(client, token, tmp_path):
    attrappe = StationsAttrappe(
        client,
        "http://spiegel",
        {
            "http://t1/graph.json": GRAPH,
            "http://t1/media/portraits/p1.png": b"\x89PNG-portrait",
            "http://t2/api/state": TRAUM,
            "http://t2/media/images/d1.png": b"\x89PNG-d1",
            "http://t2/media/images/d2.png": b"\x89PNG-d2",
        },
    )
    uploader = Uploader(
        "http://spiegel",
        token,
        tool1_url="http://t1",
        tool2_url="http://t2",
        client=attrappe,
        gedaechtnis=tmp_path / "mirror-uploaded.json",
    )

    assert uploader.runde() is True

    assert client.get("/api/graph").json() == GRAPH
    assert client.get("/api/dream").json() == TRAUM
    assert client.get("/media/portraits/p1.png").content == b"\x89PNG-portrait"
    assert client.get("/media/images/d2.png").content == b"\x89PNG-d2"

    # Zweite Runde, nichts hat sich geändert: kein einziger Upload mehr.
    vorher = len(attrappe.geschickt)
    assert uploader.runde() is True
    assert attrappe.geschickt[vorher:] == []


def test_der_uploader_merkt_sich_hochgeladene_bilder_ueber_einen_neustart(client, token, tmp_path):
    gedaechtnis = tmp_path / "mirror-uploaded.json"
    antworten = {
        "http://t1/graph.json": GRAPH,
        "http://t1/media/portraits/p1.png": b"\x89PNG-portrait",
        "http://t2/api/state": TRAUM,
        "http://t2/media/images/d1.png": b"\x89PNG-d1",
        "http://t2/media/images/d2.png": b"\x89PNG-d2",
    }
    erste = StationsAttrappe(client, "http://spiegel", antworten)
    Uploader("http://spiegel", token, tool1_url="http://t1", tool2_url="http://t2",
             client=erste, gedaechtnis=gedaechtnis).runde()
    assert json.loads(gedaechtnis.read_text())["uploaded"]

    zweite = StationsAttrappe(client, "http://spiegel", antworten)
    neu = Uploader("http://spiegel", token, tool1_url="http://t1", tool2_url="http://t2",
                   client=zweite, gedaechtnis=gedaechtnis)
    neu.runde()

    # Die Dokumente werden nach einem Neustart wieder geschickt (der Hash lebt
    # nur im Speicher, und das ist der billige Teil). Die BILDER nicht — das
    # ist der teure, und genau dafür gibt es die Datei.
    assert not [weg for weg in zweite.geschickt if "/ingest/media/" in weg]
    assert not [weg for weg in zweite.geholt if "/media/" in weg]


def test_ein_ausfall_von_tool_2_haelt_tool_1_nicht_auf(client, token, tmp_path):
    """Spec §9: die beiden Werkzeuge fallen unabhängig voneinander aus. Der
    Uploader darf aus zwei getrennten Ausfällen nicht einen gemeinsamen machen."""
    attrappe = StationsAttrappe(
        client,
        "http://spiegel",
        {"http://t1/graph.json": GRAPH, "http://t1/media/portraits/p1.png": b"\x89PNG"},
    )
    uploader = Uploader("http://spiegel", token, tool1_url="http://t1", tool2_url="http://t2",
                        client=attrappe, gedaechtnis=tmp_path / "mirror-uploaded.json")

    assert uploader.runde() is False  # Tool 2 fehlt, und das wird gemeldet
    assert client.get("/api/graph").json() == GRAPH  # Tool 1 ist trotzdem oben
    assert client.get("/media/portraits/p1.png").status_code == 200


def test_ein_fehlendes_einzelbild_kostet_nicht_die_uebrigen(client, token, tmp_path):
    """Ein Portrait, das die Station gerade erst zuschneidet, ist kurz 404."""
    attrappe = StationsAttrappe(
        client,
        "http://spiegel",
        {
            "http://t1/graph.json": GRAPH,
            "http://t1/media/portraits/p1.png": httpx.ConnectError("noch nicht da"),
            "http://t2/api/state": TRAUM,
            "http://t2/media/images/d1.png": b"\x89PNG-d1",
            "http://t2/media/images/d2.png": b"\x89PNG-d2",
        },
    )
    uploader = Uploader("http://spiegel", token, tool1_url="http://t1", tool2_url="http://t2",
                        client=attrappe, gedaechtnis=tmp_path / "mirror-uploaded.json")

    assert uploader.runde() is True
    assert client.get("/media/portraits/p1.png").status_code == 404
    assert client.get("/media/images/d2.png").status_code == 200
    # Und beim nächsten Mal wird es erneut versucht.
    attrappe.antworten["http://t1/media/portraits/p1.png"] = b"\x89PNG-endlich"
    uploader.runde()
    assert client.get("/media/portraits/p1.png").content == b"\x89PNG-endlich"


def test_ein_gescheiterter_upload_wird_wiederholt(client, tmp_path, token):
    """Erst bestätigen, wenn es wirklich oben ist — sonst gilt ein Stand als
    hochgeladen, den nie jemand bekommen hat."""
    attrappe = StationsAttrappe(client, "http://spiegel", {"http://t1/graph.json": GRAPH})
    uploader = Uploader("http://spiegel", "falsches-" + token, tool1_url="http://t1",
                        tool2_url="http://t2", client=attrappe,
                        gedaechtnis=tmp_path / "mirror-uploaded.json")

    assert uploader.runde() is False
    assert client.get("/api/graph").json()["nodes"] == []
    # Mit richtigem Token in derselben Instanz: der Graph gilt NICHT als
    # erledigt, sondern geht hoch.
    uploader._kopf = {"Authorization": f"Bearer {token}"}
    assert uploader.runde() is False  # Tool 2 fehlt weiterhin
    assert client.get("/api/graph").json() == GRAPH


def test_der_rueckwaerts_abstand_waechst_und_ist_gedeckelt(tmp_path, token):
    uploader = Uploader("http://spiegel", token, gedaechtnis=tmp_path / "x.json")

    assert uploader.schlafdauer(3.0) == 3.0
    uploader.fehler_in_folge = 1
    assert uploader.schlafdauer(3.0) == 6.0
    uploader.fehler_in_folge = 3
    assert uploader.schlafdauer(3.0) == 24.0
    # Gedeckelt: ein toter Server darf nicht dauerhaft Bandbreite fressen, ein
    # zurückkehrender aber auch nicht stundenlang übersehen werden.
    uploader.fehler_in_folge = 99
    assert uploader.schlafdauer(3.0) == 60.0


def test_die_schleife_ueberlebt_jeden_netzfehler(client, token, tmp_path, capsys):
    """Kein Netzfehler darf das Skript beenden — es läuft einen Tag lang
    unbeaufsichtigt in einem fremden WLAN."""
    attrappe = StationsAttrappe(client, "http://spiegel", {})  # nichts erreichbar
    uploader = Uploader("http://spiegel", token, tool1_url="http://t1", tool2_url="http://t2",
                        client=attrappe, gedaechtnis=tmp_path / "mirror-uploaded.json")

    uploader.laufe(intervall=0.0, runden=3)

    assert uploader.fehler_in_folge == 3
    fehler = capsys.readouterr().err
    assert "Tool 1" in fehler and "Tool 2" in fehler


def test_keine_fehlermeldung_verraet_das_token(monkeypatch):
    """Diese Ausgabe läuft in eine Datei, die am Ende des Tages irgendwer liest."""
    geheim = secrets.token_urlsafe(24)
    monkeypatch.setenv("KG_MIRROR_TOKEN", geheim)
    text = kurz(RuntimeError(f"401 für Bearer {geheim}"))
    assert geheim not in text
    assert "***" in text


def test_im_repo_steht_kein_token(tmp_path):
    """Die Regel als Test: das Token kommt ausschliesslich aus der Umgebung.

    Geprüft wird die Eigenschaft — keine Datei unter mirror/ weist einem der
    Token-Namen einen Wert zu.
    """
    import re
    from pathlib import Path

    muster = re.compile(r"KG_MIRROR_TOKEN\s*[=:]\s*[\"']?[A-Za-z0-9_\-]{4,}")
    mirror = Path(__file__).resolve().parent.parent / "mirror"
    treffer = [
        pfad.relative_to(mirror).as_posix()
        for pfad in mirror.rglob("*")
        if pfad.is_file()
        and pfad.suffix in (".py", ".md", ".conf", ".service", ".html", ".js", ".css", ".env")
        and muster.search(pfad.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert not treffer, f"möglicher Tokenwert im Repo: {treffer}"
