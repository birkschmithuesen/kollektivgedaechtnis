# -*- coding: utf-8 -*-
"""Weist Brave (und den Rest) der NVIDIA Quadro zu statt der Intel-GPU.

Birk, 2026-09-01, am Task-Manager der Station: „die interne GPU ist dauerhaft
72 % ausgelastet und die Quadro nur zu 30 %, da ist noch richtig Luft."

Er hat recht, und meine frueheren Zahlen haben das verdeckt: ich hatte die
Auslastung nach KARTE gemittelt, statt nach Prozess UND Karte aufzuschluesseln.
Gemessen (`gpu-pro-prozess.py`):

    dwm    Intel HD 530   3d        43,5 %
    brave  Intel HD 530   3d        22,9 %     <- die Anzeige rendert hier
    dwm    NVIDIA Quadro  compute   22,5 %
    brave  NVIDIA Quadro  3d        10,6 %     <- nur ein Drittel davon

    Intel HD 530   SUMME  66,4 %
    NVIDIA Quadro  SUMME  56,8 %

Brave rechnet also ueberwiegend auf der SCHWACHEN Karte, obwohl der
4K-Bildschirm an der starken haengt. Ursache: unter
`HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences` steht NICHTS --
existiert der Schluessel nicht, entscheidet Windows selbst und waehlt auf
Laptops die sparsame Intel.

Dieses Skript setzt die Zuordnung auf „Hoechstleistung" (= NVIDIA). Das ist
dieselbe Einstellung wie in
    Einstellungen > System > Anzeige > Grafik > <App> > Optionen,
nur ohne Klickerei -- und nachvollziehbar, weil sie hier als Wert steht.

🔴 Wirkt erst NACH einem Neustart der Anwendung. Brave muss also einmal
komplett beendet und neu gestartet werden (die Station stoppen und starten
erledigt das).

Aufruf auf der Station:
    C:\\Users\\birk\\kollektivgedaechtnis\\.venv\\Scripts\\python.exe ^
        gpu-auf-nvidia.py                # zeigt nur an, aendert nichts
    ... --setzen                          # setzt die Zuordnung
    ... --zuruecknehmen                   # entfernt sie wieder
"""

import argparse
import subprocess

SCHLUESSEL = r"HKCU\Software\Microsoft\DirectX\UserGpuPreferences"
# Die Programme, die das Bild erzeugen. dwm.exe ist der Fenstermanager und
# traegt mit 43,5 % die groesste Einzellast auf der Intel -- er komponiert
# beide Bildschirme zusammen.
PROGRAMME = [
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
]
HOECHSTLEISTUNG = "GpuPreference=2;"


def ps(befehl: str) -> str:
    return subprocess.run(["powershell", "-NoProfile", "-Command", befehl],
                          capture_output=True, text=True, timeout=90).stdout.strip()


def zeige() -> None:
    aus = ps(f"$p='{SCHLUESSEL}'.Replace('HKCU\\','HKCU:\\'); "
             "if (Test-Path $p) { (Get-Item $p).Property | ForEach-Object { "
             "\"$_ = \" + (Get-ItemProperty -Path $p -Name $_).$_ } } "
             "else { 'kein Eintrag' }")
    print("Aktuelle Zuordnung:")
    for z in (aus.splitlines() or ["(leer)"]):
        print("  ", z.strip())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--setzen", action="store_true")
    p.add_argument("--zuruecknehmen", action="store_true")
    args = p.parse_args()

    zeige()

    if args.setzen:
        print("\nSetze auf Hoechstleistung (NVIDIA Quadro) ...")
        for exe in PROGRAMME:
            befehl = (
                f"$p='{SCHLUESSEL}'.Replace('HKCU\\','HKCU:\\'); "
                "if (-not (Test-Path $p)) { New-Item -Path $p -Force | Out-Null }; "
                f"New-ItemProperty -Path $p -Name '{exe}' "
                f"-Value '{HOECHSTLEISTUNG}' -PropertyType String -Force | Out-Null; "
                "'ok'")
            print(f"  {exe.split(chr(92))[-1]}: {ps(befehl) or 'FEHLER'}")
        print()
        zeige()
        print("\n>>> Brave muss NEU GESTARTET werden, sonst wirkt es nicht.")
        print("    Station stoppen und starten erledigt das.")
        print("    Danach mit gpu-pro-prozess.py nachmessen -- die Zeile")
        print("    'brave / Intel HD 530 / 3d' muss verschwinden oder klein werden.")
    elif args.zuruecknehmen:
        for exe in PROGRAMME:
            ps(f"$p='{SCHLUESSEL}'.Replace('HKCU\\','HKCU:\\'); "
               f"Remove-ItemProperty -Path $p -Name '{exe}' -EA SilentlyContinue")
        print("\nZurueckgenommen.")
        zeige()
    else:
        print("\n(Nichts geaendert. --setzen zum Umstellen.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
