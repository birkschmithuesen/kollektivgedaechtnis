"""Die mechanische Pflichtauswahl (`kg2.weighting.select_required`).

Warum es diese Tests gibt: Die Auswahl der Begriffe, die ins Bild müssen, war
bis zum 2026-08-30 Prosa im Prompt — und ist an einem einzigen Tag in BEIDE
Richtungen gekippt, je nachdem wie die Bitte formuliert war. Erst gewann die
Spitze immer (fünf gleiche Bilder), dann fiel sie ganz heraus (ein Satz aus
lauter Einmal-Nennungen). Genau deshalb ist die Auswahl jetzt Code, und Code
lässt sich festnageln. Diese Tests sind die Nägel.
"""

from __future__ import annotations

from kg2.weighting import Material, TermWeight, select_required


def _material(*paare: tuple[str, int, float]) -> Material:
    weights = [TermWeight(label, mentions, created) for label, mentions, created in paare]
    return Material(
        person_count=0,
        term_count=len(weights),
        edge_count=0,
        generated_at=None,
        shared=[w for w in weights if w.mentions >= 2],
        marginal=[w for w in weights if w.mentions == 1],
        quotes=[],
    )


def test_der_meistgenannte_begriff_ist_immer_dabei():
    """Der Fehler vom 2026-08-30: Ein von sieben Menschen genannter Begriff
    fiel aus dem Bild, während der Satz aus Einmal-Nennungen bestand."""
    material = _material(
        ("Pseudo-Abstimmung", 16, 100.0),
        ("Normen-Inventur", 7, 200.0),
        ("Randnotiz A", 1, 900.0),
        ("Randnotiz B", 1, 950.0),
        ("Randnotiz C", 1, 990.0),
    )
    gewaehlt = [w.label for w in select_required(material)]
    assert "Pseudo-Abstimmung" in gewaehlt


def test_die_juengsten_begriffe_kommen_auch_ohne_nennungen_hinein():
    """Die andere Richtung: Ein Begriff, den gerade eben jemand zum ersten Mal
    gesagt hat, hat eine Nennung und könnte über die Häufigkeit nie
    hereinkommen. Genau ihn soll die Neuheitsachse holen."""
    material = _material(
        ("Alt und oft", 9, 10.0),
        ("Alt und oft 2", 8, 20.0),
        ("Alt und oft 3", 7, 30.0),
        ("Gerade eben gesagt", 1, 9999.0),
    )
    gewaehlt = [w.label for w in select_required(material)]
    assert "Gerade eben gesagt" in gewaehlt


def test_die_beiden_regler_wirken_ueber_die_ganze_spanne():
    material = _material(
        ("Oft", 9, 10.0),
        ("Oft 2", 8, 20.0),
        ("Oft 3", 7, 30.0),
        ("Neu", 1, 900.0),
        ("Neu 2", 1, 950.0),
        ("Neu 3", 1, 990.0),
    )
    nur_haeufigkeit = [w.label for w in select_required(material, recency_share=0.0)]
    nur_neuheit = [w.label for w in select_required(material, recency_share=1.0)]
    assert nur_haeufigkeit[0] == "Oft"
    assert "Neu 3" in nur_neuheit
    assert nur_haeufigkeit != nur_neuheit
    assert len(select_required(material, count=3)) == 3
    assert select_required(material, count=0) == []


def test_ein_doppelt_qualifizierter_begriff_verbraucht_nur_einen_platz():
    """Ist derselbe Begriff sowohl der häufigste als auch der jüngste, darf die
    Liste nicht schrumpfen — sonst liefert sie je nach Materiallage mal fünf
    und mal drei Pflichtbegriffe, und der Regler bedeutet nichts mehr."""
    material = _material(
        ("Haeufig UND neu", 9, 9999.0),
        ("Zweiter", 5, 20.0),
        ("Dritter", 4, 30.0),
        ("Vierter", 3, 40.0),
        ("Fuenfter", 2, 50.0),
        ("Sechster", 1, 60.0),
    )
    gewaehlt = select_required(material)
    assert len(gewaehlt) == 5
    assert len({w.label for w in gewaehlt}) == 5


def test_leeres_material_liefert_eine_leere_liste_statt_zu_krachen():
    """Am frühen Vormittag, vor dem ersten Interview, ist der Graph leer — und
    ein Traum, der daran scheitert, wäre ein Ausfall auf der Ausstellungsfläche
    (spec §8)."""
    assert select_required(_material()) == []
