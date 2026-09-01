"""FastAPI app: three static pages, one SSE stream, the operator API."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from kg.export import build_graph, write_graph_json
from kg.photos import make_portrait

# Windows resolves MIME types from the registry, where HKCR\.js is routinely
# "text/plain". Starlette's StaticFiles asks `mimetypes` and therefore serves
# our ES modules as text/plain, and Chromium refuses them outright: "Expected a
# JavaScript module script but the server responded with a MIME type of
# text/plain". The page then loads, styles fine and stays EMPTY -- no error,
# no missing file, just no script. Observed on the exhibition machine
# 2026-08-29; harmless no-op on Linux, where the mapping is already correct.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

# Obergrenze fuer ein Foto aus der App (`/api/photo`). 12 MB fasst jedes Bild,
# das die App erzeugt (2048px lange Kante, JPEG Q85, typisch deutlich unter
# 1 MB) mit reichlich Luft, und schliesst zugleich aus, dass ein versehentlich
# geschicktes Panorama den Speicher der Station belegt, waehrend die Wand
# laeuft.
MAX_PHOTO_BYTES = 12 * 1024 * 1024


class MaxTerms(BaseModel):
    # Upper bound generous enough to mean "alle" on any exhibition-scale
    # graph without needing a separate sentinel value (spec §4).
    value: int = Field(ge=1, le=1000)


class HiddenFlag(BaseModel):
    node_id: str
    hidden: bool


class PersonName(BaseModel):
    person_id: str
    # Nach oben begrenzt, aus demselben Grund wie bei den Reglern: was hier
    # ankommt, landet unter einem Zitat auf einer 1920px-Wand. 120 Zeichen
    # fassen jeden wirklichen Namen und schließen ein versehentlich
    # hineinkopiertes Transkript aus. Leer ist ausdrücklich erlaubt — so
    # löscht der Operator einen verhörten Namen wieder (kg.store).
    name: str = Field(max_length=120)


class CameraMode(BaseModel):
    mode: Literal["fit", "manual", "pan"]


class CameraSpeed(BaseModel):
    # A fraction of the tuned traversal speed: 1.0 is as fast as the tour ever
    # goes (the pace the motion was judged at), 0.25 is a quarter of that —
    # four times as long per leg.
    #
    # 🔴 Untergrenze am 2026-09-01 von 0.25 auf 0.05 gesenkt (zweimal: erst
    # 0.1, dann auf Birks „mach nach unten noch mehr headroom" 0.05). Birk stand beim
    # Einrichten vor Ort auf **genau 0,25**, also am Anschlag, und meldete:
    # „Der Tempo-Regler hat keinen Einfluss." Er hatte recht — langsamer ging
    # nicht mehr. Die alte Begründung („darunter liest sich eine Etappe wie ein
    # eingefrorener Bildschirm") galt für eine Fahrt über ein kleines Netz; bei
    # 138 Knoten auf 3840 px ist eine langsamere Fahrt genau das Gewünschte.
    #
    # Nach oben bleibt der Deckel bei 1.0: die Wand soll nie schneller laufen
    # als das Tempo, das jemand beurteilt hat.
    factor: float = Field(ge=0.05, le=1.0)


#: Die Mindestschriftgroesse, mit der eine Flaeche startet, in gezeichneten
#: Pixeln — fuer Foyer UND Saal dieselbe (Birk, 2026-09-02).
#:
#: 🔴 GEMESSEN, nicht gesetzt. Rekonstruiert aus Birks Kalibrierung vom
#: 2026-09-01, die in `data/kg.db` stand (`camera_zoom` 1.55, `portrait_size`
#: 330, `max_terms` 32), angewandt auf das dichte Netz aus `data-dichte/60`
#: (60 Personen, 78 Begriffe) auf der 3840x2160 breiten Ausstellungsflaeche:
#: fit-Niveau 0.986 x Regler 1.55 x `--label-size` 26 = 39.7 px. Die
#: Gegenprobe schliesst sich: 40 / 26 = 1.538, also praktisch genau der
#: Regler, den Birk eingestellt hatte.
#:
#: Im Saal (1920x1080) bedeuten dieselben 40 px den doppelten Bildanteil, also
#: weniger Netz und groessere Schrift — was dort die erklaerte Absicht ist
#: („aus dem Saal zaehlt Lesbarkeit, nicht Fuelle", PLENUM_REGLER unten).
#:
#: Die Herleitung im Langen steht bei `MIN_LABEL_DEFAULT` in
#: frontend/static/camera.js, zusammen mit der gemessenen Interview-Leiter.
MIN_LABEL_DEFAULT = 40.0


class CameraMinLabel(BaseModel):
    # Die kleinste Schrift, die auf der Wand noch stehen soll, in GEZEICHNETEN
    # Pixeln — der Regler, der am 2026-09-02 den Zoomfaktor abgeloest hat.
    #
    # Warum keine Vergroesserung mehr: Ein Faktor auf ein kleines Netz zoomt in
    # drei Begriffe hinein. Birk am 2026-09-02: „so wie jetzt grade erst ein
    # Interview und wenig Begriffe habe, dann ist alles viel zu gross und viel
    # zu nah." Eine Mindestschrift beantwortet dagegen die Frage, die vor der
    # Wand steht — und aus derselben Zahl folgt AUCH, ob es ueberhaupt eine
    # Kamerafahrt braucht: Liefert die Vollansicht schon diese Schriftgroesse,
    # ist das ganze Netz lesbar und die Kamera hat nichts zu suchen.
    #
    # Beidseitig beschraenkt, aus demselben Grund wie die Portraitgroesse
    # daneben: Was ein Streuwert auch anrichtet, er darf eine unbeaufsichtigte
    # Wand nicht unbrauchbar hinterlassen. 8 px ist unterhalb jeder Lesbarkeit
    # und damit praktisch „nie fahren"; 120 px sind auf 2160 px Hoehe ein
    # Zwanzigstel des Bildes und damit die Grenze, ab der ein einzelner Begriff
    # die Wand fuellt.
    pixels: float = Field(ge=8.0, le=120.0)


class PortraitSize(BaseModel):
    # The largest a portrait may get on the wall, in RENDERED pixels, while
    # the camera is driving — an upper bound, not a size (Birk, 2026-08-30;
    # frontend/static/projection.js). Bounded on both sides for the same
    # reason as the zoom next to it: whatever a stray value does, it must not
    # be able to leave an unattended wall unusable.
    #
    # 🔴 Obergrenze am 2026-09-01 von 260 auf 700 angehoben. Die 260 stammten
    # aus Birks Vorgabe vom 2026-08-29 und waren an einer **1920 px** breiten
    # Wand beurteilt („darüber verdrängen ein paar Gesichter alles andere").
    # Die Ausstellungsfläche ist inzwischen **3840 px** breit — dieselbe Zahl
    # bedeutet dort ein halb so großes Gesicht, und Birk stand beim Einrichten
    # vor Ort am Anschlag, ohne dass sich noch etwas bewegte:
    # „Der Tempo-Regler und der Portraitgrößen-Regler haben keinen Einfluss."
    #
    # 700 ist derselbe Bildanteil wie 260 auf 1920, plus etwas Luft nach oben
    # (260/1920 = 13,5 %; 700/3840 = 18,2 %). Die Untergrenze bleibt bei 40:
    # ein Punkt ist ein Punkt, unabhängig von der Wandbreite.
    pixels: float = Field(ge=40.0, le=700.0)


# ---------------------------------------------------------------------------
# Die Regler der Plenarfläche (Birk, 2026-09-01 vor Ort)
#
# 🔴 EIGENE SCHLÜSSEL, DIESELBE TABELLE. Die Saalwerte liegen als
# `plenum_<name>` in derselben `setting`-Tabelle wie die Foyerwerte und
# überschreiben nie deren Schlüssel. Das ist die ganze Trennung, und sie ist
# absichtlich so klein: eine zweite Tabelle (oder gar eine zweite Datenbank)
# hätte einen zweiten Migrationsweg, einen zweiten Sicherungsweg und einen
# zweiten Weg, beim Umschalten der Demodaten kaputtzugehen.
#
# 🔴 EINE TABELLE STATT SIEBEN MODELLE. Jeder Regler hier ist eine Zeile —
# Schranke, Vorgabe, Beschriftung und Einheit an einer Stelle. Der Server
# validiert dagegen (`_plenum_wert`), der Zustand liest daraus
# (`plenum_state`), und das Bedienfeld BAUT SICH DARAUS
# (`GET /api/plenum/regler`). Damit kann die Oberfläche keinen Wert anbieten,
# den die API ablehnt — der Fehler, der bei den Foyer-Reglern zweimal passiert
# ist (Bereich im HTML und Schranke im Server liefen auseinander, zuletzt am
# 2026-09-01 bei `portrait_size`: 260 im Markup gegen 700 im Server).
#
# Die Vorgaben sind ein Startpunkt für den Saal, kein Ergebnis: 1920×1080 aus
# Saalbreite gelesen. Beurteilt wird am Bild, deshalb sind es Regler.
PLENUM_REGLER: tuple[dict, ...] = (
    # 🔴 KEIN eigener `max_terms` mehr (Birk, 2026-09-02): „die anzahl der
    # begriffe soll bei plenar genau so sein wie auf dem touch screen, nur die
    # schriftgröße ggf anders". Der Saal hatte bis dahin einen eigenen Schieber
    # mit der Vorgabe 20 gegen 32 im Foyer — beide Flächen zeigten also
    # verschiedene Begriffe, und wer im Saal auf etwas zeigte, meinte ein
    # anderes Bild als der, der am Touchscreen stand.
    #
    # Die Trennung, die BLEIBT, ist die Schriftgröße: `camera_min_label` steht
    # weiterhin je Fläche, weil eine 1920er Projektion aus zwanzig Metern eine
    # andere Zahl braucht als ein Touchscreen aus einem Meter. Dass beide
    # Vorgaben heute gleich sind, ist eine Einstellung, keine Kopplung.
    #
    # Die Flächen greifen die Begriffszahl deshalb aus dem Foyer-Zustand ab,
    # nicht aus `plenum` — siehe frontend/projection.html, `setMaxTerms`.
    {
        "key": "camera_mode",
        "label": "Kamera",
        "typ": "auswahl",
        "auswahl": ("fit", "manual", "pan"),
        "beschriftungen": ("alles zeigen", "manuell", "automatisch schwenken"),
        # Die Fahrt IST der Entwurf für den Saal (Birks Punkt 7); im Foyer
        # bleibt die Vorgabe „alles zeigen".
        "default": "pan",
        "hinweis": "im Saal schaut man zu — die Fahrt ist die Vorgabe",
    },
    {
        "key": "camera_min_label",
        "label": "Mindestschrift",
        "typ": "float",
        # Bereich und Schritt spiegeln die Serverschranke `CameraMinLabel`,
        # damit das Bedienfeld keinen Wert anbieten kann, den die API ablehnt.
        "min": 8.0,
        "max": 120.0,
        "schritt": 1,
        "default": MIN_LABEL_DEFAULT,
        "einheit": "px",
        "hinweis": "so klein darf die Schrift werden — darunter fährt die Kamera näher heran",
    },
    {
        "key": "camera_speed",
        "label": "Tempo",
        "typ": "float",
        "min": 0.05,
        "max": 1.0,
        "schritt": 0.05,
        "default": 0.25,
        "einheit": "",
        "hinweis": "1,00 = volles Fahrtempo, 0,25 = ein Viertel davon",
    },
    {
        "key": "portrait_size",
        "label": "Porträtgröße",
        "typ": "float",
        "min": 40.0,
        "max": 700.0,
        "schritt": 5,
        "default": 260.0,
        "einheit": "px",
        # 260 ist keine geratene Zahl: genau dieser Wert war Birks Vorgabe vom
        # 2026-08-29 und ist an einer 1920 px breiten Wand beurteilt worden
        # (13,5 % der Bildbreite). Die Foyerfläche ist inzwischen 3840 px breit
        # und steht deshalb bei 700 — die Saalfläche ist wieder 1920.
        "hinweis": "Obergrenze in gezeichneten Pixeln; 260 sind an 1920 px beurteilt",
    },
    {
        "key": "qr_size",
        "label": "QR-Größe",
        "typ": "float",
        "min": 120.0,
        "max": 720.0,
        "schritt": 10,
        "default": 360.0,
        "einheit": "px",
        "hinweis": "muss aus dem Saal von einer Handykamera erfasst werden",
    },
    {
        "key": "hinweis_intervall",
        "label": "Erklärungstext alle",
        "typ": "float",
        "min": 20.0,
        "max": 900.0,
        "schritt": 10,
        "default": 120.0,
        "einheit": "s",
        "hinweis": "von Erscheinen zu Erscheinen",
    },
    {
        "key": "hinweis_dauer",
        "label": "Erklärungstext steht",
        "typ": "float",
        "min": 5.0,
        "max": 120.0,
        "schritt": 5,
        "default": 20.0,
        "einheit": "s",
        "hinweis": "lang genug zum Lesen UND zum Scannen",
    },
)

_PLENUM_NACH_SCHLUESSEL = {regler["key"]: regler for regler in PLENUM_REGLER}


def _plenum_wert(regler: dict, roh) -> str:
    """Prüft einen Saalwert gegen seine Zeile und gibt ihn als Text zurück.

    Wirft `ValueError` mit einem Satz, der im Bedienfeld lesbar ist — das ist
    hier keine Kosmetik: Wer im Saal auf einen Fehler stößt, steht neben einem
    Beamer und nicht vor einem Log.
    """
    if regler["typ"] == "auswahl":
        if roh not in regler["auswahl"]:
            raise ValueError(f"{roh!r} ist keine der Möglichkeiten {regler['auswahl']}")
        return str(roh)
    try:
        zahl = float(roh)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{roh!r} ist keine Zahl") from exc
    if not (regler["min"] <= zahl <= regler["max"]):
        raise ValueError(f"{zahl} liegt außerhalb von {regler['min']}..{regler['max']}")
    return str(int(zahl)) if regler["typ"] == "int" else str(zahl)


def _plenum_lesen(regler: dict, roh: str):
    """Ein gespeicherter Wert zurück in seinen Typ — mit der Vorgabe als Netz.

    Ein unlesbarer Eintrag (von Hand editiert, aus einer älteren Fassung, halb
    geschriebene Datei) darf die Saalwand nicht anhalten. Sie zeigt dann die
    Vorgabe, und das ist an einer unbeaufsichtigten Fläche die richtige
    Richtung zu scheitern.
    """
    if regler["typ"] == "auswahl":
        return roh if roh in regler["auswahl"] else regler["default"]
    try:
        zahl = float(roh)
    except (TypeError, ValueError):
        return regler["default"]
    if not (regler["min"] <= zahl <= regler["max"]):
        return regler["default"]
    return int(zahl) if regler["typ"] == "int" else zahl


def plenum_state(store) -> dict:
    """Die Saalwerte, wie sie die Plenarfläche liest."""
    return {
        regler["key"]: _plenum_lesen(
            regler, store.get_setting(f"plenum_{regler['key']}", str(regler["default"]))
        )
        for regler in PLENUM_REGLER
    }


class PlenumSetting(BaseModel):
    key: str = Field(max_length=40)
    # Zahl ODER Text, weil ein Regler beides sein kann (`camera_mode` ist eine
    # Auswahl). Geprüft wird nicht hier, sondern gegen die Zeile in
    # PLENUM_REGLER — sonst stünde die Schranke ein zweites Mal im Code.
    value: float | str


class InterviewSwitch(BaseModel):
    # Der Schalter am Mikrofon, gemeldet vom STT-Server (fundusbot,
    # `--mic-gate`). `source` ist bewusst frei und nur zur Nachvollziehbarkeit
    # in den Logs -- entschieden wird allein an `on`.
    on: bool
    source: str = Field(default="mic_switch", max_length=40)


class Point(BaseModel):
    x: float
    y: float


class Positions(BaseModel):
    positions: dict[str, Point]


def current_state(store) -> dict:
    person = store.open_person()
    return {
        "max_terms": int(store.get_setting("max_terms", "1")),
        "camera_mode": store.get_setting("camera_mode", "fit"),
        # D4 (Birk, 2026-08-19): Die Wand öffnet auf dem ganzen Netz, die Nähe
        # wird vor Ort eingestellt. Seit dem 2026-09-02 ist der Regler dafür
        # eine MINDESTSCHRIFTGRÖSSE in gezeichneten Pixeln statt eines
        # Zoomfaktors — und entscheidet damit zugleich, ob es überhaupt eine
        # Kamerafahrt gibt: Solange die Vollansicht diese Schrift liefert,
        # steht die Wand still (siehe MIN_LABEL_DEFAULT in camera.js).
        "camera_min_label": float(store.get_setting("camera_min_label", str(MIN_LABEL_DEFAULT))),
        # 1.0 = the traversal's tuned pace, 0.25 = a quarter of it. Slowing the
        # tour down is a room-and-audience judgement, like the zoom next to it,
        # so it belongs to the operator rather than to a constant.
        "camera_speed": float(store.get_setting("camera_speed", "1")),
        # How large a portrait may get on the wall in the automatic modes, in
        # rendered pixels (Birk, 2026-08-29 and 2026-08-30). The default
        # matches projection.js's DEFAULT_PORTRAIT_SIZE, so a station that has
        # never been touched shows the same wall whether or not this setting
        # exists yet.
        "portrait_size": float(store.get_setting("portrait_size", "120")),
        "stt_connected": store.get_setting("stt_connected", "0") == "1",
        # Der physische Schalter am Mikrofon, getrennt von `stt_connected`
        # (siehe Core.on_mic_switch). Default "1": eine Station ohne
        # Schalter-Meldung hat ein dauerhaft offenes Mikrofon, und "aus"
        # anzuzeigen waere dort schlicht falsch.
        "mic_on": store.get_setting("mic_on", "1") == "1",
        # Die Saalfläche, getrennt gespeichert (Birk, 2026-09-01). REIN
        # ADDITIV: alle Schlüssel darüber stehen unverändert, wo sie standen,
        # und jeder bestehende Leser — Foyer-Wand, /operator, Spiegel — sieht
        # seins wie bisher. Ein zweiter Zustandsweg neben /api/state und dem
        # SSE-Push wäre der zweite Weg, der still ausfällt; hier reist beides
        # in derselben Meldung, und wer welchen Satz liest, entscheidet die
        # Fläche (`?plenum=1` in frontend/projection.html).
        "plenum": plenum_state(store),
        "interview": None
        if person is None
        else {"person_id": person.id, "started_at": person.started_at},
    }


def broadcast_graph(store, cfg, bus) -> None:
    bus.publish({"type": "graph", "graph": write_graph_json(store, cfg.graph_json_path)})


def broadcast_state(store, bus) -> None:
    bus.publish({"type": "state", "state": current_state(store)})


def create_app(store, cfg, bus, core=None) -> FastAPI:
    app = FastAPI(title="Kollektivgedächtnis")
    app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")
    app.mount("/media/portraits", StaticFiles(directory=cfg.portrait_dir), name="portraits")

    @app.get("/")
    def index() -> RedirectResponse:
        return RedirectResponse("/projection")

    @app.get("/projection")
    def projection() -> FileResponse:
        return FileResponse(FRONTEND / "projection.html")

    @app.get("/plenum")
    def plenum() -> RedirectResponse:
        """Die Adresse für den Ausspieler im Plenarsaal.

        Eine UMLEITUNG auf dieselbe Wandseite mit gesetztem Schalter, keine
        zweite Datei: Die Saalfläche ist dieselbe Anwendung mit einer anderen
        Auflage (`static/plenum.css`) und anderen Reglern (`state.plenum`),
        und ein zweites HTML daneben liefe von der ersten weg — genau das,
        wovor die Kommentare in `projection.html` mehrfach warnen.

        Trotzdem eine eigene, kurze Adresse: Sie steht im Kiosk-Start des
        Saal-Laptops und wird dort von Hand getippt. `/plenum` ist zu merken,
        `/projection?plenum=1` ist es nicht — und nach der Umleitung steht der
        Schalter sichtbar in der Adresszeile, was beim Suchen hilft.
        """
        return RedirectResponse("/projection?plenum=1")

    @app.get("/operator")
    def operator() -> FileResponse:
        return FileResponse(FRONTEND / "operator.html")

    @app.get("/operator-plenum")
    def operator_plenum() -> FileResponse:
        """Das eigene Bedienfeld für den Saal.

        Getrennt vom bestehenden `/operator`, damit die Foyer-Einstellungen
        unberührt bleiben (Birk, 2026-09-01) — und weil es eine andere Aufgabe
        hat: keine Liste, kein Transkript, kein Ausblenden, nur die Regler der
        Anzeige, groß genug für einen Finger auf einem Laptop-Touchpad neben
        dem Beamer.
        """
        return FileResponse(FRONTEND / "operator-plenum.html")

    @app.get("/testpattern")
    def testpattern() -> FileResponse:
        return FileResponse(FRONTEND / "testpattern.html")

    # Wieviele Finger meldet der Touchschirm gleichzeitig? Eine eigene Adresse,
    # damit die Frage am Geraet beantwortet werden kann, ohne eine Datei
    # dorthin zu kopieren -- die Station serviert ohnehin schon alles andere.
    @app.get("/touchtest")
    def touchtest() -> FileResponse:
        return FileResponse(FRONTEND / "touchtest.html")

    @app.get("/graph.json")
    def graph_json() -> JSONResponse:
        return JSONResponse(build_graph(store))

    @app.get("/api/state")
    def api_state() -> dict:
        return current_state(store)

    @app.get("/api/plenum/regler")
    def api_plenum_regler() -> dict:
        """Die Reglertabelle, aus der sich das Saal-Bedienfeld baut.

        Damit steht jede Schranke genau einmal im Code. Die Alternative wäre,
        Bereich und Schrittweite im HTML zu wiederholen — und genau dort sind
        sie schon zweimal auseinandergelaufen (`portrait_size` stand am
        2026-09-01 auf 260 im Markup, während der Server längst 700 erlaubte,
        und Birk stand vor Ort am Anschlag).
        """
        return {"regler": [dict(regler) for regler in PLENUM_REGLER]}

    @app.post("/api/plenum")
    def api_plenum(payload: PlenumSetting) -> dict:
        """Einen Saalwert setzen — reine Anzeige, wie die Kameraregler.

        Ein Endpunkt für alle Regler, geprüft gegen PLENUM_REGLER. Was hier
        ankommt, ändert nichts an Extraktion oder Zusammenführung (Spec §7)
        und auch nichts an der Foyerfläche: geschrieben wird ausschließlich
        unter `plenum_<name>`.
        """
        regler = _PLENUM_NACH_SCHLUESSEL.get(payload.key)
        if regler is None:
            raise HTTPException(status_code=400, detail=f"unbekannter Regler {payload.key!r}")
        try:
            wert = _plenum_wert(regler, payload.value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        store.set_setting(f"plenum_{payload.key}", wert)
        broadcast_state(store, bus)
        return {"ok": True}

    @app.post("/api/max_terms")
    def api_max_terms(payload: MaxTerms) -> dict:
        store.set_setting("max_terms", str(payload.value))
        broadcast_state(store, bus)
        broadcast_graph(store, cfg, bus)
        return {"ok": True}

    @app.post("/api/hidden")
    def api_hidden(payload: HiddenFlag) -> dict:
        try:
            store.set_hidden(payload.node_id, payload.hidden)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        broadcast_graph(store, cfg, bus)
        return {"ok": True}

    @app.post("/api/person_name")
    def api_person_name(payload: PersonName) -> dict:
        # Die Spracherkennung verhört Namen zuverlässig, also muss der Operator
        # sie richtigstellen können — das ist die einzige Korrektur, die er an
        # einem fertigen Interview vornimmt.
        #
        # Nur `broadcast_graph`, kein `broadcast_state`: genau wie /api/hidden
        # darüber, und aus demselben Grund — der Name reist im Graphen mit
        # (kg.export), `current_state` kennt ihn nicht, und eine zweite
        # Rundmeldung mit unverändertem Inhalt würde die Bedienliste nur ein
        # weiteres Mal neu bauen.
        store.set_person_name(payload.person_id, payload.name)
        broadcast_graph(store, cfg, bus)
        return {"ok": True}

    @app.post("/api/camera")
    def api_camera(payload: CameraMode) -> dict:
        store.set_setting("camera_mode", payload.mode)
        broadcast_state(store, bus)
        return {"ok": True}

    @app.post("/api/camera_min_label")
    def api_camera_min_label(payload: CameraMinLabel) -> dict:
        # A display-only control, like the camera mode next to it. Spec §7's
        # "exactly one runtime dial" governs controls that change EXTRACTION
        # or MERGING; this changes neither.
        store.set_setting("camera_min_label", str(payload.pixels))
        broadcast_state(store, bus)
        return {"ok": True}

    @app.post("/api/camera_speed")
    def api_camera_speed(payload: CameraSpeed) -> dict:
        # Display-only, exactly like camera_min_label: it changes how long the tour
        # dwells and travels, never what is extracted or merged.
        store.set_setting("camera_speed", str(payload.factor))
        broadcast_state(store, bus)
        return {"ok": True}

    @app.post("/api/portrait_size")
    def api_portrait_size(payload: PortraitSize) -> dict:
        # Display-only, like the two camera controls above: it bounds how big
        # a face is drawn, never what is extracted, merged or shown.
        # Deliberately independent of camera_min_label — that one chooses the
        # SECTION of the net on the wall, this one bounds the portraits inside
        # it, and turning either must leave the other alone.
        store.set_setting("portrait_size", str(payload.pixels))
        broadcast_state(store, bus)
        return {"ok": True}

    if core is not None:
        # Nur mit Core registriert. Ein Prozess ohne Core (die reine
        # Anzeige-Konfiguration, u.a. in den Tests) hat den Endpunkt dann gar
        # nicht -- besser ein 404 als eine 200, die nichts tut.
        @app.post("/api/photo")
        async def api_photo(request: Request) -> dict:
            """Ein Foto aus der Android-App eroeffnet ein Interview.

            Derselbe Weg, den bisher nur Telegram ging (`TelegramSource.
            _handle_photo` -> `Core.on_photo`), nur ohne den Umweg ueber ein
            fremdes Netz: die App im Tailnet legt die Bytes direkt hier ab.
            Telegram bleibt unveraendert daneben bestehen -- ein zweiter
            Einwurf, kein Ersatz, damit ein Ausfall des einen Wegs die Station
            nicht stillegt.

            **Rohe Bytes im Rumpf, kein multipart.** Das spart die
            Abhaengigkeit `python-multipart` und macht die Android-Seite zu
            einem einzigen `outputStream.write(jpegBytes)` -- kein
            Boundary-Bau, keine Bibliothek. Der Dateiname wird HIER vergeben,
            nie vom Client uebernommen: ein Client-Name waere ein
            Pfad-Injektions-Vektor, und gebraucht wird er fuer nichts.

            Die Groessengrenze ist kein Schikane-Limit, sondern der Schutz
            gegen ein Handy, das versehentlich ein 50-MB-Panorama schickt und
            damit den Speicher der Station belegt, waehrend die Wand laeuft.
            """
            raw = await request.body()
            if not raw:
                raise HTTPException(status_code=400, detail="leerer Rumpf")
            if len(raw) > MAX_PHOTO_BYTES:
                raise HTTPException(
                    status_code=413, detail=f"Bild groesser als {MAX_PHOTO_BYTES} Bytes"
                )
            # Aus den Magic Bytes, nicht aus dem Content-Type-Kopf: der Kopf ist
            # eine Behauptung des Clients, die ersten Bytes sind das Bild. Ein
            # HTML-Fehlerdokument darf hier nie als .jpg auf der Platte landen.
            if not (raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n"):
                raise HTTPException(status_code=415, detail="kein JPEG/PNG")

            at = time.time()
            stem = f"{int(at)}_app{int(at * 1000) % 1000:03d}"
            photo_path = cfg.photo_dir / f"{stem}.jpg"
            portrait_path = cfg.portrait_dir / f"{stem}.png"
            try:
                await asyncio.to_thread(photo_path.write_bytes, raw)
                await asyncio.to_thread(
                    make_portrait, photo_path, portrait_path, cfg.portrait_size
                )
            except Exception as exc:  # ein kaputtes Bild darf die Station nie anhalten
                raise HTTPException(status_code=422, detail=f"Bild unlesbar: {exc}") from exc

            core.on_photo(photo_path, portrait_path, at)
            # Der Name des Portraits, damit die App es sich ansehen kann
            # (`GET /media/portraits/<name>`, schon gemountet). Absichtlich
            # der Name und nicht das Bild selbst: die App soll es sich HOLEN,
            # wenn sie es zeigen will, statt es jedem Einwurf aufzuzwingen —
            # ein Portrait ist ~100 kB, und am Booth zählt, dass der Auslöser
            # schnell wieder frei ist.
            return {"ok": True, "portrait": portrait_path.name}

        @app.post("/api/interview_switch")
        async def api_interview_switch(payload: InterviewSwitch) -> dict:
            """Der Schalter am Mikrofon, gemeldet vom STT-Server.

            Der zweite Weg, ein Interview zu beenden, neben der gesprochenen
            Schlussphrase -- und seit 2026-09-01 auch der zweite, eins zu
            beginnen: `on: true` eroeffnet ein Interview ohne Portraet, weil
            wer kein Foto von sich moechte, trotzdem teilnehmen koennen muss
            (`SessionTracker.mic_switch`). Geschlossen wird bei `on: false`,
            mit eigenem Grund "mic_switch", damit im Nachhinein unterscheidbar
            bleibt, ob ein Interview per Schlusssatz oder per Schalter endete
            -- und geoeffnet mit demselben Grund, damit dasselbe fuer den
            Anfang gilt.

            Kehrt sofort zurueck: `Core.on_mic_switch` legt den Wechsel nur in
            die Warteschlange, geoeffnet und geschlossen wird im Worker. Der
            STT-Server ruft aus einem Wegwerf-Thread heraus auf und darf nicht
            auf eine Pipeline warten.

            `async def`, und das ist hier nicht Geschmack: eine gewoehnliche
            `def`-Route laesst FastAPI im Threadpool laufen, und
            `Core.on_mic_switch` legt von dort aus mit `put_nowait` in eine
            `asyncio.Queue`. Das ist nicht threadsicher -- das Wecken des
            wartenden Workers geht ueber ein Future der Ereignisschleife.
            Verloren ginge dabei nicht die Antwort, sondern das Schliessen des
            Interviews, und zwar still. Alle anderen Einspeiser dieser
            Warteschlange (Telegram, STT-Client, tick-Schleife) sitzen ohnehin
            auf der Schleife; dieser hier muss es auch.

            Kein Test faengt das ab, und das ist ausdruecklich vermerkt statt
            verschwiegen: `put_nowait` aus einem fremden Thread geht in CPython
            meistens gut, weil die Schleife ohnehin gleich wieder pollt. Es ist
            ein Rennen, kein Fehler mit Ansage -- und genau deshalb steht das
            `async` hier und nicht das Vertrauen darauf, dass es schon
            auffiele.
            """
            core.on_mic_switch(payload.on, time.time())
            return {"ok": True, "on": payload.on}

    @app.post("/api/positions")
    def api_positions(payload: Positions) -> dict:
        # No broadcast: positions come FROM the renderer; echoing them would loop.
        store.save_positions({k: (p.x, p.y) for k, p in payload.positions.items()})
        return {"ok": True}

    @app.get("/events")
    async def events() -> StreamingResponse:
        queue = bus.subscribe()

        async def stream():
            try:
                yield _sse({"type": "graph", "graph": build_graph(store)})
                yield _sse({"type": "state", "state": current_state(store)})
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    yield _sse(event)
            finally:
                bus.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
