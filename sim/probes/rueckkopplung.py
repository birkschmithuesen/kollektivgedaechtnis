"""Kommt im Bild an, was in den Interviews gesagt wurde? Blind gemessen.

Birks Idee, 2026-08-30. Die Kette Interview → Satz → Bild verliert an jeder
Stufe etwas, und bis hierher fiel das nur auf, wenn jemand hinsah. Am
Klebepunkte-Befund war der Verlust groß: Der meistgenannte Begriff des ganzen
Materials („Scheinbeteiligung pro forma“, 7 Nennungen) stand in keinem der
fünf Bilder, und der zweitmeistgenannte („Klebepunkte-Workshop“) nur als sein
Substantiv — bunte Punkte an einer Wand, ohne den Vorgang und ohne die
Menschen, um die es ging.

WIE GEMESSEN WIRD, UND WARUM SO

Ein zweites, fremdes Modell sieht NUR das Bild. Es bekommt weder den Prompt
noch den Wandsatz noch die Begriffe — sonst liest es sie im Bild wieder, weil
es sie gelesen hat. Es soll aufschreiben, wovon dieses Bild handelt.

Erst danach, in einem ZWEITEN Aufruf ohne Bild, wird diese blinde Beschreibung
gegen die tatsächlichen Begriffe des Materials gehalten. Getrennt zu halten ist
der Kern: Ein Modell, das Bild und Sollwert gleichzeitig sieht, findet den
Sollwert im Bild. Das ist keine Messung, das ist ein Echo.

WAS DIE ZAHL IST UND WAS NICHT

Gezählt wird eine einzige Eigenschaft: Wie viele der meistgenannten Begriffe
kommen in der blinden Beschreibung vor, und zwar als das, was sie meinen, nicht
nur als ihr Etikett. Nichts davon ist ein Urteil über das Bild. Ob ein Bild gut
ist, ob die Bildsprache dem kritischen Anspruch standhält, ob es an der Wand
trägt — das entscheidet Birk am Material und niemand sonst (Spec §1). Diese
Sonde ist ein Suchwerkzeug für Prompt-Varianten: Sie sagt, wo Inhalt verloren
geht, nie, welches Bild das bessere ist.

    uv run python sim/probes/rueckkopplung.py out/<ordner> [--top N]

Schreibt `_rueckkopplung.json` in den Ordner und druckt die Tabelle.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sim.dream_calibrate import FIXTURE, prefix_graph  # noqa: E402

#: Fremdes Modell, absichtlich nicht das bilderzeugende und nicht das
#: verdichtende: Wer sein eigenes Ergebnis bewertet, misst sein Selbstbild.
_MODELL = "google/gemini-3.1-pro-preview"

#: Dieselben fünf Zeitpunkte wie sim/probes/tagesverlauf.py. Bewusst hier
#: wiederholt statt importiert, damit diese Sonde auch über Ordner läuft, die
#: eine andere Sonde erzeugt hat — sie liest die Personenzahl aus dem
#: Dateinamen und braucht nur die Zuordnung Zahl → Teilgraph.
_PERSONEN_AUS_NAME = re.compile(r"(\d+)personen")


_BLIND = """\
Describe what this photograph is about. Not its style, not its lighting, not \
its composition — its SUBJECT. Someone who cannot see it should learn from you \
what is happening in it and what it seems to be concerned with.

Write 4-6 sentences of plain prose. Name what people in it are doing, if there \
are any. Name what the place appears to be used for. If the picture seems to \
hold two things in tension with each other, say which two. Do not hedge, do \
not list, do not mention that it is an image or a render.
"""

_ABGLEICH = """\
Below is a description of a photograph, written by someone who saw only the \
photograph and knew nothing else. Below that is a list of topics that were \
actually spoken about by people in interviews, with how many people raised \
each one.

For each topic, judge from the DESCRIPTION ALONE whether that topic reached \
the picture. Be strict, and distinguish three cases:

- "present": the description shows the topic as the thing it actually is, \
including the human activity in it where the topic names one. A topic like \
"residents' participation workshop" is present only if the description has \
people taking part in something — not if it merely mentions coloured dots or \
a plan on a wall.
- "label_only": the description contains the object or the word from the \
topic, but not the matter itself — the leftover trace of an activity without \
the activity, the tool without anyone using it.
- "absent": nothing of it.

Answer as a single JSON object:
{{
  "topics": [
    {{"topic": "<topic verbatim>", "verdict": "present|label_only|absent",
      "evidence": "<the words in the description that decided it, or \\"\\">"}}
  ],
  "summary": "<one sentence: what the description is mainly about>"
}}

DESCRIPTION:
{beschreibung}

