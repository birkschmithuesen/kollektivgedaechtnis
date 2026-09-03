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


def _material(*paare, last_person_id=None, positionen=None) -> Material:
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
        x, y = (positionen or {}).get(label, (None, None))
        weights.append(TermWeight(label, mentions, created, frozenset(sprecher), x, y))
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


# --- Nähe schlägt Häufigkeit (Birk, 2026-09-02, am Ausstellungstag) ----------


def test_ein_verbundener_begriff_schlaegt_den_haeufigeren_fremden():
    """🔴 Birks Einwand am laufenden Betrieb: „alle Begriffe, die genommen
    werden, sollen sehr eng an der letzten interviewten Person dran sein, am
    besten mit ihr direkt connected. Da würde ich eher Begriffe nehmen, die im
    Zweifelsfall ein, zwei Personen weniger genannt haben."

    Gemessen, warum es vorher wegdriftete: `_naehe` ist ein Jaccard über
    Sprechermengen und liefert **exakt 0**, sobald zwei Begriffe keine einzige
    Person teilen. Eine gerade befragte Person bringt aber frische Begriffe
    mit, die noch niemand sonst gesagt hat — also war die Nähe zu allem 0, und
    in `max(key=(naehe, mentions, label))` entschied der ZWEITE Schlüssel.
    Damit gewann der meistgenannte Begriff des ganzen Tages, Bild für Bild.

    Am echten Graphen der Station gemessen (10 Personen, 29 Begriffe): 1 von 5
    Pflichtbegriffen stammte von der zuletzt befragten Person.
    """
    material = _material(
        # Der Tagessieger — von Menschen, die mit p9 nichts zu tun haben.
        ("Tagessieger fremd", 4, 100.0, {"p1", "p2", "p3", "p4"}),
        # Ihr eigener Begriff: der Anker.
        ("Ihr eigener", 2, 200.0, {"p9", "p8"}),
        # p8 hat einen Begriff MIT ihr geteilt, ist also verbunden — dieser
        # Begriff hier liegt zwei Kanten entfernt und hat WENIGER Nennungen.
        ("Verbunden ueber p8", 2, 150.0, {"p8", "p7"}),
    )
    gewaehlt = select_required(material, count=2, last_person_id="p9")
    labels = [w.label for w in gewaehlt]

    assert labels[0] == "Ihr eigener", labels
    assert "Verbunden ueber p8" in labels, (
        f"der verbundene Begriff (2x) muss den fremden Tagessieger (4x) schlagen: {labels}"
    )
    assert "Tagessieger fremd" not in labels, labels


def test_ohne_verbundene_begriffe_gilt_weiter_die_haeufigkeit():
    """Die Gegenprobe: Die Stufe darf nicht zur Sperre werden.

    Hat die letzte Person mit niemandem etwas gemeinsam, gibt es keine Stufe 1
    — dann muss die Auswahl weiterlaufen wie vorher und die Plätze mit den
    häufigsten Begriffen füllen, statt leer zu bleiben."""
    material = _material(
        ("Fremd haeufig", 4, 100.0, {"p1", "p2", "p3", "p4"}),
        ("Fremd selten", 1, 110.0, {"p1"}),
        ("Ihr eigener", 1, 200.0, {"p9"}),
    )
    gewaehlt = select_required(material, count=3, last_person_id="p9")
    labels = [w.label for w in gewaehlt]

    assert labels[0] == "Ihr eigener", labels
    assert len(gewaehlt) == 3, f"die Liste muss voll werden: {labels}"
    assert "Fremd haeufig" in labels, labels


def test_die_nachbarschaftsachse_nimmt_ihren_begriff_auch_bei_geringerer_naehe():
    """🔴 Nachgeschärft nach einer FEHLGESCHLAGENEN Mutationsprobe (2026-09-02).

    Die erste Fassung dieses Tests belegte nichts: Man konnte den Vorrang in
    der Nachbarschaftsachse ersatzlos streichen und alle Tests blieben grün.
    Der Grund ist lehrreich — ein Begriff, der über eine gemeinsame Person mit
    der letzten Befragten verbunden ist, hat zu deren Anker meist ohnehin eine
    Jaccard-Nähe über 0. Die Nähe erledigte den Fall also allein, und der
    Vorrang lief mit, ohne je den Ausschlag zu geben.

    Wirksam wird er genau dort, wo die beiden Kräfte GEGENEINANDER stehen: ein
    Begriff der letzten Person mit GERINGERER Nähe zum Anker als ein fremder.
    Ohne Vorrang gewinnt der fremde, mit Vorrang ihrer — und das ist Birks
    Anforderung („im Zweifelsfall ein, zwei Personen weniger, dafür verbunden").
    """
    material = _material(
        # Ihr häufigster Begriff wird der Anker.
        ("Anker von ihr", 2, 500.0, {"p9", "p1"}),
        # Ihr zweiter: Nähe zum Anker = |{p9}| / |{p9,p1,p30}| = 1/3.
        ("Ihr zweiter", 1, 400.0, {"p9", "p30"}),
        # Ein Fremder, der dem Anker NÄHER ist: |{p1}| / |{p9,p1}| = 1/2.
        # Ohne den Vorrang gewinnt er den einen Nachbarschaftsplatz.
        ("Fremd aber naeher", 1, 300.0, {"p1"}),
    )
    # count=3 ergibt genau EINEN Nachbarschaftsplatz — sonst kämen beide
    # hinein und der Test bewiese nur, dass die Liste voll wird.
    gewaehlt = select_required(material, count=3, last_person_id="p9")
    labels = [w.label for w in gewaehlt]

    assert labels[0] == "Anker von ihr", labels
    assert labels[1] == "Ihr zweiter", (
        f"der Nachbarschaftsplatz gehoert ihrem Begriff, obwohl der fremde "
        f"naeher am Anker liegt: {labels}"
    )


