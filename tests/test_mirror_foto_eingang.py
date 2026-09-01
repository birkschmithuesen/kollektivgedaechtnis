"""Der Foto-Einwurf von aussen und die Abholung durch die Station.

Der Weg fuer ein Handy OHNE Tailnet-Zugang: die App wirft beim Spiegel ein
(`POST /ingest/photo`, schwaches Foto-Token), die Station holt dort ab
(`/eingang`, starkes Uploader-Token). Der Spiegel ist die einzige Stelle, die
beide erreichen -- die Station sitzt hinter Venue-NAT.

Der wichtigste Test dieser Datei ist `test_foto_token_darf_sonst_nichts`.
Alles andere ist Mechanik; DAS ist die Sicherheitsaussage, auf der die
Entscheidung beruht, ein Token in eine ausgelieferte APK zu legen.
"""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mirror.receiver import Posteingang, create_app

STARK = "uploader-geheim-xyz"
SCHWACH = "foto-token-in-der-apk"


def jpeg(groesse=(400, 300)) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", groesse, (120, 90, 60)).save(puffer, format="JPEG")
    return puffer.getvalue()


@pytest.fixture()
def client(tmp_path):
    app = create_app(data_dir=tmp_path / "spiegel", token=STARK, foto_token=SCHWACH)
    with TestClient(app) as c:
        c.daten = tmp_path / "spiegel"
        yield c


def wirf_ein(client, daten=None, token=SCHWACH):
    return client.post(
        "/ingest/photo",
        content=jpeg() if daten is None else daten,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"},
    )


# --- Die Sicherheitsaussage --------------------------------------------


def test_foto_token_darf_sonst_nichts(client):
    """Das Token aus der APK darf einwerfen -- und ausschliesslich das.

    Dies ist der Test, der die ganze Entscheidung traegt: ein Token in einer
    ausgelieferten APK ist kein Geheimnis (ein APK ist ein ZIP). Vertretbar
    ist es nur, solange es nichts kann, was der oeffentlichen Seite oder der
    Wand schadet. Faellt dieser Test, ist die Annahme hinfaellig -- dann
    darf die App nicht ausgeliefert werden.
    """
    kopf = {"Authorization": f"Bearer {SCHWACH}"}

    # Einwerfen: ja.
    assert wirf_ein(client).status_code == 200

    # Alles andere: nein.
    assert client.post("/ingest/graph", json={"nodes": []}, headers=kopf).status_code == 401
    assert client.post("/ingest/dream", json={"sentence": "x"}, headers=kopf).status_code == 401
    assert client.post(
        "/ingest/media/portraits/p1.png", content=b"\x89PNG\r\n\x1a\n", headers=kopf
    ).status_code == 401

    # Auch nicht LESEN, was andere eingeworfen haben -- sonst waere jede
    # ausgelieferte APK ein Fenster in den Eingang aller anderen.
    assert client.get("/eingang", headers=kopf).status_code == 401


def test_das_uploader_token_wirft_nicht_ein(client):
    """Die Trennung gilt in beide Richtungen.

    Nicht Prinzipienreiterei: waere das starke Token hier auch gueltig,
    liesse sich am Testaufbau nicht mehr unterscheiden, welches der beiden
    gerade wirkt, und ein Fehler in der Abgrenzung fiele nicht auf.
    """
    assert wirf_ein(client, token=STARK).status_code == 401


def test_ohne_token_geht_gar_nichts(client):
    assert client.post("/ingest/photo", content=jpeg()).status_code == 401
    assert client.get("/eingang").status_code == 401


def test_ohne_konfiguriertes_foto_token_ist_der_einwurf_zu(tmp_path):
    """Fail closed, wie beim Uploader-Token: eine Instanz ohne
    `KG_FOTO_TOKEN` nimmt nichts an, statt jeden einwerfen zu lassen."""
    app = create_app(data_dir=tmp_path / "s", token=STARK, foto_token="")
    with TestClient(app) as c:
        assert c.post(
            "/ingest/photo", content=jpeg(), headers={"Authorization": "Bearer irgendwas"}
        ).status_code == 401


# --- Der Weg selbst ----------------------------------------------------


def test_eingeworfenes_foto_wartet_und_wird_abgeholt(client):
    antwort = wirf_ein(client)
    assert antwort.status_code == 200
    name = antwort.json()["name"]

    kopf = {"Authorization": f"Bearer {STARK}"}
    assert client.get("/eingang", headers=kopf).json()["wartend"] == [name]

    geholt = client.get(f"/eingang/{name}", headers=kopf)
    assert geholt.status_code == 200
    assert geholt.content == jpeg()

    assert client.delete(f"/eingang/{name}", headers=kopf).json()["ok"] is True
    assert client.get("/eingang", headers=kopf).json()["wartend"] == []


