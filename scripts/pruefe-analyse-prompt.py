"""Erprobt den Analyse-Prompt an einem ECHTEN Interview -- PII-sicher.

Birk, 2026-09-01: „mal ein reales Interview zum Testen anschauen".

🔴 Das Transkript enthaelt Aussagen realer Personen. Dieses Skript laeuft
deshalb AUF DER STATION und gibt nur das ERGEBNIS der Analyse aus -- Begriffe,
das gewaehlte Zitat, den Namen -- also genau das, was ohnehin auf der Wand
landet. Der Transkripttext selbst wird NIE gedruckt.

Verglichen werden zwei Prompts am selben Interview:
  * ALT  -- ohne den Hinweis auf zwei Sprecher
  * NEU  -- mit dem Hinweis (kg/extraction.py, Stand jetzt)

Damit ist pruefbar, ob der Zusatz wirklich etwas aendert, statt es zu glauben.

Aufruf auf der Station:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe ^
        pruefe-analyse-prompt.py --sitzung 30
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Die zu pruefende Fassung ZUERST: liegt eine neuere kg/extraction.py in der
# Probe, gewinnt sie. Der Rest (config, llm, site-packages) kommt weiterhin
# von der Station. Ohne diese Reihenfolge misst das Skript den alten Prompt
# und meldet trotzdem "neu" -- genau das ist beim ersten Lauf passiert.
PROBE = r"C:\Users\SF-Tracking\kg-start\probe"
if Path(PROBE).is_dir():
    sys.path.insert(0, PROBE)
sys.path.insert(1, r"C:\Users\birk\kollektivgedaechtnis")

PFAD = Path(r"C:\Users\birk\kollektivgedaechtnis\data\transcript.jsonl")
PAUSE = 180.0


def sitzungen(pfad: Path, pause: float) -> list[list[dict]]:
    zeilen = []
    with open(pfad, encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if not zeile:
                continue
            try:
                d = json.loads(zeile)
            except json.JSONDecodeError:
                continue
            if d.get("type") == "final":
                zeilen.append(d)
    zeilen.sort(key=lambda d: float(d.get("timestamp", 0)))
    if not zeilen:
        return []
    gruppen, aktuell = [], [zeilen[0]]
    for a, b in zip(zeilen, zeilen[1:]):
        if float(b["timestamp"]) - float(a["timestamp"]) > pause:
            gruppen.append(aktuell); aktuell = [b]
        else:
            aktuell.append(b)
    gruppen.append(aktuell)
    return gruppen


def zeige(titel: str, ergebnis, transkript: str) -> None:
    print(f"\n--- {titel} ---")
    print(f"Interview-Ende bei Zeichen {ergebnis.interview_end_index} "
          f"von {len(transkript)} "
          f"({ergebnis.interview_end_index / max(1, len(transkript)) * 100:.0f} %)")
    print(f"Begriffe ({len(ergebnis.terms)}):")
    for t in ergebnis.terms:
        print(f"   - {t.label}")
    if ergebnis.quotes:
        print(f"Zitat: „{ergebnis.quotes[0].text}\"")
    else:
        print("Zitat: (keines)")
    print(f"Name:  {ergebnis.names[0].text if ergebnis.names else '(keiner)'}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sitzung", type=int, required=True)
    p.add_argument("--pfad", default=str(PFAD))
    p.add_argument("--pause", type=float, default=PAUSE)
    p.add_argument("--max-terms", type=int, default=6)
    p.add_argument("--nur-neu", action="store_true",
                   help="nur den aktuellen Prompt fahren (spart einen LLM-Aufruf)")
    args = p.parse_args()

    from kg import extraction
    from kg.config import load_config
    from kg.llm import build_llm

    gruppen = sitzungen(Path(args.pfad), args.pause)
    if not (1 <= args.sitzung <= len(gruppen)):
        print(f"Sitzung {args.sitzung} gibt es nicht (1..{len(gruppen)})")
        return 1

    g = gruppen[args.sitzung - 1]
    transkript = " ".join(d.get("text", "") for d in g).strip()
    beginn = datetime.fromtimestamp(float(g[0]["timestamp"]))

    print(f"Sitzung {args.sitzung}: {beginn:%Y-%m-%d %H:%M}, "
          f"{len(g)} Segmente, {len(transkript)} Zeichen")
    print("(Der Transkripttext wird bewusst NICHT ausgegeben.)")
    print("=" * 74)

    cfg = load_config(Path(r"C:\Users\birk\kollektivgedaechtnis\config.toml"))
    llm = build_llm(cfg)

    if not args.nur_neu:
        # Der alte Prompt, rekonstruiert: der neue Block wird herausgeschnitten.
        # So laufen beide durch denselben Code, und der Unterschied ist
        # tatsaechlich NUR der Text -- nicht zwei verschiedene Programme.
        neu = extraction.EXTRACTION_SYSTEM
        start = neu.index("ZWEI STIMMEN, EIN KANAL.")
        ende = neu.index("Das Transkript kommt aus automatischer")
        alt_prompt = neu[:start] + neu[ende:]
        alt = llm.parse(system=alt_prompt,
                        user=extraction.build_extraction_prompt(transkript, args.max_terms),
                        output_model=extraction.ExtractionResult)
        zeige("ALT (ohne Hinweis auf zwei Sprecher)", alt, transkript)

    neu_erg = extraction.extract(llm, transkript, args.max_terms)
    zeige("NEU (mit Hinweis)", neu_erg, transkript)

    print("\n" + "=" * 74)
    print("Zu pruefen: Ist der Name der ANTWORTENDEN Person gewaehlt (nicht der")
    print("der fragenden)? Stammt das Zitat aus einer Antwort? Sind die Begriffe")
    print("das, was die Person SAGT -- nicht das, wonach sie gefragt wurde?")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
