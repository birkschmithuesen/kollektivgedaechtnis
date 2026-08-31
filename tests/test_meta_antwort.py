"""Der Traum darf keine Modell-Ausreden ausstellen (2026-08-31).

An der Wand stand als Traumsatz woertlich „language not specified", als
Bildmotiv „no explicit 'your MOTD' found". Beides kam mit HTTP 200 und
gueltigem Schema zurueck — fuer jede bestehende Pruefung ein einwandfreier
String.

**Was es NICHT war** (und das ist der Teil, der ohne diese Datei wieder
falsch geraten wird): leeres Material. Der Traum d3 hatte laut Datenbank
4 Personen, 15 Begriffe, 16 Kanten, und der gerenderte Prompt enthielt
nachweislich alle 15 Begriffe. `kg2/cycle.py` haelt den Leerfall ohnehin
seit Finding 2 ab. Das Modell (Kimi K2.6) hat bei vorhandenem Material
geantwortet, als saehe es keins — nicht reproduzierbar, aber sichtbar.

Deshalb sitzt die Reparatur dort, wo sie unabhaengig von der Ursache wirkt:
eine Antwort, die die AUFGABE beschreibt statt sie zu loesen, geht nicht an
die Wand.
"""

import pytest

from kg2.condense import _ist_meta_antwort

# Woertlich das, was am 2026-08-31 an der Wand stand bzw. in der Werkstatt-
# Ansicht lag. Nicht nachgebaut, sondern aus /api/dreams abgeschrieben.
GEMESSENE_AUSREDEN = [
    "language not specified",
    "no explicit 'your MOTD' found",
    "no explicit supporting detail",
    # Aus dem Nachstellen mit einer Person ohne Begriffe, gleiche Sitzung:
    "Ein einzelner Hauptsatz auf Deutsch, höchstens 16 Wörter, ohne Komma, "
    "ohne Nebensatz, ohne Gedankenstrich.",
    "Placeholder: Insert the actual image description here once material is provided.",
]

# Echte Saetze aus dem Betrieb (d1/d2, claude-opus-5) und aus dem Nachlauf mit
# Kimi. Der Filter MUSS diese durchlassen — ein zu breiter Filter, der gute
# Saetze wegwirft, waere schlimmer als der Fehler, den er verhindern soll.
ECHTE_SAETZE = [
    "Menschen bauen ihre Bauwagen mit Stroh und Hanf zwischen Blumenbeeten bis zum Ortsrand aus.",
    "Aus dem Serverschuppen läuft ein Warmwasserschlauch in den Bauwagen hinter dem "
    "blühenden Blumengarten.",
    "Ein Mann schraubt an einem Bauwagen in einem Gemeinschaftsgarten der Sonne entgegen "
    "während Kinder mit einer rollenden Stuhlröhre spielen",
    "Vor einem stillgelegten Fabrikgebäude stehen Bauwagen mit aufgestellten Rampen und "
    "geöffneten Türen",
    "People extend their construction trailers with straw and hemp between flower beds "
    "out to the edge of the village.",
    "From the server shed a hot-water hose runs into the construction wagon behind the "
    "flowering garden.",
    # Der Grenzfall, an dem ein zu eifriger Filter auffliegen wuerde: ein
    # echter Satz, der zufaellig EIN Wort aus dem FORM-Abschnitt enthaelt.
    "Höchstens zwei Menschen sitzen auf der Bank vor dem unfertigen Anbau.",
]


@pytest.mark.parametrize("text", GEMESSENE_AUSREDEN)
def test_ausreden_werden_erkannt(text):
    assert _ist_meta_antwort(text) is True


@pytest.mark.parametrize("satz", ECHTE_SAETZE)
def test_echte_saetze_gehen_durch(satz):
    assert _ist_meta_antwort(satz) is False


def test_leerer_text_ist_keine_ausrede():
    """Leer wird anderswo behandelt (leerer Satz -> eigener Fehler, leere
    Bildbeschreibung -> Rueckfall auf sentence_en). Dieser Filter darf sich
    darin nicht einmischen."""
    assert _ist_meta_antwort("") is False


def test_der_zyklus_haelt_die_leere_bereits_ab():
    """Gegenprobe zur Ursachensuche: `kg2/cycle.py` bricht bei
    `term_count == 0` mit „no material to condense" ab — diese Schutzpruefung
    existiert seit Finding 2 und musste NICHT neu gebaut werden.

    Der Test steht hier, damit die erste (falsche) Diagnose nicht erneut
    gestellt wird: „der Knopf traeumt ins Leere" war es nachweislich nicht.
    """
    import inspect

    from kg2 import cycle

    quelle = inspect.getsource(cycle)
    assert "material.term_count == 0" in quelle
    assert "no material to condense" in quelle
