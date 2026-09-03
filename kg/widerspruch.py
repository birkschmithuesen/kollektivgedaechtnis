"""Die Widersprüche des Tages — was sich im Material gegenübersteht.

🔴 WARUM (Birk, 2026-09-02, abends): „Da sollen zukünftig auch weitere
aggregierte Informationen angezeigt werden" — und aus der Liste, die ich
vorgeschlagen habe, hat er diesen Block gewählt: „baue auch den
Widerspruchs-Block. Der extra LLM-Call soll nach jedem Interview passieren."

## Was das ist und warum es zählt

Der Graph zeigt, WAS gesagt wurde, und das Layout zeigt, WER es zusammen
gesagt hat. Was er nicht zeigt: dass zwei Aussagen einander widersprechen.
Zwei echte Beispiele vom Ausstellungstag, beide von Hand gefunden:

  „Sanierung maroder Gebäude" (Vicki wünscht sie sich)
      gegen
  „Wohnungszwangssanierung" (Reza fürchtet sie: „Menschen fliegen aus ihren
      Wohnungen raus, weil irgendwer denkt, die Wohnung muss saniert werden")

  „KI plant und gestaltet mit" (fünf Menschen, zuversichtlich)
      gegen
  „Angst vor Stereotypen durch KI" (Tanja: „dass da genauso wenig Toiletten
      auf der einen Seite sind wie bisher")

Beide Paare stehen im Graphen weit auseinander, weil sie von verschiedenen
Menschen kamen — die soziale Nähe kennt keine Gegenrede. Sichtbar wird der
Widerspruch erst, wenn ihn jemand benennt.

## 🔴 Warum das ein eigener Aufruf ist und nicht Teil der Extraktion

Die Extraktion sieht EIN Interview. Ein Widerspruch braucht zwei, und zwar
zwei von verschiedenen Menschen. Er entsteht also nicht beim Zuhören, sondern
beim Vergleichen — und das geht erst, wenn beide Seiten im Graphen stehen.

Nach jedem Interview, nicht alle paar Minuten: Genau dann hat sich das
Material geändert, und genau dann ist die Station ohnehin mit Auswerten
beschäftigt. Ein Zeitgeber würde entweder zu oft laufen (und Geld kosten)
oder zu selten (und Veraltetes zeigen).

## Was NICHT passiert

Es wird nichts erfunden. Der Prompt verlangt für jede Seite eine
BELEGSTELLE aus dem Material, und was ohne sie zurückkommt, wird verworfen —
dieselbe Regel wie beim Traum („Ein Widerspruch darf vorkommen, wenn einer im
Material liegt — erfinde keinen", kg2/condense.py). Findet das Modell keinen,
bleibt die Liste leer und die Tafel zeigt den Block gar nicht.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

#: Wie viele Paare höchstens gesucht werden. Drei, weil die Tafel sie
#: untereinander zeigt und ein vierter unter den Bildschirmrand rutscht.
MAX_PAARE = 3

SYSTEM = """\
Du bekommst die Begriffe eines Ausstellungstags, jeden mit den Stellen aus den \
Gesprächen, auf die er sich stützt. Menschen haben über das Bauen und Wohnen \
gesprochen.

DEINE AUFGABE: Finde die Stellen, an denen zwei Menschen einander \
WIDERSPRECHEN — wo also der eine will, was der andere fürchtet, oder wo zwei \
Antworten auf dieselbe Frage nicht zusammengehen.

🔴 EIN WIDERSPRUCH IST KEIN THEMENUNTERSCHIED. „Lehmbau" und „PV auf Häusern" \
sind zwei Themen, kein Widerspruch. Gesucht ist die Spannung: dieselbe Sache, \
zwei unvereinbare Haltungen dazu.

Gute Beispiele für das, was gesucht ist:
- Jemand wünscht sich mehr Sanierung, jemand anderes fürchtet Sanierung, weil \
Menschen dabei ihre Wohnung verlieren.
- Jemand sieht KI als Werkzeug, das entlastet; jemand anderes fürchtet, dass \
sie bestehende Ungleichheiten fortschreibt.
- Jemand will radikal mit den Regeln brechen, jemand anderes das Bestehende \
behutsam weiterentwickeln.

FÜR JEDE SEITE BRAUCHST DU EINE BELEGSTELLE aus dem Material, WÖRTLICH. \
Findest du zu einer Seite keine, ist es kein Widerspruch — lass ihn weg.

🔴 ERFINDE NICHTS. Lieber eine leere Liste als ein behaupteter Gegensatz. \
Was hier steht, wird an einer Wand ausgestellt und Menschen zugeschrieben, die \
im Raum stehen.

`titel` ist die Spannung in höchstens sechs Wörtern, ohne Doppelpunkt und ohne \
Wertung — nicht „Sanierung: gut oder schlecht?", sondern „Sanierung als \
Hoffnung und als Bedrohung".\
"""


class Seite(BaseModel):
    begriff: str
    beleg: str = Field(description="Die wörtliche Stelle aus dem Material.")


class Widerspruch(BaseModel):
    titel: str
    eine: Seite
    andere: Seite


class Widersprueche(BaseModel):
    paare: list[Widerspruch] = []


def _material(begriffe: list[dict]) -> str:
    zeilen = []
    for b in begriffe:
        stimmen = b.get("stimmen") or []
        if not stimmen:
            continue
        zeilen.append(f"{b['label']} ({len(stimmen)}× gesagt)")
        for name, beleg in stimmen:
            zeilen.append(f"    {name or 'jemand'}: {beleg}")
    return "\n".join(zeilen)


def finde_widersprueche(llm, begriffe: list[dict], *, max_paare: int = MAX_PAARE):
    """Die Paare, oder eine leere Liste.

    Wirft nie: Dieser Block ist eine Zugabe auf einer Tafel. Fällt er aus,
    zeigt die Wand ihn nicht — ein Interview darf daran nie scheitern, und
    genau hier läuft der Aufruf: am Ende der Auswertung.
    """
    mit_belegen = [b for b in begriffe if b.get("stimmen")]
    # Unter zwei Begriffen mit Belegen kann es keine zwei Seiten geben.
    if len(mit_belegen) < 2:
        return []
    try:
        ergebnis = llm.parse(
            system=SYSTEM,
            user=(
                "--- BEGRIFFE UND BELEGSTELLEN ---\n\n"
                + _material(mit_belegen)
                + f"\n\n--- ENDE ---\n\nHöchstens {max_paare} Paare."
            ),
            output_model=Widersprueche,
        )
    except Exception as fehler:  # noqa: BLE001 — siehe Docstring
        log.warning("Widersprüche nicht ermittelbar: %s", fehler)
        return []

    sauber = []
    for paar in ergebnis.paare[:max_paare]:
        # 🔴 Beide Seiten brauchen eine Belegstelle. Ohne sie ist es eine
        # Behauptung des Modells, und die gehört nicht an die Wand.
        if not (paar.eine.beleg or "").strip() or not (paar.andere.beleg or "").strip():
            log.info("Widerspruch ohne Beleg verworfen: %s", paar.titel)
            continue
        if not (paar.titel or "").strip():
            continue
        sauber.append(
            {
                "titel": paar.titel.strip(),
                "eine": {"begriff": paar.eine.begriff.strip(), "beleg": paar.eine.beleg.strip()},
                "andere": {
                    "begriff": paar.andere.begriff.strip(),
                    "beleg": paar.andere.beleg.strip(),
                },
            }
        )
    return sauber