TOPICS (topic — number of people who raised it):
{begriffe}
"""


def _post(payload: dict) -> str:
    antwort = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
        json=payload,
        timeout=300.0,
    )
    antwort.raise_for_status()
    return antwort.json()["choices"][0]["message"]["content"]


def _json_aus(roh: str) -> dict:
    roh = roh.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    return json.loads(roh)


def begriffe_bei(personen: int, top: int) -> list[tuple[str, int]]:
    """Die meistgenannten Begriffe des Materials zu diesem Zeitpunkt.

    Genau der Ausschnitt, den Stufe 1 gesehen hat — sonst wird gegen Begriffe
    gemessen, die zu diesem Zeitpunkt noch niemand gesagt hatte.
    """
    graph = json.loads(FIXTURE.read_text(encoding="utf-8"))
    teil = prefix_graph(graph, personen)
    terme = [n for n in teil["nodes"] if n.get("type") == "term"]
    terme.sort(key=lambda n: -n.get("mentions", 0))
    return [(n["label"], n.get("mentions", 0)) for n in terme[:top]]


def messe(ordner: Path, top: int = 10) -> list[dict]:
    ergebnisse: list[dict] = []
    for md in sorted(ordner.glob("*.md")):
        bild = next(
            (p for p in (md.with_suffix(".png"), md.with_suffix(".jpg")) if p.exists()),
            None,
        )
        if bild is None:
            continue
        treffer = _PERSONEN_AUS_NAME.search(md.stem)
        if not treffer:
            continue
        personen = int(treffer.group(1))

        # Erster Aufruf: nur das Bild, kein Prompt, kein Satz, keine Begriffe.
        mime = "image/png" if bild.suffix == ".png" else "image/jpeg"
        b64 = base64.b64encode(bild.read_bytes()).decode()
        beschreibung = _post(
            {
                "model": _MODELL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": _BLIND},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"},
                            },
                        ],
                    }
                ],
            }
        ).strip()

        # Zweiter Aufruf: kein Bild mehr. Nur Text gegen Text.
        begriffe = begriffe_bei(personen, top)
        urteil = _json_aus(
            _post(
                {
                    "model": _MODELL,
                    "messages": [
                        {
                            "role": "user",
                            "content": _ABGLEICH.format(
                                beschreibung=beschreibung,
                                begriffe="\n".join(
                                    f"- {label} — {n}" for label, n in begriffe
                                ),
                            ),
                        }
                    ],
                    "response_format": {"type": "json_object"},
                }
            )
        )

        gewicht = dict(begriffe)
        punkte = 0.0
        moeglich = 0.0
        for t in urteil.get("topics", []):
            w = gewicht.get(t.get("topic", ""), 0)
            moeglich += w
            if t.get("verdict") == "present":
                punkte += w
            elif t.get("verdict") == "label_only":
                # Halb: der Gegenstand ist da, die Sache nicht. Genau der
                # Klebepunkte-Fall — er soll sichtbar zwischen ganz und gar
                # nicht liegen, sonst verschwindet der Unterschied, um den es
                # bei dieser Messung geht.
                punkte += w * 0.5

        ergebnisse.append(
            {
                "bild": bild.name,
                "personen": personen,
                "blinde_beschreibung": beschreibung,
                "summary": urteil.get("summary", ""),
                "topics": urteil.get("topics", []),
                "deckung": round(punkte / moeglich, 3) if moeglich else 0.0,
            }
        )
    return ergebnisse


def main() -> None:
    argumente = sys.argv[1:]
    top = 10
    if "--top" in argumente:
        i = argumente.index("--top")
        top = int(argumente[i + 1])
        del argumente[i : i + 2]
    ordner = Path(argumente[0])

    ergebnisse = messe(ordner, top)
    (ordner / "_rueckkopplung.json").write_text(
        json.dumps(ergebnisse, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    for e in ergebnisse:
        print(f"\n=== {e['bild']}  ({e['personen']} Personen)")
        print(f"  blind gesehen: {e['summary']}")
        for t in e["topics"]:
            zeichen = {"present": "+", "label_only": "~", "absent": "-"}.get(
                t.get("verdict"), "?"
            )
            print(f"    {zeichen} {t.get('topic')}")
        print(f"  Deckung: {e['deckung']:.0%}")

    if ergebnisse:
        mittel = sum(e["deckung"] for e in ergebnisse) / len(ergebnisse)
        print(f"\n--- {ordner.name}: Deckung im Mittel {mittel:.0%} "
              f"über {len(ergebnisse)} Bilder")
        print("    (+ die Sache selbst, ~ nur das Etikett, - fehlt)")


if __name__ == "__main__":
    main()
