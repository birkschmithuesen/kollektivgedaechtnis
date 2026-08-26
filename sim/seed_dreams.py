"""Seed a dreams.sqlite3 directly, with no model calls (Tool 1's Task 20 rule).

The point of the pre-render series is LAYOUT — how a strip of forty reads at the
bottom of a 65″ screen, whether a 30-word sentence still fits under the image.
None of that needs real generation, and making it need real generation would
mean debugging Playwright at a euro a frame.

So: fictional sentences of realistic length, and images from a pool. The `--generate`
path in `sim/dream_prerender.py` swaps the pool for forty real ones once the
harness is known to be correct.
"""

from __future__ import annotations

from pathlib import Path

from kg2.config import DreamConfig
from kg2.store import DreamStore

#: Forty fictional dreams of one fictional festival day. Written to spec §5.1's
#: 20-40 word target, so the layout is judged against sentences the real system
#: would actually produce — a strip judged on eight-word captions proves nothing
#: about a thirty-word one.
#:
#: Invented outright, and deliberately not drawn from the corpus: these end up
#: in a review directory, and a half-formed dream of real people's words does
#: not belong there.
SENTENCES = [
    "In einem Hof, der gleichzeitig gegossen und bepflanzt wird, warten zwei Generationen darauf, dass die jeweils andere zuerst aufgibt.",
    "Die Bagger halten an, weil jemand vergessen hat, wem der Boden gehört, und die Baugrube füllt sich langsam mit Schilf.",
    "Ein Haus lernt sprechen und benutzt sein erstes Wort, um nach der Miete zu fragen, die niemand mehr aufbringen kann.",
    "Über der Umgehungsstraße hängt ein Dorf an Seilen, und die, die es gebaut haben, dürfen nicht darin wohnen.",
    "Hundert Klebepunkte auf einem Plan ergeben zusammen ein Gesicht, das niemand wiedererkennt und alle unterschrieben haben.",
    "Der Beton atmet zum ersten Mal aus, und was er ausatmet, ist der Staub aller Häuser, die vorher hier standen.",
    "In der Tiefgarage wächst ein Wald, dessen Bäume nach oben durch die Decke wollen und dabei sehr höflich bleiben.",
    "Eine Maschine plant ein Zuhause, das perfekt ist, bis auf den Geruch, und genau daran erkennt es jeder sofort.",
    "Die Fassade wird jeden Morgen neu gedruckt, und jeden Abend sammelt jemand die alte auf und trägt sie fort.",
    "Zwei Nachbarn teilen sich eine Wand und streiten seit zwölf Jahren darüber, auf welcher Seite sie eigentlich steht.",
    "Der Kran über dem Quartier dreht sich weiter, obwohl unten längst niemand mehr baut, und niemand traut sich, ihn abzustellen.",
    "Aus dem Leerstand im Erdgeschoss wächst nachts ein Marktplatz, der morgens wieder verschwindet und Krümel hinterlässt.",
    "Ein Dach aus Solarzellen wirft einen Schatten, in dem nichts mehr wächst, und alle finden das trotzdem richtig.",
    "Die Wohnung ist so klug geworden, dass sie ihre Bewohner beim Namen nennt und dabei jedes Mal zögert.",
    "Im Modell steht schon der Park, im Maßstab eins zu fünfhundert, wo draußen noch der Parkplatz auf sein Ende wartet.",
    "Ein Bagger und eine Buche stehen sich gegenüber, und beide warten darauf, dass eine Behörde endlich zurückschreibt.",
    "Die Bauakte wird so schwer, dass sie durch den Boden des Amtes bricht und im Archiv darunter weiterwächst.",
    "Hinter der Dämmung wohnt seit Jahren ein Vogel, den niemand entfernen darf und niemand füttern will.",
    "Ein Neubau steht fertig da und wartet auf Menschen, die sich ihn ausgerechnet deshalb nicht leisten können.",
    "Der Fluss holt sich die Uferstraße zurück, sehr langsam, und die Stadt nennt es einen Naturerlebnisraum.",
    "In der Mitte des Quartiers steht ein Haus, das allen gehört und deshalb von niemandem repariert wird.",
    "Die Ziegel erinnern sich an die Hand, die sie gelegt hat, und geben das Wissen an keine Maschine weiter.",
    "Ein Aufzug fährt durch ein Gebäude, das es nicht mehr gibt, und hält weiter zuverlässig im vierten Stock.",
    "Die neue Siedlung ist aus dem Abbruch der alten gebaut, und nachts hört man, dass das Material sich nicht einig ist.",
    "Ein Balkon wächst so weit über die Straße, dass er dem Balkon gegenüber die Hand geben könnte, wenn er dürfte.",
    "Die Bewohner planen ihr Haus gemeinsam und finden nach vier Jahren heraus, dass alle etwas anderes gezeichnet haben.",
    "Auf dem Dach steht ein Feld, unten steht ein Supermarkt, und dazwischen redet niemand miteinander.",
    "Der Rechner schlägt vor, die Straße zu verschmälern, und schlägt gleichzeitig vor, mehr Autos hineinzulassen.",
    "Ein Fenster wird jeden Winter kleiner, weil die Dämmung von innen wächst, und irgendwann ist es eine Erinnerung.",
    "Zwei Bauträger bauen dasselbe Grundstück, jeder ohne den anderen zu sehen, und die Häuser stehen ineinander.",
    "Der Hof ist versiegelt, damit nichts wächst, und die Kinder tragen jeden Tag ein bisschen Erde hinein.",
    "Ein Kalksandstein träumt davon, wieder Sand zu sein, und wartet darauf, dass die Abrissbirne endlich kommt.",
    "Die Beteiligung war vorbildlich, das Protokoll ist zweihundert Seiten lang, und gebaut wird der erste Entwurf.",
    "Im Treppenhaus hängt ein Plan des Gebäudes, auf dem eine Wohnung eingezeichnet ist, die niemand finden kann.",
    "Der Rohbau steht seit sieben Jahren offen, und Efeu hat entschieden, dass er jetzt die Fassade macht.",
    "Ein Dorf zieht in die Stadt und die Stadt zieht aufs Land, und sie begegnen sich auf halber Strecke am Bahnhof.",
    "Die Wärmepumpe summt so laut, dass die Nachbarn ausziehen, und danach ist die Bilanz endlich ausgeglichen.",
    "Auf der Brache steht ein Schild, das eine Zukunft ankündigt, und das Schild ist inzwischen älter als die Brache.",
    "Ein Haus aus Lehm steht neben einem Haus aus Beton, und beide behaupten, das jeweils andere sei die Vergangenheit.",
    "Die letzte Baugenehmigung des Jahres wird erteilt für ein Gebäude, das seine eigene Grundfläche wieder freigeben soll.",
]

