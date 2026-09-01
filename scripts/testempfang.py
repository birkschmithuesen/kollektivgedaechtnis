"""Test-Station fuer die Android-App — ohne LLM, ohne STT, ohne Kosten.

Startet NUR den Webserver mit `/api/photo` und einer kleinen Schauseite, auf
der die eingegangenen Portraits erscheinen. Kein Core, keine Pipeline, kein
API-Schluessel: es geht ausschliesslich darum, die Kette

    Handy -> Tailnet -> POST /api/photo -> make_portrait

zu beweisen, bevor der Ausstellungsrechner wieder da ist.

Aufruf:  uv run python scripts/testempfang.py [--port 8805]
Ansehen: http://<tailnet-ip>:<port>/     (Handy oder Rechner)
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from kg.photos import make_portrait

MAX_PHOTO_BYTES = 12 * 1024 * 1024

# Was angekommen ist, in der Reihenfolge des Eingangs. Nur im Speicher --
# diese Station ueberlebt ihren eigenen Neustart nicht, und soll es auch nicht.
EINGANG: list[dict] = []


def baue(daten: Path) -> FastAPI:
    photo_dir = daten / "photos"
    portrait_dir = daten / "portraits"
    photo_dir.mkdir(parents=True, exist_ok=True)
    portrait_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="KG Testempfang")
    app.mount("/portraits", StaticFiles(directory=portrait_dir), name="portraits")

    @app.post("/api/photo")
    async def api_photo(request: Request) -> dict:
        """Dieselben Pruefungen wie kg/server.py -- absichtlich.

        Eine Testgegenstelle, die grosszuegiger ist als das Original, testet
        das Original nicht: dann geht hier etwas durch, das am
        Ausstellungstag abgewiesen wird.
        """
        raw = await request.body()
        if not raw:
            raise HTTPException(status_code=400, detail="leerer Rumpf")
        if len(raw) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail="Bild zu gross")
        if not (raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(status_code=415, detail="kein JPEG/PNG")

        at = time.time()
        stem = f"{int(at)}_app{int(at * 1000) % 1000:03d}"
        photo_path = photo_dir / f"{stem}.jpg"
        portrait_path = portrait_dir / f"{stem}.png"
        try:
            photo_path.write_bytes(raw)
            make_portrait(photo_path, portrait_path, 512)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Bild unlesbar: {exc}") from exc

        EINGANG.insert(0, {
            "name": portrait_path.name,
            "bytes": len(raw),
            "zeit": time.strftime("%H:%M:%S", time.localtime(at)),
        })
        print(f"[{EINGANG[0]['zeit']}] Foto empfangen: {len(raw)} Bytes -> {portrait_path.name}")
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    def schauseite() -> str:
        if EINGANG:
            kacheln = "".join(
                f'<figure><img src="/portraits/{e["name"]}" alt="">'
                f'<figcaption>{e["zeit"]} · {e["bytes"] // 1024} kB</figcaption></figure>'
                for e in EINGANG[:24]
            )
            kopf = f"<h1>{len(EINGANG)} Foto(s) angekommen</h1>"
        else:
            kacheln = ""
            kopf = "<h1>Warte auf das erste Foto …</h1><p>App: Adresse eintragen, ausloesen.</p>"

        return f"""<!doctype html><html lang="de"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>KG Testempfang</title>
<meta http-equiv="refresh" content="3">
<style>
 body{{background:#0B0B0D;color:#D8B15A;font-family:system-ui,sans-serif;margin:0;padding:24px}}
 h1{{font-size:20px;font-weight:500}}
 p{{color:#888}}
 .g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:16px;margin-top:24px}}
 figure{{margin:0;text-align:center}}
 img{{width:100%;border-radius:50%;display:block}}
 figcaption{{font-size:12px;color:#888;margin-top:6px}}
</style></head><body>{kopf}<div class="g">{kacheln}</div></body></html>"""

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True, "empfangen": len(EINGANG)}

    return app


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8805)
    p.add_argument("--daten", default="/tmp/kg-testempfang")
    args = p.parse_args()

    daten = Path(args.daten)
    print(f"Testempfang laeuft. Daten: {daten}")
    print(f"In der App eintragen:  <tailnet-ip>:{args.port}")
    # 0.0.0.0, damit das Handy im Tailnet drankommt -- genau die Einstellung,
    # die am Ausstellungstag auch in der config.toml stehen muss.
    uvicorn.run(baue(daten), host="0.0.0.0", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
