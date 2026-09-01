"""Der Abholer: Spiegel -> Station.

Die entscheidende Eigenschaft ist nicht das Zustellen, sondern das Verhalten
im FEHLERFALL: ein Foto darf nie verlorengehen, weil die Station gerade neu
startete oder das Netz kurz weg war. Genau darauf zielen die meisten Tests
hier.
"""

import httpx
import pytest

from mirror.abholer import Abholer

JPEG = b"\xff\xd8\xff" + b"bilddaten"


class Spiegelattrappe:
    """Ein Spiegel und eine Station in einem, ueber httpx.MockTransport.

    Kein echter Server: getestet wird die Entscheidungslogik des Abholers,
    und die haengt an den Antworten, nicht am Transport.
    """

    def __init__(self, wartend=None):
        self.wartend = list(wartend or [])
        self.zugestellt: list[bytes] = []
        self.quittiert: list[str] = []
        self.station_antwort = 200
        self.hole_antwort = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        weg = request.url.path

        if weg == "/eingang" and request.method == "GET":
            return httpx.Response(200, json={"wartend": self.wartend})

        if weg.startswith("/eingang/") and request.method == "GET":
            if self.hole_antwort != 200:
                return httpx.Response(self.hole_antwort)
            return httpx.Response(200, content=JPEG)

        if weg.startswith("/eingang/") and request.method == "DELETE":
            self.quittiert.append(weg.rsplit("/", 1)[-1])
            return httpx.Response(200, json={"ok": True})

        if weg == "/api/photo":
            if self.station_antwort != 200:
                return httpx.Response(self.station_antwort)
            self.zugestellt.append(request.content)
            return httpx.Response(200, json={"ok": True})

        return httpx.Response(404)


def baue(spiegel: Spiegelattrappe) -> Abholer:
    client = httpx.Client(transport=httpx.MockTransport(spiegel.handler))
    return Abholer("https://spiegel.example", "starkes-token", "http://127.0.0.1:8800", client)


def test_ein_wartendes_foto_landet_bei_der_station():
    s = Spiegelattrappe(["1000.000_aaa.jpg"])

    assert baue(s).einmal() == 1

    assert s.zugestellt == [JPEG]
    assert s.quittiert == ["1000.000_aaa.jpg"]


def test_mehrere_fotos_in_ihrer_reihenfolge():
    s = Spiegelattrappe(["1000_a.jpg", "1001_b.jpg", "1002_c.jpg"])

    assert baue(s).einmal() == 3
    assert s.quittiert == ["1000_a.jpg", "1001_b.jpg", "1002_c.jpg"]


def test_ein_foto_wird_erst_nach_der_zustellung_quittiert():
    """Die wichtigste Eigenschaft: nimmt die Station nicht an, bleibt das
    Foto liegen und wird beim naechsten Mal erneut versucht.

    Sonst kostet jeder Neustart der Station genau die Portraits, die
    waehrenddessen eingeworfen wurden -- und der Moment kommt nicht wieder.
    """
    s = Spiegelattrappe(["1000_a.jpg"])
    s.station_antwort = 503

    assert baue(s).einmal() == 0

    assert s.zugestellt == []
    assert s.quittiert == [], "nicht quittieren, was nie ankam"


def test_ein_fehlschlag_beim_holen_haelt_den_abholer_nicht_an():
    """Ein kaputtes Foto darf die anderen nicht blockieren.

    Der Fall ist real: liegt ein beschaedigter Eintrag im Eingang, wuerde ein
    `break` statt `continue` jedes nachfolgende Foto fuer immer aufhalten --
    der Eingang laeuft voll und kein Portrait erscheint mehr. Deshalb muss in
    DERSELBEN Runde das zweite Foto durchkommen, nicht erst in der naechsten;
    ein Test, der zweimal `einmal()` ruft, wuerde den Unterschied nicht sehen.
    """
    s = Spiegelattrappe(["kaputt.jpg", "gut.jpg"])

    def erstes_kaputt(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("kaputt.jpg"):
            return httpx.Response(500)
        return s.handler(request)

    client = httpx.Client(transport=httpx.MockTransport(erstes_kaputt))
    ab = Abholer("https://spiegel.example", "t", "http://127.0.0.1:8800", client)

    assert ab.einmal() == 1, "das zweite Foto muss in derselben Runde durchgehen"
    assert s.quittiert == ["gut.jpg"]


def test_ein_leerer_eingang_ist_kein_fehler():
    s = Spiegelattrappe([])
    assert baue(s).einmal() == 0


def test_ein_unerreichbarer_spiegel_wirft_nach_oben_statt_still_zu_scheitern():
    """`einmal()` darf den Fehler nicht schlucken -- `laufe()` braucht ihn
    fuer das Backoff. Ein stiller Fehlschlag saehe aus wie ein leerer
    Eingang und wuerde die Wartezeit nie verlaengern."""

    def tot(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("kein Netz")

    client = httpx.Client(transport=httpx.MockTransport(tot))
    ab = Abholer("https://spiegel.example", "t", "http://127.0.0.1:8800", client)

    with pytest.raises(httpx.ConnectError):
        ab.einmal()


def test_eine_fehlende_quittung_verliert_das_foto_nicht():
    """Zugestellt ist zugestellt.

    Bleibt die Quittung aus, kommt das Foto beim naechsten Durchlauf ein
    zweites Mal -- ein doppeltes Portrait ist aergerlich, ein verlorenes
    waere schlimmer. Der Abholer darf daran nicht scheitern.
    """
    s = Spiegelattrappe(["1000_a.jpg"])
    echter_handler = s.handler

    def quittung_kaputt(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            raise httpx.ConnectError("Quittung weg")
        return echter_handler(request)

    client = httpx.Client(transport=httpx.MockTransport(quittung_kaputt))
    ab = Abholer("https://spiegel.example", "t", "http://127.0.0.1:8800", client)

    assert ab.einmal() == 1
    assert s.zugestellt == [JPEG], "die Station hat es trotzdem bekommen"


def test_der_abholer_verwendet_das_starke_token():
    """Abholen und quittieren darf nur die Station -- nie das Foto-Token
    aus der APK."""
    gesehen: list[str] = []

    def merke(request: httpx.Request) -> httpx.Response:
        gesehen.append(request.headers.get("authorization", ""))
        if request.url.path == "/eingang":
            return httpx.Response(200, json={"wartend": []})
        return httpx.Response(200, json={})

    client = httpx.Client(transport=httpx.MockTransport(merke))
    Abholer("https://spiegel.example", "STARK-xyz", "http://127.0.0.1:8800", client).einmal()

    assert gesehen == ["Bearer STARK-xyz"]


def test_die_station_bekommt_die_bytes_unveraendert():
    """Kein Umkodieren, kein Zuschneiden: der Abholer ist ein Briefträger.

    Das Portrait entsteht auf der Station (kg/photos.py). Wer hier
    dazwischenfunkt, hat zwei Orte fuer dieselbe Entscheidung.
    """
    s = Spiegelattrappe(["1000_a.jpg"])
    baue(s).einmal()
    assert s.zugestellt[0] == JPEG
