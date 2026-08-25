import json

import pytest

from kg.config import Config
from kg.embeddings import HashEmbedder
from kg.pipeline import ProcessResult
from kg.store import Store
from sim.replay import find_late_renames, load_corpus, replay, score_run, snapshot_labels


@pytest.fixture()
def corpus_dir(tmp_path):
    directory = tmp_path / "interviews"
    directory.mkdir()
    for index, text in enumerate(["eins", "zwei", "drei"]):
        (directory / f"{index:03d}.json").write_text(
            json.dumps({"index": index, "question_index": 0, "speaker_type": "x", "text": text}),
            encoding="utf-8",
        )
    return directory


def test_load_corpus_is_ordered_by_index(corpus_dir):
    assert [item["index"] for item in load_corpus(corpus_dir)] == [0, 1, 2]


def test_replay_creates_one_person_per_interview_with_spaced_timestamps(tmp_path, corpus_dir):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    seen = []

    def processor(store_, cfg_, llm_, embedder_, log_, person_id, started_at, stopped_at):
        seen.append((person_id, started_at, stopped_at))
        return ProcessResult(person_id, "done", [], "")

    ids = replay(
        load_corpus(corpus_dir),
        store,
        cfg,
        llm=object(),
        embedder=HashEmbedder(dim=16),
        start_time=1000.0,
        spacing=300.0,
        processor=processor,
    )

    assert ids == ["p1", "p2", "p3"]
    assert [start for _, start, _ in seen] == [1000.0, 1300.0, 1600.0]
    assert all(stop > start for _, start, stop in seen)
    # the text really reached the transcript log
    assert "zwei" in cfg.transcript_log_path.read_text(encoding="utf-8")
    store.close()


def test_on_step_is_called_after_every_interview(tmp_path, corpus_dir):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    steps = []

    replay(
        load_corpus(corpus_dir),
        store,
        cfg,
        llm=object(),
        embedder=HashEmbedder(dim=16),
        # positional order: store, cfg, llm, embedder, log, person_id, started, stopped
        processor=lambda *a: ProcessResult(a[5], "done", [], ""),
        on_step=lambda index, person_id: steps.append((index, person_id)),
    )

    assert steps == [(0, "p1"), (1, "p2"), (2, "p3")]
    store.close()


def test_snapshot_labels_records_every_nodes_label_and_how_many_people_said_it(tmp_path):
    # The database keeps no rename history, so D5 ("a node two people share
    # never changes its name") cannot be checked after the fact from a finished
    # run. The run has to write the history down as it goes.
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    term = store.get_or_create_term("Baustoff mit Geschichte", created_at=1.0)
    p1 = store.create_person(started_at=1.0)
    p2 = store.create_person(started_at=2.0)
    store.add_edge(p1.id, term.id, created_at=1.0)
    store.add_edge(p2.id, term.id, created_at=2.0)

    snapshot = snapshot_labels(store, 7, p2.id)

    assert snapshot["index"] == 7
    assert snapshot["person_id"] == p2.id
    assert snapshot["terms"] == {term.id: ["Baustoff mit Geschichte", 2]}
    store.close()


def test_find_late_renames_reports_a_rename_of_a_node_two_people_already_shared():
    snapshots = [
        {"index": 0, "person_id": "p1", "terms": {"t1": ["Baustoff mit Geschichte", 2]}},
        {"index": 1, "person_id": "p2", "terms": {"t1": ["Vorzeitiger Gebäudeabriss", 3]}},
    ]

    assert find_late_renames(snapshots) == [
        {
            "index": 1,
            "term_id": "t1",
            "from": "Baustoff mit Geschichte",
            "to": "Vorzeitiger Gebäudeabriss",
            "mentions_before": 2,
        }
    ]


def test_find_late_renames_leaves_the_still_private_and_the_unchanged_alone():
    # A node one person has mentioned may still be renamed (D5 allows exactly
    # that), and a node that keeps its name is not a rename at all.
    snapshots = [
        {"index": 0, "person_id": "p1", "terms": {"t1": ["Erster Name", 1], "t2": ["Fest", 4]}},
        {"index": 1, "person_id": "p2", "terms": {"t1": ["Besserer Name", 2], "t2": ["Fest", 5]}},
    ]

    assert find_late_renames(snapshots) == []


