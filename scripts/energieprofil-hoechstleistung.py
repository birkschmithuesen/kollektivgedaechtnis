# -*- coding: utf-8 -*-
"""Stellt den Rechner auf Hoechstleistung -- gegen die schwankende GPU-Last.

Birk, 2026-09-01: „Manchmal geht sie hoch auf 80 und dann laeuft alles sauber
und perfekt, und manchmal geht sie runter auf 50 und dann ruckelt alles. Wenn
die immer auf 80 bleiben wuerde, wuerde es laufen. Aber irgendwas verhindert
das."

GEMESSEN (`gpu-drossel-diagnose.py`, 45 s waehrend der Fahrt):

    Auslastung   22 bis 58 %
    Takt        810 bis 1124 MHz     <- schwankt um 28 %
    Drosselgrund laut Treiber: KEINER
        (Leistungsgrenze: Not Active, Temperatur: Not Active,
         Bitmaske 0x0000000000000000)

Kein Hitzeproblem, keine Leistungsgrenze der Karte. Der Takt faellt trotzdem.
Der Grund steht im Energieprofil:

    Power Scheme: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)
    Stromversorgung: Netzteil angeschlossen

„Balanced" senkt den Takt, sobald die Last kurz nachlaesst -- und genau das
passiert bei jeder Standzeit zwischen zwei Fahrt-Etappen (4,2 s Rast auf
5,2 s Fahrt). Die Karte taktet in der Rast runter und ist zu Beginn der
naechsten Etappe noch unten: das ist Birks „mal 80, mal 50".

Das erklaert auch, warum die Beobachtung anders herum ist, als man erwarten
wuerde: Bei einer ueberlasteten Karte wuerde es bei HOHER Last ruckeln. Hier
laeuft es bei hoher Last sauber -- die Karte kann, sie darf nur nicht
durchgehend.

🔴 Das ist eine Systemeinstellung, kein Programmzustand: sie bleibt nach dem
Neustart erhalten und gilt fuer den ganzen Rechner. Zuruecknehmen mit
`--zuruecknehmen`.

Aufruf auf der Station:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe ^
        energieprofil-hoechstleistung.py                 # nur anzeigen
    ... --setzen
    ... --zuruecknehmen
"""

import argparse
import re
import subprocess

# Windows-Standardprofile, feste GUIDs auf jedem System
HOECHSTLEISTUNG = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
AUSBALANCIERT = "381b4222-f694-41f0-9685-ff5bb260df2e"


def cmd(*teile: str) -> str:
    return subprocess.run(list(teile), capture_output=True, text=True,
                          timeout=60).stdout.strip()


def aktiv() -> str:
    return cmd("powercfg", "/getactivescheme")


def verfuegbar() -> list:
    aus = cmd("powercfg", "/list")
    return re.findall(r"([0-9a-f\-]{36})\s+\((.+?)\)", aus)


def zeige() -> None:
    print("Aktives Profil:")
    print("  ", aktiv() or "nicht lesbar")
    print("\nVerfuegbare Profile:")
    for guid, name in verfuegbar():
        marke = "  <- aktiv" if guid in aktiv() else ""
        print(f"   {guid}  {name}{marke}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--setzen", action="store_true")
    p.add_argument("--zuruecknehmen", action="store_true")
    args = p.parse_args()

    zeige()

    if args.setzen:
        guids = [g for g, _ in verfuegbar()]
        if HOECHSTLEISTUNG not in guids:
            # Auf manchen Systemen ist das Profil ausgeblendet; -duplicatescheme
            # legt es aus der eingebauten Vorlage neu an.
            print("\nProfil 'Hoechstleistung' fehlt, lege es an ...")
            print("  ", cmd("powercfg", "-duplicatescheme", HOECHSTLEISTUNG))
        print("\nSetze auf Hoechstleistung ...")
        cmd("powercfg", "/setactive", HOECHSTLEISTUNG)
        print("  ", aktiv())
        print("\n-> Wirkt sofort, kein Neustart noetig.")
        print("-> Danach mit gpu-drossel-diagnose.py nachmessen: der Takt")
        print("   sollte konstant nahe 1124 MHz stehen statt zwischen 810")
        print("   und 1124 zu schwanken.")
    elif args.zuruecknehmen:
        print("\nZurueck auf Ausbalanciert ...")
        cmd("powercfg", "/setactive", AUSBALANCIERT)
        print("  ", aktiv())
    else:
        print("\n(Nichts geaendert. --setzen zum Umstellen.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
