"""Der Abholer braucht einen Weg auf dem Mac — und darf nicht mitlaufen.

🔴 WARUM ES DIESE DATEI GIBT (2026-09-02, beim Abschluss der Nacht):

Der Abholer ist das Gegenstueck zum Uploader. Ein Handy OHNE Tailnet erreicht
die Station nicht (sie sitzt hinter Venue-NAT); der Spiegel ist die einzige
Stelle, die beide sehen. Das Foto liegt dort zwischen, und die Station HOLT es
ab — dieselbe Richtung wie beim Uploader: die Station spricht nach draussen,
nie umgekehrt.

`mirror/abholer.py` ist gebaut und funktioniert. Der ganze Weg ist an diesem
Rechner durchgemessen worden (2026-09-02, 07:15):

    POST /ingest/photo (Foto-Token)      -> 200, im Posteingang
    Abholer: GET /eingang                -> die Datei
    Abholer: POST /api/photo (Station)   -> 200
    Abholer: DELETE /eingang/<datei>     -> quittiert
    Station: p9 mit Foto (80 645 B) UND Portrait (206 426 B)
    Posteingang danach leer

Zum Starten gab es aber nur `mirror/abholer-start.bat` — den Windows-Weg von
vor dem Rechnerwechsel. Genau dieselbe Luecke wie beim Uploader.

🔴 UND ER LAEUFT NICHT IM SAMMELSTART MIT. Anders als beim Uploader liegt der
Grund hier nicht beim Datenschutz, sondern bei der Reichweite: Der Abholer
braucht das STARKE Uploader-Token und darf damit beim Spiegel loeschen. Ein
Dienst mit dieser Befugnis geht nicht als Nebenwirkung eines Startknopfs an.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKRIPT = REPO / "scripts" / "abholer-start-mac.sh"


def test_es_gibt_ihn_und_er_ist_ausfuehrbar():
    assert SKRIPT.exists(), "der Abholer hat keinen Mac-Weg"
    assert SKRIPT.stat().st_mode & 0o111, "nicht ausfuehrbar"


def test_die_shell_haelt_ihn_fuer_gueltig():
    fertig = subprocess.run(["bash", "-n", str(SKRIPT)], capture_output=True, text=True)
    assert fertig.returncode == 0, fertig.stderr


def test_er_nennt_das_token_niemals_im_klartext():
    text = SKRIPT.read_text(encoding="utf-8")
    # Ein Token im Skript waere in jedem Checkout und jedem Verlauf.
    assert not re.search(r"KG_MIRROR_TOKEN=[A-Za-z0-9_-]{8,}", text)


def test_er_laeuft_nicht_ohne_schalter():
    """Er darf beim Spiegel LOESCHEN — das geht nicht nebenbei an.

    Anders als beim Uploader ist der Grund nicht der Datenschutz, sondern die
    BEFUGNIS: Der Abholer braucht das starke Uploader-Token. Seit 2026-09-02
    kann `--mit-abholer` ihn mitstarten; die Regel bleibt, dass er NIE VON
    SELBST anlaeuft.

    Geprueft wird durch Ausfuehren (`--trocken`), nicht durch Lesen des
    Quelltextes: Die Vorgaengerfassung suchte Zeilen mit dem Dateinamen und
    musste dafuer graue Hinweiszeilen ausnehmen — eine Regel ueber die FORM
    des Codes, die bei jeder Umformulierung neu justiert werden muss und
    dazwischen still grün steht.
    """
    ohne = _trocken()
    assert "kein Abholer" in ohne, ohne
    assert "Abholer (abholer-start-mac.sh)" not in ohne, ohne


def test_mit_schalter_laeuft_er_mit():
    mit = _trocken("--mit-abholer")
    assert "Abholer (abholer-start-mac.sh)" in mit, mit
    assert "kein Uploader" in mit, mit


def _trocken(*schalter) -> str:
    fertig = subprocess.run(
        [str(REPO / "scripts" / "start-station.sh"), "--trocken", *schalter],
        capture_output=True, text=True, cwd=REPO, timeout=30,
    )
    assert fertig.returncode == 0, fertig.stderr
    return fertig.stdout


def test_ohne_tokendatei_bricht_er_ab_und_sagt_wie_es_geht(tmp_path):
    fertig = subprocess.run(
        [str(SKRIPT), "--pruefen"],
        capture_output=True, text=True, cwd=REPO,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin",
             "HOME": str(tmp_path),
             "KG_TOKENDATEI": str(tmp_path / "gibt-es-nicht")},
    )
    assert fertig.returncode != 0, "ohne Token darf er nicht so tun, als ginge es"
    zusammen = fertig.stdout + fertig.stderr
    assert "token-verteilen.sh" in zusammen, "er sagt nicht, wie man das Token bekommt"


def test_pruefen_schickt_nichts_und_loescht_nichts():
    """`--pruefen` ist ein Bericht. Der Abholer QUITTIERT sonst mit DELETE —
    eine Probe, die das tut, wirft ein Foto weg, das noch niemand hat."""
    text = SKRIPT.read_text(encoding="utf-8")
    pruefteil = text.split("--pruefen")[1].split("# --- Lauf")[0] if "# --- Lauf" in text else text
    assert "DELETE" not in pruefteil.upper() or "curl -X DELETE" not in pruefteil
