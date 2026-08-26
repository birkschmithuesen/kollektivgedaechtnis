"""Export seeded interviews as one Markdown file each, for reading them back
one at a time.

The wall shows the RESULT — nodes and edges. This exporter shows the WAY there:
per person, the full transcript exactly as it was heard, the terms that were
extracted from it, and the quotes that were kept. That is the artefact Birk
reads through interview by interview, so nothing here is summarised, shortened
or re-ordered: a term that looks wrong has to be traceable to the sentence it
came from, and that only works if the sentence is present verbatim.

Deterministic and offline: reads the simulation database, writes files. No LLM,
no network, no cost per run.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def _term_rows(conn: sqlite3.Connection, person_id: str) -> list[tuple[str, int]]:
    """This person's terms, each with the number of people sharing it.

    The share count is what makes a single interview readable against the whole:
    a term at 1 is this person's alone, a term at 7 is where the wall actually
    condenses. Counting it here rather than in the caller keeps the two numbers
    (label and reach) from ever drifting apart.
    """
    return conn.execute(
        """
        SELECT t.label, (SELECT COUNT(DISTINCT e2.person_id)
                         FROM edge e2 WHERE e2.term_id = t.id) AS reach
        FROM edge e
        JOIN term t ON t.id = e.term_id
        WHERE e.person_id = ?
        ORDER BY reach DESC, t.label COLLATE NOCASE
        """,
        (person_id,),
    ).fetchall()


def _quotes(conn: sqlite3.Connection, person_id: str) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            "SELECT text FROM quote WHERE person_id = ? ORDER BY created_at, id",
            (person_id,),
        )
    ]


def render_person(conn: sqlite3.Connection, person_id: str, index: int, total: int) -> str:
    row = conn.execute(
        "SELECT id, started_at, stopped_at, stop_reason, status, transcript FROM person WHERE id = ?",
        (person_id,),
    ).fetchone()
    pid, started, stopped, stop_reason, status, transcript = row
    duration = int((stopped or started) - started)
    terms = _term_rows(conn, pid)
    quotes = _quotes(conn, pid)

    lines: list[str] = []
    lines.append("---")
    lines.append(f"person_id: {pid}")
    lines.append(f"interview: {index} von {total}")
    lines.append(f"status: {status}")
    lines.append(f"stop_reason: {stop_reason}")
    lines.append(f"dauer_s: {duration}")
    lines.append(f"begriffe: {len(terms)}")
    lines.append(f"zitate: {len(quotes)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Interview {index} — {pid}")
    lines.append("")
    lines.append("## Transkript")
    lines.append("")
    # Verbatim, including the filler words: this is what the extractor saw, and
    # a cleaned-up version would quietly make its job look easier than it is.
    lines.append(transcript.strip() if transcript else "_(kein Transkript)_")
    lines.append("")
    lines.append("## Begriffe")
    lines.append("")
    if terms:
        lines.append("| Begriff | von wie vielen Menschen genannt |")
        lines.append("|---|---|")
        for label, reach in terms:
            lines.append(f"| {label} | {reach} |")
    else:
        lines.append("_(keine Begriffe — Extraktion fehlgeschlagen oder Interview zu kurz)_")
    lines.append("")
    lines.append("## Zitate")
    lines.append("")
    if quotes:
        for quote in quotes:
            lines.append(f"> {quote}")
            lines.append("")
    else:
        lines.append("_(keine Zitate)_")
        lines.append("")
    return "\n".join(lines)


def render_index(rows: list[tuple[str, int, int, int]], total: int) -> str:
    """One table over all interviews, so the reading order is a choice."""
    lines = ["# Interviews — Übersicht", ""]
    lines.append(f"{total} Interviews aus dem Simulationslauf. Ein Datei je Interview.")
    lines.append("")
    lines.append("| # | Person | Begriffe | Zitate | Transkript-Zeichen |")
    lines.append("|---|---|---|---|---|")
    for index, (pid, terms, quotes, chars) in enumerate(rows, start=1):
        lines.append(f"| {index} | [[interview-{index:02d}-{pid}]] | {terms} | {quotes} | {chars} |")
    lines.append("")
    return "\n".join(lines)


def export(db_path: Path, out_dir: Path) -> int:
    conn = sqlite3.connect(db_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    person_ids = [r[0] for r in conn.execute("SELECT id FROM person ORDER BY started_at, id")]
    total = len(person_ids)

    index_rows: list[tuple[str, int, int, int]] = []
    for index, pid in enumerate(person_ids, start=1):
        text = render_person(conn, pid, index, total)
        (out_dir / f"interview-{index:02d}-{pid}.md").write_text(text, encoding="utf-8")
        transcript = conn.execute("SELECT transcript FROM person WHERE id = ?", (pid,)).fetchone()[0]
        index_rows.append(
            (pid, len(_term_rows(conn, pid)), len(_quotes(conn, pid)), len(transcript or ""))
        )

    (out_dir / "00-uebersicht.md").write_text(render_index(index_rows, total), encoding="utf-8")
    conn.close()
    return total


def main() -> None:
    parser = argparse.ArgumentParser(prog="export_interviews_md")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    count = export(args.db, args.out)
    print(f"{count} Interviews -> {args.out}")


if __name__ == "__main__":
    main()
