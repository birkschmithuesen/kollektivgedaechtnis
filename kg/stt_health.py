"""Aufsicht über die Spracherkennung: antwortet der Anbieter, und welcher läuft?

🔴 WARUM ES DIESE DATEI GIBT (2026-09-02, am Gerät passiert):
Infomaniaks Whisper fiel aus. Von außen sah alles in Ordnung aus — der STT-
Dienst antwortete auf `/status` mit „running", der Pegel schlug aus, das
Mikrofongate öffnete, ein Interview begann. Nur kam kein einziges Wort an.
26 erkannte Äußerungen, 0 Transkripte, der Fehler ausschließlich im Log unter
17.000 Zeilen `GET /levels`. Es hat eine Viertelstunde gekostet, das zu finden.

Am Ausstellungstag steht niemand vor einem Terminal. Deshalb gehört diese
Auskunft an dieselbe Stelle wie alles andere, was man wissen muss: ins
Bedienpult.

ZWEI DINGE, DIE HIER ABSICHT SIND

1. **Die Probe geht durch die ganze Kette.** Der Endpunkt nimmt die Datei an
   und gibt eine `batch_id` zurück; der Text kommt erst beim Abholen. Während
   des Ausfalls lieferte das bloße Absenden zeitweise HTTP 200 — eine Probe,
   die dort aufhört, hätte „alles gut" gemeldet, während nichts ankam.
   Gemessen: 6 von 8 Absendungen 200, davon 0 mit Ergebnis.

2. **`gesund` darf `None` sein.** Zwischen Programmstart und erster Probe weiß
   diese Aufsicht nichts. „Nicht geprüft" ist eine andere Auskunft als „geht
   nicht" — dieselbe Regel wie beim „Zustand unbekannt" der Interviewknöpfe im
   Bedienpult. Wer `None` als „ok" rendert, baut genau die stille Falle nach,
   derentwegen es diese Datei gibt.
"""

from __future__ import annotations

import logging
import math
import struct
import time
import wave
from dataclasses import dataclass
from io import BytesIO

log = logging.getLogger(__name__)

#: Die zwei Anbieter, die `scripts/start-stt-mac.sh` über `KG_STT` kennt.
#: 🔴 Die Reihenfolge ist die Rangfolge: Infomaniak (Genf, EU) ist die Vorgabe,
#: ElevenLabs (USA) die Ausnahme. Die ganze Kette ist bewusst EU-souverän —
#: das ist die Zusage an Menschen, die hier ihre Stimme hergeben, keine
#: Vorliebe. Ein Wechsel muss deshalb gedrückt werden und sich melden.
ANBIETER = ("infomaniak", "elevenlabs")

#: Der Endpunkt, den `infomaniak_whisper_backend.py` im fremden Repo benutzt.
#: 🔴 `/1/…`, NICHT `/2/…`: unter `/2/…/openai/v1/audio/transcriptions`
#: antwortet Infomaniak mit 404 (gemessen 2026-09-02). Das LLM und die
#: Embeddings liegen umgekehrt unter `/2/` — beim Ausfall lief das eine
#: tadellos, während das andere weg war. Wer hier den Pfad des LLM einsetzt,
#: misst dauerhaft den falschen Dienst und meldet „gesund", während niemand
#: verstanden wird.
ABSENDEN = "{basis}/1/ai/{produkt}/openai/audio/transcriptions"
ABHOLEN = "{basis}/1/ai/{produkt}/results/{batch}"

#: Status-Wörter, die der Endpunkt für „fertig" benutzt. Mehrere, weil das
#: fremde Backend selbst mehrere prüft und nicht dokumentiert ist, welches gilt.
FERTIG = ("ok", "done", "success", "finished")


def probe_wav(sekunden: float = 0.3, hz: int = 300, rate: int = 16000) -> bytes:
    """Ein kurzer Ton als Prüfgegenstand.

    Absichtlich Sinus und keine Sprache: geprüft wird, ob der DIENST antwortet,
    nicht ob er gut erkennt. Ein leeres Transkript mit Status „fertig" ist ein
    voller Erfolg — die Kette hat getragen. 0,3 s halten die Kosten pro Probe
    bei nahezu nichts, auch wenn sie jede Minute läuft.
    """
    puffer = BytesIO()
    with wave.open(puffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(6000 * math.sin(2 * math.pi * hz * i / rate)))
                for i in range(int(rate * sekunden))
            )
        )
    return puffer.getvalue()


@dataclass(frozen=True)
class Befund:
    """Was die Aufsicht über den Anbieter weiß.

    `gesund is None` heißt „noch nicht geprüft" und ist keine Entwarnung.
    """

    gesund: bool | None
    meldung: str
    geprueft_am: float | None = None
    dauer_s: float | None = None

    def als_dict(self, jetzt: float | None = None) -> dict:
        jetzt = time.time() if jetzt is None else jetzt
        return {
            "gesund": self.gesund,
            "meldung": self.meldung,
            "geprueft_am": self.geprueft_am,
            "geprueft_vor_s": None if self.geprueft_am is None else jetzt - self.geprueft_am,
            "dauer_s": self.dauer_s,
        }


