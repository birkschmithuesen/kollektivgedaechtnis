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

#: Forty fictional dreams of one fictional festival day. Spec §5.1's target is
#: ~20-40 words; this corpus genuinely SPANS that range (20 to 40, six of them
#: at 36-40) rather than clustering at the bottom of it. A strip judged only on
#: sentences barely over the floor never exercises the hard case: whether a
#: real 36-40 word sentence still fits the two-line `#sentence` budget without
#: pushing the strip off screen (review finding, 2026-08-26 — the previous
#: corpus topped out at 21 words, so that case was never rendered at all).
#:
#: Invented outright, and deliberately not drawn from the corpus: these end up
#: in a review directory, and a half-formed dream of real people's words does
#: not belong there.
SENTENCES = [
    "In einem Hof, der gleichzeitig gegossen und bepflanzt wird, warten zwei Generationen geduldig darauf, dass die jeweils andere zuerst endgültig aufgibt und den Platz freimacht.",
    "Die Bagger halten mitten in der Nacht an, weil plötzlich niemand mehr sagen kann, wem der Boden eigentlich gehört, und die Baugrube füllt sich langsam mit Schilf und stillem Wasser, während am Rand jemand die Grenze längst vergessen hat.",
    "Ein Haus lernt sprechen und benutzt sein allererstes, mühsam geübtes Wort ausgerechnet dafür, nach einer Miete zu fragen, die in dieser Stadt niemand mehr aufbringen kann.",
    "Über der alten Umgehungsstraße hängt an dünnen Seilen ein ganzes Dorf, und ausgerechnet die, die es mit eigenen Händen gebaut haben, dürfen darin nicht wohnen.",
    "Hundert kleine Klebepunkte auf einem ausgebreiteten Plan ergeben zusammen ein einziges Gesicht, das niemand im Saal wiedererkennt, obwohl alle Anwesenden es am Ende bereitwillig unterschrieben haben.",
    "Der Beton atmet zum allerersten Mal richtig aus, und was er dabei ausatmet, ist der feine Staub sämtlicher Häuser, die vor ihm genau hier gestanden hatten.",
    "In der Tiefgarage wächst über Nacht ein ganzer Wald, dessen junge Bäume unbedingt nach oben durch die Betondecke wollen und dabei erstaunlich höflich und rücksichtsvoll bleiben.",
    "Eine Maschine entwirft in Sekunden ein Zuhause, das in jeder Hinsicht perfekt ist, bis auf den fehlenden Geruch, und genau daran erkennt es jeder Besucher sofort.",
    "Die Fassade wird jeden einzelnen Morgen frisch neu gedruckt, und jeden Abend sammelt jemand still die alte, ausrangierte Haut ein und trägt sie schweigend fort.",
    "Zwei Nachbarn teilen sich seit Jahrzehnten eine einzige tragende Wand und streiten seit zwölf zähen Jahren unversöhnt darüber, auf welcher Seite diese Wand eigentlich wirklich steht.",
    "Der Kran über dem halbfertigen Quartier dreht sich unbeirrt weiter, obwohl unten längst niemand mehr baut, und keiner traut sich, ihn nach all der Zeit endlich abzustellen.",
    "Aus dem dauerhaften Leerstand im Erdgeschoss wächst mitten in der Nacht ein ganzer Marktplatz, der jeden Morgen wieder spurlos verschwindet und nur ein paar Krümel hinterlässt.",
    "Ein Dach aus dicht montierten Solarzellen wirft einen so tiefen Schatten, dass darunter nichts mehr wachsen kann, und trotzdem finden alle Beteiligten diese Lösung erstaunlich richtig.",
    "Die Wohnung ist im Lauf der Jahre so klug geworden, dass sie ihre eigenen Bewohner beim vollen Namen nennt und dabei jedes einzelne Mal spürbar zögert.",
    "Im sorgfältig gebauten Modell steht schon der Park, exakt im Maßstab eins zu fünfhundert, während draußen in der echten Welt der Parkplatz geduldig auf sein Ende wartet.",
    "Ein alter Bagger und eine junge Buche stehen sich mitten auf der Brache gegenüber, und beide warten seit Wochen still darauf, dass irgendeine Behörde endlich zurückschreibt.",
    "Die Bauakte wird über die Jahre so unfassbar schwer, dass sie eines Tages durch den Boden des Amtes bricht und im Archiv darunter einfach weiterwächst.",
    "Hinter der alten Dämmung wohnt schon seit Jahren ein Vogel, den offiziell niemand entfernen darf und den niemand füttern will.",
    "Ein fertiggestellter Neubau steht glänzend da und wartet geduldig auf Menschen, die sich ausgerechnet ihn, mit all seiner Perfektion, am Ende schlicht nicht leisten können.",
    "Der Fluss holt sich die alte Uferstraße ganz langsam, aber unaufhaltsam zurück, Stein für Stein, und die Stadtverwaltung nennt das Ganze am Ende einen Naturerlebnisraum.",
    "In der genauen Mitte des neuen Quartiers steht ein einzelnes Haus, das offiziell allen zugleich gehört und deshalb, wie sich zeigt, von niemandem mehr repariert wird.",
    "Die alten Ziegel erinnern sich noch genau an die Hand, die sie einst gelegt hat, und geben dieses stille Wissen an keine einzige Maschine weiter.",
    "Ein Aufzug fährt gleichmäßig weiter durch ein Gebäude, das es schon lange nicht mehr gibt, und hält trotzdem jeden Tag zuverlässig genau im vierten Stock.",
    "Die neue Siedlung ist vollständig aus dem Abbruch der alten errichtet worden, und nachts hört man deutlich, dass sich das wiederverwertete Material darüber noch immer nicht einig ist, als stritten sich die Steine noch über ihr früheres Haus.",
    "Ein Balkon wächst so weit und so beharrlich über die Straße hinaus, dass er dem Balkon gegenüber fast die Hand geben könnte, wenn er es nur dürfte.",
    "Die Bewohner planen ihr gemeinsames Haus jahrelang einträchtig zusammen und finden nach vier zähen Jahren überrascht heraus, dass am Ende alle etwas ganz anderes gezeichnet haben.",
    "Auf dem flachen Dach steht still ein ganzes Feld, unten direkt darunter steht ein großer Supermarkt, und zwischen den beiden Ebenen redet buchstäblich niemand mehr miteinander.",
    "Der Planungsrechner schlägt in einem Atemzug vor, die enge Straße zu verschmälern, und schlägt im nächsten gleich vor, deutlich mehr Autos zusätzlich hineinzulassen.",
    "Ein Fenster wird jeden einzelnen Winter ein kleines Stück kleiner, weil die Dämmung von innen unaufhaltsam wächst, und irgendwann ist von ihm nur noch eine Erinnerung übrig.",
    "Zwei Bauträger bebauen gleichzeitig dasselbe Grundstück, jeder ohne den anderen je zu sehen, und am Ende stehen die Häuser ineinander verschachtelt.",
    "Der versiegelte Hof lässt bewusst nichts mehr wachsen, und trotzdem tragen die Kinder jeden Tag geduldig ein kleines bisschen echte Erde heimlich wieder hinein.",
    "Ein alter Kalksandstein träumt insgeheim davon, irgendwann wieder loser Sand zu sein, und wartet seit Jahren geduldig darauf, dass die Abrissbirne endlich kommt und ihn erlöst.",
    "Die Bürgerbeteiligung war in jeder Hinsicht vorbildlich organisiert, das fertige Protokoll ist zweihundert Seiten lang, und am Ende wird trotzdem exakt der allererste Entwurf gebaut.",
    "Im dunklen Treppenhaus hängt ein alter Plan des Gebäudes, auf dem eine kleine Wohnung eingezeichnet ist, die seit Jahren beim besten Willen niemand mehr finden kann.",
    "Der Rohbau steht bereits seit sieben langen Jahren offen zum Himmel, und der Efeu hat inzwischen ganz von selbst entschieden, dass er ab jetzt die Fassade übernimmt.",
    "Ein ganzes Dorf zieht geschlossen in die große Stadt, während zur gleichen Zeit die Stadt aufs weite Land zieht, und beide begegnen sich schließlich zufällig auf halber Strecke am alten Bahnhof, ohne sich zu erkennen.",
    "Die neue Wärmepumpe summt so beharrlich und so laut, dass nach und nach sämtliche Nachbarn ausziehen, und erst danach ist die viel besprochene Energiebilanz des Hauses endlich wirklich ausgeglichen, obwohl niemand im Amt das jemals so geplant hatte.",
    "Auf der weiten Brache steht seit Jahren ein verblasstes Schild, das lautstark eine glänzende Zukunft ankündigt, und inzwischen ist dieses Schild selbst schon spürbar älter als die Brache, die es bewirbt, und niemand erinnert sich mehr an die gemeinte Zukunft.",
    "Ein schlichtes Haus aus gestampftem Lehm steht direkt neben einem kühlen Haus aus rohem Beton, und beide behaupten, wechselseitig und mit großer Überzeugung, das jeweils andere sei eindeutig die Vergangenheit, während der Wind das letzte Wort behält.",
    "Die allerletzte Baugenehmigung des Jahres wird ausgerechnet für ein Gebäude erteilt, das laut Auflage seine eigene, mühsam versiegelte Grundfläche am Ende wieder vollständig freigeben soll, sobald die Frist abgelaufen ist, bis dort am Ende gar nichts mehr steht.",
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
