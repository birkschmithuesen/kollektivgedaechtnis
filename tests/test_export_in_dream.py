"""Die Begriffe, aus denen gerade das Bild entsteht, sind an der Wand markiert.

Birk, 2026-08-30: „Der Graph soll die Begriffe hervorheben, die gerade zur
Bildgenerierung genutzt werden."

Der interessante Teil ist nicht die Farbe, sondern WOHER Tool 1 das weiß.
Tool 1 darf Tool 2 nicht kennen (spec §9 — die Kopplung geht nur in eine
Richtung: Tool 2 pollt `graph.json`, nicht umgekehrt). Möglich ist die
Markierung nur, weil die Auswahl seit 2026-08-30 mechanisch aus zwei Zahlen
folgt: dieselben Eingaben ergeben in `kg.export` dieselbe Liste wie in
`kg2.cycle`, ohne dass ein Wert übertragen werden müsste.

Diese Tests halten beide Hälften fest: dass die Markierung dieselbe Auswahl
trifft wie der Traum, und dass ein fehlendes Tool 2 den Export nicht kostet.
"""

from __future__ import annotations

from kg.export import build_graph
from kg2.weighting import build_material, select_required


class _FakeStore:
    """Nur so viel Store, wie `build_graph` anfasst."""

    def __init__(self, terms, persons=(), edges=(), settings=None):
        self._terms = terms
        self._persons = list(persons)
        self._edges = list(edges)
        self._settings = settings or {"max_terms": "32"}

    def get_positions(self):
        return {}

    def list_persons(self):
        return list(self._persons)

    def list_terms(self):
        return list(self._terms)

    def mention_count(self, term_id):
        return next(t.mentions for t in self._terms if t.id == term_id)

    def list_edges(self):
        return self._edges

    def list_quotes(self):
        return []

    def get_setting(self, key, default=None):
        return self._settings.get(key, default)


class _Person:
    def __init__(self, id):
        self.id = id
        self.portrait_path = None
        self.started_at = 0.0
        self.hidden = False
        # Namenlos, wie fast jede Person: In diesen Tests geht es um die
        # Begriffsknoten, aber der Export liest das Feld an jedem Personenknoten.
        self.name = None


class _Edge:
    def __init__(self, id, person_id, term_id):
        self.id = id
        self.person_id = person_id
        self.term_id = term_id


class _Term:
    def __init__(self, id, label, mentions, created_at, hidden=False):
        self.id = id
        self.label = label
        self.mentions = mentions
        self.created_at = created_at
        self.hidden = hidden


def _store():
    """Nennungen entstehen aus Person->Begriff-KANTEN, nicht aus einem
    mentions-Feld — `kg2.weighting.build_material` zaehlt die Kanten selbst
    (und ignoriert `mentions` im Knoten). Ein Fixture ohne Kanten liefert
    deshalb leeres Material, und der Test wuerde die Gleichheit zweier leerer
    Mengen bestaetigen statt der Auswahl."""
    terms = [
        _Term("t1", "Oft genannt", 9, 100.0),
        _Term("t2", "Auch oft", 7, 200.0),
        _Term("t3", "Mittelfeld", 4, 300.0),
        _Term("t4", "Alt und selten", 1, 50.0),
        _Term("t5", "Gerade eben", 1, 9999.0),
        _Term("t6", "Fast eben", 1, 9998.0),
    ]
    personen = [_Person(f"p{i}") for i in range(1, 10)]
    kanten = []
    for term in terms:
        for i in range(term.mentions):
            kanten.append(_Edge(f"e{term.id}-{i}", personen[i].id, term.id))
    return _FakeStore(terms, personen, kanten)


def test_jeder_begriffsknoten_sagt_ob_er_gerade_ins_bild_geht():
    graph = build_graph(_store())
    terms = [n for n in graph["nodes"] if n["type"] == "term"]

    assert terms, "keine Begriffe im Export"
    assert all("in_dream" in n for n in terms), "in_dream fehlt an einem Knoten"