UNGEPRUEFT = Befund(gesund=None, meldung="noch nicht geprüft")


def pruefe_infomaniak(
    *,
    api_key: str,
    absenden,
    abholen,
    basis: str = "https://api.infomaniak.com",
    produkt: str = "110416",
    modell: str = "whisper",
    sprache: str = "de",
    versuche: int = 6,
    warten_s: float = 2.0,
    schlafen=time.sleep,
    jetzt=time.time,
) -> Befund:
    """Die ganze Kette einmal durchlaufen: absenden, dann abholen.

    `absenden`/`abholen` werden hereingereicht, damit kein Test ins Netz geht —
    dieselbe Bauweise wie im fremden Backend (`submit_transcription(post=…)`).
    Wirft nie: eine Aufsicht, die den Server mitreißt, ist schlimmer als keine.
    """
    if not api_key:
        return Befund(False, "kein API-Schlüssel gesetzt", jetzt())

    start = jetzt()
    try:
        antwort = absenden(
            url=ABSENDEN.format(basis=basis.rstrip("/"), produkt=produkt),
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("probe.wav", probe_wav(), "audio/wav")},
            data={"model": modell, "language": sprache},
        )
    except Exception as fehler:  # noqa: BLE001 — jede Netzstörung ist hier ein Befund
        return Befund(False, f"Absenden scheiterte: {_kurz(fehler)}", jetzt(), jetzt() - start)

    batch = (antwort or {}).get("batch_id")
    if not batch:
        # 🔴 Genau der Fall vom 2026-09-02: Infomaniak antwortete mit einer
        # HTML-Seite „service unavailable" statt mit JSON. Ohne diese Zeile
        # steht in der Meldung nur „None" und niemand weiß, was los war.
        return Befund(
            False,
            f"keine batch_id zurück ({_kurz(antwort)})",
            jetzt(),
            jetzt() - start,
        )

    url = ABHOLEN.format(basis=basis.rstrip("/"), produkt=produkt, batch=batch)
    for _ in range(versuche):
        try:
            ergebnis = abholen(url=url, headers={"Authorization": f"Bearer {api_key}"})
        except Exception as fehler:  # noqa: BLE001
            return Befund(False, f"Abholen scheiterte: {_kurz(fehler)}", jetzt(), jetzt() - start)
        daten = (ergebnis or {}).get("data", ergebnis) or {}
        status = str(daten.get("status", "")).lower()
        if status in FERTIG:
            return Befund(True, "antwortet", jetzt(), jetzt() - start)
        schlafen(warten_s)

    return Befund(
        False,
        f"Ergebnis kam nicht innerhalb von {versuche * warten_s:.0f} s",
        jetzt(),
        jetzt() - start,
    )


def _kurz(wert, laenge: int = 120) -> str:
    """Für die Meldung im Bedienpult: eine Zeile, nicht eine HTML-Seite."""
    text = " ".join(str(wert).split())
    return text if len(text) <= laenge else text[: laenge - 1] + "…"


# ---------------------------------------------------------------------------
# Welcher Anbieter läuft gerade, und wie wechselt man ihn?
# ---------------------------------------------------------------------------
# 🔴 Das Backend wird beim START gewählt (`args.py`: es ist ein Unterbefehl,
# kein Schalter) und lässt sich im Lauf nicht tauschen. Ein Wechsel ist deshalb
# immer ein Neustart des STT-Dienstes — nicht schön, aber die Wahrheit, und
# besser hier festgehalten als im Bedienpult versprochen.
#
# Der Kern startet damit einen fremden Prozess. Das ist eine ernste Befugnis,
# also drei Schranken, alle notwendig:
#   1. Nur Namen aus `ANBIETER` — nichts aus der Anfrage erreicht je eine Shell.
#   2. Der Pfad des Skripts steht hier, er kommt nicht von außen.
#   3. `shell=False`. Kein zusammengebauter Befehlsstring.

import os  # noqa: E402 — bewusst hier, der Block oben ist netzfrei und rein
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

STARTSKRIPT = "scripts/start-stt-mac.sh"


