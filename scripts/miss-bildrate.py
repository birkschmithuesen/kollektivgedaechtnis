# -*- coding: utf-8 -*-
"""Prueft, ob eine Massnahme gegen das Ruckeln wirklich etwas bringt.

Birk, 2026-09-01 vor Ort: der Touchscreen ruckelt beim Kameraschwenk und bei
der Interaktion, sobald viele Begriffe im Bild sind. Frage war: Webansicht
schneller machen oder Dienste auslagern?

GEMESSEN (2026-09-01, Stufe 60 an der Wand):
  Brave gesamt      90,5 % CPU-Anteil   1604 MB
  Python gesamt     18,7 % CPU-Anteil    210 MB   <- alle Dienste zusammen
  GPU 3D-Einheit  ~100 %                          <- AM ANSCHLAG

Damit ist die Frage beantwortet: Auslagern der Dienste braechte hoechstens
ein Fuenftel der CPU-Last -- und die CPU ist gar nicht der Engpass. Die
Grafikeinheit ist es. Zwei Bildschirme, zwei Vollbild-Fenster, ein
Dauer-Kameraschwenk ueber 138 Knoten auf einer Quadro M1000M von 2015.

Dieses Skript misst dieselben Groessen vor und nach einer Aenderung, damit
"besser" eine Zahl ist und kein Gefuehl. Es aendert selbst NICHTS.

Aufruf auf der Station:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe ^
        miss-bildrate.py --sekunden 30 --notiz "vorher"
"""

import argparse
import json
import statistics
import subprocess
import time
from datetime import datetime
from pathlib import Path

PROTOKOLL = Path(r"C:\Users\SF-Tracking\kg-start\bildrate-protokoll.jsonl")


def ps(befehl: str, timeout: float = 120) -> str:
    return subprocess.run(["powershell", "-NoProfile", "-Command", befehl],
                          capture_output=True, text=True, timeout=timeout).stdout.strip()


def gpu_last() -> dict:
    """3D-, Compute- und Kopier-Anteil, getrennt nach Grafikkarte.

    Die LUID `186fe` ist die NVIDIA Quadro (1117 MB dedizierter Speicher
    belegt, gemessen), `18451` die Intel HD. Beide sind aktiv: Brave rendert
    auf der NVIDIA, der Fenstermanager (dwm) zusaetzlich auf der Intel.
    """
    roh = ps("(Get-Counter '\\GPU Engine(*)\\Utilization Percentage' -EA SilentlyContinue)"
             ".CounterSamples | Where-Object {$_.CookedValue -gt 0.2} | "
             "ForEach-Object { @{n=$_.InstanceName; v=[math]::Round($_.CookedValue,1)} } | "
             "ConvertTo-Json -Compress")
    if not roh or roh == "null":
        return {}
    d = json.loads(roh)
    d = d if isinstance(d, list) else [d]
    aus = {}
    for e in d:
        name = e["n"]
        karte = "nvidia" if "186fe" in name else ("intel" if "18451" in name else "?")
        art = name.split("engtype_")[-1] if "engtype_" in name else "?"
        aus[f"{karte}_{art}"] = aus.get(f"{karte}_{art}", 0.0) + e["v"]
    return aus


def cpu_je_programm() -> dict:
    roh = ps("Get-Process brave,python,dwm -EA SilentlyContinue | "
             "ForEach-Object { @{n=$_.ProcessName; id=$_.Id; "
             "cpu=[math]::Round($_.TotalProcessorTime.TotalSeconds,2)} } | ConvertTo-Json -Compress")
    if not roh or roh == "null":
        return {}
    d = json.loads(roh)
    return {p["id"]: p for p in (d if isinstance(d, list) else [d])}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sekunden", type=float, default=30)
    p.add_argument("--takt", type=float, default=3.0)
    p.add_argument("--notiz", default="", help="z.B. 'vorher' / 'nur ein Screen'")
    args = p.parse_args()

    print(f"Messung ueber {args.sekunden:.0f} s  ({args.notiz or 'ohne Notiz'})")
    print("=" * 74)

    start_cpu = cpu_je_programm()
    t0 = time.time()
    proben = []

    while time.time() - t0 < args.sekunden:
        g = gpu_last()
        proben.append(g)
        d3 = g.get("nvidia_3d", 0) + g.get("intel_3d", 0)
        print(f"  [{time.time()-t0:>5.0f}s] 3D {d3:>6.1f} %   "
              f"nvidia {g.get('nvidia_3d',0):>5.1f}   intel {g.get('intel_3d',0):>5.1f}")
        time.sleep(args.takt)

    dauer = time.time() - t0
    end_cpu = cpu_je_programm()

    # CPU-Anteil je Programm ueber den Zeitraum
    nach_programm = {}
    for pid, jetzt in end_cpu.items():
        vorher = start_cpu.get(pid)
        if not vorher:
            continue
        anteil = (jetzt["cpu"] - vorher["cpu"]) / dauer * 100
        nach_programm[jetzt["n"]] = nach_programm.get(jetzt["n"], 0.0) + anteil

    def mittel(schluessel):
        werte = [p.get(schluessel, 0.0) for p in proben if p]
        return statistics.mean(werte) if werte else 0.0

    ergebnis = {
        "zeit": datetime.now().isoformat(timespec="seconds"),
        "notiz": args.notiz,
        "sekunden": round(dauer, 1),
        "gpu_3d_nvidia": round(mittel("nvidia_3d"), 1),
        "gpu_3d_intel": round(mittel("intel_3d"), 1),
        "gpu_compute": round(mittel("nvidia_compute_0"), 1),
        "cpu": {k: round(v, 1) for k, v in nach_programm.items()},
    }

    print()
    print(f"{'GPU 3D nvidia':<18}{ergebnis['gpu_3d_nvidia']:>8.1f} %")
    print(f"{'GPU 3D intel':<18}{ergebnis['gpu_3d_intel']:>8.1f} %")
    print(f"{'GPU compute':<18}{ergebnis['gpu_compute']:>8.1f} %")
    for name, wert in sorted(nach_programm.items(), key=lambda x: -x[1]):
        print(f"{'CPU ' + name:<18}{wert:>8.1f} %")

    with PROTOKOLL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ergebnis, ensure_ascii=False) + "\n")
    print(f"\nProtokolliert nach {PROTOKOLL.name} -- fuer den Vorher/Nachher-Vergleich.")

    if ergebnis["gpu_3d_nvidia"] > 85:
        print("\n>>> Die 3D-Einheit ist am Anschlag. Das IST das Ruckeln.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
