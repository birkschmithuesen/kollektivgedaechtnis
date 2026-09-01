# -*- coding: utf-8 -*-
"""Sucht die Ursache fuer die schwankende GPU-Last.

Birk, 2026-09-01: „Manchmal geht sie hoch auf 80 und dann laeuft alles sauber
und perfekt, und manchmal geht sie runter auf 50 und dann ruckelt alles. Wenn
die immer auf 80 bleiben wuerde, wuerde es laufen. Aber irgendwas verhindert
das."

Das ist ein wichtiger Befund und er widerspricht der naheliegenden Deutung:
Wenn die Karte am Anschlag waere, WUERDE es bei 80 % ruckeln und bei 50 %
laufen. Es ist genau andersherum. Hohe Last + fluessig heisst: die Karte KANN,
sie darf nur nicht durchgehend. Etwas bremst sie.

Verdaechtige, die dieses Muster erzeugen -- alle hier gemessen:

  1. Taktdrosselung wegen Temperatur oder Leistungsgrenze. Klassisch bei einem
     Laptop von 2015 mit zugesetztem Luefter: die Karte laeuft heiss, taktet
     runter, kuehlt ab, taktet hoch. Genau das erzeugt „mal 80, mal 50".
  2. Energieprofil von Windows (Energiesparmodus / Akkubetrieb). Ein
     Netzteil, das nicht steckt, oder ein Profil auf „Ausbalanciert" deckelt
     die Karte hart.
  3. NVIDIA-eigene Energieverwaltung („Optimale Leistung" gegen „Adaptiv").
     Adaptiv senkt den Takt, sobald die Last kurz faellt -- und die Standzeit
     zwischen zwei Fahrt-Etappen ist genau so eine Pause.

Nur Kennzahlen, kein Eingriff. Aendert NICHTS.

Aufruf auf der Station:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe ^
        gpu-drossel-diagnose.py --sekunden 60
"""

import argparse
import json
import subprocess
import time


def ps(befehl: str, timeout: float = 90) -> str:
    return subprocess.run(["powershell", "-NoProfile", "-Command", befehl],
                          capture_output=True, text=True, timeout=timeout).stdout.strip()


def nvidia_smi(felder: str) -> str:
    """nvidia-smi liegt nicht im PATH, sondern im Treiberverzeichnis."""
    pfade = [
        r"C:\Windows\System32\nvidia-smi.exe",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
    ]
    for p in pfade:
        try:
            aus = subprocess.run([p, f"--query-gpu={felder}",
                                  "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=30)
            if aus.returncode == 0 and aus.stdout.strip():
                return aus.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return ""


def energie() -> None:
    print("--- Windows-Energieprofil ---")
    aus = ps("powercfg /getactivescheme")
    print("  ", aus or "nicht lesbar")
    # Netzteil oder Akku? Ein Laptop im Akkubetrieb drosselt IMMER.
    akku = ps("(Get-CimInstance Win32_Battery).BatteryStatus")
    deutung = {"1": "AKKU (entlaedt) -- drosselt!", "2": "Netzteil angeschlossen"}
    print("   Stromversorgung:", deutung.get(akku.strip(), f"Status {akku or '?'} (kein Akku = Desktop)"))


def gpu_statisch() -> None:
    print("\n--- NVIDIA Quadro: Grenzen und Zustand ---")
    z = nvidia_smi("name,temperature.gpu,power.draw,power.limit,"
                   "clocks.current.graphics,clocks.max.graphics,"
                   "utilization.gpu,pstate")
    if not z:
        print("   nvidia-smi nicht gefunden -- Treiberpfad pruefen.")
        return
    teile = [t.strip() for t in z.split(",")]
    namen = ["Name", "Temperatur C", "Leistung W", "Leistungsgrenze W",
             "Takt MHz", "Takt max MHz", "Auslastung %", "P-State"]
    for n, w in zip(namen, teile):
        print(f"   {n:<20} {w}")


def drosselgruende() -> None:
    """Der eigentliche Kern: WARUM taktet die Karte runter?"""
    print("\n--- Drosselungsgruende laut Treiber ---")
    z = nvidia_smi("clocks_throttle_reasons.active,"
                   "clocks_throttle_reasons.gpu_idle,"
                   "clocks_throttle_reasons.sw_power_cap,"
                   "clocks_throttle_reasons.hw_thermal_slowdown,"
                   "clocks_throttle_reasons.sw_thermal_slowdown")
    if not z:
        print("   Diese Karte meldet keine Drosselgruende (aeltere Quadro).")
        print("   Ersatzweise Takt und Temperatur ueber die Zeit beobachten.")
        return
    teile = [t.strip() for t in z.split(",")]
    namen = ["aktiv (Bitmaske)", "Leerlauf", "Leistungsgrenze",
             "Temperatur (Hardware)", "Temperatur (Software)"]
    for n, w in zip(namen, teile):
        print(f"   {n:<26} {w}")


def verlauf(sekunden: float, takt: float) -> None:
    """Takt, Temperatur und Auslastung ueber die Zeit -- hier wird das
    Schwanken sichtbar, das Birk beschreibt."""
    print(f"\n--- Verlauf ueber {sekunden:.0f} s ---")
    print(f"{'s':>5}{'Auslastung':>12}{'Takt MHz':>10}{'Temp C':>8}{'Watt':>7}{'P':>4}")
    t0 = time.time()
    proben = []
    while time.time() - t0 < sekunden:
        z = nvidia_smi("utilization.gpu,clocks.current.graphics,"
                       "temperature.gpu,power.draw,pstate")
        if z:
            t = [x.strip() for x in z.split(",")]
            try:
                proben.append((float(t[0]), float(t[1]), float(t[2])))
            except ValueError:
                pass
            print(f"{time.time()-t0:>5.0f}{t[0]:>11}%{t[1]:>10}{t[2]:>8}{t[3]:>7}{t[4]:>4}")
        time.sleep(takt)

    if len(proben) > 2:
        ausl = [p[0] for p in proben]
        takte = [p[1] for p in proben]
        temps = [p[2] for p in proben]
        print()
        print(f"   Auslastung: {min(ausl):.0f} bis {max(ausl):.0f} %")
        print(f"   Takt:       {min(takte):.0f} bis {max(takte):.0f} MHz")
        print(f"   Temperatur: {min(temps):.0f} bis {max(temps):.0f} C")
        print()
        if max(takte) - min(takte) > 100:
            print("   >>> Der TAKT schwankt deutlich. Das ist die Drosselung,")
            print("       die Birk als 'mal 80, mal 50' sieht.")
        if max(temps) >= 80:
            print("   >>> Ueber 80 C: Temperatur ist ein plausibler Grund.")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sekunden", type=float, default=60)
    p.add_argument("--takt", type=float, default=3.0)
    args = p.parse_args()

    energie()
    gpu_statisch()
    drosselgruende()
    verlauf(args.sekunden, args.takt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
