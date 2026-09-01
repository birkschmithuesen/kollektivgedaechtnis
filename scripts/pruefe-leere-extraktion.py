"""Warum liefern Interviews nichts -- und hilft der zweite Anlauf?

Anlass: docs/STAND.md 2h. 17 von 30 Laeufen leer, und `interview_end_index`
schwankte zwischen 0 % und 100 %. Die naheliegende Erklaerung ("bei Ende = 0
ist das Interview verworfen") traegt NICHT: in mindestens 6 der leeren Laeufe
stand das Ende bei 100 %, es wurde also gar nichts beschnitten. Ausserdem hat
`scripts/ab-analyse-prompt.py` bis zum 2026-09-01 jeden FEHLGESCHLAGENEN Aufruf
als "terms=0, ende=0 %" verbucht, ohne den Fehler zu drucken -- ein Teil der
Korrelation zwischen beiden Befunden war das Messwerkzeug selbst.

Dieses Skript trennt, was dort vermischt war, und misst in EINEM Lauf drei
Dinge an echten Sitzungen:

  1. FEHLER gegen LEER. Ein gescheiterter Aufruf wird als Fehler gezaehlt und
     mit seiner Klasse gedruckt, nicht als leeres Ergebnis.
  2. ENDE-INDEX gegen LEER. Ausgezaehlt nach Ende-Klasse (<10 %, 10-90 %,
     >90 %) -- nur ueber gelungene Aufrufe. Verteilen sich die leeren Laeufe
     ueber alle drei Klassen, liegt es nicht am Ende-Index.
  3. RETTET DER ZWEITE ANLAUF? Jeder komplett leere Lauf wird sofort mit
     `EXTRACTION_SYSTEM_WITHOUT_END` wiederholt -- derselbe Prompt, nur ohne
     die Ende-Beschneidung. Rettet er die Faelle, ist die Ein-Aufruf-Kopplung
     belegt; rettet er sie nicht, ist es der Text und kein Prompt-Problem.

🔴 Gibt AUSSCHLIESSLICH Kennzahlen aus. Kein Transkripttext, keine Begriffe,
keine Zitate, keine Namen -- die Transkripte enthalten Aussagen realer
Personen.

Aufruf auf der Station:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe ^
        pruefe-leere-extraktion.py --sitzungen 5,6,19,30,37 --laeufe 3
"""

import argparse
import json
import sys
from pathlib import Path

PROBE = r"C:\Users\SF-Tracking\kg-start\probe"
if Path(PROBE).is_dir():
    sys.path.insert(0, PROBE)
sys.path.insert(1, r"C:\Users\birk\kollektivgedaechtnis")

PFAD = Path(r"C:\Users\birk\kollektivgedaechtnis\data\transcript.jsonl")
PAUSE = 180.0


def sitzungen(pfad, pause):
    z = [json.loads(l) for l in open(pfad, encoding="utf-8") if l.strip()]
    z = [d for d in z if d.get("type") == "final"]
    z.sort(key=lambda d: float(d["timestamp"]))
    g = [[z[0]]]
    for a, b in zip(z, z[1:]):
        if float(b["timestamp"]) - float(a["timestamp"]) > pause:
            g.append([b])
        else:
            g[-1].append(b)
    return g


