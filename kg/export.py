"""Complete graph.json after every change — no delta mechanism (spec 11).

This file is also the read-only interface for Tool 2 („Kollektivtraum"), so it
carries the full state including quotes and flags; consumers filter.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from kg.semantik import eigenster_ort, entzerre, semantische_lage, verwandte


#: Zwischenspeicher fuer die semantische Lage: {Begriffsmenge -> Lage}.
#:
#: t-SNE ueber 54 Begriffe kostet rund eine Sekunde. `graph.json` wird bei
#: jedem Zustandswechsel neu gebaut und vom Spiegel-Uploader alle 3 s
#: abgeholt — ohne diesen Speicher liefe die Rechnung im Sekundentakt und
#: blockierte den Kern. Der Schluessel ist die MENGE der Begriffe: Solange
#: keiner dazukommt oder verschwindet, aendert sich die Karte nicht.
def _neben_der_datenbank(store) -> Path:
    """Wo der Embedding-Cache liegt: neben der Hauptdatenbank (spec 6.2).

    `cfg.embedding_cache_path` führt dorthin, aber `build_graph` bekommt keine
    cfg — es wird an vielen Stellen aufgerufen, auch aus Werkzeugen und Tests.

    🔴 Defensiv, weil hier auch STUBS ankommen: `tests/test_export_in_dream.py`
    reicht einen `_FakeStore` herein, der nur `list_terms` und Verwandtes kann.
    Ein `store.conn` darauf warf, und damit fiel `graph.json` aus — an dem die
    ganze Wand hängt. Ohne Datenbankpfad gibt es eben keine semantische
    Ansicht; das ist genau der Zustand, den ein Stub abbilden soll.
    """
    conn = getattr(store, "conn", None)
    if conn is None:
        return Path("data") / "embeddings.sqlite3"
    try:
        zeile = conn.execute("PRAGMA database_list").fetchone()
    except Exception:  # noqa: BLE001 — ein Stub darf alles Mögliche sein
        return Path("data") / "embeddings.sqlite3"
    haupt = Path(zeile[2]) if zeile and zeile[2] else Path("data/kg.db")
    return haupt.parent / "embeddings.sqlite3"


_SEMANTIK_CACHE: tuple[frozenset[str], dict[str, tuple[float, float]]] | None = None
_VERWANDT_CACHE: tuple[frozenset[str], dict[str, list[str]]] | None = None


def _verwandte(store, labels: list[str]) -> dict[str, list[str]]:
    """Wie `_semantische_lage`: gecacht ueber die Begriffsmenge, weil das
    Skalarprodukt ueber 54x3584 Zahlen sonst bei jedem Abruf liefe."""
    global _VERWANDT_CACHE
    schluessel = frozenset(labels)
    if _VERWANDT_CACHE is not None and _VERWANDT_CACHE[0] == schluessel:
        return _VERWANDT_CACHE[1]
    raus = verwandte(_neben_der_datenbank(store), labels)
    _VERWANDT_CACHE = (schluessel, raus)
    return raus


def _semantische_lage(store, labels: list[str]) -> dict[str, tuple[float, float]]:
    global _SEMANTIK_CACHE
    db = _neben_der_datenbank(store)
    # 🔴 DER EMBEDDING-BESTAND GEHOERT IN DEN SCHLUESSEL (gemessen 2026-09-03).
    #
    # Vorher hing der Cache allein an der Menge der Etiketten. Werden Begriffe
    # UMBENANNT und die Vektoren dazu nachtraeglich geholt, aendert sich die
    # Menge danach nicht mehr — der Cache lieferte weiter die alte Rechnung,
    # in der die neun umbenannten Begriffe gar keine Lage hatten. An der Wand
    # blieben sie an ihrer SOZIALEN Position stehen und zogen die
    # Bedeutungsansicht auf das Doppelte auseinander (Birk: „einige begriffe
    # sind ganz weit aussen und machen den graphen unnoetig gross").
    #
    # Die Aenderungszeit der Cache-Datei genuegt: Sie springt bei jedem neuen
    # Vektor, und ein Vergleich kostet einen `stat`.
    try:
        stand = db.stat().st_mtime_ns if db.exists() else 0
    except OSError:
        stand = 0
    schluessel = (frozenset(labels), stand)
    if _SEMANTIK_CACHE is not None and _SEMANTIK_CACHE[0] == schluessel:
        return _SEMANTIK_CACHE[1]
    # Der Pfad neben der Hauptdatenbank — `cfg.embedding_cache_path` fuehrt
    # dorthin, aber `build_graph` bekommt keine cfg (es wird an vielen Stellen
    # aufgerufen, auch aus Werkzeugen). `PRAGMA database_list` liefert den
    # Ort der geoeffneten Datei, und der Cache liegt per Spec daneben.
    lage = semantische_lage(db, labels)
    _SEMANTIK_CACHE = (schluessel, lage)
    return lage


def build_graph(store) -> dict:
    positions = store.get_positions()
    nodes: list[dict] = []

    # 🔴 Die ZWEITE Anordnung (Birk, 2026-09-02): `sx`/`sy` liegen neben
    # `x`/`y` und ordnen nach BEDEUTUNG statt nach gemeinsamen Sprechern. Die
    # Wand blendet auf Knopfdruck zwischen beiden ueber (kg.semantik).
    # Fehlt sie — keine Embeddings, zu wenige Begriffe, Rechnung gescheitert —
    # bleiben die Felder weg und die Wand bietet den Umschalter nicht an.
    alle_labels = [t.label for t in store.list_terms() if not t.hidden]
    sem = _semantische_lage(store, alle_labels)
    # Was inhaltlich nebeneinanderliegt, auch wenn es niemand zusammen gesagt
    # hat — die Information, die der Graph selbst nicht hat.
    nachbarn = _verwandte(store, alle_labels)
    begriffe_je_person: dict[str, list[str]] = {}
    if sem:
        etikett = {t.id: t.label for t in store.list_terms()}
        for kante in store.list_edges():
            label = etikett.get(kante.term_id)
            if label:
                begriffe_je_person.setdefault(kante.person_id, []).append(label)

    # Wie viele Menschen jeden Begriff gesagt haben — daraus ergibt sich der
    # EIGENSTE Begriff einer Person (kg.semantik.eigenster_ort).
    sprecherzahl: dict[str, int] = {}
    for labels in begriffe_je_person.values():
        for label in set(labels):
            sprecherzahl[label] = sprecherzahl.get(label, 0) + 1

    # Erst alle Orte bestimmen, dann in EINEM Durchgang entzerren: Ein
    # Verdraengen je Person waere von der Reihenfolge abhaengig und ergaebe
    # bei jedem Abruf ein anderes Bild.
    roh = {}
    if sem:
        for person in store.list_persons():
            ort = eigenster_ort(sem, begriffe_je_person.get(person.id, []), sprecherzahl)
            if ort is not None:
                roh[person.id] = ort
    person_orte = entzerre(roh) if roh else {}

    for person in store.list_persons():
        x, y = positions.get(person.id, (None, None))
        sp = person_orte.get(person.id)
        nodes.append(
            {
                "id": person.id,
                "type": "person",
                "portrait": _portrait_url(person.portrait_path),
                # Null, solange sich niemand vorgestellt hat oder der Operator
                # den verhörten Namen gelöscht hat. Die Wand zeigt ihn nur im
                # Zitat-Overlay beim Antippen, nie dauerhaft am Porträt.
                "name": person.name,
                "created_at": person.started_at,
                "hidden": person.hidden,
                "x": x,
                "y": y,
                # 🔴 Nur DA, wenn es sie gibt — nicht als `null`. Ohne
                # Embeddings, mit zu wenigen Begriffen oder nach einer
                # gescheiterten Rechnung fehlen die Felder ganz, und der
                # Vertrag mit Tool 2 ist derselbe wie vor dieser Ansicht
                # (`tests/test_dream_contract.py` haelt das fest). Die Wand
                # prueft ohnehin auf `typeof === 'number'`.
                **({"sx": sp[0], "sy": sp[1]} if sp else {}),
            }
        )

    for term in store.list_terms():
        x, y = positions.get(term.id, (None, None))
        nodes.append(
            {
                "id": term.id,
                "type": "term",
                "label": term.label,
                "mentions": store.mention_count(term.id),
                "created_at": term.created_at,
                "hidden": term.hidden,
                "x": x,
                "y": y,
                **(
                    {"sx": sem[term.label][0], "sy": sem[term.label][1]}
                    if term.label in sem
                    else {}
                ),
                **({"verwandt": nachbarn[term.label]} if nachbarn.get(term.label) else {}),
            }
        )

    # 🔴 `evidence` nur, wenn es eine gibt (Birk, 2026-09-02): die Textstelle
    # aus dem Interview, auf die sich dieser Begriff bei DIESER Person stuetzt.
    # Ein leeres Feld waere schlechter als gar keins -- es saehe aus wie „wir
    # haben nachgesehen und nichts gefunden", und der Unterschied zu „diese
    # Spalte gab es damals noch nicht" ginge verloren.
    edges = []
    for e in store.list_edges():
        kante = {"id": e.id, "source": e.person_id, "target": e.term_id}
        if e.evidence:
            kante["evidence"] = e.evidence
        edges.append(kante)

    # Welche Begriffe der Traum gerade benutzt (Birk, 2026-08-30): „Der Graph
    # soll die Begriffe hervorheben, die gerade zur Bildgenerierung genutzt
    # werden." Berechnet, NICHT von Tool 2 gemeldet — Tool 1 darf Tool 2 nicht
    # kennen (spec §9, die Kopplung geht nur in eine Richtung: Tool 2 pollt
    # diese Datei). Möglich ist das nur, weil die Auswahl seit 2026-08-30
    # mechanisch aus zwei Zahlen folgt (`kg2.weighting.select_required`):
    # dieselben Eingaben ergeben hier dieselbe Liste wie dort, ohne dass ein
    # Wert hin und her laufen müsste.
    #
    # Der Import steht bewusst hier unten und nicht oben: Er ist die EINZIGE
    # Stelle, an der Tool 1 etwas aus `kg2` liest, und ein Fehlschlag darf den
    # Export nicht kosten — ohne Tool 2 im Pfad bleibt `in_dream` schlicht
    # überall False und die Wand sieht aus wie vorher.
    dream_labels: dict[str, str] = {}
    try:
        from kg2.weighting import build_material, select_required

        material = build_material({"nodes": nodes, "edges": edges})
        gewaehlt = select_required(material, last_person_id=material.last_person_id)
        # Die ROLLE, nicht nur ein Ja/Nein: Die Wand färbt nach ihr (Bauhaus-
        # Theme, Birk 2026-08-30), und die Rolle folgt aus der Reihenfolge, in
        # der `select_required` vergibt — Anker zuerst, dann die Nachbarschaft,
        # zuletzt das Jüngste. Hier nachgebildet statt dort zurückgegeben, weil
        # die Funktion eine reine Auswahl bleibt; ändert sich ihre Aufteilung,
        # ändert sich diese Zuordnung mit — deshalb liest sie dieselben
        # Regler-Konstanten und rät sie nicht.
        from kg2.weighting import NEIGHBOUR_SHARE, RECENCY_SHARE

        plaetze = max(0, len(gewaehlt) - 1)
        aus_neuheit = round(plaetze * RECENCY_SHARE)
        aus_naehe = min(plaetze - aus_neuheit, round(plaetze * NEIGHBOUR_SHARE))
        for i, w in enumerate(gewaehlt):
            if i == 0:
                dream_labels[w.label] = "anchor"
            elif i <= aus_naehe:
                dream_labels[w.label] = "neighbour"
            else:
                dream_labels[w.label] = "recent"
    except Exception:  # noqa: BLE001 — die Wand darf daran nicht scheitern
        dream_labels = {}
    for node in nodes:
        if node["type"] == "term":
            rolle = dream_labels.get(node.get("label") or "")
            node["in_dream"] = rolle is not None
            node["dream_role"] = rolle or ""

    return {
        "version": 1,
        "generated_at": time.time(),
        "max_terms": int(store.get_setting("max_terms", "1")),
        "nodes": nodes,
        "edges": edges,
        "quotes": _quotes(store),
        # 🔴 Die Widersprüche des Tages (Birk, 2026-09-02). Sie entstehen nach
        # jedem Interview in `kg.pipeline` und liegen als JSON in `setting` —
        # hier werden sie nur durchgereicht, damit die Wand sie zeigen kann,
        # ohne einen zweiten Weg zum Kern zu brauchen.
        # Ebenso: kein leeres Feld, wenn es nichts zu zeigen gibt.
        **({"widersprueche": wsp} if (wsp := _widersprueche(store)) else {}),
    }


def _widersprueche(store) -> list[dict]:
    """Was in `setting` steht, oder eine leere Liste.

    Defensiv gelesen: Ein halb geschriebener Eintrag darf `graph.json` nicht
    kosten — daran hängt die ganze Wand."""
    if not hasattr(store, "get_setting"):
        return []
    roh = store.get_setting("widersprueche", "")
    if not roh:
        return []
    try:
        werte = json.loads(roh)
    except (TypeError, ValueError):
        return []
    return werte if isinstance(werte, list) else []


def _quotes(store) -> list[dict]:
    """At most one quote per person.

    The pipeline never writes more than one these days, but older stores
    (never migrated — deletions are Birk's call, not this code's) can still
    hold several per person. `store.list_quotes()` is ordered by created_at,
    so keeping the first person_id we see keeps the oldest — the deliberate
    compromise for that leftover data.
    """
    seen: set[str] = set()
    quotes = []
    for q in store.list_quotes():
        if q.person_id in seen:
            continue
        seen.add(q.person_id)
        quotes.append({"id": q.id, "person_id": q.person_id, "text": q.text})
    return quotes


def write_graph_json(store, path: Path) -> dict:
    graph = build_graph(store)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return graph


def _portrait_url(portrait_path: str | None) -> str | None:
    if not portrait_path:
        return None
    return f"/media/portraits/{Path(portrait_path).name}"
