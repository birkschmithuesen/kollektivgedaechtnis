"""Der Startweg des Uploaders auf dem MacBook.

🔴 WARUM ES DIESE DATEI GIBT (Birk, 2026-09-02):

    „Ich bin dort draufgegangen. Der verbindet sich gar nicht zu dem MacBook."

Gemessen am 2026-09-02, bevor hier etwas geändert wurde:

  * `ps aux | grep -iE "mirror|uploader"` auf diesem Mac: **kein einziger
    Uploader-Prozess**. Nur `MirrorDisplays.app` von macOS selbst.
  * `mirror/` enthält zum Starten ausschliesslich `spiegel-start.bat` und
    `abholer-start.bat`. Die Station lief bis 2026-09-01 auf Windows; seither
    ist sie dieses MacBook, und `.bat`-Dateien laufen dort nicht.
  * `~/.kg-mirror-token` existiert nicht. Ohne Token nimmt der Empfänger
    nichts an.
  * Der öffentliche Spiegel antwortete trotzdem mit `{"ok":true,
    "graph_age_s":5109.7}` und einem Graphen mit 138 Knoten und
    `person-000.png` — das ist der **Simulationsstand** (`sim/data/`), nicht
    die Ausstellung. Deshalb sah die Seite „alt und komisch" aus: sie zeigte
    etwas, nur nicht das Haus.

Die Übertragungskette selbst ist in Ordnung. Belegt am selben Tag: ein
`mirror.receiver` auf 127.0.0.1:8899 und eine einzelne `Uploader.runde()`
gegen die laufende Station haben Graph, Traum UND alle drei echten Portraits
(`1788297712_app595.png` u.a.) übertragen. Es fehlte nur der Prozess, der das
im Betrieb tut.

🔴 SEIT 2026-09-02, 11:20 läuft dieses Skript im Sammelstart MIT (Birk, am
Ausstellungstag: „baue ihn auch in die start routine ein"). Vorher war die
Trennung absichtlich, und ihr Grund gilt weiter — hier gehen Portraits und
Zitate von Menschen ins öffentliche Netz. Geändert hat sich nur, WER die
Entscheidung trägt: nicht mehr ein getippter Schalter, sondern eine Zeile in
`start-station.sh`, die auf Birks Ansage steht.

Was die alte Regel schützen sollte, prüfen die Tests unten weiter: dass
niemand UNBEMERKT veröffentlicht. Der Start sagt es in Rot, `--ohne-spiegel`
schaltet es in einem Wort ab, und der Abholer — der beim Spiegel LÖSCHEN darf —
bleibt aus.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SKRIPT = Path("scripts/spiegel-start-mac.sh")

#: Ein Wert, der wie ein Token aussieht und in KEINER Ausgabe auftauchen darf.
GEHEIMNIS = "geheim-XyZ123-nicht-ausgeben"


def lauf(argumente, heim: Path, umgebung=None) -> subprocess.CompletedProcess:
    """Das Skript wirklich ausführen, mit einem eigenen HOME.

    Kein Lesen des Quelltextes an dieser Stelle: „das Skript enthält das Wort
    `token`" ist kein Beleg dafür, dass es abbricht, wenn keins da ist.
    """
    env = dict(os.environ)
    env["HOME"] = str(heim)
    env.update(umgebung or {})
    return subprocess.run(
        ["bash", str(SKRIPT), *argumente],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


# --- Es gibt ihn überhaupt ---------------------------------------------------


def test_es_gibt_einen_startweg_fuer_den_mac():
    """Der Kern des Auftrags: auf diesem Rechner muss man den Uploader starten
    können, ohne eine `.bat` zu übersetzen."""
    assert SKRIPT.exists(), f"{SKRIPT} fehlt — der Spiegel bekommt dann nichts"
    assert os.access(SKRIPT, os.X_OK), f"{SKRIPT} ist nicht ausführbar (chmod +x)"


def test_er_startet_wirklich_den_uploader_und_nichts_anderes():
    """`mirror.uploader` schiebt hoch. `mirror.receiver` gehört auf herkules,
    `mirror.abholer` ist die Gegenrichtung und ein eigener Dienst."""
    text = SKRIPT.read_text(encoding="utf-8")
    assert "mirror.uploader" in text
    assert "mirror.receiver" not in text
    # Der Abholer darf ERWÄHNT werden (er ist der Nachbar), aber nicht
    # gestartet: `python -m mirror.abholer` wäre ein zweiter Dienst in einem
    # Fenster, das nur einen ankündigt.
    assert "-m mirror.abholer" not in text


# --- Ohne Token bricht er ab, laut und mit Anleitung -------------------------


def test_ohne_tokendatei_bricht_er_ab_und_sagt_wo_sie_hingehoert(tmp_path):
    """Der häufigste Fehler bei einem Rechnerwechsel, und der teuerste: ein
    Uploader, der ohne Token startet, läuft und wirft den ganzen Tag 401 —
    sichtbar nur, wenn jemand in sein Fenster sieht."""
    ergebnis = lauf(["--pruefen"], tmp_path)
    assert ergebnis.returncode != 0, "ohne Token darf das nicht als Erfolg durchgehen"
    ausgabe = ergebnis.stdout + ergebnis.stderr
    assert ".kg-mirror-token" in ausgabe, ausgabe
    # Was Birk dann TUN muss, nicht nur was fehlt.
    assert "token-verteilen.sh" in ausgabe, ausgabe


def test_die_pruefung_gibt_das_token_niemals_aus(tmp_path):
    """Die Ausgabe eines Ausstellungsrechners liest am Ende irgendwer.

    Dieselbe Regel, die `mirror/uploader.py::kurz()` und
    `scripts/token-verteilen.sh` durchhalten: der Wert wandert durch die
    Prozessumgebung und sonst nirgendwohin.
    """
    (tmp_path / ".kg-mirror-token").write_text(GEHEIMNIS + "\n", encoding="utf-8")
    ergebnis = lauf(
        ["--pruefen"],
        tmp_path,
        # Auf eine tote lokale Adresse, damit die Prüfung nicht am
        # öffentlichen Spiegel hängt und nichts dorthin schickt.
        {"KG_MIRROR_URL": "http://127.0.0.1:1", "KG_MIRROR_PRUEF_TIMEOUT": "2"},
    )
    ausgabe = ergebnis.stdout + ergebnis.stderr
    assert GEHEIMNIS not in ausgabe, "das Token steht in der Ausgabe"
    # Es muss trotzdem etwas ÜBER das Token sagen, sonst ist die Prüfung
    # wertlos: Länge und Fingerabdruck unterscheiden zwei Token, ohne eins zu
    # verraten (Muster aus scripts/token-verteilen.sh).
    assert "Token" in ausgabe


def test_die_pruefung_ist_ein_bericht_und_kein_tor(tmp_path):
    """Mit Token, aber ohne erreichbare Gegenstelle: das ist ein BEFUND, kein
    Abbruch. Wer am Morgen prüft, will alle vier Zeilen sehen und nicht nach
    der ersten stehen bleiben."""
    (tmp_path / ".kg-mirror-token").write_text(GEHEIMNIS + "\n", encoding="utf-8")
    ergebnis = lauf(
        ["--pruefen"],
        tmp_path,
        {"KG_MIRROR_URL": "http://127.0.0.1:1", "KG_MIRROR_PRUEF_TIMEOUT": "2"},
    )
    ausgabe = ergebnis.stdout + ergebnis.stderr
    # Die drei Gegenstellen, die der Uploader braucht (mirror/uploader.py::main).
    assert "8800" in ausgabe and "8810" in ausgabe, ausgabe
    assert "127.0.0.1:1" in ausgabe, ausgabe


# --- Die Umgebung, die `mirror/uploader.py::main` wirklich liest -------------


def test_er_setzt_genau_die_variablen_die_der_uploader_liest():
    """Am Quelltext abgelesen, nicht aus der `.bat` abgeschrieben:
    `main()` liest KG_MIRROR_URL, KG_MIRROR_TOKEN, KG_TOOL1_URL, KG_TOOL2_URL
    und KG_MIRROR_INTERVAL."""
    text = SKRIPT.read_text(encoding="utf-8")
    for name in (
        "KG_MIRROR_URL",
        "KG_MIRROR_TOKEN",
        "KG_TOOL1_URL",
        "KG_TOOL2_URL",
        "KG_MIRROR_INTERVAL",
    ):
        assert name in text, f"{name} kommt im Skript nicht vor"

    quelle = Path("mirror/uploader.py").read_text(encoding="utf-8")
    for name in ("KG_MIRROR_URL", "KG_MIRROR_TOKEN", "KG_TOOL1_URL", "KG_TOOL2_URL"):
        assert f'"{name}"' in quelle, f"{name} liest der Uploader gar nicht (mehr)"


def test_im_skript_steht_kein_token():
    """Ein Geheimnis im Repo ist ein veröffentlichtes Geheimnis."""
    text = SKRIPT.read_text(encoding="utf-8")
    # Eine Zuweisung mit einem LITERAL dahinter wäre der Fehler.
    # `KG_MIRROR_TOKEN=$(…)` ist dagegen genau richtig: der Wert kommt zur
    # Laufzeit aus der Datei und steht nirgends im Quelltext.
    for zeile in text.splitlines():
        blank = zeile.strip()
        if blank.startswith("#"):
            continue
        if blank.startswith("KG_MIRROR_TOKEN="):
            wert = blank[len("KG_MIRROR_TOKEN=") :]
            assert "$" in wert, f"Token als Literal im Skript: {blank}"
        assert "Bearer " not in blank, f"Token fest verdrahtet: {blank}"


# --- Was er NICHT tun darf ---------------------------------------------------


def test_der_uploader_laeuft_im_sammelstart_mit():
    """🔴 Birks Ansage am Ausstellungstag (2026-09-02, 11:20).

    Vorgeschichte in einem Satz: Der Uploader lief hier NICHT mit, weil er
    Interviewdaten ins öffentliche Netz schiebt. Am Ausstellungstag hiess das
    zweimal, dass der QR-Code auf der Wand ins Leere führte — einmal früh
    (`docs/STAND.md` §4z: der Spiegel zeigte die Simulationsdaten), einmal um
    11:20 nach einem Neustart. Birk hat daraufhin entschieden, dass er
    mitläuft.

    🔴 Geprüft wird durch AUSFÜHREN, nicht durch Lesen des Quelltextes. Die
    Vorgängerfassung suchte Textmuster wie `"./scripts/spiegel-start-mac.sh &"`.
    Als der Aufruf am 2026-09-02 seine Form änderte (er läuft jetzt über eine
    Funktion `starte_draussen`), fand sie ihn nicht mehr und wurde still grün,
    ohne noch irgendetwas zu belegen — die gefährlichere Hälfte des Problems,
    das dieser Test verhindern soll.
    """
    ohne = _trocken()
    assert "Uploader (spiegel-start-mac.sh)" in ohne, ohne


def test_ohne_spiegel_bleibt_er_aus():
    """🔴 Der Rest der alten Regel, und er trägt sie allein.

    Dass der Spiegel Vorgabe ist, darf nicht heissen, dass man ihn nicht mehr
    los wird. Wer heute NICHT veröffentlichen will — ein Probelauf, eine
    Person, die es sich anders überlegt hat — braucht dafür ein Wort und keinen
    Eingriff in ein Skript.

    Zugleich der Gegenbeweis zum Test oben: ohne diesen wäre er auch dann
    grün, wenn `--ohne-spiegel` gar nichts täte.
    """
    ohne = _trocken("--ohne-spiegel")
    assert "kein Uploader" in ohne, ohne
    assert "Uploader (spiegel-start-mac.sh)" not in ohne, ohne


def test_der_abholer_haengt_nicht_am_spiegel():
    """Zwei Dienste, zwei Entscheidungen — und der Abholer ist der schärfere.

    Er darf beim Spiegel LÖSCHEN und braucht dafür das starke Token. Dass der
    Spiegel jetzt von selbst mitläuft, zieht ihn NICHT mit."""
    assert "kein Abholer" in _trocken(), "der Abholer laeuft ungefragt mit"
    assert "kein Abholer" in _trocken("--mit-spiegel"), "--mit-spiegel zieht den Abholer mit"


def test_der_alte_schalter_bricht_nicht_ab():
    """`--mit-spiegel` war über einen Tag lang der Weg. Wer ihn aus Gewohnheit
    tippt, soll die Station starten und nicht eine Fehlermeldung lesen."""
    mit = _trocken("--mit-spiegel")
    assert "Uploader (spiegel-start-mac.sh)" in mit, mit


def _trocken(*schalter) -> str:
    """`--trocken` sagt, was gestartet WÜRDE, und startet nichts.

    Diesen Modus gibt es genau für diesen Test — und für den Menschen am
    Gerät, der vor dem Drücken wissen will, was gleich nach draußen geht.
    """
    fertig = subprocess.run(
        ["./scripts/start-station.sh", "--trocken", *schalter],
        capture_output=True, text=True, cwd=Path("."), timeout=30,
    )
    assert fertig.returncode == 0, fertig.stderr
    return fertig.stdout


def test_er_veroeffentlicht_beim_pruefen_nichts(tmp_path):
    """Die Prüfung darf LESEN und nichts schreiben.

    Der Empfänger kennt genau einen Schreibweg — alles unter `/ingest/`
    (`test_mirror.py::test_es_gibt_keinen_schreibweg_richtung_station`). Ein
    `--pruefen`, das dorthin postet, würde den Stand des Tages ersetzen.
    """
    text = SKRIPT.read_text(encoding="utf-8")
    for zeile in text.splitlines():
        blank = zeile.strip()
        if blank.startswith("#"):
            continue
        assert "/ingest/" not in blank, f"das Skript schreibt zum Spiegel: {blank}"
        assert "-X POST" not in blank, f"das Skript schreibt zum Spiegel: {blank}"


@pytest.mark.parametrize("nachbar", ["scripts/start-stt-mac.sh", "scripts/start-station.sh"])
def test_er_haelt_den_ton_der_nachbarskripte(nachbar):
    """Dieselbe Form wie die Skripte daneben: Kopfkommentar mit Grund und
    Aufruf, `set -u`, eine Zeile, wie man ihn wieder beendet."""
    text = SKRIPT.read_text(encoding="utf-8")
    vorbild = Path(nachbar).read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -u" in text
    assert "Aufruf:" in text
    assert "Beenden" in text
    # Kein leerer Vergleich: das Vorbild trägt diese Merkmale wirklich.
    assert "set -u" in vorbild and "Aufruf:" in vorbild