#: A realistic festival-day cadence: one dream every eight minutes.
SPACING_S = 480.0
START_AT = 1_700_000_000.0


def seed_dreams(data_dir, count: int, images, *, start_at=START_AT, sentences=None) -> Path:
    """Write `count` finished dreams into a fresh store. Returns the db path.

    `images` is a list of source PNGs, cycled if it is shorter than `count`.
    Sentences are taken in order, so a 5-dream seed is a strict PREFIX of a
    40-dream one — the same day at two points, not two different days. Tool 1's
    `seed_graph` holds the same property for the same reason.
    """
    sentences = SENTENCES if sentences is None else sentences
    if count > len(sentences):
        raise ValueError(f"only {len(sentences)} sentences available, {count} requested")
    images = list(images)
    if not images:
        raise ValueError("seed_dreams needs at least one source image")

    cfg = DreamConfig(data_dir=Path(data_dir))
    store = DreamStore.open(cfg.db_path)
    for index in range(count):
        at = start_at + index * SPACING_S
        persons = 3 + index * 2  # the graph grows through the day
        dream = store.create_dream(
            created_at=at,
            graph_generated_at=at - 30.0,
            person_count=persons,
            term_count=persons * 3,
            edge_count=persons * 4,
            contradiction=persons >= 6,
            guiding_question=cfg.guiding_question,
            absorbed_persons=[f"p{n}" for n in range(1, persons + 1)],
        )
        store.set_stage1(
            dream.id,
            prompt="(seeded — no model call)",
            sentence=sentences[index],
            model=cfg.condense_model,
        )
        store.set_stage2_prompt(
            dream.id, prompt="(seeded — no model call)", model=cfg.image_model
        )
        filename = f"{dream.id}.png"
        (cfg.image_dir / filename).write_bytes(
            Path(images[index % len(images)]).read_bytes()
        )
        store.finish_dream(dream.id, image_path=filename)
    store.close()
    return cfg.db_path
