"""Deutsche Silben zaehlen — mechanisch, ohne Woerterbuch.

🔴 WARUM ES DAS GIBT (Birk, 2026-09-02): Der Satz unter dem Traumbild soll ein
Haiku sein, also 5-7-5 Silben. Kein bei Infomaniak verfuegbares Modell kann
seine eigenen Silben zaehlen — gemessen am selben Tag: Liess man das Modell die
Zahl selbst mitliefern, wich seine Zaehlung in 14 von 16 Faellen von der
echten ab, und es glaubte jedes Mal, getroffen zu haben.

Deshalb zaehlt hier ein Programm, und das Modell bekommt die Zahl gesagt
(`kg2.haiku`). Damit haengt die Form nicht mehr an einer Faehigkeit, die diese
Modelle nicht haben: Die Trefferquote stieg von 12/20 auf 19–20/20.

## Was die Zaehlung kann

Vokalgruppen, mit zwei Sonderfaellen, die beide gemessen wurden:

1. **Hiatus nach Diphthong.** „bauen" ist zweisilbig (Bau-en), obwohl au und e
   direkt aneinanderstossen. Eine naive Zaehlung zieht sie zu EINER Gruppe
   zusammen und kommt auf 1. Ebenso Frau-en, blau-es, neu-e, Feu-er, Ei-er.
2. **„-ie" am Wortende** nach l/n/r ist meist zweisilbig (Fa-mi-li-e, Li-ni-e,
   Se-ri-e), nicht der Diphthong wie in „Pa-pier".

## 🔴 Was sie NICHT kann

Hiatus zwischen zwei EINFACHEN Vokalen: „The-a-ter", „Mu-se-um", „na-iv"
zaehlt sie zu knapp. Ohne Woerterbuch ist das nicht zu entscheiden, und ein
Woerterbuch liegt auf der Station nicht. Die Zaehlung ist also eine Naeherung,
kein Beweis — was durchgeht, ist „sehr wahrscheinlich 5-7-5", nicht „sicher".
Fuer eine Bildunterschrift traegt das; fuer einen Lyrikwettbewerb nicht.
"""

from __future__ import annotations

import re

#: Reihenfolge zaehlt: „äu" vor „au", sonst bliebe das ä stehen.
DIPHTHONGE = ("äu", "eu", "au", "ei", "ie")

_UNWORT = re.compile(r"[^a-zäöüßA-ZÄÖÜ]")
_VOKALGRUPPE = re.compile(r"[aeiouäöüy]+")


def silben_wort(wort: str) -> int:
    w = _UNWORT.sub("", wort).lower()
    if not w:
        return 0
    zusatz = 0
    if re.search(r"[lnr]ie$", w):
        # Li-ni-e: das „e" ist eine eigene Silbe, das „i" gehoert zur vorigen.
        w = w[:-2] + "i"
        zusatz = 1
    for d in DIPHTHONGE:
        w = w.replace(d, "0")
    # Jeder Diphthong ist EINE Silbe fuer sich; die uebrigen Vokalgruppen
    # daneben. Das „ " beim Ersetzen trennt sie, damit „bauen" (b0en) nicht
    # als eine Gruppe durchgeht.
    zahl = w.count("0") + len(_VOKALGRUPPE.findall(w.replace("0", " ")))
    return max(1, zahl + zusatz)


def silben_zeile(zeile: str) -> int:
    return sum(silben_wort(w) for w in zeile.split())