def test_score_run_reports_satisfied_and_missed_expectations(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    persons = [store.create_person(started_at=float(i)) for i in range(4)]
    shared = store.get_or_create_term("Recycling-Beton", created_at=1.0)
    other_a = store.get_or_create_term("Holzbau", created_at=2.0)
    other_b = store.get_or_create_term("Bodenpreise", created_at=3.0)
    store.add_edge(persons[0].id, shared.id, created_at=4.0)
    store.add_edge(persons[3].id, shared.id, created_at=5.0)
    store.add_edge(persons[1].id, other_a.id, created_at=6.0)
    store.add_edge(persons[2].id, other_b.id, created_at=7.0)

    expectations = {
        "expected_merges": [
            {"concept": "Recycling-Beton", "interviews": [0, 3]},
            {"concept": "Ländlicher Leerstand", "interviews": [1, 2]},
        ]
    }

    report = score_run(store, expectations, [p.id for p in persons])

    assert report["satisfied"] == 1
    assert report["total"] == 2
    assert report["score"] == 0.5
    by_concept = {g["concept"]: g for g in report["groups"]}
    assert by_concept["Recycling-Beton"]["merged"] is True
    assert by_concept["Recycling-Beton"]["label"] == "Recycling-Beton"
    assert by_concept["Ländlicher Leerstand"]["merged"] is False
    assert report["term_count"] == 3


def test_score_run_handles_an_interview_without_terms(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    persons = [store.create_person(started_at=float(i)) for i in range(2)]

    report = score_run(
        store, {"expected_merges": [{"concept": "X", "interviews": [0, 1]}]}, [p.id for p in persons]
    )

    assert report["satisfied"] == 0
    assert report["groups"][0]["merged"] is False
    store.close()


def test_score_run_never_credits_a_group_whose_interviews_were_not_all_replayed(tmp_path):
    """A truncated run (--limit) must not report a merge that could not happen.

    With only interview 0 replayed, the group [0, 5] has exactly one present
    member; intersecting a single term set would hand back that set and claim a
    merge — of a concept the group never even names.
    """
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    persons = [store.create_person(started_at=float(i)) for i in range(2)]
    term = store.get_or_create_term("Recycling-Beton", created_at=1.0)
    store.add_edge(persons[0].id, term.id, created_at=2.0)
    store.add_edge(persons[1].id, term.id, created_at=3.0)

    expectations = {
        "expected_merges": [
            {"concept": "Recycling-Beton", "interviews": [0, 1]},
            {"concept": "Bodenversiegelung", "interviews": [0, 5]},
        ]
    }

    report = score_run(store, expectations, [p.id for p in persons])

    by_concept = {g["concept"]: g for g in report["groups"]}
    assert by_concept["Bodenversiegelung"]["merged"] is False
    assert by_concept["Bodenversiegelung"]["complete"] is False
    assert by_concept["Bodenversiegelung"]["missing_interviews"] == [5]
    assert by_concept["Bodenversiegelung"]["label"] is None
    assert by_concept["Recycling-Beton"]["complete"] is True
    # only the fully replayed group is scorable at all
    assert report["satisfied"] == 1
    assert report["total"] == 1
    assert report["score"] == 1.0
    assert report["complete_corpus"] is False
    assert report["incomplete"] == ["Bodenversiegelung"]
    store.close()


def test_score_run_marks_a_fully_replayed_corpus_as_complete(tmp_path):
    cfg = Config(data_dir=tmp_path / "state")
    store = Store.open(cfg.db_path)
    persons = [store.create_person(started_at=float(i)) for i in range(2)]

    report = score_run(
        store, {"expected_merges": [{"concept": "X", "interviews": [0, 1]}]}, [p.id for p in persons]
    )

    assert report["complete_corpus"] is True
    assert report["incomplete"] == []
    assert report["total"] == 1
    store.close()
