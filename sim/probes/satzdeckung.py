"""Deckt das Bild den Satz, der daneben an der Wand hängt?

Birks Befund vom 2026-08-30 an `out/vgl-F-massstab/5-60personen.jpg`: Der
Wandsatz sagt „mauern Abbruchschutt ins Dorfhaus vor den ausgehobenen
Kellergruben\" — im Bild mauern sie eine Mauer, kein Dorfhaus, und Kellergruben
sind keine zu sehen. Zwei von drei Aussagen fehlen.

Das ist eine andere Frage als die in `rueckkopplung.py`. Dort geht es darum, ob
das INTERVIEWMATERIAL im Bild ankommt. Hier geht es darum, ob der TEXT, der
neben dem Bild hängt, hält was er sagt — denn Satz und Bild stehen zusammen an
der Wand, und ein Satz, der etwas behauptet, das die Besucherin im Bild nicht
findet, sieht nicht nach einem Traum aus, sondern nach einem Fehler.

Vor jeder Entscheidung über eine Laufzeitprüfung (`docs/decisions/
satz-bild-deckung.md`) fehlt genau eine Zahl: **wie oft passiert das
überhaupt?** Ein Befund an einem Bild ist ein Verdacht, keine Häufigkeit.

## Wie gemessen wird

Derselbe Aufbau wie in `rueckkopplung.py`, aus demselben Grund getrennt in zwei
Aufrufe: Ein fremdes Modell sieht NUR das Bild und beschreibt es blind. Erst
danach, ohne Bild, wird der deutsche Wandsatz in seine einzelnen Aussagen
zerlegt und jede gegen die blinde Beschreibung gehalten. Wer Bild und Sollsatz
gleichzeitig zeigt, bekommt ein Echo statt einer Messung.

Zerlegt wird in Aussagen, nicht in Wörter: „Anwohner und Fachleute mauern
Abbruchschutt ins Dorfhaus vor den ausgehobenen Kellergruben" enthält drei
prüfbare Behauptungen (wer, was womit, wo) — und genau zwei davon fehlten.
Eine Deckungsquote über den ganzen Satz würde das verwischen.

    uv run python sim/probes/satzdeckung.py out/<ordner> [weitere ordner...]
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from pathlib import Path

import httpx

#: Fremdes Modell, nicht das bilderzeugende — siehe rueckkopplung.py.
_MODELL = "google/gemini-3.1-pro-preview"

_BLIND = """\
Describe what is visible in this photograph. Name the things, the people and \
what they are doing, the place, and the materials. Be concrete and complete; \
someone who cannot see it should be able to tell from your description whether \
a given object is in it or not. 5-7 sentences of plain prose. Do not comment \
on style, mood or composition, and do not mention that it is an image.
"""

_ABGLEICH = """\
Below is a German sentence that hangs on a wall next to a photograph, and a \
description of that photograph written by someone who saw only the photograph \
and never read the sentence.

Split the German sentence into its individual factual claims — who is present, \
what they are doing, with what, and where. Usually three to five claims. Then \
judge each one against the DESCRIPTION ALONE.

Answer as a single JSON object:
{{
  "claims": [
    {{"claim": "<the claim, in German, as the sentence states it>",
      "verdict": "present|altered|absent",
      "evidence": "<the words in the description that decided it, or \\"\\">"}}
  ],
  "summary": "<one German sentence: what the picture shows instead, where it differs>"
}}

- "present": the description clearly contains this claim.
- "altered": something of the kind is there, but not as the sentence states it \
— a wall instead of the named building, a machine instead of the named people.
- "absent": nothing of it.

Be strict. A sentence naming a specific building, place or object is not \
satisfied by a generic one of the same category.

GERMAN SENTENCE:
{satz}

DESCRIPTION OF THE PHOTOGRAPH:
{beschreibung}
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


def messe(ordner: Path) -> list[dict]:
    ergebnisse: list[dict] = []
    for md in sorted(ordner.glob("*.md")):
        bild = next(
            (p for p in (md.with_suffix(".png"), md.with_suffix(".jpg")) if p.exists()),
            None,
        )
        if bild is None:
            continue
        treffer = re.search(r"> \*\*(.*?)\*\*", md.read_text(encoding="utf-8"))
        if not treffer:
            continue
        satz = treffer.group(1)

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

        urteil = _json_aus(
            _post(
                {
                    "model": _MODELL,
                    "messages": [
                        {
                            "role": "user",
                            "content": _ABGLEICH.format(
                                satz=satz, beschreibung=beschreibung
                            ),
                        }
                    ],
                    "response_format": {"type": "json_object"},
                }
            )
        )

        claims = urteil.get("claims", [])
        da = sum(1 for c in claims if c.get("verdict") == "present")
        ergebnisse.append(
            {
                "bild": bild.name,
                "ordner": ordner.name,
                "satz": satz,
                "blinde_beschreibung": beschreibung,
                "summary": urteil.get("summary", ""),
                "claims": claims,
                "gedeckt": da,
                "gesamt": len(claims),
            }
        )
    return ergebnisse


def main() -> None:
    alle: list[dict] = []
    for arg in sys.argv[1:]:
        ordner = Path(arg)
        ergebnisse = messe(ordner)
        (ordner / "_satzdeckung.json").write_text(
            json.dumps(ergebnisse, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        alle += ergebnisse
        print(f"\n########## {ordner.name}")
        for e in ergebnisse:
            print(f"\n=== {e['bild']}   {e['gedeckt']}/{e['gesamt']} Aussagen gedeckt")
            print(f"  SATZ: {e['satz']}")
            for c in e["claims"]:
                z = {"present": "+", "altered": "~", "absent": "-"}.get(
                    c.get("verdict"), "?"
                )
                print(f"    {z} {c.get('claim')}")
            if e["summary"]:
                print(f"  -> {e['summary']}")

    if alle:
        claims = sum(e["gesamt"] for e in alle)
        gedeckt = sum(e["gedeckt"] for e in alle)
        fehlend = sum(
            1 for e in alle for c in e["claims"] if c.get("verdict") == "absent"
        )
        veraendert = sum(
            1 for e in alle for c in e["claims"] if c.get("verdict") == "altered"
        )
        makellos = sum(1 for e in alle if e["gedeckt"] == e["gesamt"])
        print(f"\n\n===== GESAMT über {len(alle)} Bilder")
        print(f"  Aussagen gesamt:        {claims}")
        print(f"  davon im Bild:          {gedeckt}  ({gedeckt / claims:.0%})")
        print(f"  verändert:              {veraendert}")
        print(f"  fehlend:                {fehlend}")
        print(f"  Bilder ohne jeden Fehl: {makellos}/{len(alle)}")


if __name__ == "__main__":
    main()
