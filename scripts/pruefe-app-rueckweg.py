"""Faehrt den Weg der App nach: Foto rein, Portrait zurueck, Bild abholen.

Genau die Kette, die `MainActivity` geht -- ohne Handy, damit sie pruefbar ist,
wenn Birk nur das Telefon dabei hat:

  1. POST /api/photo   mit rohen JPEG-Bytes (kein multipart, wie die App)
  2. Antwort lesen     -> {"ok": true, "portrait": "<name>.png"}
  3. GET  /media/portraits/<name>   -> das fertige Portrait

Punkt 3 ist der, um den es geht: Birks Frage war, ob der Foto-Ausschnitt
zurueck bis in die App kommt. Ein `ok: true` allein beweist das NICHT -- die
Vorschau blieb schon einmal stumm, weil die Gegenstelle zwar `ok` sagte, aber
kein `portrait`-Feld lieferte und unter dem falschen Pfad mountete.

Zusaetzlich wird das zurueckgeholte Portrait vermessen: Groesse, und ob es
ueberhaupt Bildinhalt hat. Ausgegeben werden nur Zahlen und Dateinamen.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def hole(url: str, timeout: int = 30) -> tuple[int, bytes, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as antwort:
            return antwort.status, antwort.read(), antwort.headers.get("Content-Type", "")
    except urllib.error.HTTPError as fehler:
        return fehler.code, fehler.read(), ""


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("foto", help="JPEG, das eingeworfen wird")
    p.add_argument("--station", default="100.94.47.6:8800")
    p.add_argument("--ziel", default=None, help="wohin das zurueckgeholte Portrait geschrieben wird")
    args = p.parse_args()

    basis = f"http://{args.station}"
    bytes_ = Path(args.foto).read_bytes()

    print(f"Weg der App gegen {basis}")
    print(f"Foto: {Path(args.foto).name}  ({len(bytes_) / 1024:.0f} kB)")
    print("=" * 66)

    # --- 1. Einwurf, exakt wie die App: rohe Bytes im Rumpf ---
    anfrage = urllib.request.Request(
        f"{basis}/api/photo", data=bytes_,
        headers={"Content-Type": "image/jpeg"}, method="POST")
    try:
        with urllib.request.urlopen(anfrage, timeout=120) as antwort:
            code = antwort.status
            rumpf = antwort.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as fehler:
        print(f"1. POST /api/photo   -> HTTP {fehler.code}")
        print(f"   {fehler.read().decode('utf-8', 'replace')[:200]}")
        return 1
    except urllib.error.URLError as fehler:
        print(f"1. POST /api/photo   -> nicht erreichbar: {fehler.reason}")
        return 1

    print(f"1. POST /api/photo   -> HTTP {code}")
    daten = json.loads(rumpf)
    print(f"   Antwort: {rumpf[:120]}")

    # --- 2. Das Feld, an dem die Vorschau haengt ---
    name = daten.get("portrait")
    if not name:
        print("2. FEHLER: die Antwort nennt KEIN 'portrait' -- die App kann nichts zeigen.")
        return 2
    print(f"2. Portraitname      -> {name}")

    # --- 3. Genau der Aufruf, den die App macht ---
    url = f"{basis}/media/portraits/{name}"
    status, inhalt, typ = hole(url)
    print(f"3. GET {url}")
    print(f"   -> HTTP {status}, {len(inhalt) / 1024:.0f} kB, {typ}")

    if status != 200:
        print("   FEHLER: die App bekaeme hier nichts zu sehen.")
        return 3
    if not inhalt.startswith(b"\x89PNG\r\n\x1a\n"):
        print("   FEHLER: das ist kein PNG.")
        return 4

    ziel = Path(args.ziel) if args.ziel else Path(f"/tmp/{name}")
    ziel.write_bytes(inhalt)
    print(f"   gespeichert: {ziel}")

    print("=" * 66)
    print("Der Ausschnitt kommt bis zur App zurueck: ok=%s, Portrait %d kB."
          % (daten.get("ok"), len(inhalt) / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
