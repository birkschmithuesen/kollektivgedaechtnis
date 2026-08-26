"""The runbook must not describe a control that does not exist, and must not
carry template placeholders into the exhibition day. Tool 1's Task 21 rule.

Adapted from the plan's original Task 18 test file for one reason that could
not be worked around: Tasks 15-17 needed ANTHROPIC_API_KEY and
OPENROUTER_API_KEY to produce final calibrated values for the guiding
question, the visual register, the contradiction threshold, the strip mode
and the 40-image series, and neither key is available in this environment.
`min_interval_s` and `poll_interval_s` ARE genuinely calibrated (the floor
run is pure arithmetic and needs no model). The rest are open decisions, and
this file checks that the runbook says so plainly instead of writing a
confident-looking number for a choice nobody has made — see
docs/operations.md, "Offene Entscheidungen".
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RUNBOOK = Path("docs/operations.md").read_text(encoding="utf-8")
EXAMPLE = Path("config2.example.toml").read_text(encoding="utf-8")


def tool2_section() -> str:
    start = RUNBOOK.index("## Kollektivtraum")
    return RUNBOOK[start:]


def open_decisions_section() -> str:
    section = tool2_section()
    start = section.index("### Offene Entscheidungen")
    return section[start:]


def test_the_runbook_has_a_tool_2_section():
    assert "## Kollektivtraum" in RUNBOOK


def test_the_runbook_carries_no_placeholders():
    """No template artefact may survive into the document the operator trusts
    on the festival morning."""
    section = tool2_section()
    for placeholder in ("TODO", "TBD", "XXX", "<hier", "…tragen", "PLATZHALTER", "‹", "›"):
        assert placeholder not in section, f"template placeholder {placeholder!r} left in the runbook"


def test_the_runbook_has_an_open_decisions_section():
    """Undetermined values must live somewhere clearly marked, not be scattered
    unlabelled through the calibrated-values section."""
    section = tool2_section()
    assert "### Offene Entscheidungen" in section


def test_every_determined_value_is_recorded_with_its_run():
    """min_interval_s and poll_interval_s are genuinely calibrated (the floor
    run is arithmetic, needs no model) and must be recorded as such."""
    section = tool2_section()
    for key in ("min_interval_s", "poll_interval_s"):
        assert key in section


def test_the_recorded_values_match_the_example_config():
    """A runbook that disagrees with the file the operator copies is worse than
    no runbook."""
    section = tool2_section()
    for key in ("min_interval_s", "contradiction_min_persons"):
        in_config = re.search(rf"^{key}\s*=\s*(\d+)", EXAMPLE, re.M)
        assert in_config, f"{key} missing from config2.example.toml"
        assert in_config.group(1) in section, (
            f"{key} = {in_config.group(1)} in config2.example.toml "
            f"but that value does not appear in the runbook"
        )


def test_the_min_interval_floor_finding_is_stated_plainly():
    """The Task 16 finding that matters: at the expected cadence the floor
    never binds. If this sentence disappears, someone will eventually 'tune'
    the value upward believing it does routine work."""
    section = tool2_section()
    assert "240" in section
    assert "nie" in section or "No-op" in section or "kein Normalbetrieb" in section
    assert "480" in section  # the day's actual cadence at 60 interviews / 8h


def test_the_unvalidated_value_is_marked_as_not_calibrated():
    """contradiction_min_persons is the spec's start value, not a calibration
    result. The runbook must not dress it up as one."""
    section = tool2_section()
    idx = section.index("contradiction_min_persons")
    # Somewhere near its first mention, the text must say it is unconfirmed.
    nearby = section[idx : idx + 800]
    assert "noch nicht kalibriert" in nearby.lower() or "nicht kalibriert" in nearby.lower()


@pytest.mark.parametrize(
    "undetermined_marker,command",
    [
        # The guiding question's wording.
        ("Wortlaut der Leitfrage", "sim.dream_calibrate questions"),
        # The contradiction threshold's confirmation.
        ("Bestätigung der Widerspruchsschwelle", "sim.dream_calibrate contradiction"),
        # The visual register.
        ("Bildregister", "sim.dream_register --out"),
        # The 40-image pre-render series.
        ("40-Bilder-Vorab-Serie", "sim.dream_prerender --out"),
    ],
)
def test_every_open_decision_is_listed_with_its_resolving_command(undetermined_marker, command):
    """Each open decision must be named AND paired with the exact command that
    produces the artefact it is decided from — otherwise the document cannot
    be told apart from one that quietly forgot a decision."""
    section = open_decisions_section()
    assert undetermined_marker in section, f"{undetermined_marker!r} not listed as an open decision"
    assert command in section, f"resolving command for {undetermined_marker!r} not given"


def test_the_history_strip_modes_are_reported_without_a_recommendation():
    """Task 17's ledger: three modes were measured, none is to be recommended
    here — Birk picks by looking at the rendered files."""
    section = open_decisions_section()
    start = section.index("Modus des Verlaufsstreifens")
    end = section.index("40-Bilder-Vorab-Serie")
    strip_block = section[start:end]

    for mode in ("cover", "aspect", "wrap"):
        assert mode in strip_block
    for word in ("empfehl", "Empfehl"):
        assert word not in strip_block, "the strip-mode comparison must not recommend one"


def test_the_image_contract_probe_is_named_as_an_open_action():
    section = tool2_section()
    assert "docs/dream-image-contract.md" in section
    assert "NOCH NICHT VERIFIZIERT" in section


def test_the_guiding_question_default_in_the_runbook_matches_the_config():
    """The runbook may quote the current provisional wording for context, but
    it must be the SAME string that ships in the example config — otherwise
    the two documents contradict each other."""
    question = re.search(r'^guiding_question\s*=\s*"([^"]+)"', EXAMPLE, re.M)
    assert question
    assert question.group(1) in tool2_section()


def test_the_runbook_describes_only_controls_that_exist():
    """Every control named must be reachable in the operator UI."""
    operator = Path("frontend2/operator.html").read_text(encoding="utf-8")
    section = tool2_section()

    if "Jetzt träumen" in section:
        assert "Jetzt träumen" in operator
    if "Schreibmaschine" in section:
        assert "Schreibmaschine" in operator
    if "verwerfen" in section:
        assert "verwerfen" in operator.lower() or "discard" in operator.lower()


def test_the_runbook_names_no_control_absent_from_the_operator_ui():
    """The converse check: things explicitly called out as NOT in the
    interface really must be absent from it."""
    operator = Path("frontend2/operator.html").read_text(encoding="utf-8")
    section = tool2_section()
    if "Nicht im Interface, absichtlich" in section:
        # Guiding question is shown read-only, never editable; register and
        # weighting have no control at all.
        assert 'id="guiding-question"' not in operator
        assert "Gewichtung" not in operator


@pytest.mark.parametrize(
    "claim,evidence",
    [
        # Every command the runbook tells the operator to type must exist.
        ("python -m kg2", "kg2/__main__.py"),
        ("--no-watch", "kg2/__main__.py"),
        ("sim.dream_calibrate questions", "sim/dream_calibrate.py"),
        ("sim.dream_calibrate contradiction", "sim/dream_calibrate.py"),
        ("sim.dream_register --out", "sim/dream_register.py"),
        ("sim.dream_prerender --out", "sim/dream_prerender.py"),
    ],
)
def test_every_command_the_runbook_names_really_exists(claim, evidence):
    section = tool2_section()
    if claim not in section:
        pytest.skip(f"{claim} is not mentioned")
    token = claim.split()[-1].lstrip("-")
    assert token in Path(evidence).read_text(encoding="utf-8")


def test_the_cross_machine_check_is_run_from_the_other_box():
    """The pitfall CR-1 names: a curl on the server succeeds even when the bind
    is wrong, and therefore proves nothing."""
    assert "Traum-Maschine" in RUNBOOK
    assert "nicht auf dem Ausstellungsrechner" in RUNBOOK


def test_the_runbook_says_what_a_restart_preserves():
    section = tool2_section()

    assert "Neustart" in section
    for preserved in ("Streifen", "Einstellung"):
        assert preserved in section
