"""Das Haiku unter dem Traumbild — erzeugt, gemessen, nachgebessert.

🔴 WARUM (Birk, 2026-09-02): „Der Satz, der unter dem Traumbild steht, mit max
16 Wörtern — versuch mal eine Anweisung an das LLM, daraus ein Haiku-Gedicht zu
machen." Nach zwei Messreihen: „bau das ein."

## Warum das Zaehlen NICHT dem Modell ueberlassen wird

Gemessen am selben Tag: Liess man das Modell seine Silben selbst zaehlen und
die Zahl mitliefern, wich seine Zaehlung in **14 von 16 Faellen** von der
echten ab — und es glaubte jedes Mal, 5-7-5 getroffen zu haben. Es kann die
Form nicht pruefen, also kann es sie auch nicht einhalten. Mit dem urspruenglich
konfigurierten Modell (Kimi K2.6, `reasoning_effort="none"`, und dieser Wert
ist dort Pflicht) trafen 3 von 32 Versuchen.

Deshalb zaehlt `kg2.silben`, und die schiefe Zeile geht mit ihrer ECHTEN
Silbenzahl zurueck an das Modell („Zeile 2 hat 8 Silben, sie braucht 7").
Damit stieg die Quote auf **19–20 von 20**.

## Warum es zusaetzlich einen Lektor gibt

Die Form allein reichte nicht: Das Modell kaufte sich die fehlende Silbe durch
VERSTUEMMELTE Woerter — „Ein Blatt ist gefalt", „Kies knirscht unter Schuhn",
„Haende praegen Erd", dazu „Kindrad" und ein englisches „Grit". 6 von 20 waren
so beschaedigt, und mechanisch ist das ohne Woerterbuch nicht zu erkennen (auf
der Station liegt keines).

Ein zweiter, sehr kurzer Aufruf prueft deshalb NUR die drei fertigen Zeilen auf
heiles Deutsch — ohne Bild, ohne Silbenauftrag. Das ist eine viel leichtere
Aufgabe als das Dichten, und danach waren 18 von 20 sprachlich einwandfrei.

## 🔴 Was passiert, wenn es scheitert

Nichts Schlimmes: `erzeuge_haiku` gibt `None` zurueck, und der Aufrufer behaelt
den Prosasatz, den Stufe 1 ohnehin geliefert hat. Die Wand bleibt nie leer und
zeigt nie ein kaputtes Haiku — im Zweifel steht dort der Satz, der seit
Wochen dort steht.
"""

from __future__ import annotations

import logging
import re
import time

from pydantic import BaseModel

from kg2.silben import silben_zeile

log = logging.getLogger(__name__)

#: 5-7-5, die klassische Form.
SOLL = (5, 7, 5)

#: Wie oft nachgebessert wird. 6 war in der Messreihe reichlich — die meisten
#: Haikus standen nach ein bis zwei Runden.
MAX_RUNDEN = 6

#: Zeitdeckel fuer das ganze Haiku. Der Traum entsteht alle 240 s; ein
#: Ausreisser von 36 s wurde gemessen (Latenzschwankung bei Infomaniak, nicht
#: viele Runden). 60 s ist die Grenze, ab der es den Betrieb stoert.
MAX_SEKUNDEN = 60.0

