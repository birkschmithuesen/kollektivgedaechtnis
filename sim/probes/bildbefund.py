"""Sieh dir gerenderte Bilder an, statt über sie zu spekulieren.

Warum es das gibt: Der Bildkanal wird an realen Bildern beurteilt (Handoff §2 —
alle fünf Befunde eines Abends kamen daher, dass jemand HINGESEHEN hat). Diese
Sonde schickt jedes Bild eines out/-Ordners zusammen mit dem Prompt, der es
erzeugt hat, an ein Sehmodell und fragt genau die Eigenschaften ab, die der
Prompt zu erreichen versucht.

Ausdrücklich KEIN Urteil über Schönheit. Gefragt wird nur nach Prüfbarem:
Ist Schrift im Bild und in welcher Sprache, teilt sich das Bild in zwei Hälften,
sind beide benannten Seiten des Widerspruchs zu sehen, ist die Schärfe
hyperreal. Das sind die vier Eigenschaften, gegen die der Prompt gebaut ist.

Die Antwort kommt als JSON, damit sich über mehrere Läufe zählen lässt statt zu
behaupten — dieselbe Disziplin wie bei der Lesbarkeitsmessung des Wandsatzes.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from pathlib import Path

import httpx

#: Ein ANDERES Modell als das bilderzeugende (google/gemini-3-pro-image). Wer
#: ein Modell sein eigenes Ergebnis beurteilen lässt, misst dessen Selbstbild,
#: nicht das Bild. Bei OpenRouter am 2026-08-30 geprüft: `google/gemini-3-pro`
#: existiert dort NICHT (400), die Sehvariante heißt so:
_VISION_MODEL = "google/gemini-3.1-pro-preview"

_FRAGE = """\
You are looking at one image produced by a text-to-image model, plus the exact \
prompt that produced it. Report only what is VISIBLE in the image. Do not \
praise, do not interpret intent, do not repeat the prompt back.

Answer as a single JSON object with exactly these keys:

- "text_in_image": list of strings — every piece of readable lettering visible \
in the image, transcribed literally, however small. Empty list if there is none.
- "text_language": "none", "german", "english", "gibberish" or "mixed" — \
gibberish means letter shapes that do not form real words.
- "split_frame": true if the image reads as two pictures side by side (a clear \
vertical or horizontal division separating two scenes), false if it is one \
continuous space seen from one camera position.
- "side_a_visible": true if the FIRST of the two things named in \
CONTRADICTION below is actually visible in the image.
- "side_b_visible": true if the SECOND of them is actually visible.
- "sharpness": "hyperreal", "normal" or "soft" — hyperreal means micro-detail \
is separately legible (pores, fibres, individual blades of grass).
- "depicted": one plain sentence naming what the picture actually shows.
- "prompt_elements_missing": list of concrete things the prompt asks for that \
are NOT in the image.
- "most_wrong": one plain sentence naming the single biggest way the image \
departs from its prompt, or "" if it follows it closely.

CONTRADICTION: {tension_source}

FULL PROMPT:
{prompt}
"""

_PROMPT_BLOCK = re.compile(r"```\n(.*?)\n```\n</details>", re.DOTALL)
_TENSION = re.compile(r"\*\*Widerspruch im Material\*\* \| (.*?) \|")


def _aus_md(md: Path) -> tuple[str, str]:
    """Prompt und Widerspruch aus dem Begleittext, den die Sonde geschrieben hat.

    Gelesen wird der wortwörtlich gesendete Prompt aus dem <details>-Block, nicht
    die deutsche Bausteintabelle darüber: Die Tabelle ist eine Übersetzung für
    Menschen, der Block ist, was das Bildmodell bekommen hat.
    """
    text = md.read_text(encoding="utf-8")
    prompt = _PROMPT_BLOCK.search(text)
    tension = _TENSION.search(text)
    return (
        prompt.group(1) if prompt else "",
        tension.group(1) if tension else "(none named)",
    )


def befunde(ordner: Path) -> list[dict]:
    key = os.environ["OPENROUTER_API_KEY"]
    ergebnisse: list[dict] = []
    for md in sorted(ordner.glob("*.md")):
        bild = next(
            (p for p in (md.with_suffix(".png"), md.with_suffix(".jpg")) if p.exists()),
            None,
        )
        if bild is None:
            continue
        prompt, tension_source = _aus_md(md)
        mime = "image/png" if bild.suffix == ".png" else "image/jpeg"
        b64 = base64.b64encode(bild.read_bytes()).decode()
        antwort = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": _VISION_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": _FRAGE.format(
                                    prompt=prompt, tension_source=tension_source
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"},
                            },
                        ],
                    }
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=300.0,
        )
        antwort.raise_for_status()
        roh = antwort.json()["choices"][0]["message"]["content"]
        # Manche Modelle rahmen JSON in einen Codeblock, obwohl json_object
        # verlangt wurde. Das ist Formatrauschen, kein Fehlschlag.
        roh = roh.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        befund = json.loads(roh)
        befund["bild"] = bild.name
        ergebnisse.append(befund)
    return ergebnisse


def main() -> None:
    ordner = Path(sys.argv[1])
    ergebnisse = befunde(ordner)
    ziel = ordner / "_befund.json"
    ziel.write_text(json.dumps(ergebnisse, indent=2, ensure_ascii=False), "utf-8")
    for b in ergebnisse:
        print(f"\n=== {b['bild']}")
        print(f"  zeigt:        {b['depicted']}")
        print(f"  schrift:      {b['text_language']} {b['text_in_image']}")
        print(f"  geteilt:      {b['split_frame']}")
        print(f"  beide seiten: A={b['side_a_visible']} B={b['side_b_visible']}")
        print(f"  schaerfe:     {b['sharpness']}")
        print(f"  fehlt:        {b['prompt_elements_missing']}")
        print(f"  groesster abstand: {b['most_wrong']}")
    mit_schrift = sum(1 for b in ergebnisse if b["text_language"] != "none")
    geteilt = sum(1 for b in ergebnisse if b["split_frame"])
    beide = sum(1 for b in ergebnisse if b["side_a_visible"] and b["side_b_visible"])
    hyper = sum(1 for b in ergebnisse if b["sharpness"] == "hyperreal")
    n = len(ergebnisse)
    print(f"\n--- {ordner.name}: {n} Bilder")
    print(f"  mit Schrift:        {mit_schrift}/{n}")
    print(f"  geteiltes Bild:     {geteilt}/{n}")
    print(f"  beide Seiten sichtbar: {beide}/{n}")
    print(f"  hyperreale Schaerfe: {hyper}/{n}")
    print(f"  -> {ziel}")


if __name__ == "__main__":
    main()
