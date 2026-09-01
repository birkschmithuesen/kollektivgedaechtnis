# -*- coding: utf-8 -*-
"""Misst die Last auf dem Ausstellungsrechner -- wer frisst CPU und RAM?

Birk, 2026-09-01 vor Ort: der Touchscreen ruckelt, sowohl beim automatischen
Kameraschwenk als auch bei der Interaktion, und zwar bei vielen Begriffen.
Frage: Performance der Webansicht verbessern oder Dienste auf andere Rechner
auslagern?

Diese Messung beantwortet den ERSTEN Teil: was laeuft ueberhaupt, und wieviel
nimmt es. Ohne Zahlen ist "auslagern" geraten -- es koennte genauso gut sein,
dass die Dienste harmlos sind und allein das Rendern im Browser klemmt.

Gemessen wird ueber mehrere Runden, weil ein einzelner Blick auf die CPU
nichts sagt: Prozesse schwanken, und die Spitze zaehlt mehr als der Moment.

Nur Zahlen und Prozessnamen, keine Kommandozeilen mit Tokens.

Aufruf auf der Station:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe ^
        miss-last.py --runden 5
"""

import argparse
import json
import subprocess
import time
from collections import defaultdict


def ps(befehl: str) -> str:
    fertig = subprocess.run(
        ["powershell", "-NoProfile", "-Command", befehl],
        capture_output=True, text=True, timeout=90)
    return fertig.stdout


def kerne_und_ram() -> tuple:
    roh = ps("$c=Get-CimInstance Win32_ComputerSystem; "
             "$p=Get-CimInstance Win32_Processor | Select-Object -First 1; "
             "@{kerne=$p.NumberOfCores; logisch=$p.NumberOfLogicalProcessors; "
             "  ram=[math]::Round($c.TotalPhysicalMemory/1GB,1); "
             "  cpu=$p.Name} | ConvertTo-Json -Compress")
    try:
        d = json.loads(roh.strip())
        return d.get("kerne"), d.get("logisch"), d.get("ram"), d.get("cpu", "").strip()
    except Exception:
        return None, None, None, "?"


def messrunde() -> list:
    """Ein Blick auf alle relevanten Prozesse. CPU-Prozent ueber Zeitdifferenz."""
    roh = ps(
        "Get-Process brave,msedge,chrome,python,pythonw,sclang,scsynth -EA SilentlyContinue | "
        "ForEach-Object { @{name=$_.ProcessName; id=$_.Id; "
        "  ws=[math]::Round($_.WorkingSet64/1MB,0); "
        "  cpu=[math]::Round($_.TotalProcessorTime.TotalSeconds,2) } } | "
        "ConvertTo-Json -Compress")
    try:
        d = json.loads(roh.strip())
        return d if isinstance(d, list) else [d]
    except Exception:
        return []


def gesamtlast() -> dict:
    roh = ps("$os=Get-CimInstance Win32_OperatingSystem; "
             "$cpu=(Get-CimInstance Win32_Processor | "
             "  Measure-Object -Property LoadPercentage -Average).Average; "
             "@{cpu=$cpu; freiMB=[math]::Round($os.FreePhysicalMemory/1KB,0); "
             "  gesamtMB=[math]::Round($os.TotalVisibleMemorySize/1KB,0)} | ConvertTo-Json -Compress")
    try:
        return json.loads(roh.strip())
    except Exception:
        return {}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runden", type=int, default=5)
    p.add_argument("--pause", type=float, default=6.0)
    args = p.parse_args()

    kerne, logisch, ram, cpuname = kerne_und_ram()
    print("Ausstellungsrechner")
    print(f"  CPU:  {cpuname}")
    print(f"  Kerne: {kerne} physisch / {logisch} logisch")
    print(f"  RAM:   {ram} GB")
    print("=" * 88)

    # CPU-Zeit je Prozess ueber die Runden -> echter Anteil, nicht Momentaufnahme
    erst = {p["id"]: p for p in messrunde()}
    t0 = time.time()
    gesamt = []

    for r in range(args.runden):
        time.sleep(args.pause)
        g = gesamtlast()
        gesamt.append(g.get("cpu"))
        print(f"  Runde {r+1}: CPU gesamt {g.get('cpu','?')} %, "
              f"frei {g.get('freiMB','?')} von {g.get('gesamtMB','?')} MB")

    letzt = {p["id"]: p for p in messrunde()}
    dauer = time.time() - t0

    print()
    print(f"Ueber {dauer:.0f} s, {logisch or '?'} logische Kerne")
    print(f"{'Prozess':<14}{'PID':>7}{'CPU-Anteil':>12}{'RAM MB':>9}")

    zeilen = []
    for pid, jetzt in letzt.items():
        vorher = erst.get(pid)
        if not vorher:
            continue
        verbraucht = jetzt["cpu"] - vorher["cpu"]
        # Anteil EINES Kerns; >100 % heisst mehrere Kerne parallel
        anteil = verbraucht / dauer * 100
        zeilen.append((jetzt["name"], pid, anteil, jetzt["ws"]))

    zeilen.sort(key=lambda z: -z[2])
    for name, pid, anteil, ws in zeilen:
        print(f"{name:<14}{pid:>7}{anteil:>11.1f}%{ws:>9}")

    # --- Zusammenfassung nach Programm ---
    print()
    nach_name = defaultdict(lambda: [0.0, 0, 0])
    for name, _pid, anteil, ws in zeilen:
        nach_name[name][0] += anteil
        nach_name[name][1] += ws
        nach_name[name][2] += 1
    print(f"{'Programm':<14}{'CPU gesamt':>12}{'RAM MB':>9}{'Prozesse':>10}")
    for name, (a, w, n) in sorted(nach_name.items(), key=lambda x: -x[1][0]):
        print(f"{name:<14}{a:>11.1f}%{w:>9}{n:>10}")

    sauber = [c for c in gesamt if isinstance(c, (int, float))]
    if sauber:
        print()
        print(f"CPU gesamt: min {min(sauber)} %, max {max(sauber)} %, "
              f"Mittel {sum(sauber)/len(sauber):.0f} %")
    print()
    print("Lesart: 100 % = ein voller Kern. Bei", logisch or "?", "logischen Kernen")
    print("ist", (logisch or 1) * 100, "% die Obergrenze aller Prozesse zusammen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
