# -*- coding: utf-8 -*-
"""Wartet auf die Aufloesungsumstellung und misst dann automatisch.

Birk stellt das Laptoppanel gerade von 3840x2160 auf 1920x1080. Statt im
Sekundentakt nachzufragen, wartet dieses Skript auf die Aenderung und faehrt
dann sofort dieselbe Messung wie vorher -- damit der Vergleich echte Zahlen
hat und kein Gefuehl ist.

VORHER gemessen (2026-09-01, Stufe 60, 138 Knoten, beide Schirme, Fahrt `pan`):
    GPU 3D nvidia   38,5 %      GPU 3D intel   22,9 %
    CPU brave      144,4 %      CPU dwm  21,3 %      CPU python  13,4 %

Aufruf auf der Station:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe ^
        warte-auf-fullhd.py
"""

import json
import subprocess
import sys
import time

GEDULD_S = 900          # 15 Minuten warten, dann aufgeben
TAKT_S = 10


def aufloesungen() -> list:
    roh = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_VideoController | "
         "Where-Object {$_.CurrentHorizontalResolution} | "
         "ForEach-Object { @{x=$_.CurrentHorizontalResolution; "
         "y=$_.CurrentVerticalResolution} } | ConvertTo-Json -Compress"],
        capture_output=True, text=True, timeout=60).stdout.strip()
    if not roh or roh == "null":
        return []
    d = json.loads(roh)
    return d if isinstance(d, list) else [d]


def main() -> int:
    start = aufloesungen()
    print("jetzt:", ", ".join(f"{a['x']}x{a['y']}" for a in start))
    if not any(a["x"] >= 3840 for a in start):
        print("Kein 4K mehr aktiv -- die Umstellung ist schon passiert.")
    else:
        print(f"Warte auf die Umstellung (bis zu {GEDULD_S//60} Minuten) ...")
        t0 = time.time()
        while time.time() - t0 < GEDULD_S:
            time.sleep(TAKT_S)
            jetzt = aufloesungen()
            if not any(a["x"] >= 3840 for a in jetzt):
                print(f"\nUmgestellt nach {time.time()-t0:.0f} s: "
                      + ", ".join(f"{a['x']}x{a['y']}" for a in jetzt))
                break
        else:
            print("\nNach der Wartezeit immer noch 4K -- nichts gemessen.")
            return 1

    px = sum(a["x"] * a["y"] for a in aufloesungen())
    print(f"Pixel gesamt jetzt: {px/1e6:.2f} MPx (vorher 10,37 MPx)")
    print("\nBrowserfenster brauchen einen Neuaufbau, damit die Zeichenflaeche")
    print("der neuen Aufloesung entspricht. 20 s Ruhe, dann wird gemessen.")
    time.sleep(20)

    print("\n--- Messung nachher ---")
    subprocess.run([sys.executable, "miss-bildrate.py", "--sekunden", "30",
                    "--notiz", "nachher, Laptoppanel FullHD"], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