def einmal(llm, extraction, sysmsg, text, max_terms):
    """Ein Aufruf. Gibt Kennzahlen zurueck -- oder den Fehler, unterscheidbar."""
    try:
        r = llm.parse(
            system=sysmsg,
            user=extraction.build_extraction_prompt(text, max_terms),
            output_model=extraction.ExtractionResult,
        )
    except Exception as exc:
        return {"fehler": f"{type(exc).__name__}: {str(exc)[:70]}"}
    return {
        "fehler": None,
        "terms": len(r.terms),
        "quote": len(r.quotes),
        "name": len(r.names),
        "ende": r.interview_end_index / max(1, len(text)),
        "leer": not (r.terms or r.quotes or r.names),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sitzungen", default="5,6,19,30,37")
    p.add_argument("--laeufe", type=int, default=3)
    p.add_argument("--max-terms", type=int, default=6)
    args = p.parse_args()

    from kg import extraction
    from kg.config import load_config
    from kg.llm import build_llm

    cfg = load_config(Path(r"C:\Users\birk\kollektivgedaechtnis\config.toml"))
    llm = build_llm(cfg)

    g = sitzungen(PFAD, PAUSE)
    nummern = [int(x) for x in args.sitzungen.split(",")]

    print(f"{len(nummern)} Sitzungen x {args.laeufe} Laeufe, Modell {cfg.llm_model}")
    print("=" * 78)

    erste, zweite = [], []
    for n in nummern:
        text = " ".join(d.get("text", "") for d in g[n - 1]).strip()
        print(f"\nSitzung {n} ({len(text)} Zeichen)")
        for lauf in range(args.laeufe):
            e = einmal(llm, extraction, extraction.EXTRACTION_SYSTEM, text, args.max_terms)
            e["sitzung"] = n
            erste.append(e)
            if e["fehler"]:
                print(f"  Lauf {lauf + 1}: FEHLER  {e['fehler']}")
                continue
            print(
                f"  Lauf {lauf + 1}: terms={e['terms']} quote={e['quote']} "
                f"name={e['name']} ende={e['ende'] * 100:.0f}%"
            )
            if not e["leer"]:
                continue
            # Genau der Weg, den kg.extraction.extract() jetzt selbst geht.
            z = einmal(
                llm, extraction, extraction.EXTRACTION_SYSTEM_WITHOUT_END, text, args.max_terms
            )
            z["sitzung"] = n
            zweite.append(z)
            if z["fehler"]:
                print(f"          2. Anlauf: FEHLER  {z['fehler']}")
            else:
                gerettet = "GERETTET" if not z["leer"] else "weiterhin leer"
                print(
                    f"          2. Anlauf ohne Ende-Suche: terms={z['terms']} "
                    f"quote={z['quote']} name={z['name']}  -> {gerettet}"
                )

    ok = [e for e in erste if not e["fehler"]]
    print("\n" + "=" * 78)
    print("1. FEHLER gegen LEER (erster Aufruf)")
    print(f"   Laeufe gesamt        : {len(erste)}")
    print(f"   davon FEHLER         : {len(erste) - len(ok)}")
    print(f"   davon gelungen       : {len(ok)}")
    print(f"   davon leer           : {sum(1 for e in ok if e['leer'])}")

    print("\n2. ENDE-INDEX gegen LEER (nur gelungene Aufrufe)")
    print(f"   {'Ende':<12}{'Laeufe':>8}{'davon leer':>12}")
    for etikett, gilt in (
        ("< 10 %", lambda e: e["ende"] < 0.10),
        ("10-90 %", lambda e: 0.10 <= e["ende"] <= 0.90),
        ("> 90 %", lambda e: e["ende"] > 0.90),
    ):
        gruppe = [e for e in ok if gilt(e)]
        print(f"   {etikett:<12}{len(gruppe):>8}{sum(1 for e in gruppe if e['leer']):>12}")
    print("   Leere Laeufe in der Zeile > 90 % sind der Gegenbeweis: dort wurde")
    print("   nichts beschnitten, und es kam trotzdem nichts.")

    print("\n3. ZWEITER ANLAUF OHNE ENDE-SUCHE")
    if not zweite:
        print("   kein leerer Lauf aufgetreten -- nichts zu retten")
    else:
        z_ok = [z for z in zweite if not z["fehler"]]
        gerettet = sum(1 for z in z_ok if not z["leer"])
        print(f"   ausgeloest           : {len(zweite)}")
        print(f"   davon FEHLER         : {len(zweite) - len(z_ok)}")
        print(f"   davon GERETTET       : {gerettet}")
        print(f"   davon weiterhin leer : {len(z_ok) - gerettet}")
        print()
        print("   Viele Rettungen  -> die Ein-Aufruf-Kopplung war die Ursache.")
        print("   Keine Rettungen  -> der Text enthaelt kein Interview; dann ist")
        print("                       die leere Antwort richtig und die Warnung")
        print("                       im Log der Station der eigentliche Gewinn.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
