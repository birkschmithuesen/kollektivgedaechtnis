"""Die Widersprüche des Tages (`kg.widerspruch`).

🔴 WARUM DIESE TESTS SCHARF SEIN MÜSSEN: Was hier herauskommt, steht an einer
Wand und wird Menschen zugeschrieben, die im Raum stehen. Ein erfundener
Gegensatz legt zwei Besuchern eine Haltung in den Mund, die sie nicht haben.

Zweitens läuft der Aufruf am Ende JEDER Interviewauswertung. Wirft er, kostet
er das Interview — die Begriffe sind zu dem Zeitpunkt zwar geschrieben, aber
die Person hängt mitten in der Pipeline.
"""

from __future__ import annotations

import pytest

from kg.widerspruch import MAX_PAARE, Widersprueche, finde_widersprueche

BEGRIFFE = [
    {"label": "Sanierung maroder Gebäude",
     "stimmen": [("Vicki", "Ich würde mir mehr sanierte Gebäude wünschen")]},
    {"label": "Wohnungszwangssanierung",
     "stimmen": [("Reza", "Dass Menschen nicht mehr aus ihren Wohnungen rausfliegen")]},
    {"label": "Lehmbau", "stimmen": [("Daniela", "auch mit Lehm")]},
]


class Modell:
    """Gibt zurück, was ihm mitgegeben wurde, und merkt sich den Auftrag."""

    def __init__(self, antwort):
        self.antwort = antwort
        self.auftraege: list[str] = []

    def parse(self, *, system, user, output_model):
        self.auftraege.append(user)
        if isinstance(self.antwort, Exception):
            raise self.antwort
        return output_model(**self.antwort)


def _paar(titel="Sanierung als Hoffnung und als Bedrohung", beleg_a="ja", beleg_b="nein"):
    return {
        "titel": titel,
        "eine": {"begriff": "Sanierung maroder Gebäude", "beleg": beleg_a},
        "andere": {"begriff": "Wohnungszwangssanierung", "beleg": beleg_b},
    }


def test_ein_vollstaendiges_paar_geht_durch():
    llm = Modell({"paare": [_paar()]})
    raus = finde_widersprueche(llm, BEGRIFFE)

    assert len(raus) == 1
    assert raus[0]["titel"] == "Sanierung als Hoffnung und als Bedrohung"
    assert raus[0]["eine"]["begriff"] == "Sanierung maroder Gebäude"


def test_das_material_traegt_die_belegstellen_mit():
    """Ohne die Stellen sähe das Modell nur Etiketten — und ein Widerspruch
    zwischen zwei Etiketten ist geraten, nicht gefunden."""
    llm = Modell({"paare": []})
    finde_widersprueche(llm, BEGRIFFE)

    auftrag = llm.auftraege[0]
    assert "Dass Menschen nicht mehr aus ihren Wohnungen rausfliegen" in auftrag
    assert "Reza" in auftrag


@pytest.mark.parametrize("fehlt", ["eine", "andere"])
def test_ein_paar_ohne_belegstelle_wird_verworfen(fehlt):
    """🔴 Die wichtigste Regel. Ohne Beleg ist es eine Behauptung des Modells,
    und die gehört nicht an eine Wand, an der Namen stehen."""
    paar = _paar()
    paar[fehlt]["beleg"] = "   "
    llm = Modell({"paare": [paar]})

    assert finde_widersprueche(llm, BEGRIFFE) == []


def test_ein_paar_ohne_titel_wird_verworfen():
    llm = Modell({"paare": [_paar(titel="  ")]})
    assert finde_widersprueche(llm, BEGRIFFE) == []


def test_es_werden_hoechstens_drei_paare_genommen():
    """Die Tafel zeigt sie untereinander; ein viertes rutscht unter den Rand."""
    llm = Modell({"paare": [_paar(titel=f"Nummer {i}") for i in range(6)]})
    raus = finde_widersprueche(llm, BEGRIFFE)
    assert len(raus) == MAX_PAARE


def test_ein_toter_anbieter_kostet_kein_interview():
    """🔴 Der Aufruf läuft am Ende JEDER Auswertung. Wirft er, hängt die
    Person mitten in der Pipeline."""
    llm = Modell(RuntimeError("Anbieter weg"))
    assert finde_widersprueche(llm, BEGRIFFE) == []


def test_zu_wenig_material_wird_gar_nicht_erst_gefragt():
    """Unter zwei Begriffen mit Belegen kann es keine zwei Seiten geben —
    dann ist der Aufruf verschwendetes Geld."""
    llm = Modell({"paare": [_paar()]})
    assert finde_widersprueche(llm, [BEGRIFFE[0]]) == []
    assert llm.auftraege == []


def test_begriffe_ohne_belegstellen_zaehlen_nicht_als_material():
    """Sie stünden im Auftrag als nackte Etiketten und verleiteten das Modell
    dazu, den Gegensatz aus dem Wort zu erfinden."""
    llm = Modell({"paare": [_paar()]})
    ohne = [{"label": "A", "stimmen": []}, {"label": "B", "stimmen": []}]
    assert finde_widersprueche(llm, ohne) == []
    assert llm.auftraege == []


def test_das_schema_erlaubt_eine_leere_antwort():
    """„Ich habe keinen gefunden" muss eine gültige Antwort sein — sonst
    erfindet das Modell einen, um das Schema zu erfüllen."""
    assert Widersprueche().paare == []
