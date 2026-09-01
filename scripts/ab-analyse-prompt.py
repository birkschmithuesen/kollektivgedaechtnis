"""A/B-Vergleich der Prompt-Fassungen ueber MEHRERE echte Interviews.

Ein einzelnes Interview beweist bei einem LLM gar nichts -- die Antwort
schwankt von Lauf zu Lauf. Deshalb hier: mehrere Sitzungen, mehrere
Wiederholungen, und ausgezaehlt wird im Code.

Anlass (Birk, 2026-09-01): Im Transkript sprechen zwei Personen, die
Spracherkennung trennt sie nicht (gemessen: ueberall genau EIN recognizer_id).
Der Analyse-Prompt sollte das wissen. Ob der Zusatz wirklich hilft, ist eine
Messfrage -- ein erster Einzellauf zeigte naemlich das Gegenteil: mit Block
verschwanden Zitat und Name, die ohne Block da waren.

🔴 Gibt AUSSCHLIESSLICH Kennzahlen und die extrahierten BEGRIFFE aus (die
landen ohnehin auf der Wand). Kein Transkripttext, keine Zitate im Klartext --
die stehen unter echten Namen realer Personen.

Aufruf auf der Station:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe ^
        ab-analyse-prompt.py --sitzungen 5,6,19,30,37 --laeufe 3
"""

import argparse
import json
import statistics
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

    neu = extraction.EXTRACTION_SYSTEM
    a = neu.index("ZWEI STIMMEN, EIN KANAL.")
    b = neu.index("Das Transkript kommt aus automatischer")
    fassungen = {"ohne": neu[:a] + neu[b:], "mit": neu}

    g = sitzungen(PFAD, PAUSE)
    nummern = [int(x) for x in args.sitzungen.split(",")]

    print(f"A/B ueber {len(nummern)} Sitzungen x {args.laeufe} Laeufe je Fassung")
    print("=" * 84)

    roh = {k: [] for k in fassungen}
    for n in nummern:
        s = g[n - 1]
        t = " ".join(d.get("text", "") for d in s).strip()
        print(f"\nSitzung {n} ({len(t)} Zeichen)")
        for name, sysmsg in fassungen.items():
            for lauf in range(args.laeufe):
                try:
                    r = llm.parse(system=sysmsg,
                                  user=extraction.build_extraction_prompt(t, args.max_terms),
                                  output_model=extraction.ExtractionResult)
                    eintrag = {"sitzung": n, "terms": len(r.terms),
                               "quote": len(r.quotes), "name": len(r.names),
                               "ende": r.interview_end_index / max(1, len(t)),
                               "labels": [x.label for x in r.terms]}
                except Exception as exc:
                    eintrag = {"sitzung": n, "terms": 0, "quote": 0, "name": 0,
                               "ende": 0.0, "labels": [], "fehler": str(exc)[:60]}
                roh[name].append(eintrag)
                print(f"  {name:<5} Lauf {lauf+1}: terms={eintrag['terms']} "
                      f"quote={eintrag['quote']} name={eintrag['name']} "
                      f"ende={eintrag['ende']*100:.0f}%  {eintrag['labels']}")

    print("\n" + "=" * 84)
    print("ZUSAMMENFASSUNG (ueber alle Sitzungen und Laeufe)")
    print(f"{'Fassung':<8}{'Begriffe':>10}{'mit Zitat':>12}{'mit Name':>11}{'leer':>7}")
    for name, eintraege in roh.items():
        n_ges = len(eintraege)
        begriffe = statistics.mean(e["terms"] for e in eintraege)
        mit_zitat = sum(1 for e in eintraege if e["quote"] > 0)
        mit_name = sum(1 for e in eintraege if e["name"] > 0)
        leer = sum(1 for e in eintraege if e["terms"] == 0)
        print(f"{name:<8}{begriffe:>10.1f}{mit_zitat:>9}/{n_ges:<2}"
              f"{mit_name:>8}/{n_ges:<2}{leer:>5}/{n_ges}")

    print()
    print("Ein leeres Ergebnis ist ein AUSFALL, keine Meinung: die Station")
    print("bekommt dann weder Begriff noch Zitat noch Namen fuer diese Person.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