SYSTEM = """\
Du schreibst ein HAIKU auf Deutsch. Es steht als Bildunterschrift unter einem \
grossen Traumbild in einer Ausstellung und muss im Vorbeigehen in einem Blick \
erfassbar sein.

Du bekommst die englische BESCHREIBUNG genau dieses Bildes.

🔴 DAS HAIKU TRAEGT NICHT DAS GANZE BILD. Es zeigt DIESELBE Szene wie die \
Beschreibung, keine zweite daneben, und ist ihre VERDICHTUNG: EIN Vorgang \
daraus, der eine, an dem man die anderen ahnt. Das Nahe und das Weite, beide \
Seiten, alle Begriffe -- das steht schon im Bild und muss hier nicht noch \
einmal vorkommen. Nenne weniger und zeige das genau.

FORM: drei Zeilen, klassisch 5 - 7 - 5 Silben. Kein Reim. Kein Titel, keine \
Erklaerung, keine Anfuehrungszeichen, kein Punkt am Ende.

DIE SILBENZAHL IST PFLICHT, nicht Zierde. Zaehle jede Zeile laut durch, Silbe \
fuer Silbe, wie man ein Wort trennt, BEVOR du sie hinschreibst: \
"Die Kin-der druecken" = 5, "Ge-laen-der" = 3, "Bau-stel-le" = 3. Im Deutschen \
sind au, ei, eu, aeu und ie EINE Silbe: "Lehm-wand" = 2, "Haus" = 1. Kommt eine \
Zeile nicht auf ihre Zahl, schreibe sie um, statt sie stehenzulassen.

SPRACHE: Gegenwart. Konkret und bildhaft -- Dinge, Oberflaechen, Haende, was \
jemand tut. Keine Begriffe, die man nicht fotografieren kann (Zukunft, \
Beteiligung, Dialog, Wandel, Identitaet). Kein "ich", keine Anrede, keine \
Deutung, keine Pointe. Eine Aufzaehlung ist nicht die Rettung: "A und B und C" \
haelt zwar die Silbenzahl ein, ist aber kein Bild, sondern eine Liste.

SCHREIBE ORDENTLICHES DEUTSCH: nur wirklich existierende Wörter, vollständig \
ausgeschrieben, mit korrekten Umlauten. Kein Wort in der Mitte abbrechen, \
keine Bindestriche zur Silbentrennung in der fertigen Zeile.
🔴 DIE ZEILE MUSS EIN HEILER DEUTSCHER SATZTEIL SEIN. Die Silbenzahl ist \
Pflicht, aber sie wird NICHT durch kaputtes Deutsch erkauft. Verboten sind \
deshalb:
- Woerter aneinanderreihen wie ein Telegramm ("Hand drückt Lehmwand Tisch \
hält Plan"). Eine Zeile hat ein Subjekt und ein Verb, oder sie ist eine \
saubere Wortgruppe -- nie beides halb.
- erfundene Zusammensetzungen ("Kindblatt", "Brettwerk", "Erdenhand"). Nur \
Woerter, die im Duden stehen.
- angefangene und dann abgebrochene Saetze ("Karte krümmt, hier spielt").
- Codes und Kuerzel aus der Bildbeschreibung ("Modul 3A", "Bad C", "Typ B"). \
Nenne den Gegenstand deutsch beim Namen oder lass ihn weg.
- Grossschreibung ganzer Woerter, Anfuehrungszeichen, Bindestriche, \
Gedankenstriche.
- englische Woerter ("Moss", "Grit", "Gravel").

LIEBER EIN WORT WENIGER SAGEN. Passt der Gedanke nicht in die Silben, nimm \
einen kleineren Gedanken -- nicht ein zerhacktes Deutsch. Lies die fertige \
Zeile zum Schluss noch einmal: Wuerde ein deutscher Muttersprachler sie so \
sagen?
"""


LEKTOR = """\
Du bist Lektor fuer deutsche Sprache. Du bekommst drei Zeilen und pruefst NUR, \
ob sie sprachlich heil sind. Der Inhalt geht dich nichts an, die Laenge auch \
nicht -- pruefe ausschliesslich das Deutsch.

Beanstande eine Zeile, wenn sie enthaelt:
- ein abgeschnittenes Wort ("gefalt" statt "gefaltet", "gleit" statt \
"gleitet", "Erd" statt "Erde", "Schuhn" statt "Schuhen"),
- ein Wort, das es im Deutschen nicht gibt ("Kindrad", "Brettwerk"),
- ein englisches Wort ("Grit", "Moss", "Room", "Van"),
- einen Kongruenzfehler ("glaetten weisse Plan" statt "weissen Plan"),
- einen Kasus- oder Verbfehler.

Beanstande NICHT: fehlende Artikel, Kleinschreibung am Zeilenanfang, einen \
Satz, der ueber zwei Zeilen laeuft, ungewoehnliche aber korrekte Wortstellung, \
seltene aber echte Woerter. Eine knappe, dichte Sprache ist beabsichtigt.

`heil` ist true, wenn nichts zu beanstanden ist. Sonst false, und in \
`beanstandet` steht fuer jede schadhafte Stelle EIN Satz: welches Wort in \
welcher Zeile, und wie es richtig hiesse.\
"""


class Haiku(BaseModel):
    zeile1: str
    zeile2: str
    zeile3: str


class Lektorat(BaseModel):
    beanstandet: list[str]
    heil: bool