def test_die_nachbarn_liegen_raeumlich_beieinander_wenn_positionen_da_sind():
    """🔴 Birk an der Wand, 2026-09-02: „Die blauen / Nachbarn sind oftmals
    über eine andere Person verbunden und erscheinen daher im Graphen sehr weit
    auseinander."

    Der Code hatte diesen Einwand vorweggenommen und anders entschieden:
    „Bildschirmnähe IST geteilte Sprecherschaft, nur als Ergebnis statt als
    Ursache." Die Annahme trägt nicht. Gemessen am Graphen der Station
    (36 Begriffe, Feld 2694 × 1553 px), letzte ausgewertete Person p15:

        Jaccard über Sprecher:  Abstände min 220, max 1153, Mittel 695 px
        räumlich:               Abstände min 191, max  882, Mittel 482 px

    Der Grund ist mechanisch: Zwei Begriffe teilen eine Person, aber diese
    Person hat zwanzig weitere Begriffe genannt — das Layout zieht sie
    auseinander, die Jaccard-Zahl weiss davon nichts.

    Die Sorge aus dem alten Kommentar bleibt gültig und wird nicht widerlegt:
    Positionen hängen am Layoutlauf. Deshalb der Rückfall im Test darunter.
    """
    # Beide Kandidaten stehen auf DERSELBEN Stufe (sie teilen p1 mit dem
    # Anker) — sonst pruefte der Test den Personenvorrang statt die Lage.
    # Was sie unterscheidet, ist genau der Streitpunkt: Der eine ist ueber
    # gemeinsame Sprecher naeher, der andere im Bild.
    paare = (
        ("Anker", 3, 500.0, {"p9", "p1", "p2"}),
        ("Weit weg, mehr geteilte Sprecher", 3, 400.0, {"p1", "p2", "p3"}),
        ("Direkt daneben, kaum geteilt", 3, 300.0, {"p1", "p20", "p21"}),
        # Fuer die Neuheitsachse, damit sie nicht in den Nachbarschaftsplatz
        # hineinregiert.
        ("Juengster Begriff", 2, 900.0, {"p30", "p31"}),
    )
    lagen = {
        "Anker": (0.0, 0.0),
        "Weit weg, mehr geteilte Sprecher": (2000.0, 1500.0),
        "Direkt daneben, kaum geteilt": (60.0, 40.0),
        "Juengster Begriff": (900.0, 900.0),
    }
    # count=3 ergibt genau EINEN Nachbarschaftsplatz — bei 2 kaeme die Auswahl
    # aus der Auffuellschleife und der Test bewiese nichts ueber diese Achse.
    labels = [
        w.label
        for w in select_required(
            _material(*paare, positionen=lagen), count=3, last_person_id="p9"
        )
    ]

    assert labels[0] == "Anker", labels
    assert labels[1] == "Direkt daneben, kaum geteilt", (
        f"der raeumlich nahe Begriff muss den gewinnen, der ueber gemeinsame "
        f"Sprecher naeher ist, aber am anderen Ende des Feldes liegt: {labels}"
    )


def test_ohne_positionen_gilt_weiter_die_sprechernaehe():
    """Der Rückfall, und er ist keine Formsache.

    Ein frischer Graph hat noch kein Layout: `x`/`y` sind dann `None`, und
    zwar für ALLE Knoten. Eine Auswahl, die darauf rechnet, verglich sonst
    lauter Unendlichkeiten und fiele auf die Reihenfolge der Liste zurück —
    die Nachbarschaftsachse bedeutete nichts mehr, ohne dass es auffiele."""
    paare = (
        ("Anker", 3, 500.0, {"p9", "p1", "p2"}),
        ("Weit weg, mehr geteilte Sprecher", 3, 400.0, {"p1", "p2", "p3"}),
        ("Direkt daneben, kaum geteilt", 3, 300.0, {"p1", "p20", "p21"}),
        ("Juengster Begriff", 2, 900.0, {"p30", "p31"}),
    )
    labels = [
        w.label
        for w in select_required(_material(*paare), count=3, last_person_id="p9")
    ]

    # Dasselbe Material, nur ohne Lagen: jetzt gewinnt wieder der Begriff mit
    # den meisten gemeinsamen Sprechern — und damit ist auch der Test darueber
    # ein echter Beleg und kein Zufall der Reihenfolge.
    assert labels[1] == "Weit weg, mehr geteilte Sprecher", labels
