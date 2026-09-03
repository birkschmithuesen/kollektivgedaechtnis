"""Die zweite Anordnung: Nähe nach Bedeutung (`kg.semantik`).

🔴 Diese Rechnung sitzt im heissen Pfad: `build_graph` laeuft bei jedem
Zustandswechsel, und der Spiegel-Uploader holt `graph.json` alle 3 s. Faellt
sie um, faellt die Wand um. Deshalb fragt fast jeder Test hier dasselbe:
Kommt etwas Brauchbares zurueck, und wenn nicht — bleibt es bei einem leeren
Ergebnis statt bei einer Ausnahme?
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from kg.semantik import MIN_BEGRIFFE, eigenster_ort, entzerre, semantische_lage


def _db(tmp_path, eintraege):
    pfad = tmp_path / "embeddings.sqlite3"
    with sqlite3.connect(pfad) as conn:
        conn.execute(
            "CREATE TABLE embedding (model TEXT NOT NULL, text TEXT NOT NULL, "
            "vector TEXT NOT NULL, PRIMARY KEY (model, text))"
        )
        conn.executemany(
            "INSERT INTO embedding VALUES ('m', ?, ?)",
            [(t, json.dumps(v)) for t, v in eintraege.items()],
        )
    return pfad


def _wolke(n, dim=16):
    """n Vektoren in zwei klar getrennten Gruppen."""
    eintraege = {}
    for i in range(n):
        v = [0.0] * dim
        v[0] = 1.0 if i < n // 2 else 0.0
        v[1] = 0.0 if i < n // 2 else 1.0
        v[2 + (i % (dim - 2))] = 0.35  # Streuung innerhalb der Gruppe
        eintraege[f"begriff-{i}"] = v
    return eintraege


def test_die_lage_kommt_fuer_alle_begriffe_mit_embedding(tmp_path):
    eintraege = _wolke(12)
    lage = semantische_lage(_db(tmp_path, eintraege), list(eintraege))

    assert set(lage) == set(eintraege)
    assert all(isinstance(x, float) and isinstance(y, float) for x, y in lage.values())


def test_die_wolke_wird_auf_den_massstab_der_wand_gebracht(tmp_path):
    """Ohne das spraenge der Umschalter zwischen zwei voellig verschiedenen
    Groessen, und die Kamera muesste jedes Mal neu fassen."""
    eintraege = _wolke(14)
    lage = semantische_lage(_db(tmp_path, eintraege), list(eintraege), spanne=1000.0)

    xs = [p[0] for p in lage.values()]
    ys = [p[1] for p in lage.values()]
    grosse_achse = max(max(xs) - min(xs), max(ys) - min(ys))
    assert 400 <= grosse_achse <= 1100, grosse_achse


def test_ein_begriff_ohne_embedding_faellt_einfach_weg(tmp_path):
    """Er darf nicht bei (0,0) landen — dort laege er mitten im Bild und saehe
    aus wie eine Aussage, die er nicht ist."""
    eintraege = _wolke(10)
    lage = semantische_lage(_db(tmp_path, eintraege), [*eintraege, "brandneu"])

    assert "brandneu" not in lage
    assert len(lage) == 10


def test_zu_wenige_begriffe_ergeben_gar_keine_ansicht(tmp_path):
    """Frueh am Tag. Der Umschalter darf dann nicht erscheinen, statt eine
    Anordnung aus vier Punkten als Bedeutung auszugeben."""
    eintraege = _wolke(MIN_BEGRIFFE - 2)
    assert semantische_lage(_db(tmp_path, eintraege), list(eintraege)) == {}


def test_eine_fehlende_datenbank_kostet_die_wand_nichts(tmp_path):
    assert semantische_lage(tmp_path / "gibtesnicht.sqlite3", ["a", "b", "c"]) == {}


def test_kaputte_vektoren_werfen_nicht(tmp_path):
    """Ein halb geschriebener Cache-Eintrag darf `graph.json` nicht kosten."""
    pfad = _db(tmp_path, _wolke(10))
    with sqlite3.connect(pfad) as conn:
        conn.execute("INSERT INTO embedding VALUES ('m', 'kaputt', 'kein json')")
        conn.execute("INSERT INTO embedding VALUES ('m', 'leer', '[]')")
    lage = semantische_lage(pfad, [*_wolke(10), "kaputt", "leer"])
    assert "kaputt" not in lage and "leer" not in lage


def test_dieselbe_menge_ergibt_dieselbe_karte(tmp_path):
    """Sonst spraenge die Ansicht bei jedem Abruf von `graph.json`, ohne dass
    sich etwas geaendert haette."""
    eintraege = _wolke(12)
    pfad = _db(tmp_path, eintraege)
    a = semantische_lage(pfad, list(eintraege))
    b = semantische_lage(pfad, list(eintraege))
    assert a == b


def test_eine_person_steht_bei_ihrem_eigensten_begriff():
    """🔴 NICHT im Mittel ihrer Begriffe (Birk sah es an der Wand, 2026-09-02).

    Der Mittelwert zieht jeden, der über vieles spricht, in die Bildmitte —
    und das tun fast alle. Gemessen an 21 Personen: Personenfeld 459x559,
    während die Begriffe 958x951 einnahmen; 47 von 210 Paaren lagen näher
    beieinander als ein Portrait breit ist.

    Der eigenste Begriff ist der, den außer ihr am wenigsten andere genannt
    haben. Gemessen: Feld 939x931, kein Paar mehr zu eng.
    """
    lage = {"geteilt": (0.0, 0.0), "ihres": (500.0, 500.0)}
    # „geteilt" haben fünf Menschen gesagt, „ihres" nur sie.
    zahl = {"geteilt": 5, "ihres": 1}

    assert eigenster_ort(lage, ["geteilt", "ihres"], zahl) == (500.0, 500.0)


def test_bei_gleichstand_entscheidet_das_etikett():
    """Zwei Läufe über dieselben Daten müssen dieselbe Karte ergeben — sonst
    springt die Ansicht bei jedem Abruf von `graph.json`."""
    lage = {"a": (1.0, 1.0), "b": (2.0, 2.0)}
    zahl = {"a": 3, "b": 3}
    assert eigenster_ort(lage, ["b", "a"], zahl) == (1.0, 1.0)
    assert eigenster_ort(lage, ["a", "b"], zahl) == (1.0, 1.0)


def test_eine_person_ohne_begriffe_bekommt_keinen_ort():
    """Sie darf nicht bei (0,0) landen — dort lägen alle stummen Personen auf
    einem Haufen in der Bildmitte."""
    assert eigenster_ort({"a": (1.0, 2.0)}, [], {}) is None
    assert eigenster_ort({}, ["a"], {}) is None


def test_portraits_werden_auseinandergeschoben():
    """🔴 Auch beim eigensten Begriff bleiben Überschneidungen: Zwei Menschen
    können denselben eigensten Begriff haben und stehen dann exakt
    aufeinander. Gemessen vor der Entzerrung: 10 von 210 Paaren zu eng."""
    orte = {"p1": (0.0, 0.0), "p2": (10.0, 0.0), "p3": (500.0, 500.0)}
    raus = entzerre(orte, abstand=130.0)

    import math
    for a in raus:
        for b in raus:
            if a < b:
                assert math.dist(raus[a], raus[b]) >= 129.9, (a, b, raus)
    # Wer schon weit genug weg war, bleibt stehen.
    assert raus["p3"] == (500.0, 500.0)


def test_zwei_personen_exakt_aufeinander_kleben_nicht():
    """Bei Abstand 0 ist die Schubrichtung unbestimmt — ohne Sonderfall
    blieben die beiden für immer übereinander."""
    import math
    raus = entzerre({"p1": (7.0, 7.0), "p2": (7.0, 7.0)}, abstand=130.0)
    assert math.dist(raus["p1"], raus["p2"]) >= 129.9, raus


def test_die_entzerrung_ist_wiederholbar():
    """Zwei Läufe, dieselben Orte — sonst wandert die Wand bei jedem Abruf."""
    orte = {"p3": (0.0, 0.0), "p1": (10.0, 5.0), "p2": (20.0, 0.0)}
    assert entzerre(orte) == entzerre(orte)


def test_eine_einzelne_person_bleibt_wo_sie_ist():
    assert entzerre({"p1": (3.0, 4.0)}) == {"p1": (3.0, 4.0)}
    assert entzerre({}) == {}


def test_vektoren_verschiedener_laenge_werfen_nicht(tmp_path):
    """🔴 Gefunden durch eine Mutationsprobe (2026-09-02), und es ist ein
    echter Fehlerfall, kein konstruierter.

    Die Tabelle `embedding` hat `(model, text)` als Schluessel — nach einem
    Modellwechsel liegen Vektoren VERSCHIEDENER LAENGE nebeneinander im Cache
    (heute 3584 Dimensionen; ein anderes Modell liefert 1024 oder 1536). Ein
    numpy-Array daraus zu bauen wirft, und diese Rechnung sitzt im heissen
    Pfad von `graph.json`: Der Spiegel-Uploader holt es alle 3 s.

    Erwartet wird kein Absturz, sondern eine brauchbare Karte aus der
    Mehrheitslaenge — die Minderheit faellt weg wie ein Begriff ohne Embedding.
    """
    eintraege = dict(_wolke(12, dim=16))
    eintraege["fremdes-modell"] = [0.5] * 8   # andere Laenge
    lage = semantische_lage(_db(tmp_path, eintraege), list(eintraege))

    assert lage, "die ganze Ansicht ist an einem einzelnen Vektor gescheitert"
    assert "fremdes-modell" not in lage
    assert len(lage) == 12


def test_ohne_sklearn_bleibt_die_wand_stehen(tmp_path, monkeypatch):
    """🔴 Das Sicherheitsnetz, und es ist kein hypothetisches.

    `scikit-learn` wurde am 2026-09-02 fuer diese Ansicht nachinstalliert. Auf
    einem Rechner ohne das Paket — dem Windows-Vorgaenger, einem frischen
    Checkout, nach einem misslungenen `uv sync` — wirft der Import. Diese
    Rechnung sitzt aber im heissen Pfad von `graph.json`, das der
    Spiegel-Uploader alle 3 s abholt.

    Erwartet wird eine leere Karte, kein Absturz: Die Wand sieht dann aus wie
    vor diesem Feature, und der Umschalter erscheint gar nicht erst.
    """
    import builtins

    echtes_import = builtins.__import__

    def kein_sklearn(name, *args, **kwargs):
        if name.startswith("sklearn"):
            raise ImportError("kein scikit-learn auf dieser Maschine")
        return echtes_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", kein_sklearn)

    eintraege = _wolke(12)
    assert semantische_lage(_db(tmp_path, eintraege), list(eintraege)) == {}
