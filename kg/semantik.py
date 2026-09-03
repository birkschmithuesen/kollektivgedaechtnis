"""Die zweite Anordnung: Nähe nach BEDEUTUNG statt nach gemeinsamen Sprechern.

🔴 WARUM (Birk, 2026-09-02): „Unsere Kraft behauptet soziale Nähe und nicht
semantische Nähe. Es wäre cool als Feature, im Graph mit Button zwischen
sozialer Nähe und semantischer Nähe hin- und herschalten zu können."

Das Layout an der Wand (fcose, kräftebasiert) ordnet nach GETEILTER
SPRECHERSCHAFT: Zwei Begriffe liegen beieinander, weil dieselben Menschen sie
gesagt haben. Was inhaltlich zusammengehört, aber von verschiedenen Menschen
kam, liegt dort weit auseinander — „Hören auf Erfahrene" und „Involvierung der
Menschen" etwa, obwohl sie fast dasselbe meinen.

Diese Datei rechnet die andere Anordnung: Position aus dem EMBEDDING des
Begriffs. Beide Positionsmengen gehen in `graph.json`, die Wand blendet auf
Knopfdruck zwischen ihnen über — und der Übergang ist die eigentliche Aussage,
weil man sieht, WELCHE Begriffe sich aus der sozialen Ordnung lösen.

## Warum t-SNE

Gemessen am Bestand der Station (54 Begriffe, 3584 Dimensionen), Anteil der
fünf nächsten Nachbarn, die auch in 2D Nachbarn bleiben:

    t-SNE perplexity=10     54,8 %      <- gewählt
    t-SNE perplexity=15     53,0 %
    t-SNE perplexity=5      49,3 %
    MDS (metrisch)          31,1 %
    PCA                     30,7 %

t-SNE ist damit fast doppelt so treu wie die linearen Verfahren. Es erhält
absichtlich die NAHBEREICHE und nicht die großen Abstände — genau die
Eigenschaft, die hier gebraucht wird: „was liegt beieinander" trägt, „was liegt
weit auseinander" bedeutet wenig.

## 🔴 Was es NICHT kann

Die Anordnung ist nicht stabil, wenn Begriffe dazukommen. Kommt ein Interview
hinzu, sieht die semantische Karte anders aus als vorher — anders als das
soziale Layout, das mit `randomize: false` von den alten Positionen ausgeht.
Für einen Umschalter ist das hinnehmbar (man vergleicht zwei Zustände in
diesem Moment), für eine Dauerdarstellung wäre es keins.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

#: Unter so wenigen Begriffen lohnt die Rechnung nicht — und t-SNE braucht
#: `perplexity < n`. Früh am Tag zeigt die semantische Ansicht dann einfach
#: dieselben Positionen wie die soziale.
MIN_BEGRIFFE = 8

#: Gemessen bester Wert (siehe Modul-Docstring). Wird bei kleinen Graphen
#: heruntergezogen, weil sklearn `perplexity < n` verlangt.
PERPLEXITY = 10.0


def _vektoren(embedding_db: Path, labels: list[str]) -> tuple[list[str], list[list[float]]]:
    """Die Embeddings zu den Begriffen, die eines haben."""
    if not embedding_db.exists():
        return [], []
    with sqlite3.connect(f"file:{embedding_db}?mode=ro", uri=True) as conn:
        vorrat = dict(conn.execute("SELECT text, vector FROM embedding"))
    namen, vektoren = [], []
    for label in labels:
        roh = vorrat.get(label)
        if not roh:
            continue
        try:
            v = json.loads(roh)
        except (TypeError, ValueError):
            continue
        if isinstance(v, list) and v:
            namen.append(label)
            vektoren.append([float(x) for x in v])

    # 🔴 NUR EINE VEKTORLAENGE (gefunden durch eine Mutationsprobe, 2026-09-02).
    # Die Tabelle hat `(model, text)` als Schluessel: Nach einem Modellwechsel
    # liegen Vektoren verschiedener Laenge nebeneinander im Cache — heute 3584
    # Dimensionen, ein anderes Modell liefert 1024 oder 1536. Ein numpy-Array
    # daraus zu bauen wirft, und ein EINZIGER solcher Eintrag haette die ganze
    # Ansicht gekostet.
    #
    # Die Mehrheitslaenge gewinnt; der Rest faellt weg wie ein Begriff ohne
    # Embedding.
    if vektoren:
        laengen: dict[int, int] = {}
        for v in vektoren:
            laengen[len(v)] = laengen.get(len(v), 0) + 1
        haupt = max(laengen, key=lambda k: (laengen[k], k))
        if len(laengen) > 1:
            log.info(
                "Embeddings mit %d verschiedenen Laengen im Cache — %d Vektoren "
                "der Laenge %d werden verwendet",
                len(laengen), laengen[haupt], haupt,
            )
        gefiltert = [(n, v) for n, v in zip(namen, vektoren) if len(v) == haupt]
        namen = [n for n, _ in gefiltert]
        vektoren = [v for _, v in gefiltert]
    return namen, vektoren


def semantische_lage(
    embedding_db: Path, labels: list[str], *, spanne: float = 1000.0
) -> dict[str, tuple[float, float]]:
    """{Begriff: (x, y)} im semantischen Raum, auf `spanne` normiert.

    Leeres Ergebnis heisst: keine semantische Ansicht. Der Aufrufer laesst dann
    die Felder weg, und die Wand bietet den Umschalter gar nicht erst an.

    Wirft nie: Diese Ansicht ist ein Zusatz. Faellt sie aus, bleibt die Wand
    genau so, wie sie ohne sie waere — sie darf `graph.json` nie kosten.
    """
    try:
        namen, vektoren = _vektoren(embedding_db, labels)
        if len(namen) < MIN_BEGRIFFE:
            return {}

        import numpy as np
        from sklearn.manifold import TSNE

        X = np.asarray(vektoren, dtype=float)
        norm = np.linalg.norm(X, axis=1, keepdims=True)
        # Ein Nullvektor waere eine Division durch 0 und faerbte die ganze
        # Karte mit NaN ein.
        norm[norm == 0] = 1.0
        X = X / norm
        # Kosinus-Distanz, auf 0 geklemmt: `1 - x·y` wird durch Rundung
        # minimal negativ, und sklearn weist negative Distanzen ab.
        D = np.clip(1.0 - X @ X.T, 0.0, None)
        np.fill_diagonal(D, 0.0)

        perplexity = min(PERPLEXITY, max(2.0, (len(namen) - 1) / 3.0))
        lage = TSNE(
            n_components=2,
            metric="precomputed",
            init="random",
            perplexity=perplexity,
            # Dieselbe Menge ergibt dieselbe Karte — sonst sprang die Ansicht
            # bei jedem Abruf von `graph.json`, ohne dass sich etwas geaendert
            # haette.
            random_state=0,
        ).fit_transform(D)

        # Auf denselben Massstab wie das Wandlayout bringen. Ohne das springt
        # der Umschalter zwischen zwei voellig verschiedenen Groessen, und die
        # Kamera muesste jedes Mal neu fassen.
        spanne_ist = float(np.max(np.abs(lage - lage.mean(axis=0)))) or 1.0
        faktor = (spanne / 2.0) / spanne_ist
        mitte = lage.mean(axis=0)
        return {
            name: (
                round(float((p[0] - mitte[0]) * faktor), 2),
                round(float((p[1] - mitte[1]) * faktor), 2),
            )
            for name, p in zip(namen, lage)
        }
    except Exception as fehler:  # noqa: BLE001 — siehe Docstring
        log.warning("semantische Lage nicht berechenbar: %s", fehler)
        return {}


#: Wie weit zwei Portraits mindestens auseinanderstehen, in Modellpixeln.
#: Etwas mehr als die Scheibe breit ist (`portrait_size`, 120–260 je nach
#: Flaeche), damit sie sich nicht beruehren.
PORTRAIT_ABSTAND = 130.0


def verwandte(
    embedding_db: Path, labels: list[str], *, wieviele: int = 3
) -> dict[str, list[str]]:
    """Je Begriff die inhaltlich naechsten anderen — {Begriff: [Begriff, …]}.

    🔴 Das ist die Information, die der Graph NICHT hat (Birk, 2026-09-02):
    Er verbindet nur, was dieselben Menschen gesagt haben. „Hoeren auf
    Erfahrene" und „Involvierung der Menschen" meinen fast dasselbe, stehen
    aber weit auseinander, weil es verschiedene Personen waren.

    Gerechnet auf den vollen Vektoren, nicht auf der 2D-Karte: Die
    Dimensionsreduktion verliert 3582 von 3584 Dimensionen, und was dort
    nebeneinander landet, ist eine Naeherung. Fuer eine Liste, die als Aussage
    an der Wand steht, ist die Kosinus-Naehe im Originalraum die ehrlichere
    Zahl.

    Wirft nie — dieselbe Regel wie `semantische_lage`.
    """
    try:
        namen, vektoren = _vektoren(embedding_db, labels)
        if len(namen) < 2:
            return {}

        import numpy as np

        X = np.asarray(vektoren, dtype=float)
        norm = np.linalg.norm(X, axis=1, keepdims=True)
        norm[norm == 0] = 1.0
        X = X / norm
        aehnlich = X @ X.T
        np.fill_diagonal(aehnlich, -2.0)  # sich selbst nie vorschlagen
        raus: dict[str, list[str]] = {}
        for i, name in enumerate(namen):
            beste = np.argsort(aehnlich[i])[::-1][:wieviele]
            raus[name] = [namen[j] for j in beste if aehnlich[i][j] > 0]
        return raus
    except Exception as fehler:  # noqa: BLE001
        log.warning("verwandte Begriffe nicht berechenbar: %s", fehler)
        return {}


def eigenster_ort(
    lage: dict[str, tuple[float, float]],
    labels: list[str],
    sprecherzahl: dict[str, int],
) -> tuple[float, float] | None:
    """Wo eine PERSON im semantischen Raum steht: bei ihrem EIGENSTEN Begriff.

    Personen haben kein eigenes Embedding — sie sind kein Text. Ihre Begriffe
    sind aber genau das, was sie inhaltlich ausmacht.

    🔴 NICHT der Mittelwert ihrer Begriffe (so war es bis zum 2026-09-02
    abends, und Birk hat es an der Wand gesehen): Wer ueber vieles spricht,
    landet dann zwangslaeufig in der Bildmitte — und das tun fast alle.
    Gemessen an 21 Personen: Das Personenfeld war 459x559 gross, waehrend die
    Begriffe 958x951 einnahmen, und 47 von 210 Paaren lagen naeher beieinander
    als ein Portrait breit ist. Die Gesichter klumpten in der Mitte.

    Der eigenste Begriff ist der, den ausser ihr am WENIGSTEN andere genannt
    haben. Gemessen ergibt das ein Feld von 939x902 — fast die volle Breite —
    und es ist zugleich die staerkere Aussage: Eine Person steht dort, wo ihr
    Thema liegt, nicht im Mittel ihrer Themen.
    """
    eigene = [l for l in labels if l in lage]
    if not eigene:
        return None
    # Bei Gleichstand das Etikett, damit zwei Laeufe dasselbe ergeben.
    bester = min(eigene, key=lambda l: (sprecherzahl.get(l, 1), l))
    return lage[bester]


def entzerre(
    orte: dict[str, tuple[float, float]],
    *,
    abstand: float = PORTRAIT_ABSTAND,
    runden: int = 200,
) -> dict[str, tuple[float, float]]:
    """Portraits auseinanderschieben, bis keines das andere mehr verdeckt.

    🔴 Auch beim eigensten Begriff bleiben Ueberschneidungen: Zwei Menschen
    koennen denselben eigensten Begriff haben, und dann stehen sie exakt
    aufeinander. Gemessen: 10 von 210 Paaren zu eng, kleinster Abstand 65 px.

    Ein Verdraengungsdurchgang wie in einem Kraft-Layout, aber ohne Federn —
    es zieht nichts zusammen, es schiebt nur auseinander. Danach: 0 von 210 zu
    eng, kleinster Abstand exakt `abstand`.

    Die Reihenfolge ist sortiert und der Durchgang bricht ab, sobald nichts
    mehr zu schieben ist: Zwei Laeufe ueber dieselben Daten muessen dasselbe
    ergeben, sonst spraenge die Ansicht bei jedem Abruf von `graph.json`.
    """
    if len(orte) < 2:
        return dict(orte)
    ids = sorted(orte)
    pos = {i: list(orte[i]) for i in ids}
    for _ in range(runden):
        bewegt = False
        for a_i in range(len(ids)):
            for b_i in range(a_i + 1, len(ids)):
                a, b = ids[a_i], ids[b_i]
                dx = pos[b][0] - pos[a][0]
                dy = pos[b][1] - pos[a][1]
                d = math.hypot(dx, dy)
                if d >= abstand:
                    continue
                if d < 1e-9:
                    # Exakt aufeinander: eine feste Richtung waehlen, sonst
                    # bliebe die Verschiebung 0 und die beiden klebten ewig.
                    dx, dy, d = 1.0, 0.0, 1.0
                schub = (abstand - d) / 2.0
                ux, uy = dx / d, dy / d
                pos[a][0] -= ux * schub
                pos[a][1] -= uy * schub
                pos[b][0] += ux * schub
                pos[b][1] += uy * schub
                bewegt = True
        if not bewegt:
            break
    return {i: (round(pos[i][0], 2), round(pos[i][1], 2)) for i in ids}
