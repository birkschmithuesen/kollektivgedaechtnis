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


def _material(*paare, last_person_id=None) -> Material:
    """Jedes Paar ist (label, mentions, created_at), optional gefolgt von einer
    Sprechermenge.

    Die Sprecher braucht es seit 2026-08-30: Sowohl die Nachbarschaftsachse
    (`_naehe`) als auch der wandernde Anker rechnen über `person_ids`, nicht
    über die blosse Zahl `mentions`. Ohne Angabe werden Sprecher erfunden, die
    zu der Nennungszahl passen.
    """
    weights = []
    for eintrag in paare:
        label, mentions, created = eintrag[0], eintrag[1], eintrag[2]
        sprecher = (
            eintrag[3]
            if len(eintrag) > 3
            else frozenset(f"p{i}" for i in range(mentions))
        )
        weights.append(TermWeight(label, mentions, created, frozenset(sprecher)))
    return Material(
        person_count=0,
        term_count=len(weights),
        edge_count=0,
        generated_at=None,
        shared=[w for w in weights if w.mentions >= 2],
        marginal=[w for w in weights if w.mentions == 1],
        quotes=[],
        last_person_id=last_person_id,
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


def test_die_regler_wirken_ueber_die_ganze_spanne():
    material = _material(
        ("Oft", 9, 10.0),
        ("Oft 2", 8, 20.0),
        ("Oft 3", 7, 30.0),
        ("Neu", 1, 900.0),
        ("Neu 2", 1, 950.0),
        ("Neu 3", 1, 990.0),
    )
    nur_haeufigkeit = [
        w.label for w in select_required(material, recency_share=0.0, neighbour_share=0.0)
    ]
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


def test_der_anker_wandert_mit_der_zuletzt_befragten_person():
    """Birks Entwurf, 2026-08-30: „Cooler wär's, wenn immer andere Felder
    angesehen werden ... es könnte das meistgenannte Wort in dem Bereich sein,
    wo die letzte Interviewperson zugeordnet war."

    Mein erster Entwurf nahm den Spitzenreiter des GANZEN Graphen als Anker —
    bei sechzig Interviews zeigt das immer dasselbe Feld, weil der oben bleibt.
    Der Anker springt jetzt dorthin, wo gerade jemand gesprochen hat, und nimmt
    von dort den meistgenannten Begriff. Das ist zugleich der Übergang zwischen
    den beiden Kräften: verankert im Zuletzt-Gesagten, gewichtet nach dem
    Oft-Gesagten.
    """
    material = _material(
        ("Tagessieger", 20, 10.0, {f"p{i}" for i in range(20)}),
        ("Bei der letzten Person, oft", 6, 20.0, {"p90", "p1", "p2", "p3", "p4", "p5"}),
        ("Bei der letzten Person, selten", 2, 30.0, {"p90", "p7"}),
        ("Anderswo", 5, 40.0, {"p50", "p51", "p52", "p53", "p54"}),
    )

    ohne = select_required(material)
    assert ohne[0].label == "Tagessieger", "ohne Person zählt der ganze Tag"

    mit = select_required(material, last_person_id="p90")
    assert mit[0].label == "Bei der letzten Person, oft", (
        "der Anker muss zur letzten Person springen — und dort den "
        "meistgenannten ihrer Begriffe nehmen, nicht irgendeinen"
    )


def test_eine_person_ohne_begriffe_faellt_auf_den_tagessieger_zurueck():
    """Ein Interview, aus dem nichts ins Material kam (zu kurz, unbrauchbar,
    vom Operator versteckt), darf den Traum nicht ohne Anker lassen."""
    material = _material(
        ("Tagessieger", 9, 10.0, {f"p{i}" for i in range(9)}),
        ("Zweiter", 4, 20.0, {"p1", "p2", "p3", "p4"}),
    )

    gewaehlt = select_required(material, last_person_id="p999-hat-nichts-gesagt")

    assert gewaehlt[0].label == "Tagessieger"


def test_die_nachbarn_teilen_sprecher_mit_dem_anker():
    """Die zweite Achse: Der Ausschnitt soll zusammenhängen. Ein Nachbar ohne
    gemeinsamen Sprecher wäre nur ein weiterer häufiger Begriff — und das Bild
    zeigte wieder mehrere Themen nebeneinander statt eines."""
    material = _material(
        ("Anker", 6, 10.0, {"p1", "p2", "p3", "p4", "p5", "p6"}),
        ("Nah dran", 4, 20.0, {"p1", "p2", "p3", "p9"}),
        ("Auch nah", 3, 30.0, {"p2", "p3", "p8"}),
        ("Voellig woanders", 5, 40.0, {"p50", "p51", "p52", "p53", "p54"}),
    )

    gewaehlt = select_required(
        material, count=3, recency_share=0.0, neighbour_share=1.0
    )
    nachbarn = gewaehlt[1:]

    assert nachbarn, "es müssen Nachbarplätze vergeben worden sein"
    anker_sprecher = set(gewaehlt[0].person_ids)
    for w in nachbarn:
        assert anker_sprecher & set(w.person_ids), f"{w.label} hängt nicht am Anker"
