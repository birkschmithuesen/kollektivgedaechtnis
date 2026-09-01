"""graph.json -> the material stage 1 reasons over (spec §5.1).

Four rules, each with a reason that has to survive a later edit:

* **Weight by structure.** The numbers already exist in the payload, so nothing
  is computed on Tool 1's side. Frequently mentioned terms are dominant; single
  mentions are marginal detail, and are LABELLED as such in the rendered block
  so the model can place them as a detail rather than as a theme.
* **Quotes are collected but not rendered.** They stay in `graph.json` and in
  `Material.quotes` (T1§11 stores them for Tool 2's benefit), but
  `render_material` leaves them out by default (decided 2026-08-28): on the
  wall only the terms are visible, quotes appear only when a visitor taps a
  person. At 60 people they were 76% of the material block for something
  invisible in the room — the same argument spec §10 uses against
  graph-driven style. `include_quotes=True` exists for a side-by-side
  comparison run, not for production.
* **Hidden nodes are out.** `hidden: true` is the operator's emergency exit on
  the wall (T1§8); something pulled from the wall must not reappear in the
  dream.
* **`min_mentions` is NOT applied — Tool 1 and Tool 2 share the SAME rule, but
  are NOT coupled.** Both now read „all shared terms, topped up with the most
  recent single mentions" (see `select_marginal` below) — but each computes it
  independently, from its own two constants, not from one shared dial. This is
  deliberate, not an oversight to "clean up" later: the wall's `min_mentions`
  is a **physical** limit (screen area, font size) that an operator turns
  while thinking about legibility, not about content. If it also controlled
  what the dream reads, an operator adjusting font size at 14:00 would
  unknowingly change what the images are made from, and two exhibition days
  would stop being comparable. The dream's cap (`SINGLE_MENTION_BUDGET`,
  `SHARED_TERMS_SATURATION` below) is a **content** limit — keeping the model
  from drowning in footnotes — and is a property of the condensing procedure,
  not a knob either tool's operator turns.

* **A second axis: recency (added 2026-08-29).** The blocks above rank purely
  by final mention count, which encodes no order in time — at the end of the
  day seven mentions are seven mentions, whichever interview said the
  seventh one last, and a term that started late still catches up as more
  people repeat it. That is NOT what today's prompt gets wrong. The problem
  is a DELAY effect: at the moment THIS dream is rendered, a term that was
  first said in the interview that just finished has whatever count it has
  accumulated so far — usually one or two — and cannot compete with a term
  that has been repeated all morning. The dream can therefore fail to react
  to the interview that produced it, which the two screens standing side by
  side make visible. The fix chosen (2026-08-29, over multiplying the count
  by an aging factor — rejected because it would put an invented number in
  the prompt instead of the honest one) is `select_recent`/the „Zuletzt
  gesagt" block below: a second, independent block, unchanged mention counts,
  drawn from shared AND marginal terms alike so a just-said single mention
  that could never out-weigh the count-based block still gets to appear.

One thing the spec does not spell out and the code must: the payload's
`mentions` counts edges from hidden persons too, so it is RECOMPUTED here from
the surviving edges. Reading it off the node would leave a hidden visitor's
voice weighting the dream they were pulled out of.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TermWeight:
    label: str
    mentions: int
    #: The term node's `created_at` (0.0 if the payload did not carry a valid
    #: one) — the only thing `select_marginal` below uses to break ties among
    #: single mentions: the newest interview must be the one represented.
    created_at: float = 0.0
    #: Wer diesen Begriff genannt hat. Seit 2026-08-30 für die dritte
    #: Auswahlachse (`select_required`): Nähe zweier Begriffe heißt „dieselben
    #: Menschen haben beide gesagt", und dafür reicht `mentions` als blosse
    #: Zahl nicht — man braucht die Mengen selbst. Ein `frozenset`, weil
    #: `TermWeight` frozen ist und ein `set` das Hashing bräche.
    person_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Material:
    person_count: int
    term_count: int
    edge_count: int
    generated_at: float | None
    #: Said by two or more people, most-said first.
    shared: list[TermWeight]
    #: Said by exactly one person. Detail, not theme.
    marginal: list[TermWeight]
    quotes: list[str]
    #: Zu jedem Eintrag in `quotes` die Person, die ihn gesagt hat -- gleiche
    #: Reihenfolge, juengste Person zuerst. Getrennt gefuehrt, weil `quotes`
    #: eine reine Textliste bleiben muss: sim/dream_calibrate.py und die
    #: Pruefskripte zaehlen darauf.
    quote_person_ids: list[str] = field(default_factory=list)
    #: Die zuletzt hinzugekommene Person, nach `created_at` — der Anker fuer
    #: den Bildausschnitt (`select_required`, Birk 2026-08-30). Hier bestimmt
    #: und nicht vom Aufrufer uebergeben, weil das genau einmal falsch geraten
    #: werden kann: Personen-Ids sind Strings, und `sorted(ids)[-1]` liefert
    #: „p9" statt „p60". Der Zeitstempel ist die einzige verlaessliche Quelle.
    last_person_id: str | None = None


# Gefahren am 2026-08-28 (`sim.dream_calibrate terms`,
# `out/calibrate-terms.txt`): vier Graphgrößen × N ∈ {10, 20, 30} × X ∈ {15,
# 25, 40}, 36 echte Stufe-1-Läufe. Befund: Ab 30 Personen ist die Wahl
# WIRKUNGSLOS — dort liegen 25 bzw. 49 geteilte Begriffe vor, also über jedem
# geprüften X, und es kommen ohnehin null Einmal-Nennungen mehr durch. Ein
# Unterschied entsteht nur bei 3 und 10 Personen, und dort war unter allen
# neun Kombinationen kein Qualitätsunterschied lesbar (die Sätze sind
# durchweg brauchbar, sie greifen nur andere Randbegriffe auf).
#
# Deshalb bewusst NICHT weiter kalibriert: Die Werte sind gesetzt, nicht
# gemessen, weil die Messung gezeigt hat, dass es hier nichts zu messen gibt.
# N=20 ist die Mitte des geprüften Bereichs; X=25 ist die Zahl geteilter
# Begriffe, die der reale Graph bei 30 Personen erreicht — also etwa zur
# Tagesmitte, ab wann der Traum nur noch aus Geteiltem entsteht.
# Wer sie später ändert, sollte den Lauf wiederholen statt zu raten.
SINGLE_MENTION_BUDGET = 20  # N
SHARED_TERMS_SATURATION = 25  # X

#: How many of the newest terms go into the „Zuletzt gesagt" block (module
#: docstring). Deliberately small: an accent, not a second theme list — too
#: many and it competes with the weighting it is not meant to override.
RECENT_TERMS = 5

#: Von wie vielen der ZULETZT befragten Personen die Zitate in den Prompt
#: gehen (Birk, 2026-09-01: „zitat: nur von der letzten person mit rein
#: nehmen. nicht alle zitate. oder nur von den letzten drei personen").
#:
#: Warum ueberhaupt eine Grenze: Bei 60 Menschen machten alle Zitate 76 % des
#: Materialblocks aus -- deshalb waren sie bis dahin GANZ abgeschaltet. Das
#: warf mit dem Ballast auch das Einzige weg, was die Menschen woertlich
#: gesagt haben. Am 2026-09-01 fehlte im ersten Traum genau das: „alles ein
#: bisschen mehr mit der Natur verbunden" stand im Zitat, erreichte Stufe 1
#: nie, und im Bild war keine Natur.
#:
#: Drei und nicht eins: bei einer einzigen Stimme haengt das Bild des Tages an
#: der Person, die zufaellig zuletzt dran war. Drei ist die kleinste Zahl, die
#: dagegen etwas mittelt, und bleibt bei 60 Personen ein Fuenfzigstel des
#: Blocks statt drei Vierteln.
QUOTE_PERSONS = 3


def _empty_material() -> Material:
    return Material(0, 0, 0, None, [], [], [])


def _as_list(value) -> list:
    """Coerce whatever `graph.get(key, ())` returned into a list to iterate.

    `kg2.graph_client.fetch_graph` only validates that `version`, `nodes` and
    `edges` are present — never their value types (see review of an earlier
    task, and `kg2.trigger.absorbed_persons`, hardened against exactly this).
    A payload can therefore reach here with `nodes`, `edges` or `quotes` being
    a string, a dict, or anything else non-list. Treating that as „nothing
    there" rather than raising is what lets this module degrade to empty
    material instead of crashing whatever calls it.
    """
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        return []
    return list(value)


def build_material(graph: dict | None) -> Material:
    if not isinstance(graph, dict):
        return _empty_material()

    nodes = _as_list(graph.get("nodes", ()))
    # `.get("id")` rather than `node["id"]`: a person/term dict with no `id`
    # (or no `label`) is exactly the malformed shape this function promises to
    # survive. The `isinstance(..., str)` checks do double duty, same as in
    # `kg2.trigger.absorbed_persons`: a Tool 1 id/label is always a string, so
    # anything else is dropped before it can reach a set or dict key — an
    # unhashable value (a list) would otherwise crash the comprehension below,
    # and a hashable-but-wrong-type one (an int label) would later make
    # `weights.sort()` crash by comparing a str to it.
    persons = {
        node.get("id")
        for node in nodes
        if isinstance(node, dict)
        and node.get("type") == "person"
        and not node.get("hidden")
        and isinstance(node.get("id"), str)
    }
    terms = {
        node.get("id"): (node.get("label"), node.get("created_at"))
        for node in nodes
        if isinstance(node, dict)
        and node.get("type") == "term"
        and not node.get("hidden")
        and isinstance(node.get("id"), str)
        and isinstance(node.get("label"), str)
    }

    letzte_person = None
    letzte_zeit = None
    # Seit 2026-09-01 wird nicht nur die JUENGSTE Person gemerkt, sondern die
    # Zeit JEDER Person: die Zitatauswahl unten braucht eine Reihenfolge, und
    # Zitate selbst tragen keinen Zeitstempel (nur `person_id`).
    personen_zeit: dict[str, float] = {}
    for node in nodes:
        if not isinstance(node, dict) or node.get("type") != "person":
            continue
        if node.get("hidden") or not isinstance(node.get("id"), str):
            continue
        zeit = node.get("created_at")
        if not isinstance(zeit, (int, float)):
            continue
        personen_zeit[node["id"]] = float(zeit)
        if letzte_zeit is None or zeit > letzte_zeit:
            letzte_zeit, letzte_person = zeit, node["id"]

    counts: dict[str, int] = {}
    edge_count = 0
    sprecher: dict[str, set[str]] = {}
    for edge in _as_list(graph.get("edges", ())):
        if not isinstance(edge, dict):
            continue
        source, target = edge.get("source"), edge.get("target")
        # `source`/`target` must themselves be checked before the `in` test
        # below: set/dict membership hashes its argument, so an unhashable
        # source (e.g. a list) would raise here even though `persons`/`terms`
        # are already guaranteed to contain only strings.
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if source in persons and target in terms:
            counts[target] = counts.get(target, 0) + 1
            # Wer genau, nicht nur wie viele: die dritte Auswahlachse
            # (`select_required`, 2026-08-30) braucht die Sprechermengen, um
            # Naehe zwischen zwei Begriffen zu bestimmen.
            sprecher.setdefault(target, set()).add(source)
            edge_count += 1

    weights = []
    for tid, count in counts.items():
        label, created_at = terms[tid]
        if not isinstance(created_at, (int, float)):
            created_at = 0.0
        weights.append(
            TermWeight(label, count, created_at, frozenset(sprecher.get(tid, ())))
        )
    # Descending by count, then by label: two runs over the same graph must
    # produce the same prompt, or the record in spec §5.3 explains nothing.
    weights.sort(key=lambda w: (-w.mentions, w.label))

    roh_zitate = [
        quote
        for quote in _as_list(graph.get("quotes", ()))
        if isinstance(quote, dict)
        # Same hashability landmine as the edge loop above: `in persons` hashes
        # `person_id`, so an unhashable value (a list) must be filtered first.
        and isinstance(quote.get("person_id"), str)
        and quote.get("person_id") in persons
        and "text" in quote
    ]
    # JUENGSTE PERSON ZUERST. `render_material` schneidet danach bei den
    # letzten `quote_persons` Personen ab -- ohne diese Ordnung waere „die
    # letzten drei" die Reihenfolge, in der Tool 1 die Zitate zufaellig
    # ausliefert. `-personen_zeit[...]` sortiert absteigend, der zweite
    # Schluessel haelt die Ausgabe bei gleicher Zeit stabil (zwei Laeufe ueber
    # denselben Graphen muessen denselben Prompt ergeben, Spec §5.3).
    roh_zitate.sort(key=lambda q: (-personen_zeit.get(q["person_id"], 0.0), q["person_id"]))
    quotes = [q["text"] for q in roh_zitate]
    quote_person_ids = [q["person_id"] for q in roh_zitate]

    generated_at = graph.get("generated_at")
    if not isinstance(generated_at, (int, float)):
        generated_at = None

    return Material(
        person_count=len(persons),
        term_count=len(weights),
        edge_count=edge_count,
        generated_at=generated_at,
        shared=[w for w in weights if w.mentions >= 2],
        marginal=[w for w in weights if w.mentions == 1],
        quotes=quotes,
        quote_person_ids=quote_person_ids,
        last_person_id=letzte_person,
    )


def select_marginal(
    material: Material,
    *,
    budget: int = SINGLE_MENTION_BUDGET,
    saturation: int = SHARED_TERMS_SATURATION,
) -> list[TermWeight]:
    """The single mentions that make it into the prompt (decided 2026-08-28).

    All shared terms always go in — there is no cap on them, unlike the wall.
    Single mentions are topped up on a gliding budget that shrinks linearly to
    zero as the number of shared terms grows from 0 to `saturation`, so the
    transition falls out of the graph itself rather than a threshold or a
    stored day-part. The newest single mentions are kept, not the oldest, so
    the interview that just finished is guaranteed to be represented.
    """
    allowed = round(budget * max(0, 1 - len(material.shared) / saturation))
    if allowed <= 0:
        return []
    newest_first = sorted(material.marginal, key=lambda w: (-w.created_at, w.label))
    return newest_first[:allowed]


def select_recent(material: Material, *, count: int = RECENT_TERMS) -> list[TermWeight]:
    """The terms behind the „Zuletzt gesagt" block (module docstring).

    Drawn from `shared` AND `marginal` together — the recency axis is
    independent of the weighting axis, so a term that just entered the graph
    with a single mention belongs here exactly as much as one repeated all
    day. `shared` and `marginal` never overlap (a term is one or the other by
    construction), so this cannot itself produce a duplicate; the same term
    reappearing in BOTH this block and the weighted block above is expected,
    not a bug — it is how one gets doubly emphasised.
    """
    if count <= 0:
        return []
    newest_first = sorted(
        material.shared + material.marginal, key=lambda w: (-w.created_at, w.label)
    )
    return newest_first[:count]


#: Wie viele Begriffe VERBINDLICH ins Bild müssen (`select_required` unten).
#: Fünf, weil ein Bild etwa so viele Dinge tragen kann, ohne zur Aufzählung zu
#: werden — bei zehn beschreibt Stufe 1 einen Katalog, bei zwei fällt die
#: halbe Materiallage weg. Nicht kalibriert, sondern gesetzt: Der Wert ist ein
#: Regler für Birk (Operator-UI), keine Messgröße.
REQUIRED_TERMS = 5

#: Wie sich die fünf Pflichtplätze zwischen den beiden Achsen aufteilen:
#: 0.0 = alle nach Häufigkeit, 1.0 = alle nach Neuheit. 0.4 heißt drei
#: meistgenannte plus zwei jüngste.
#:
#: Warum es diesen Regler gibt (Birk, 2026-08-30): Die beiden Achsen ziehen
#: gegeneinander. Nur Häufigkeit heißt, dass das Bild bei sechzig Interviews
#: dasselbe zeigt wie bei zehn, weil die frühen Begriffe oben bleiben. Nur
#: Neuheit heißt, dass das, worüber alle geredet haben, aus dem Bild fällt.
#: Beides ist am Material passiert, beides an einem Tag.
RECENCY_SHARE = 0.4


#: Wie viele der Plätze über die NACHBARSCHAFT vergeben werden, statt über
#: Häufigkeit oder Neuheit: 0.0 = keiner, 1.0 = alle außer dem Anker.
#:
#: Warum es diese dritte Achse gibt (Birk, 2026-08-30): „Nimm Begriffe, die im
#: Graphen eng beieinander liegen — wir wollen einen inhaltlichen
#: Detailausschnitt des Graphen mit dem Bild zeigen." Häufigkeit und Neuheit
#: sind beides Ranglisten über EINZELNE Begriffe; sie wissen nichts davon, ob
#: die fünf Gewählten etwas miteinander zu tun haben. Genau das fehlte: Fünf
#: Spitzenreiter aus fünf verschiedenen Gesprächen ergeben ein Bild, das fünf
#: Themen nebeneinanderstellt, statt eines zu zeigen.
NEIGHBOUR_SHARE = 0.4


def _mitsprecher(material: Material) -> dict[str, set[str]]:
    """Wer hat welchen Begriff genannt — die Grundlage der Nachbarschaft.

    Nähe im Graphen heißt hier NICHT Bildschirmabstand: Der ist ein Ergebnis
    des Layout-Algorithmus und ändert sich, wenn jemand die Dichte verstellt.
    Nah sind zwei Begriffe, wenn DIESELBEN MENSCHEN sie genannt haben — das
    ist die Kante, die der Graph tatsächlich trägt (Person → Begriff), und sie
    bedeutet etwas: Zwei Begriffe, die immer wieder im selben Gespräch fallen,
    gehören inhaltlich zusammen, auch wenn kein Wort sie verbindet.
    """
    return {w.label: set(w.person_ids) for w in material.shared + material.marginal}


def _naehe(a: str, b: str, sprecher: dict[str, set[str]]) -> float:
    """Wie eng zwei Begriffe beieinander liegen, zwischen 0 und 1.

    Jaccard über die Sprechermengen: gemeinsame Sprecher geteilt durch alle,
    die eines von beidem gesagt haben. Nicht die rohe Zahl der Gemeinsamen —
    die würde Begriffe bevorzugen, die ohnehin überall vorkommen, und die
    Nachbarschaft wäre nur eine zweite Häufigkeitsliste.
    """
    x, y = sprecher.get(a, set()), sprecher.get(b, set())
    if not x or not y:
        return 0.0
    vereint = len(x | y)
    return len(x & y) / vereint if vereint else 0.0


def select_required(
    material: Material,
    *,
    count: int = REQUIRED_TERMS,
    recency_share: float = RECENCY_SHARE,
    neighbour_share: float = NEIGHBOUR_SHARE,
    allow_single_mentions: bool = True,
    last_person_id: str | None = None,
) -> list[TermWeight]:
    """Die Begriffe, die in DIESEM Bild vorkommen MÜSSEN — mechanisch bestimmt.

    Birks Einwand vom 2026-08-30, und er trifft: „Wie oft ein Begriff genannt
    wurde und wie lange er schon besteht, das sind harte Zahlen. Da könntest du
    doch einfach mit einem Script die Liste machen, die im Bild sein muss."

    Bis dahin bekam Stufe 1 die vollständige, nach Häufigkeit sortierte Liste
    — bei sechzig Interviews 49 geteilte Begriffe — und dazu die Prosa-Bitte,
    „das Meistgenannte" zu berücksichtigen. Das Ergebnis war beides Mal falsch,
    je nachdem wie die Bitte formuliert war: Einmal stand in allen fünf Bildern
    dasselbe (die Spitze gewann immer), einmal fiel der von sieben Menschen
    genannte Begriff ganz heraus, während der Satz aus lauter Einmal-Nennungen
    bestand. Eine Auswahl, die sich aus Zahlen ergibt, gehört nicht in einen
    Prompt, sondern in Code — dort ist sie nachvollziehbar, prüfbar und für
    Birk verstellbar, statt vom Formulierungsglück abzuhängen.

    ## Der Aufbau: ein Anker, dann seine Nachbarschaft

    Drei Achsen, alle aus dem Graphen, keine davon geschätzt. Sie sind aber
    NICHT gleichberechtigt nebeneinandergestellt, und das ist der Kern des
    Entwurfs (Birk, 2026-08-30: „Wir wollen einen inhaltlichen
    Detailausschnitt des Graphen mit dem Bild zeigen"):

    1. **Der Anker** ist der meistgenannte Begriff DER ZULETZT BEFRAGTEN
       PERSON — nicht der des ganzen Tages. Birks Entwurf, 2026-08-30, und er
       löst ein Problem, das mein erster hatte: Ein fester Anker über dem
       gesamten Graphen zeigt bei sechzig Interviews immer dasselbe Feld, weil
       der Spitzenreiter oben bleibt. Der Anker wandert jetzt mit den
       Gesprächen — er springt dorthin, wo gerade jemand gesprochen hat, und
       nimmt von dort den Begriff, den die meisten Menschen teilen. Damit ist
       er zugleich der Übergang zwischen den beiden Kräften: verankert im
       Zuletzt-Gesagten, gewichtet nach dem Oft-Gesagten. Ohne
       `last_person_id` (oder wenn diese Person keine Begriffe hat) fällt er
       auf den Spitzenreiter des ganzen Materials zurück.
    2. **Die Nachbarschaft** füllt den Großteil der übrigen Plätze: Begriffe,
       die dem bereits Gewählten am nächsten liegen. Nähe heißt „dieselben
       Menschen haben beide genannt" (`_naehe`), gemessen als Jaccard über die
       Sprechermengen. Gewählt wird jeweils der Begriff mit der größten Nähe
       zur bisherigen Auswahl — nicht nur zum Anker, sondern zur ganzen
       wachsenden Gruppe, damit der Ausschnitt zusammenwächst statt sternförmig
       um einen Punkt zu hängen.
    3. **Die Neuheit** bekommt die restlichen Plätze und darf die
       Nachbarschaft ausdrücklich verlassen: Was gerade erst gesagt wurde,
       gehört ins Bild, auch wenn es zum Rest (noch) nichts zu tun hat.

    Warum in dieser Reihenfolge und nicht als drei getrennte Ranglisten: Die
    ersten beiden Achsen beschreiben ZUSAMMENHANG, die dritte BEWEGUNG. Drei
    unabhängige Listen ergäben fünf Begriffe aus fünf verschiedenen Gesprächen
    — ein Bild, das fünf Themen nebeneinanderstellt, statt eines zu zeigen.
    Genau das war der Zustand vorher.

    Ein Wort zur „Nähe im Graphen", weil beide Lesarten dasselbe meinen: Birk
    dachte an den Bildschirmabstand, hier gerechnet wird über geteilte
    Sprecher. Das Layout ist fcose, also kraftbasiert, und Begriffe hängen an
    Personen — zwei Begriffe, die dieselben Menschen genannt haben, teilen
    Nachbarn und werden ins selbe Feld gezogen. Bildschirmnähe IST geteilte
    Sprecherschaft, nur als Ergebnis statt als Ursache. Gerechnet wird mit der
    Ursache: Die Bildschirmposition hängt am Layoutlauf und ändert sich, sobald
    jemand die Dichte verstellt oder das Fenster anders steht — ein Bild, das
    davon abhinge, sähe je nach Reglerstellung anders aus.


    Anteile: `neighbour_share` und `recency_share` teilen die Plätze NACH dem
    Anker auf. Bei fünf Plätzen und den Vorgaben (0.4 / 0.4) heißt das: ein
    Anker, zwei Nachbarn, zwei junge Begriffe. Beide Regler gehören in die
    Operator-UI; die Voreinstellungen sind gesetzt, nicht kalibriert.

    `allow_single_mentions=False` sperrt Einmal-Nennungen ganz aus. Nur für
    Kalibrierläufe, die `single_mention_budget=0` setzen: Sonst bekämen sie
    die Randbegriffe über diese Liste zurück, und der Regler, den sie messen
    wollen, bedeutete nichts mehr.
    """
    if count <= 0:
        return []

    alle = material.shared + material.marginal
    if not allow_single_mentions:
        alle = list(material.shared)
    if not alle:
        return []

    plaetze = count - 1  # der Anker belegt den ersten
    aus_neuheit = round(plaetze * max(0.0, min(1.0, recency_share)))
    aus_naehe = min(
        plaetze - aus_neuheit, round(plaetze * max(0.0, min(1.0, neighbour_share)))
    )

    haeufigste = sorted(alle, key=lambda w: (-w.mentions, w.label))
    juengste = sorted(alle, key=lambda w: (-w.created_at, w.label))
    sprecher = _mitsprecher(material)

    # Der Anker wandert mit den Gesprächen: der meistgenannte Begriff DER
    # ZULETZT BEFRAGTEN PERSON. Damit zeigt das Bild jedes Mal ein anderes
    # Feld des Graphen, statt sechzig Interviews lang um denselben
    # Spitzenreiter zu kreisen — und weil die Begriffe der letzten Person
    # ohnehin dicht beieinander liegen, hängen die Nachbarn danach thematisch
    # an dem, was gerade gesagt wurde. Fällt die Person aus (kein Wert, oder
    # keiner ihrer Begriffe hat es ins Material geschafft), gilt wieder der
    # Spitzenreiter des ganzen Tages.
    anker = haeufigste[0]
    if last_person_id is not None:
        von_ihr = [w for w in alle if last_person_id in w.person_ids]
        if von_ihr:
            anker = max(von_ihr, key=lambda w: (w.mentions, w.created_at, w.label))

    gewaehlt: list[TermWeight] = [anker]
    schon = {anker.label}

    # Die Nachbarschaft wächst um die bisherige Auswahl herum: Bewertet wird
    # gegen ALLE schon Gewählten, nicht nur gegen den Anker. Bei Gleichstand
    # (etwa ganz am Anfang, wenn noch niemand zwei Begriffe zusammen genannt
    # hat) entscheidet die Häufigkeit — sonst hinge die Auswahl an der
    # zufälligen Reihenfolge der Liste.
    for _ in range(aus_naehe):
        kandidaten = [w for w in alle if w.label not in schon]
        if not kandidaten:
            break
        bester = max(
            kandidaten,
            key=lambda w: (
                sum(_naehe(w.label, g.label, sprecher) for g in gewaehlt),
                w.mentions,
                w.label,
            ),
        )
        gewaehlt.append(bester)
        schon.add(bester.label)

    # Nur so viele Plätze, wie der Regler hergibt. Die Begrenzung ist NICHT
    # kosmetisch: Ohne sie nimmt diese Schleife jeden freien Platz, und
    # `recency_share=0.0` — „gar keine jungen Begriffe" — lieferte trotzdem
    # eine Liste voller Einmal-Nennungen, weil die Nachbarschaftsplätze bei
    # `neighbour_share=0.0` ebenfalls frei bleiben. Der Regler bedeutete dann
    # schlicht nichts, und das ist genau die Sorte stiller Wirkungslosigkeit,
    # gegen die die mechanische Auswahl gebaut wurde.
    vergeben = 0
    for w in juengste:
        if len(gewaehlt) >= count or vergeben >= aus_neuheit:
            break
        if w.label not in schon:
            gewaehlt.append(w)
            schon.add(w.label)
            vergeben += 1

    # Bleiben Plätze frei (weil eine Achse nur Duplikate lieferte), fülle mit
    # den nächsten häufigsten auf — die Liste soll `count` lang sein.
    for w in haeufigste:
        if len(gewaehlt) >= count:
            break
        if w.label not in schon:
            gewaehlt.append(w)
            schon.add(w.label)
    return gewaehlt


def render_material(
    material: Material,
    *,
    include_quotes: bool = False,
    quote_persons: int = QUOTE_PERSONS,
    single_mention_budget: int = SINGLE_MENTION_BUDGET,
    shared_terms_saturation: int = SHARED_TERMS_SATURATION,
    recent_terms: int = RECENT_TERMS,
    required_terms: int = REQUIRED_TERMS,
    recency_share: float = RECENCY_SHARE,
    last_person_id: str | None = None,
) -> str:
    """The German block that goes into stage 1's user message.

    Shared terms are never truncated. At Tool 1's documented ceiling of ~50
    persons (T1§2) this stays comfortably inside the model's window, and a
    silent cap would make the dream quietly stop reading the day's later
    interviews — the one failure this station cannot afford, because the
    strip is what makes drift visible. Single mentions ARE limited, by
    `select_marginal` above — on purpose, see the module docstring.

    `single_mention_budget`/`shared_terms_saturation`/`recent_terms` default
    to this module's constants and only exist as parameters so
    `sim.dream_calibrate terms`/`recency` can try other values (including 0,
    to switch the recency block off for comparison) without duplicating this
    function.
    """
    blocks: list[str] = []

    required = select_required(
        material,
        count=required_terms,
        recency_share=recency_share,
        allow_single_mentions=single_mention_budget > 0,
        last_person_id=last_person_id,
    )
    if required:
        lines = "\n".join(
            f"  {w.label} ({w.mentions}× genannt)" for w in required
        )
        blocks.append(
            "DIESE BEGRIFFE MÜSSEN INS BILD — alle, jeder als das was er "
            "meint, nicht nur als sein Wort. Sie sind nicht ausgewählt, "
            "sondern ausgerechnet: aus der Zahl der Menschen, die einen "
            "Begriff genannt haben, und aus dem Zeitpunkt, an dem er zuerst "
            "fiel. Steht einer nicht in deiner Bildbeschreibung, fehlt dem "
            "Bild etwas, worüber heute wirklich gesprochen wurde:\n" + lines
        )

    if material.shared:
        lines = "\n".join(f"  {w.mentions}× {w.label}" for w in material.shared)
        blocks.append(
            "Geteilte Begriffe — die Zahl sagt, wie viele Menschen sie genannt "
            "haben. Was oft genannt wurde, beherrscht das Bild:\n" + lines
        )

    marginal = select_marginal(
        material, budget=single_mention_budget, saturation=shared_terms_saturation
    )
    # 🔴 Was oben Pflicht ist, steht hier nicht noch einmal als Beiwerk
    # (Birk, 2026-09-01, am ersten Traum des Ausstellungstags).
    #
    # `select_required` zieht seine Begriffe aus `shared` UND `marginal`.
    # Solange kein Begriff von zwei Menschen genannt wurde -- also den ganzen
    # VORMITTAG -- ist `shared` leer und jeder Pflichtbegriff zwangslaeufig
    # auch eine Einmal-Nennung. Der Prompt sagte dann ueber dieselben Woerter
    # „MUESSEN INS BILD, als das was er meint" und zwei Absaetze spaeter
    # „Detail und Beiwerk, nicht Thema ... klein und am Rand".
    #
    # Gemessen an Traum d1 (1 Interview, 3 Begriffe): 3 von 3 Pflichtbegriffen
    # waren betroffen, und der bildstaerkste -- „Earthship" -- fehlte im Bild
    # vollstaendig, obwohl er als Pflicht gefuehrt war.
    #
    # Der Block selbst bleibt: Einmal-Nennungen, die NICHT Pflicht sind, sind
    # weiter genau das, was er sagt.
    pflicht_labels = {w.label for w in required}
    marginal = [w for w in marginal if w.label not in pflicht_labels]
    if marginal:
        lines = "\n".join(f"  {w.label}" for w in marginal)
        blocks.append(
            "Randnotizen — jede davon hat genau ein Mensch gesagt. Das sind "
            "Detail und Beiwerk, nicht Thema. Sie dürfen im Bild vorkommen, "
            "aber klein und am Rand:\n" + lines
        )

    recent = select_recent(material, count=recent_terms)
    if recent:
        lines = "\n".join(f"  {w.label}" for w in recent)
        blocks.append(
            "Zuletzt gesagt — die jüngsten Begriffe aus den letzten Interviews, "
            "unabhängig davon wie oft sie insgesamt genannt wurden. Mindestens "
            "einer davon soll im Bild vorkommen:\n" + lines
        )

    if include_quotes and material.quotes:
        # Nur die juengsten `quote_persons` Personen (siehe QUOTE_PERSONS).
        # Gezaehlt werden PERSONEN, nicht Zitate: haette jemand zwei Zitate,
        # waere „die letzten drei Zitate" sonst nur eine Person.
        gesehen: list[str] = []
        ausgewaehlt: list[str] = []
        for text, pid in zip(material.quotes, material.quote_person_ids):
            if pid not in gesehen:
                if len(gesehen) >= quote_persons:
                    break
                gesehen.append(pid)
            ausgewaehlt.append(text)
        # Ohne `quote_person_ids` (z. B. ein von Hand gebautes Material in
        # einem Test) faellt die Auswahl auf die ersten N Zitate zurueck,
        # statt still gar keins zu liefern.
        if not material.quote_person_ids:
            ausgewaehlt = material.quotes[:quote_persons]
        if ausgewaehlt:
            # Single-quoted f-string: the German quotation marks are literal
            # text, and a double-quoted one would end at the closing „ ".
            lines = "\n".join(f'  „{quote}"' for quote in ausgewaehlt)
            blocks.append(
                "Stimmen aus den zuletzt gefuehrten Interviews, woertlich. "
                "Das ist das Einzige, was die Menschen selbst gesagt haben -- "
                "die Begriffe oben sind bereits Verdichtungen davon:\n" + lines
            )

    return "\n\n".join(blocks)
