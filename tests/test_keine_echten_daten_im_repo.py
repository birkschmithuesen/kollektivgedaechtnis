"""Echte Interviewdaten dürfen niemals in dieses Repo (Birk, 2026-08-29).

Das Repo ist **öffentlich**. Was Besucherinnen und Besucher vor Ort sagen, und
jedes Foto, das sie von sich machen lassen, bleibt lokal — wer es sichern will,
nimmt ein separates privates Repo.

Diese Datei ist der ausführbare Teil dieser Regel. `.gitignore` allein ist eine
Bitte: ein `git add -f`, ein umbenanntes Verzeichnis oder ein geänderter
`data_dir` hebeln sie aus, ohne dass irgendetwas rot wird. Die Tests hier
werden rot.

Bewusst NICHT geprüft wird, ob `.gitignore` bestimmte Zeilen enthält — das
wäre ein Change-Detector, der bei jeder Umformulierung bricht. Geprüft wird
die Eigenschaft: *diese Pfade sind ignoriert* und *im Index liegt nichts, was
nach echten Daten aussieht*, egal über welche Regel das erreicht wird.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30
    ).stdout


def is_ignored(path: str) -> bool:
    """`git check-ignore` — die Autorität, nicht ein Selbstbau-Parser von
    `.gitignore`. Exit 0 heißt: git würde diesen Pfad ignorieren."""
    return subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=REPO, capture_output=True, timeout=30,
    ).returncode == 0


#: Jeder Pfad, unter dem im Betrieb echte Daten entstehen. Abgeleitet aus
#: kg/config.py und kg2/config.py — wer dort ein neues Verzeichnis einführt,
#: trägt es hier nach.
ECHTE_DATEN = [
    "data/kg.db",                     # Transkripte, Personen, Begriffe
    "data/transcript.jsonl",          # jedes gesprochene Wort, roh
    "data/graph.json",                # der gewachsene Graph des Tages
    "data/embeddings.sqlite3",
    "data/photos/besucherin.jpg",     # das Originalfoto
    "data/portraits/besucherin.jpg",  # der Zuschnitt, der an die Wand geht
    "dream-data/dreams.sqlite3",      # Sätze über das Gesagte
    "dream-data/images/d1.png",
    "out/irgendein-lauf.txt",
]

#: Konfigurationen der konkreten Aufbauten. Ohne Schlüssel (die kommen aus der
#: Umgebung), aber mit telegram_chat_id und den Adressen im Ausstellungsnetz.
ECHTE_CONFIGS = ["config.toml", "config2.toml"]


@pytest.mark.parametrize("pfad", ECHTE_DATEN)
def test_echte_interviewdaten_sind_ignoriert(pfad):
    assert is_ignored(pfad), (
        f"{pfad} würde committet. Das Repo ist öffentlich; hier stehen die "
        f"Worte und Gesichter realer Menschen drin."
    )


@pytest.mark.parametrize("pfad", ECHTE_CONFIGS)
def test_die_benutzten_konfigurationen_sind_ignoriert(pfad):
    assert is_ignored(pfad), (
        f"{pfad} würde committet — mit telegram_chat_id und den Adressen der "
        f"Maschinen. Nur die *.example.toml gehören ins Repo."
    )


def test_die_beispielkonfigurationen_laufen_weiterhin_mit():
    """Die Gegenrichtung: Wer die echten Configs ignoriert, darf nicht aus
    Versehen auch die Vorlagen ausschließen — sonst kann niemand das Projekt
    mehr aufsetzen."""
    getrackt = set(git("ls-files").splitlines())
    for vorlage in ("config.example.toml", "config2.example.toml"):
        assert vorlage in getrackt, f"{vorlage} fehlt im Repo"


def test_kein_getracktes_verzeichnis_mit_echten_daten():
    """Der Index selbst, nicht die Regel: Liegt trotz allem etwas drin?

    Fängt den Fall, den `.gitignore` prinzipiell nicht abdecken kann — eine
    Datei, die per `git add -f` erzwungen wurde. Ein Ignore-Muster gilt nicht
    mehr, sobald eine Datei einmal im Index ist.
    """
    getrackt = git("ls-files").splitlines()
    verboten = [
        p for p in getrackt
        if p.startswith(("data/", "dream-data/", "out/", "sim/data/runs/"))
    ]
    assert not verboten, f"echte Daten liegen im Repo: {verboten}"


def test_die_einzigen_getrackten_bilder_sind_synthetisch():
    """16 Portraits liegen im Repo — die sind von einem Bildmodell erzeugt
    (sim/cut_portrait_sheet.py) und zeigen niemanden. Kommt ein Bild
    ANDERSWO her, ist es vermutlich ein echtes Gesicht.
    """
    bilder = [
        p for p in git("ls-files").splitlines()
        if p.lower().endswith((".jpg", ".jpeg", ".png"))
    ]
    fremd = [p for p in bilder if not p.startswith("sim/data/")]
    assert not fremd, (
        f"Bilder außerhalb von sim/data/: {fremd}. Wenn das echte Portraits "
        f"sind, dürfen sie nicht ins öffentliche Repo."
    )


def test_das_synthetische_material_ist_als_solches_gekennzeichnet():
    """Birk, 2026-08-29: „sollte vielleicht als synthetische Daten markiert
    sein.\"

    Die Kennzeichnung muss AM MATERIAL liegen, nicht nur im Haupt-README —
    wer in `sim/data/` landet (etwa über einen Link auf eine einzelne Datei),
    soll dort sehen, woher es kommt, ohne eine Ebene höher gehen zu müssen.
    """
    marker = REPO / "sim" / "data" / "README.md"
    assert marker.exists(), "sim/data/README.md fehlt — das Material ist nicht gekennzeichnet"
    text = marker.read_text(encoding="utf-8")
    assert "synthetisch" in text.lower()
    assert "claude-sonnet-5" in text, "das erzeugende Modell muss benannt sein"
    # Die Kernaussage, an der sich alles entscheidet.
    assert "keine echten menschen" in text.lower() or "keine realen" in text.lower()


def test_jedes_synthetische_interview_nennt_sein_modell():
    """Die Kennzeichnung darf nicht nur Prosa sein: Jede Datei trägt ihre
    Herkunft im eigenen `model`-Feld. Ein echtes Interview hätte das nicht —
    genauso wenig wie `planted_concept`, den vorher zugewiesenen Begriff.
    """
    import json

    dateien = sorted((REPO / "sim" / "data" / "interviews").glob("*.json"))
    assert dateien, "keine synthetischen Interviews gefunden"
    for pfad in dateien:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        assert daten.get("model"), f"{pfad.name} nennt kein erzeugendes Modell"
        assert "planted_concept" in daten, (
            f"{pfad.name} hat kein planted_concept — ohne diese Felder ist "
            f"nicht mehr erkennbar, dass die Datei generiert ist"
        )
