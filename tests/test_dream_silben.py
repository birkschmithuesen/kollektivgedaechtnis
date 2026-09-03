"""Die deutsche Silbenzaehlung (`kg2.silben`).

Sie ist der Grund, warum das Haiku ueberhaupt funktioniert: Kein bei
Infomaniak verfuegbares Modell kann seine eigenen Silben zaehlen (gemessen
2026-09-02: 14 von 16 Selbstzaehlungen falsch, jedes Mal in gutem Glauben).
Zaehlt dieses Modul falsch, schickt die Schleife das Modell in die falsche
Richtung — und zwar unbemerkt, weil das Ergebnis dann trotzdem „5-7-5" meldet.
"""

from __future__ import annotations

import pytest

from kg2.silben import silben_wort, silben_zeile


@pytest.mark.parametrize(
    "wort, erwartet",
    [
        # Der Grundfall.
        ("Lehm", 1), ("Haus", 1), ("Wand", 1),
        ("Fenster", 2), ("Geländer", 3), ("Baustelle", 3), ("Asphalt", 2),
        # 🔴 Hiatus nach Diphthong — hier zaehlte die erste Fassung 1 statt 2.
        ("bauen", 2), ("Frauen", 2), ("blaues", 2), ("neue", 2), ("Feuer", 2),
        # 🔴 „-ie" am Wortende nach l/n/r: zwei Silben.
        ("Familie", 4), ("Linie", 3),
        # ...aber nicht ueberall: „Papier" ist der Diphthong.
        ("Papier", 2),
        # Umlaute und ss/ß.
        ("Räume", 2), ("drücken", 2), ("Straße", 2),
    ],
)
def test_einzelne_woerter(wort, erwartet):
    assert silben_wort(wort) == erwartet, wort


def test_eine_zeile_ist_die_summe_ihrer_woerter():
    # Das erste Haiku, das am 2026-09-02 sauber durchkam.
    assert silben_zeile("Hand an kühlem Lehm") == 5
    assert silben_zeile("rote Dächer tief im Tal") == 7
    assert silben_zeile("Wege führen fort") == 5


def test_satzzeichen_und_leerraum_zaehlen_nicht_mit():
    assert silben_zeile("  Lehm,   Haus!  ") == 2
    assert silben_wort("„Wand“") == 1


def test_ein_leeres_wort_ist_null_silben_und_kracht_nicht():
    assert silben_wort("") == 0
    assert silben_wort("—") == 0
    assert silben_zeile("") == 0


def test_jedes_echte_wort_hat_mindestens_eine_silbe():
    """Sonst koennte eine Zeile aus lauter Kurzwoertern auf 0 kommen und die
    Schleife haette nichts zu korrigieren."""
    for w in ["Uhr", "Ei", "Au", "Bau"]:
        assert silben_wort(w) >= 1, w
