"""Das Haiku unter dem Traumbild (`kg2.haiku`).

Der Kern dieser Tests: Das Modell kann seine Silben NICHT zaehlen (gemessen
2026-09-02: 14 von 16 Selbstzaehlungen falsch). Die Form entsteht allein
dadurch, dass ein Programm nachzaehlt und die schiefe Zeile zurueckschickt.
Faellt diese Schleife weg oder greift sie ins Leere, sinkt die Trefferquote von
19/20 auf ~12/20 — und zwar unbemerkt, weil das Modell weiterhin behauptet,
getroffen zu haben.
"""

from __future__ import annotations

from kg2.haiku import SOLL, erzeuge_haiku, formfehler
from kg2.silben import silben_zeile

BILD = "A hand presses clay into a wooden form while roofs stretch to the valley."

# 5-7-5, gemessen. Das erste Haiku, das am 2026-09-02 sauber durchkam.
GUT = ("Hand an kühlem Lehm", "rote Dächer tief im Tal", "Wege führen fort")
# 6-7-5: die erste Zeile hat eine Silbe zu viel. („Eine Hand am Lehm" waere
# hier falsch — das IST fuenfsilbig, Ei-ne Hand am Lehm. Beim Schreiben dieses
# Tests einmal danebengegriffen und von `kg2.silben` korrigiert worden.)
SCHIEF = ("Eine Hand am Boden", "rote Dächer tief im Tal", "Wege führen fort")


class Modell:
    """Liefert der Reihe nach, was ihm mitgegeben wurde, und merkt sich die
    Auftraege — daran wird geprueft, ob die Silbenzahl zurueckgemeldet wurde."""

    def __init__(self, *antworten):
        self.antworten = list(antworten)
        self.auftraege: list[str] = []

    def parse(self, *, system, user, output_model):
        self.auftraege.append(user)
        if not self.antworten:
            raise AssertionError("mehr Aufrufe als vorgesehen")
        naechste = self.antworten.pop(0)
        if isinstance(naechste, Exception):
            raise naechste
        if naechste == "heil":
            return output_model(beanstandet=[], heil=True)
        if isinstance(naechste, list):
            return output_model(beanstandet=naechste, heil=False)
        return output_model(zeile1=naechste[0], zeile2=naechste[1], zeile3=naechste[2])


def test_ein_haiku_das_stimmt_geht_in_einer_runde_durch():
    llm = Modell(GUT, "heil")
    assert erzeuge_haiku(llm, BILD) == "\n".join(GUT)
    assert [silben_zeile(z) for z in GUT] == list(SOLL)


def test_eine_schiefe_zeile_geht_mit_ihrer_echten_silbenzahl_zurueck():
    """🔴 Das ist der ganze Mechanismus. Das Modell erfaehrt die Zahl, die es
    selbst nicht ermitteln kann."""
    llm = Modell(SCHIEF, GUT, "heil")

    assert erzeuge_haiku(llm, BILD) == "\n".join(GUT)

    nachbesserung = llm.auftraege[1]
    assert "Zeile 1 hat 6 Silben, sie braucht 5" in nachbesserung, nachbesserung
    # Die heilen Zeilen werden NICHT beanstandet.
    assert "Zeile 2 hat" not in nachbesserung
    assert "Zeile 3 hat" not in nachbesserung


def test_ein_verstuemmeltes_wort_wird_vom_lektor_zurueckgewiesen():
    """Die Form allein reichte nicht: Das Modell kaufte die fehlende Silbe
    durch abgeschnittene Woerter („Haende praegen Erd"). 6 von 20 waren so
    beschaedigt, und mechanisch ist das ohne Woerterbuch nicht zu sehen."""
    kaputt = ("Hände prägen Erd", "rote Dächer tief im Tal", "Wege führen fort")
    assert [silben_zeile(z) for z in kaputt] == list(SOLL), "die Form stimmt ja gerade"

    llm = Modell(kaputt, ["Zeile 1: „Erd“ muss „Erde“ heißen"], GUT, "heil")
    assert erzeuge_haiku(llm, BILD) == "\n".join(GUT)
    # auftraege[0] Erzeugung, [1] Lektor (nur die drei Zeilen), [2] die
    # Nachbesserung — dort muss die Beanstandung stehen.
    assert "Erde" in llm.auftraege[2], llm.auftraege[2]


def test_ohne_haiku_gibt_es_none_und_der_prosasatz_bleibt():
    """🔴 Die Wand bleibt nie leer und zeigt nie ein kaputtes Haiku."""
    llm = Modell(*[SCHIEF] * 3)
    assert erzeuge_haiku(llm, BILD, max_runden=3) is None


def test_ein_toter_dienst_kostet_keinen_traum():
    llm = Modell(RuntimeError("Verbindung weg"))
    assert erzeuge_haiku(llm, BILD) is None


def test_faellt_der_lektor_aus_gilt_die_form():
    """Lieber ein ungeprueftes Haiku als gar keines — der Rueckfall auf den
    Prosasatz waere der groessere Bruch im Bild."""
    llm = Modell(GUT, RuntimeError("Lektor weg"))
    assert erzeuge_haiku(llm, BILD) == "\n".join(GUT)


def test_der_zeitdeckel_bricht_ab():
    """Ein Ausreisser von 36 s wurde gemessen (Latenz, nicht viele Runden).
    Der Traum entsteht alle 240 s — laenger als 60 s stoert den Betrieb."""
    uhr = iter([0.0, 0.5, 999.0])
    llm = Modell(SCHIEF, SCHIEF)
    assert erzeuge_haiku(llm, BILD, jetzt=lambda: next(uhr)) is None


def test_ohne_bildbeschreibung_wird_gar_nicht_erst_gefragt():
    llm = Modell()
    assert erzeuge_haiku(llm, "  ") is None
    assert llm.auftraege == []


def test_die_formpruefung_faengt_den_trennstrich():
    """Der haeufigste Trick: ein Wort mit Bindestrich zerlegen, um eine Silbe
    zu gewinnen („Kerbe wirft der Löff- / el Ton in Schüssel"). Mechanisch
    stimmt die Silbenzahl dann sogar."""
    assert formfehler(["Kerbe wirft der Löff-", "el Ton in Schüssel", "gut"])
    assert formfehler(["Hand am LEHM", "b", "c"])
    assert formfehler(["Hand am Lehm.", "b", "c"])
    assert formfehler(['Hand am „Lehm“', "b", "c"])
    assert formfehler(["3 Hände", "b", "c"])
    assert formfehler(list(GUT)) == []