def test_abholen_loescht_nicht_von_selbst(client):
    """Erst quittieren, dann weg.

    Bricht die Verbindung zur Station nach dem Lesen ab, muss das Foto noch
    da sein -- sonst ist ein Portrait verloren, und der Moment kommt nicht
    wieder.
    """
    name = wirf_ein(client).json()["name"]
    kopf = {"Authorization": f"Bearer {STARK}"}

    client.get(f"/eingang/{name}", headers=kopf)
    assert client.get("/eingang", headers=kopf).json()["wartend"] == [name]


def test_reihenfolge_ist_die_des_booths(client):
    namen = [wirf_ein(client).json()["name"] for _ in range(5)]
    kopf = {"Authorization": f"Bearer {STARK}"}
    assert client.get("/eingang", headers=kopf).json()["wartend"] == namen


def test_zwei_fotos_derselben_millisekunde_kollidieren_nicht(tmp_path):
    """Zwei Handys duerfen unabhaengig voneinander druecken."""
    eingang = Posteingang(tmp_path / "e")
    namen = {eingang.lege_ab(jpeg(), 1000.0) for _ in range(20)}
    assert len(namen) == 20


# --- Was abgewiesen wird ------------------------------------------------


def test_kein_bild_wird_abgewiesen_und_landet_nicht_auf_der_platte(client):
    """Ohne diese Pruefung liesse sich auf einem oeffentlichen Server
    Beliebiges ablegen und ueber die Abholroute wieder herausholen."""
    antwort = wirf_ein(client, daten=b"<html>kein bild</html>")

    assert antwort.status_code == 415
    kopf = {"Authorization": f"Bearer {STARK}"}
    assert client.get("/eingang", headers=kopf).json()["wartend"] == []


def test_leerer_rumpf_wird_abgewiesen(client):
    assert wirf_ein(client, daten=b"").status_code == 400


def test_ein_voller_eingang_weist_ab_statt_die_platte_zu_fuellen(tmp_path):
    eingang = Posteingang(tmp_path / "e")
    for _ in range(Posteingang.MAX_WARTEND):
        eingang.lege_ab(jpeg(), 1000.0)

    with pytest.raises(Exception) as fehler:
        eingang.lege_ab(jpeg(), 1000.0)
    assert "429" in str(fehler.value) or "voll" in str(fehler.value)


def test_alte_fotos_verfallen(tmp_path):
    """Ein Foto, das so lange niemand abholte, gehoert zu einem Interview,
    das laengst vorbei ist -- und darf auf dem oeffentlichen Server nicht
    liegenbleiben."""
    eingang = Posteingang(tmp_path / "e")
    eingang.lege_ab(jpeg(), 1000.0)
    assert len(eingang.wartend()) == 1

    # Ein neuer Einwurf weit spaeter raeumt den alten weg.
    import os

    for p in eingang.wartend():
        os.utime(p, (1000.0, 1000.0))
    eingang.lege_ab(jpeg(), 1000.0 + Posteingang.MAX_ALTER_S + 1)

    assert len(eingang.wartend()) == 1  # nur noch das neue


def test_ein_ausbruchsversuch_im_namen_wird_abgewiesen(client):
    """Kein Name aus dem Netz darf aus dem Eingangsverzeichnis herausfuehren.

    `..` und `.` stehen bewusst NICHT in der Liste: gemessen am 2026-09-01
    normalisiert der HTTP-Client `/eingang/..` und `/eingang/.` zu `/` und
    bekommt die Startseite (200). Das ist kein Datenabfluss -- die Anfrage
    erreicht die Route nie -- aber es waere ein Test, der die falsche Ebene
    prueft und bei jeder Client-Aenderung umkippt. Geprueft wird, was
    tatsaechlich an der Route ankommt; die beiden Punktnamen deckt
    `test_der_eingang_bleibt_unter_seinem_verzeichnis` direkt ab.
    """
    kopf = {"Authorization": f"Bearer {STARK}"}
    for boese in ["../../etc/passwd", "a/b.jpg", "%2e%2e%2fetc%2fpasswd", "x.jpg%00"]:
        antwort = client.get(f"/eingang/{boese}", headers=kopf)
        assert antwort.status_code in (400, 404), f"{boese} -> {antwort.status_code}"


def test_der_eingang_bleibt_unter_seinem_verzeichnis(tmp_path):
    """Dieselbe Aussage eine Ebene tiefer, ohne HTTP-Client dazwischen.

    Der Test darueber kann durch Normalisierung im Client verfaelscht werden;
    dieser hier trifft `_pruefe_namen` direkt und ist deshalb der eigentliche
    Beleg.
    """
    eingang = Posteingang(tmp_path / "e")
    for boese in ["..", "../x", "a/b", "/etc/passwd", "", "x:y"]:
        with pytest.raises(Exception):
            eingang.hole(boese)
