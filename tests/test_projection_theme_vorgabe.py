"""Ohne `?theme=` laedt die Wand das Schwarzplan-Theme f.

Birk, 2026-09-01: „das standard graph layout soll f sein. also wenn kein
kommentar kommt, soll immer layout f geladen werden."

Vorher stand hier 'e' (Bauhaus, Vorgabe seit 2026-08-30). Der Wechsel kostet
nichts, was die Wand braucht: beide Themes tragen die Farbcodierung der drei
Auswahlachsen.

Warum ein Test und nicht nur die eine geaenderte Zeile: die Vorgabe ist genau
die Einstellung, die NIEMAND bemerkt, wenn sie zurueckfaellt — an der Wand
steht die vollstaendige Adresse mit `?theme=f`, dort faellt ein falscher
Default gar nicht auf. Bemerkt wird er nur da, wo ohne Parameter aufgerufen
wird, und das ist der Fall, den dieser Test festhaelt.
"""

import re
from pathlib import Path

import pytest

PROJECTION = Path("frontend/projection.html").read_text(encoding="utf-8")


def test_ohne_parameter_faellt_die_wand_auf_theme_f_zurueck():
    # Am Quelltext geprueft und nicht im Browser: die Zeile IST die
    # Entscheidung, und ein Browsertest dafuer braeuchte einen Server, nur um
    # eine Konstante zu lesen.
    treffer = re.search(
        r"KNOWN_THEMES\.includes\(requestedTheme\)\s*\?\s*requestedTheme\s*:\s*'([a-z])'",
        PROJECTION,
    )
    assert treffer, "die Theme-Vorgabe steht nicht mehr an der erwarteten Stelle"
    assert treffer.group(1) == "f", (
        f"die Vorgabe ist '{treffer.group(1)}', erwartet 'f' (Birk, 2026-09-01)"
    )


def test_die_vorgabe_ist_ein_theme_das_es_gibt():
    """Eine Vorgabe, die auf eine fehlende Datei zeigt, ergaebe eine leere
    Wand — und zwar unbeaufsichtigt, ohne dass jemand einen Fehler sieht."""
    treffer = re.search(
        r"KNOWN_THEMES\.includes\(requestedTheme\)\s*\?\s*requestedTheme\s*:\s*'([a-z])'",
        PROJECTION,
    )
    assert treffer, "die Theme-Vorgabe steht nicht mehr an der erwarteten Stelle"
    vorgabe = treffer.group(1)
    datei = Path(f"frontend/static/theme-{vorgabe}.css")
    assert datei.exists(), f"die Vorgabe zeigt auf {datei}, die es nicht gibt"

    # Und sie muss in der Liste der bekannten Themes stehen, sonst waere sie
    # ueber `?theme=` nicht einmal erreichbar.
    liste = re.search(r"KNOWN_THEMES\s*=\s*\[([^\]]*)\]", PROJECTION)
    assert liste, "KNOWN_THEMES steht nicht mehr an der erwarteten Stelle"
    assert f"'{vorgabe}'" in liste.group(1), f"'{vorgabe}' fehlt in KNOWN_THEMES"


@pytest.mark.parametrize("theme", ["a", "b", "c", "e", "f"])
def test_jedes_bekannte_theme_hat_seine_datei(theme):
    """`?theme=` validiert gegen KNOWN_THEMES; ein Name in der Liste ohne
    Datei ergaebe einen 404 auf einer unbeaufsichtigten Wand."""
    assert Path(f"frontend/static/theme-{theme}.css").exists()
