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

🔴 Dieses Skript steht ABSICHTLICH NICHT in `scripts/start-station.sh`. Es
schiebt Interviewdaten ins öffentliche Netz — das ist Birks Entscheidung, kein
Nebeneffekt eines Sammelstarts. `test_der_uploader_haengt_nicht_am_sammelstart`
hält das fest, damit es niemand später „aufräumt".
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


def test_der_uploader_haengt_nicht_am_sammelstart():
    """🔴 Birks Entscheidung, nicht unsere.

    `start-station.sh` startet die Station im Haus. Der Uploader schiebt
    Interviewdaten ins ÖFFENTLICHE Netz. Wer beides in einen Knopf legt,
    nimmt Birk die Entscheidung ab, ob heute veröffentlicht wird.

    Ein HINWEIS darauf, dass es ihn gibt, ist dagegen erwünscht — sonst findet
    ihn am Ausstellungstag niemand. Verboten ist der AUFRUF, nicht die
    Erwähnung.
    """
    sammel = Path("scripts/start-station.sh").read_text(encoding="utf-8")
    aufrufe = (
        "./scripts/spiegel-start-mac.sh &",
        "bash scripts/spiegel-start-mac.sh",
        "sh scripts/spiegel-start-mac.sh",
        "-m mirror.uploader",
    )
    for nummer, zeile in enumerate(sammel.splitlines(), start=1):
        blank = zeile.strip()
        if blank.startswith("#"):
            continue
        for aufruf in aufrufe:
            assert aufruf not in blank, f"Sammelstart startet den Uploader (Zeile {nummer}): {blank}"


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
