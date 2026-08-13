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


def test_min_mentions_is_persisted_and_reported(client):
    assert client.post("/api/min_mentions", json={"value": 3}).status_code == 200
    assert client.get("/api/state").json()["min_mentions"] == 3
    assert client.store.get_setting("min_mentions", "1") == "3"


def test_min_mentions_rejects_nonsense(client):
    assert client.post("/api/min_mentions", json={"value": 0}).status_code == 422
    assert client.post("/api/min_mentions", json={"value": "viele"}).status_code == 422


def test_hiding_sets_the_flag_without_deleting_anything(client):
    term_id = client.store.list_terms()[0].id

    assert client.post("/api/hidden", json={"node_id": f"term:{term_id}", "hidden": True}).status_code == 200

    assert client.store.get_term(term_id).hidden is True
    graph = client.get("/graph.json").json()
    assert [n for n in graph["nodes"] if n["id"] == term_id][0]["hidden"] is True
    assert len(graph["edges"]) == 1


def test_hiding_an_unknown_node_is_a_client_error(client):
    assert client.post("/api/hidden", json={"node_id": "nonsense:1", "hidden": True}).status_code == 400


def test_camera_mode_round_trips(client):
    assert client.post("/api/camera", json={"mode": "pan"}).status_code == 200
    assert client.get("/api/state").json()["camera_mode"] == "pan"
    assert client.post("/api/camera", json={"mode": "warp"}).status_code == 422


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