def test_die_markierung_trifft_genau_die_auswahl_des_traums():
    """Die eigentliche Behauptung: keine zweite, ähnliche Logik, sondern
    dieselbe Funktion. Läuft die Auswahl hier auseinander, zeigt die Wand
    andere Begriffe, als tatsächlich ins Bild gehen — schlimmer als keine
    Markierung, weil sie etwas Falsches behauptet."""
    graph = build_graph(_store())
    markiert = {n["label"] for n in graph["nodes"] if n.get("in_dream")}

    material = build_material({"nodes": graph["nodes"], "edges": graph["edges"]})
    erwartet = {w.label for w in select_required(material)}

    assert markiert == erwartet
    assert markiert, "nichts markiert, obwohl Material da ist"


def test_jeder_markierte_begriff_traegt_seine_rolle():
    """Die Wand faerbt nach der Rolle (Bauhaus-Theme): Rot = Anker,
    Blau = Nachbarschaft, Gelb = das Juengste. Ohne Rolle im Export koennte
    die Projektion nur ein Ja/Nein zeigen, und die drei Achsen waeren an der
    Wand nicht mehr auseinanderzuhalten."""
    graph = build_graph(_store())
    markiert = [n for n in graph["nodes"] if n.get("in_dream")]

    assert markiert
    assert all(n["dream_role"] in {"anchor", "neighbour", "recent"} for n in markiert)
    rollen = [n["dream_role"] for n in markiert]
    assert rollen.count("anchor") == 1, "genau ein Anker, sonst faerbt Rot mehrfach"
    assert "neighbour" in rollen
    assert "recent" in rollen
    # Unmarkierte Begriffe tragen ein leeres Feld, nicht None: die Projektion
    # baut daraus einen Klassennamen.
    unmarkiert = [n for n in graph["nodes"] if n["type"] == "term" and not n["in_dream"]]
    assert all(n["dream_role"] == "" for n in unmarkiert)


def test_der_anker_ist_der_meistgenannte_und_die_nachbarn_haengen_an_ihm():
    """Der Kern des Entwurfs (Birk, 2026-08-30): nicht drei unabhaengige
    Ranglisten, sondern ein Anker und sein Umfeld. Die Nachbarn muessen
    Sprecher mit dem Anker teilen — sonst waere es wieder nur Haeufigkeit."""
    graph = build_graph(_store())
    rollen = {n["label"]: n["dream_role"] for n in graph["nodes"] if n.get("in_dream")}
    anker = [k for k, v in rollen.items() if v == "anchor"][0]
    nachbarn = [k for k, v in rollen.items() if v == "neighbour"]

    assert anker == "Oft genannt", "der Anker ist der meistgenannte Begriff"

    material = build_material({"nodes": graph["nodes"], "edges": graph["edges"]})
    sprecher = {w.label: set(w.person_ids) for w in material.shared + material.marginal}
    for nachbar in nachbarn:
        assert sprecher[anker] & sprecher[nachbar], (
            f"{nachbar} teilt keinen Sprecher mit dem Anker — das ist keine Nachbarschaft"
        )


def test_die_spitze_und_das_juengste_sind_beide_dabei():
    """Was die Markierung sichtbar machen soll: dass die Wand beides zeigt —
    worüber viele gesprochen haben UND was gerade erst gesagt wurde."""
    graph = build_graph(_store())
    markiert = {n["label"] for n in graph["nodes"] if n.get("in_dream")}

    assert "Oft genannt" in markiert
    assert "Gerade eben" in markiert


def test_ein_leerer_graph_markiert_nichts_und_kracht_nicht():
    """Vor dem ersten Interview. Ein Export, der hier scheitert, nimmt die
    ganze Wand mit (spec §8)."""
    graph = build_graph(_FakeStore([]))

    assert [n for n in graph["nodes"] if n.get("in_dream")] == []


def test_ohne_tool_2_bleibt_der_export_heil(monkeypatch):
    """Die Markierung ist ein Zusatz, keine Voraussetzung. Fällt der Import
    aus, muss die Wand aussehen wie vorher — nicht ausfallen."""
    import builtins

    echtes_import = builtins.__import__

    def kein_kg2(name, *args, **kwargs):
        if name.startswith("kg2"):
            raise ImportError("Tool 2 ist hier nicht installiert")
        return echtes_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", kein_kg2)

    graph = build_graph(_store())
    terms = [n for n in graph["nodes"] if n["type"] == "term"]

    assert terms, "der Export selbst muss weiterlaufen"
    assert all(n["in_dream"] is False for n in terms)