def formfehler(zeilen: list[str]) -> list[str]:
    """Was sich ohne Modell und ohne Woerterbuch feststellen laesst.

    Bindestriche sind der wichtigste Punkt: Das Modell trennt Woerter damit,
    um eine Silbe zu gewinnen („Kerbe wirft der Löff- / el Ton in Schüssel"),
    und mechanisch stimmt die Zahl dann sogar."""
    fehler = []
    for i, z in enumerate(zeilen, 1):
        if re.search(r"[-–—]", z):
            fehler.append(f"Zeile {i} enthaelt einen Binde- oder Gedankenstrich: „{z}“")
        if re.search(r"\b[A-ZÄÖÜ]{2,}\b", z):
            fehler.append(f"Zeile {i} schreibt ein Wort ganz gross: „{z}“")
        if re.search(r"[\"„“«»]", z):
            fehler.append(f"Zeile {i} enthaelt Anfuehrungszeichen: „{z}“")
        if re.search(r"\d", z):
            fehler.append(f"Zeile {i} enthaelt eine Ziffer: „{z}“")
        if z.rstrip().endswith((".", "!", "?")):
            fehler.append(f"Zeile {i} endet mit einem Satzzeichen: „{z}“")
        if not z.strip():
            fehler.append(f"Zeile {i} ist leer")
    return fehler


def _auftrag(bildbeschreibung: str) -> str:
    return (
        "--- BESCHREIBUNG DES BILDES (englisch) ---\n\n"
        f"{bildbeschreibung}\n\n"
        "--- ENDE BESCHREIBUNG ---\n\n"
        "Antworte mit genau einem Haiku."
    )


def _nachbesserung(zeilen: list[str], gemessen: list[int], sprache: list[str]) -> str:
    schief = [
        f"Zeile {i + 1} hat {g} Silben, sie braucht {s}: „{z}“"
        for i, (z, g, s) in enumerate(zip(zeilen, gemessen, SOLL))
        if g != s
    ] + formfehler(zeilen) + sprache
    return (
        "Dein Haiku war:\n"
        + "\n".join(f"{i + 1}. {z}" for i, z in enumerate(zeilen))
        + "\n\nEs wurde geprueft. DAS IST ZU AENDERN:\n"
        + "\n".join(f"- {p}" for p in schief)
        + "\n\nSchreibe das Haiku noch einmal. Zeilen ohne Beanstandung laesst "
        "du WOERTLICH stehen. 🔴 Ein Wort NIE abschneiden, um eine Silbe zu "
        "sparen -- nimm lieber ein anderes, kuerzeres Wort, das es wirklich "
        "gibt. Antworte wieder mit genau einem Haiku."
    )


def erzeuge_haiku(
    llm,
    bildbeschreibung: str,
    *,
    max_runden: int = MAX_RUNDEN,
    max_sekunden: float = MAX_SEKUNDEN,
    jetzt=time.monotonic,
) -> str | None:
    """Drei Zeilen mit „\\n" getrennt, oder `None`.

    `None` heisst: Der Aufrufer behaelt den Prosasatz. Diese Funktion wirft
    nie — ein misslungenes Haiku darf keinen Traum kosten.
    """
    if not (bildbeschreibung or "").strip():
        return None
    beginn = jetzt()
    user = _auftrag(bildbeschreibung)
    letzte: list[str] | None = None
    for runde in range(max_runden):
        if jetzt() - beginn > max_sekunden:
            log.warning("Haiku: Zeitdeckel nach %d Runden erreicht", runde)
            break
        try:
            h = llm.parse(system=SYSTEM, user=user, output_model=Haiku)
        except Exception as fehler:  # noqa: BLE001 — siehe Docstring
            log.warning("Haiku: Aufruf gescheitert (%s)", fehler)
            break
        zeilen = [h.zeile1.strip(), h.zeile2.strip(), h.zeile3.strip()]
        letzte = zeilen
        gemessen = [silben_zeile(z) for z in zeilen]
        form = formfehler(zeilen)
        sprache: list[str] = []
        if gemessen == list(SOLL) and not form:
            # Der Lektor kostet einen Aufruf — nur, wenn die Form schon steht.
            try:
                lek = llm.parse(system=LEKTOR, user="\n".join(zeilen), output_model=Lektorat)
                if not lek.heil:
                    sprache = list(lek.beanstandet)[:4]
            except Exception as fehler:  # noqa: BLE001
                # Lektor weg: Die Form gilt, das Haiku geht durch. Lieber ein
                # ungeprueftes als gar keines — der Prosasatz waere der
                # groessere Bruch.
                log.info("Haiku: Lektor nicht erreichbar (%s), Form gilt", fehler)
        if gemessen == list(SOLL) and not form and not sprache:
            log.info("Haiku steht nach Runde %d", runde + 1)
            return "\n".join(zeilen)
        user = _auftrag(bildbeschreibung) + "\n\n" + _nachbesserung(zeilen, gemessen, sprache)
    log.warning(
        "Haiku nicht zustande gekommen, letzter Stand: %s — der Prosasatz bleibt",
        letzte,
    )
    return None