def laufender_anbieter(port: int = 5051, lauf=subprocess.run) -> str | None:
    """Welches Backend hält gerade Port 5051? Aus der Befehlszeile gelesen.

    Nicht gemerkt, sondern nachgesehen: Der Dienst kann von Hand gestartet
    worden sein, von `start-station.sh`, oder von einem früheren Wechsel, den
    ein Neustart des Kerns längst vergessen hat. Ein gemerkter Wert wäre
    genau dann falsch, wenn man ihn braucht.

    `None` heißt „niemand lauscht" oder „unbekanntes Backend" — beides ist
    etwas anderes als „Infomaniak", und die Seite zeigt es auch anders.
    """
    try:
        pids = lauf(
            ["lsof", "-t", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=5,
        ).stdout.split()
        for pid in pids:
            zeile = lauf(
                ["ps", "-o", "command=", "-p", pid],
                capture_output=True, text=True, timeout=5,
            ).stdout
            for name in ANBIETER:
                # Der Unterbefehl heißt `infomaniak-whisper` bzw.
                # `elevenlabs-scribe` — der Anbietername steckt als Präfix drin.
                if f"{name}-" in zeile:
                    return name
    except Exception as fehler:  # noqa: BLE001
        log.warning("konnte den laufenden STT-Anbieter nicht ermitteln: %s", fehler)
    return None


def wechsle(
    anbieter: str,
    *,
    repo: Path,
    port: int = 5051,
    log_datei: Path | None = None,
    lauf=subprocess.run,
    starte=subprocess.Popen,
) -> dict:
    """Den STT-Dienst mit dem anderen Anbieter neu starten.

    Erst beenden, dann starten — und zwar nach PORT, nicht nach Namen. Auf
    macOS heißt das Binary `Python` mit großem P und `uv run` schiebt einen
    weiteren Prozess davor; ein `pkill -f "python -m …"` trifft den Mantel und
    lässt den Dienst am Leben, der dann Mikrofon oder Port belegt hält
    (`scripts/stop-station.sh` erklärt den Fall ausführlich, er ist am
    2026-09-01 real passiert).
    """
    if anbieter not in ANBIETER:
        raise ValueError(f"unbekannter Anbieter: {anbieter!r}")

    skript = repo / STARTSKRIPT
    if not skript.is_file():
        raise FileNotFoundError(f"{skript} fehlt")

    beendet = []
    try:
        pids = lauf(
            ["lsof", "-t", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=5,
        ).stdout.split()
        for pid in pids:
            lauf(["kill", pid], capture_output=True, text=True, timeout=5)
            beendet.append(int(pid))
    except Exception as fehler:  # noqa: BLE001
        log.warning("beim Beenden des alten STT-Dienstes: %s", fehler)

    umgebung = dict(os.environ, KG_STT=anbieter)
    # 🔴 KG_STT_PROBE=0: Die Vorabprobe im Skript prüft Infomaniak und wartet
    # dabei bis zu 20 s. Hier weiß der Kern es längst besser — er misst
    # ohnehin im Takt — und ein Bedienpultknopf, der eine halbe Minute hängt,
    # fühlt sich kaputt an.
    umgebung["KG_STT_PROBE"] = "0"

    ziel = log_datei or (Path.home() / "kg-logs" / "stt.log")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    strom = open(ziel, "ab")  # noqa: SIM115 — der Kindprozess erbt ihn und lebt länger
    prozess = starte(
        [str(skript)],
        cwd=str(repo),
        env=umgebung,
        stdout=strom,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # überlebt ein Strg-C im Fenster des Kerns
    )
    log.info("STT-Anbieter auf %s gewechselt (PID %s)", anbieter, prozess.pid)
    return {"anbieter": anbieter, "beendet": beendet, "pid": prozess.pid, "log": str(ziel)}


class Aufsicht:
    """Hält den letzten Befund und misst im Takt weiter.

    Der Takt ist die einzige Stelle, die Geld kostet: 0,3 s Ton pro Probe.
    Bei 60 s Abstand sind das 18 Sekunden Audio pro Stunde — nichts gegen den
    Preis, eine Ausstellung lang nicht zu merken, dass niemand verstanden wird.
    """

    def __init__(self, *, api_key: str, repo: Path, takt_s: float = 60.0, probe=None) -> None:
        self.api_key = api_key
        self.repo = repo
        self.takt_s = takt_s
        self._probe = probe or self._echte_probe
        self.befund: Befund = UNGEPRUEFT

    def _echte_probe(self) -> Befund:
        import httpx

        def absenden(*, url, headers, files, data):
            with httpx.Client(timeout=20.0) as c:
                return _als_json(c.post(url, headers=headers, files=files, data=data))

        def abholen(*, url, headers):
            with httpx.Client(timeout=15.0) as c:
                return _als_json(c.get(url, headers=headers))

        return pruefe_infomaniak(api_key=self.api_key, absenden=absenden, abholen=abholen)

    def als_dict(self) -> dict:
        return {
            "anbieter": laufender_anbieter(),
            "anbieter_moeglich": list(ANBIETER),
            "infomaniak": self.befund.als_dict(),
        }

    async def lauf(self) -> None:
        import asyncio

        while True:
            try:
                self.befund = await asyncio.to_thread(self._probe)
            except Exception as fehler:  # noqa: BLE001 — die Aufsicht darf nie sterben
                self.befund = Befund(False, f"Probe scheiterte: {_kurz(fehler)}", time.time())
            await asyncio.sleep(self.takt_s)


def _als_json(antwort) -> dict:
    """Antwort zu JSON — und eine HTML-Fehlerseite bleibt lesbar.

    🔴 Kein `raise_for_status()`: Beim Ausfall am 2026-09-02 kam HTTP 200 mit
    einer HTML-Seite „service unavailable". Der Statuscode war also nicht das
    Signal; der fehlende `batch_id` war es. Wer hier wirft, verliert den Text,
    aus dem die Meldung im Bedienpult entsteht.
    """
    try:
        return antwort.json()
    except Exception:  # noqa: BLE001
        return {"_roh": _kurz(getattr(antwort, "text", antwort))}
