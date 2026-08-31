"""Time-lapse replay of the synthetic corpus (spec 9).

Text in, graph state out. STT is deliberately out of scope: the transcript log
is written directly, then the real pipeline runs unchanged.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Sequence
from pathlib import Path

from kg.pipeline import process_interview
from kg.transcript import TranscriptionEvent, TranscriptLog

INTERVIEW_LENGTH = 180.0  # synthetic spoken duration of one interview


def load_corpus(directory: Path) -> list[dict]:
    items = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(Path(directory).glob("*.json"))
    ]
    return sorted(items, key=lambda item: item["index"])


def replay(
    corpus: list[dict],
    store,
    cfg,
    llm,
    embedder,
    start_time: float = 1_700_000_000.0,
    spacing: float = 300.0,
    speed: float = 0.0,
    processor=process_interview,
    on_step=None,
) -> list[str]:
    transcript_log = TranscriptLog(cfg.transcript_log_path)
    person_ids: list[str] = []

    for position, item in enumerate(corpus):
        started_at = start_time + position * spacing
        stopped_at = started_at + INTERVIEW_LENGTH
        person = store.create_person(
            started_at=started_at, photo_path=None, portrait_path=None
        )
        # Spread the text over the interview so the time cut is exercised too.
        sentences = [s.strip() for s in item["text"].split(".") if s.strip()] or [item["text"]]
        step = INTERVIEW_LENGTH / (len(sentences) + 1)
        for offset, sentence in enumerate(sentences, start=1):
            transcript_log.append(
                TranscriptionEvent(
                    type="final", text=sentence + ".", timestamp=started_at + offset * step
                )
            )
        store.close_person(person.id, stopped_at=stopped_at, reason="text")
        processor(store, cfg, llm, embedder, transcript_log, person.id, started_at, stopped_at)
        person_ids.append(person.id)
        if on_step:
            on_step(item["index"], person.id)
        if speed > 0 and position + 1 < len(corpus):
            time.sleep(spacing / speed)

    return person_ids


def snapshot_labels(store, index: int, person_id: str) -> dict:
    """Every node's visible label and how many people said it, after one interview.

    The database keeps no rename history — a finished run only shows the labels
    that survived. D5 ("a node two people share never changes its name",
    Task 19c) is a statement about the run's *course*, so the run writes one of
    these lines per interview as it goes and `find_late_renames` reads the
    answer back off them.
    """
    return {
        "index": index,
        "person_id": person_id,
        "terms": {t.id: [t.label, store.mention_count(t.id)] for t in store.list_terms()},
    }


def find_late_renames(snapshots: Sequence[dict]) -> list[dict]:
    """Every D5 violation in a label audit: a node renamed after two people
    had already mentioned it. An empty list is the claim the run has to prove."""
    violations: list[dict] = []
    previous: dict[str, list] = {}
    for snapshot in snapshots:
        for term_id, (label, mentions) in snapshot["terms"].items():
            before = previous.get(term_id)
            if before is None or before[0] == label or before[1] < 2:
                continue
            violations.append(
                {
                    "index": snapshot["index"],
                    "term_id": term_id,
                    "from": before[0],
                    "to": label,
                    "mentions_before": before[1],
                }
            )
        previous = dict(snapshot["terms"])
    return violations


def score_run(store, expectations: dict, person_ids: list[str]) -> dict:
    """Score the graph against the documented expectations of Task 18.

    A truncated run (`--limit`) does not contain every interview an expectation
    group names. Such a group is NOT scorable: it could never have merged, so
    counting it either way would lie. It is reported with `complete: False`,
    always `merged: False`, and it is left out of `satisfied`/`total` — which
    is why `total` differs from `len(groups)` on a partial run, and why
    `complete_corpus` says so outright.
    """
    edges = store.list_edges()
    terms_by_person: dict[str, set[str]] = {}
    for edge in edges:
        terms_by_person.setdefault(edge.person_id, set()).add(edge.term_id)

    groups = []
    for expected in expectations.get("expected_merges", []):
        indices = expected["interviews"]
        missing = [i for i in indices if i >= len(person_ids)]
        term_sets = [terms_by_person.get(person_ids[i], set()) for i in indices if i not in missing]
        # `not missing` first: intersecting a single present set would hand back
        # that whole set and report a merge for a group of one.
        shared = (
            set.intersection(*term_sets)
            if not missing and term_sets and all(term_sets)
            else set()
        )
        term_id = sorted(shared)[0] if shared else None
        groups.append(
            {
                "concept": expected["concept"],
                "interviews": indices,
                "complete": not missing,
                "missing_interviews": missing,
                "merged": term_id is not None,
                "term_id": term_id,
                "label": store.get_term(term_id).label if term_id else None,
            }
        )

    scorable = [group for group in groups if group["complete"]]
    incomplete = [group["concept"] for group in groups if not group["complete"]]
    satisfied = sum(1 for group in scorable if group["merged"])
    return {
        "groups": groups,
        "satisfied": satisfied,
        "total": len(scorable),
        "score": round(satisfied / len(scorable), 3) if scorable else 0.0,
        "complete_corpus": not incomplete,
        "incomplete": incomplete,
        "term_count": len(store.list_terms()),
        "person_count": len(person_ids),
        "edge_count": len(edges),
    }


def main() -> None:
    import yaml

    from kg.config import load_config
    from kg.embeddings import build_embedder
    from kg.export import write_graph_json
    from kg.llm import build_llm
    from kg.store import Store

    parser = argparse.ArgumentParser(prog="sim.replay")
    parser.add_argument("--data", default="sim/data")
    parser.add_argument("--db", default="out/sim.db")
    parser.add_argument("--speed", type=float, default=0.0, help="0 = as fast as possible")
    parser.add_argument("--limit", type=int, default=0, help="stop after N interviews")
    parser.add_argument(
        "--hash-embedder", action="store_true", help="deterministic local hashing, no API call"
    )
    args = parser.parse_args()

    cfg = load_config()
    data = Path(args.data)
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    # A fresh run needs a fresh transcript log too.
    run_cfg = type(cfg)(**{**cfg.__dict__, "data_dir": db_path.parent})
    if run_cfg.transcript_log_path.exists():
        run_cfg.transcript_log_path.unlink()
    audit_path = db_path.parent / "labels.jsonl"
    audit_path.unlink(missing_ok=True)

    store = Store.open(db_path)
    # Genau derselbe Weg wie an der Station (kg/llm.py: build_llm) — sonst
    # misst der Regressionslauf nicht das, was am 01.09. läuft.
    llm = build_llm(cfg)
    # NB: built from `cfg`, not `run_cfg` — the embedding cache must live in the
    # real data_dir so a second run over the same corpus is free and offline.
    embedder = build_embedder(cfg, hash_only=args.hash_embedder)

    corpus = load_corpus(data / "interviews")
    if args.limit:
        corpus = corpus[: args.limit]

    def step(index: int, person_id: str) -> None:
        print(f"interview {index:03d} -> {person_id}")
        with audit_path.open("a", encoding="utf-8") as handle:
            line = json.dumps(snapshot_labels(store, index, person_id), ensure_ascii=False)
            handle.write(line + "\n")

    person_ids = replay(corpus, store, run_cfg, llm, embedder, speed=args.speed, on_step=step)

    snapshots = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    expectations = yaml.safe_load((data / "expectations.yaml").read_text(encoding="utf-8"))
    report = score_run(store, expectations, person_ids)
    # D5 (Task 19c): must be empty. Read off the audit the run itself wrote.
    report["late_renames"] = find_late_renames(snapshots)
    write_graph_json(store, db_path.parent / "graph.json")
    if not report["complete_corpus"]:
        print(
            f"PARTIAL RUN — {len(report['incomplete'])} of "
            f"{len(report['groups'])} expectation groups are not fully replayed "
            f"and are NOT scored: {', '.join(report['incomplete'])}. "
            "This score is not comparable to a full run."
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    store.close()


if __name__ == "__main__":
    main()
