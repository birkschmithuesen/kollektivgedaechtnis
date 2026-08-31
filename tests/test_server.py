import pytest
from fastapi.testclient import TestClient

from kg.bus import EventBus
from kg.config import Config
from kg.server import create_app
from kg.store import Store


@pytest.fixture()
def client(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    person = store.create_person(started_at=1.0, portrait_path="portraits/a.png")
    term = store.get_or_create_term("Holzbau", created_at=2.0)
    store.add_edge(person.id, term.id, created_at=3.0)
    app = create_app(store, cfg, EventBus())
    with TestClient(app) as test_client:
        test_client.store = store
        test_client.cfg = cfg
        yield test_client
    store.close()


def test_graph_json_serves_the_current_state(client):
    data = client.get("/graph.json").json()
    assert {n["type"] for n in data["nodes"]} == {"person", "term"}
    assert len(data["edges"]) == 1


def test_max_terms_is_persisted_and_reported(client):
    assert client.post("/api/max_terms", json={"value": 45}).status_code == 200
    assert client.get("/api/state").json()["max_terms"] == 45
    assert client.store.get_setting("max_terms", "1") == "45"


def test_max_terms_rejects_nonsense(client):
    assert client.post("/api/max_terms", json={"value": 0}).status_code == 422
    assert client.post("/api/max_terms", json={"value": "viele"}).status_code == 422


def test_a_legacy_database_with_min_mentions_set_starts_without_crashing(tmp_path):
    # Bestandsdatenbank: an old `min_mentions` value must never be read as a
    # `max_terms` value (spec 2026-08-29 §4) -- it just sits there unused, and
    # the server falls back to its own default for the new key.
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    store.set_setting("min_mentions", "2")
    app = create_app(store, cfg, EventBus())
    with TestClient(app) as legacy_client:
        state = legacy_client.get("/api/state").json()
        assert "max_terms" in state
        assert legacy_client.get("/graph.json").status_code == 200
    store.close()


def test_hiding_sets_the_flag_without_deleting_anything(client):
    term_id = client.store.list_terms()[0].id

    assert client.post("/api/hidden", json={"node_id": f"term:{term_id}", "hidden": True}).status_code == 200

    assert client.store.get_term(term_id).hidden is True
    graph = client.get("/graph.json").json()
    assert [n for n in graph["nodes"] if n["id"] == term_id][0]["hidden"] is True
    assert len(graph["edges"]) == 1


def test_hiding_an_unknown_node_is_a_client_error(client):
    assert client.post("/api/hidden", json={"node_id": "nonsense:1", "hidden": True}).status_code == 400


def test_the_operator_can_correct_and_clear_a_misheard_name(client):
    """Die einzige Korrektur, die der Operator an einem fertigen Interview
    vornimmt: Die Spracherkennung verhört Namen zuverlässig.

    Und leeren muss er ihn können — ein leerer Wert ist kein Fehler, sondern
    die Aussage „hier steht kein Name", die der Graph als null trägt.
    """
    person_id = client.store.list_persons()[0].id

    assert (
        client.post(
            "/api/person_name", json={"person_id": person_id, "name": "Frau Kirchner"}
        ).status_code
        == 200
    )
    assert client.store.get_person(person_id).name == "Frau Kirchner"
    graph = client.get("/graph.json").json()
    assert [n for n in graph["nodes"] if n["id"] == person_id][0]["name"] == "Frau Kirchner"

    assert (
        client.post("/api/person_name", json={"person_id": person_id, "name": ""}).status_code
        == 200
    )
    assert client.store.get_person(person_id).name is None
    graph = client.get("/graph.json").json()
    assert [n for n in graph["nodes"] if n["id"] == person_id][0]["name"] is None


def test_a_name_the_size_of_a_transcript_is_refused(client):
    """Was hier ankommt, steht später unter einem Zitat auf der Wand."""
    person_id = client.store.list_persons()[0].id
    antwort = client.post("/api/person_name", json={"person_id": person_id, "name": "A" * 200})
    assert antwort.status_code == 422
    assert client.store.get_person(person_id).name is None


def test_camera_mode_round_trips(client):
    assert client.post("/api/camera", json={"mode": "pan"}).status_code == 200
    assert client.get("/api/state").json()["camera_mode"] == "pan"
    assert client.post("/api/camera", json={"mode": "warp"}).status_code == 422


def test_camera_zoom_round_trips_and_defaults_to_the_whole_net(client):
    # D4: the wall opens on the whole net, so an untouched station reports 1.
    assert client.get("/api/state").json()["camera_zoom"] == 1.0

    assert client.post("/api/camera_zoom", json={"factor": 2}).status_code == 200
    assert client.get("/api/state").json()["camera_zoom"] == 2.0

    # Below 1 the camera would show LESS than the net without filling the wall,
    # and Camera.setZoomFactor raises on it; above 4 a stray value would zoom
    # the unattended wall into a single node.
    assert client.post("/api/camera_zoom", json={"factor": 0.5}).status_code == 422
    assert client.post("/api/camera_zoom", json={"factor": 99}).status_code == 422
    # The rejected writes must not have moved the stored value.
    assert client.get("/api/state").json()["camera_zoom"] == 2.0


def test_portrait_size_round_trips_and_survives_a_restart(client):
    # An untouched station reports projection.js's own default, so the wall
    # looks the same whether or not this setting has ever been written.
    assert client.get("/api/state").json()["portrait_size"] == 120.0

    assert client.post("/api/portrait_size", json={"pixels": 180}).status_code == 200
    assert client.get("/api/state").json()["portrait_size"] == 180.0
    # It is a stored setting like camera_zoom, so it comes back after a crash
    # (spec 10.5) — the same store, re-read, is what a restart does.
    assert client.store.get_setting("portrait_size", "120") == "180.0"

    # Below 40px a portrait is a dot on a 1920px wall, above 260px a handful of
    # faces crowd everything else off it.
    assert client.post("/api/portrait_size", json={"pixels": 10}).status_code == 422
    assert client.post("/api/portrait_size", json={"pixels": 1000}).status_code == 422
    assert client.get("/api/state").json()["portrait_size"] == 180.0


def test_the_portrait_size_and_the_camera_zoom_do_not_touch_each_other(client):
    # Two different controls (Birk's brief, 2026-08-29): the zoom chooses the
    # section of the net on the wall, the portrait size how big the faces in it
    # are drawn. Both must keep working independently.
    client.post("/api/camera_zoom", json={"factor": 2.5})
    client.post("/api/portrait_size", json={"pixels": 60})

    state = client.get("/api/state").json()
    assert (state["camera_zoom"], state["portrait_size"]) == (2.5, 60.0)

    client.post("/api/camera_zoom", json={"factor": 1.5})
    state = client.get("/api/state").json()
    assert (state["camera_zoom"], state["portrait_size"]) == (1.5, 60.0)


def test_positions_are_persisted_so_the_layout_never_reshuffles(client):
    term_id = client.store.list_terms()[0].id

    response = client.post("/api/positions", json={"positions": {term_id: {"x": 4.5, "y": -2.0}}})

    assert response.status_code == 200
    assert client.store.get_positions()[term_id] == (4.5, -2.0)
    node = [n for n in client.get("/graph.json").json()["nodes"] if n["id"] == term_id][0]
    assert (node["x"], node["y"]) == (4.5, -2.0)


def test_pages_and_static_assets_are_served(client):
    assert client.get("/", follow_redirects=False).status_code in (302, 307)
    assert client.get("/projection").status_code == 200
    assert client.get("/operator").status_code == 200
    assert client.get("/testpattern").status_code == 200
    assert client.get("/static/graph-model.js").status_code == 200
