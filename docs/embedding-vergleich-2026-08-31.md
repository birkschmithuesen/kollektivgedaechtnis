# Embedding-Wechsel OpenAI → bge (Infomaniak): gemessen, nicht geschätzt

**Erhoben 2026-08-31** gegen echte Daten: 1126 gecachte Labels aus Lauf 19c
(`data/embeddings.sqlite3`) und **108 reale Merge-Paare** aus der Alias-Tabelle
von `out/sim19c/sim.db` — also Paare, die der Judge tatsächlich als dasselbe
erkannt hat. Keine ausgedachten Begriffe.

**Frage:** Trägt `merge_neighbours = 12` auch mit dem Schweizer Modell? Der
Wert ist gegen `text-embedding-3-small` kalibriert (merge-audit-2026-08-27,
Lauf 19b→19c). Embeddings entscheiden nichts, sie wählen nur die Kandidaten
aus, die der Judge zu sehen bekommt — fällt der Partner aus den Top-12, wird
er nie gemerged.

---

## Ergebnis

| | Partner in den Top-12 |
|---|---|
| OpenAI `text-embedding-3-small` | **66/108 = 61 %** |
| bge `bge_multilingual_gemma2` (Infomaniak) | **69/108 = 64 %** |

**bge ist insgesamt leicht besser.** Der Gesamtwert allein trägt aber keine
Entscheidung — er könnte Gewinne und Verluste verstecken. Die Aufschlüsselung:

| Fall | Anzahl |
|---|---|
| beide finden den Partner | 57 |
| **nur bge** findet ihn | **12** |
| **nur OpenAI** findet ihn | **9** |
| keiner | 30 |

### Wo bge klar gewinnt — und warum das inhaltlich zählt

Die Gewinne sind keine Zufallstreffer, sie liegen dort, wo **Umschreibungen
statt Wortstämme** verglichen werden:

| Label | Partner | OpenAI | bge |
|---|---|---|---|
| CO2-Bilanz der Bauindustrie | Graue Energie | #198 | **#9** |
| Umbau statt Neubau | Weiterbauen im Bestand | #101 | **#8** |
| Beteiligung als Feigenblatt | Scheinbeteiligung pro forma | #44 | **#6** |
| Materialkreisläufe | Bauteilrecycling | #30 | **#2** |
| Lineare Bauwirtschaft | Abriss-Neubau-Paradigma | #27 | **#2** |

Das ist genau die „Perspektiv-Varianz auf gleicher Abstraktionsebene", die der
Merge-Audit als **eigentliche Fehlerquelle** benannt hat (Phase 4a). bge trifft
sie besser — plausibel, denn es ist ein mehrsprachiges Modell auf einem
Sprachmodell-Rückgrat, während `text-embedding-3-small` das kleine
englischzentrierte OpenAI-Modell ist.

### Wo bge verliert

Neun Paare fallen aus dem Fenster, die meisten knapp (#13–#22) — mit zwei
Ausreißern:

| Label | Partner | OpenAI | bge |
|---|---|---|---|
| Kluges Reparieren | Bröckelnder Putz statt Abriss | #9 | **#353** |
| Ländlicher Leerstand | Leerstehende Häuser im Dorfkern | #10 | **#68** |

Auffällig: mehrere Verluste betreffen dasselbe Ziel („Leerstehende Häuser im
Dorfkern"). Ein größeres `K` heilt das **nicht** vollständig — selbst bei
K=120 fehlt ein Paar, das OpenAI in den Top-12 hatte.

## Bewertung

**Der Wechsel ist vertretbar, aber er ist ein Tausch, kein Upgrade.** bge
gewinnt 12 und verliert 9; netto +3. Die Gewinne liegen bei der dominanten
Fehlerklasse (Umschreibungen), die Verluste bei Wortstamm-Ähnlichkeit, wo der
Judge ohnehin oft über die Alias-Tabelle greift (exakter String-Vergleich läuft
**vor** der Embedding-Vorauswahl, `merging.py:73-83`).

`merge_neighbours = 12` bleibt tragfähig — der Wert war nie gegen ein Modell
kalibriert, sondern gegen die Frage „steht der Partner im Fenster", und die
beantwortet bge minimal besser.

**Wichtig:** Der Cache ist modell-verschlüsselt (`kg/embeddings.py`, Zeile 15:
*„Vectors from two different models are not comparable"*). Ein Wechsel trifft
also einfach den Cache nicht und embeddet neu — nichts zu migrieren, aber ein
Lauf mit gemischten Modellen wäre Unsinn. Deshalb: umstellen heißt, den
nächsten Simulationslauf komplett neu zu embedden (1126 Labels, wenige Cent).

## Reproduktion

```bash
# Vergleichsskripte (Wegwerf-Code, in /tmp):
python /tmp/embedding_vergleich.py   # Top-12-Trefferquote beider Modelle
python /tmp/embedding_bilanz.py      # Gewinne/Verluste im Detail
# bge-Vektoren liegen zwischengespeichert in /tmp/bge_vecs.json
```
