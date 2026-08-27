# Bild-Endpunkt — Vertrag (VERIFIZIERT 2026-08-26)

> ✅ **Sondierung durchgeführt am 2026-08-26** (Birks vServer, Schlüssel aus
> `~/.hermes/.env` per `set -a; . ~/.hermes/.env; set +a`). Drei echte Aufrufe
> gegen `POST https://openrouter.ai/api/v1/chat/completions`. Die
> Request-Form der Annahme hat sich bestätigt, die Response-Form **nicht
> vollständig** — siehe „Abweichungen" unten.
>
> Es gilt weiterhin dieselbe Regel wie bei `docs/stt-contract.md`: **dieses
> Dokument ist die Autorität.** Der Code folgt ihm, nicht umgekehrt.

Wie `docs/stt-contract.md` für Tool 1: **erst am echten Endpunkt prüfen, dann
dagegen programmieren.** Dieser Schritt ist jetzt erfolgt.

| | |
|---|---|
| Geprüft am | **2026-08-26**, drei Aufrufe, alle HTTP 200 |
| Endpunkt | `POST https://openrouter.ai/api/v1/chat/completions` — bestätigt |
| Modell | `google/gemini-3-pro-image` — bestätigt |
| Auth | `Authorization: Bearer $OPENR...KEY` — bestätigt |
| Abweichungen von Spec §5.2 | **Drei** — (1) `images` enthält **zwei** Einträge, nicht einen; (2) `message.content` ist `None`, nicht Text; beide unkritisch für `kg2/imagegen.py`. (3) **das Bildformat variiert pro Aufruf** (PNG oder JPEG) — kritisch, macht eine Codeänderung nötig. Details unten. |
| Kosten | **≈ 0,139 USD pro Bild** (gemessen: 0,138882 / 0,138146). Das ist **nicht** „ein paar Cent" — siehe „Kosten" unten. |

## Request — bestätigte Form

Die angenommene Request-Form war korrekt und wurde unverändert übernommen.
`modalities` ist tatsächlich erforderlich.

```json
{
  "model": "google/gemini-3-pro-image",
  "modalities": ["image", "text"],
  "messages": [{"role": "user", "content": "<Prompt>"}]
}
```

`modalities` ist laut Modell-Dokumentation nicht optional: ohne den Eintrag
antwortet das Modell mit Text über das Bild statt mit dem Bild. **Nicht
gegengeprüft** — die Sondierung hat nur den Erfolgsfall MIT `modalities`
gefahren; ein Aufruf ohne den Eintrag wurde nicht gemacht (er hätte einen
weiteren Bildaufruf gekostet, ohne eine offene Entscheidung zu beantworten).
Der Eintrag bleibt drin.

## Response — BEOBACHTETE Form (2026-08-26)

Tatsächlich beobachtet, dreimal reproduziert:

```
choices: [1 items]
  message:
    role: 'assistant'
    content: None                      # <-- NICHT Text, sondern None
    refusal: None
    reasoning: <str len≈1400>          # Denkspur des Modells, im Vertrag nicht vorgesehen
    reasoning_details: [1 items]
      signature: <str len≈2,5 Mio>     # sehr groß, wird nicht gelesen
    images: [2 items]                  # <-- ZWEI, nicht eines
      type: 'image_url'
      image_url:
        url: <str len≈2,2 Mio> starts: 'data:image/png;base64,iVBORw0KGgo…'
usage:
  cost: 0.138882                       # USD, pro Aufruf
```

Bestätigt: Das Bild kommt als **Data-URL im Body**, nicht als nachzuladender
Link. Der Client dekodiert Base64 und schreibt die dekodierten Bytes weg.
In dieser Sondierung (drei Aufrufe) PNG, RGB, **1376 × 768 px**
(Seitenverhältnis 16:9 wird also geliefert) — im späteren Produktivbetrieb
kam aber auch JPEG vor, siehe „Abweichung 3" unten. Das Seitenverhältnis gilt
für beide Formate gleichermaßen.

### Abweichung 1: `images` enthält ZWEI Einträge

Die Annahme war „1 items". Real sind es zwei. Untersucht statt vermutet:

- Beide Data-URLs sind **exakt gleich lang** (2 352 598 Zeichen), beide
  dekodieren zu 1 764 430 Bytes, beide sind PNG 1376 × 768 RGB.
- **Pixelweise identisch**: maximale Abweichung über alle Kanäle = `0.0`,
  0,000 % der Pixel unterscheiden sich (Vergleich per Pillow/NumPy).
- Unterschiedlich sind nur **1196 Bytes Metadaten** ab Offset 1042: ein GUID
  im eingebetteten IPTC-/XMP-Block (`Made with Google AI`,
  `trainedAlgorithmicMedia`). Zwei Ausfertigungen desselben Bildes mit
  verschiedener Kennung.

**Folge für den Code: keine.** `images[0]` zu nehmen ist korrekt — es gibt
kein zweites, besseres Bild, das dabei verloren ginge. `kg2/imagegen.py`
bleibt an dieser Stelle unverändert.

### Abweichung 2: `message.content` ist `None`

`decode_image` liest `content` nur im **Fehlerfall**, um die Textantwort des
Modells in die Fehlermeldung zu setzen (`str(message.get("content", ""))`).
Bei `content: None` liefert `.get` nicht den Default, sondern `None`, und die
Meldung enthält dann `'None'` statt der Prosa. Das ist kosmetisch und betrifft
ausschließlich die Fehlermeldung — der Erfolgspfad ist nicht berührt.

### Abweichung 3: Bildformat variiert (PNG oder JPEG)

**Am echten Endpunkt beobachtet, 2026-08-26**, außerhalb der obigen
Drei-Aufrufe-Sondierung: bei einer Serie von 5 Bild-Aufrufen kamen **2 von 5**
Bildern als JPEG zurück statt als PNG, korrekt deklariert als
`data:image/jpeg;base64,` (Bytes beginnen mit `\xff\xd8\xff\xe0\x00\x10JF`,
der JPEG-typische JFIF-Header). Die übrigen 3 kamen als
`data:image/png;base64,` wie in der Sondierung oben.

Nicht prompt-abhängig reproduzierbar — das Modell entscheidet das Format pro
Aufruf, unabhängig vom Inhalt der Anfrage. Beide Formate sind vollständige,
unbeschädigte Bilder; keines davon ist ein Fehlerfall.

**Folge für den Code:** `kg2/imagegen.py::save_image` prüfte bisher hart auf
die PNG-Magic-Number und verwarf jedes JPEG als `ImageError`, obwohl das Bild
intakt war. Der Code muss **beide** Formate akzeptieren und die Dateiendung
aus den tatsächlichen Bytes ableiten (nicht aus dem deklarierten MIME-Typ,
der nicht als vertrauenswürdig gilt — nur der Byte-Header entscheidet). Die
Schutzwirkung gegen Nicht-Bild-Inhalte (z. B. ein base64-dekodierter
Fehlertext) bleibt bestehen: abgelehnt wird, was weder PNG noch JPEG ist.

### Kosten — die eigentliche Überraschung

Gemessen **0,138882 USD** bzw. **0,138146 USD** pro Bild. Sowohl dieses
Dokument als auch `docs/operations.md` beschrieben den Sondierungslauf als
„kostet einen Aufruf (ein paar Cent)". Das ist um gut das Fünffache daneben.
Hochgerechnet auf die geplanten Läufe:

| Lauf | Bilder | Kosten |
|---|---|---|
| Sondierung (dieses Dokument) | 1 | ≈ 0,14 USD |
| `sim.dream_register` (Registermuster) | 4 | ≈ 0,56 USD |
| `sim.dream_prerender --generate` (40-Bilder-Serie) | 40 | **≈ 5,55 USD** |
| Ausstellungstag, ~40 Träume | ~40 | **≈ 5,55 USD** |

Das ist immer noch klein, aber es ist eine **andere Größenordnung als
angekündigt** und gehört vor die Entscheidung über die 40-Bilder-Serie, nicht
danach. Der Betrag ist gemessen, nicht geschätzt: `usage.cost` aus der
Antwort.

## Sondierungsskript (erledigt am 2026-08-26 — nicht erneut nötig)

Dieses Skript hat die oben dokumentierte Form geliefert. Es steht hier als
Beleg und für den Fall, dass sich das Modell ändert. **Ein erneuter Lauf ist
nicht nötig** und kostet ≈ 0,14 USD. Es druckt nur die **Form** der Antwort,
nicht die Bilddaten selbst.

```bash
uv run python - <<'PY'
import json, os, httpx
key = os.environ["OPENROUTER_API_KEY"]
response = httpx.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": f"Bearer {key}"},
    json={
        "model": "google/gemini-3-pro-image",
        "modalities": ["image", "text"],
        "messages": [{"role": "user", "content":
            "Ein Betonhof, in dem Kinder Bäume pflanzen. "
            "Malerisch und atmosphärisch, weiche Übergänge, gedämpfte Farbigkeit, "
            "diffuses Licht. Kein Fotorealismus, keine Schrift im Bild. "
            "Seitenverhältnis 16:9, Querformat."}],
    },
    timeout=180.0,
)
print("HTTP", response.status_code)
payload = response.json()
# Print the SHAPE, not the base64 payload — a data URL is megabytes.
def shape(value, depth=0):
    pad = "  " * depth
    if isinstance(value, dict):
        for key, item in value.items():
            print(f"{pad}{key}:")
            shape(item, depth + 1)
    elif isinstance(value, list):
        print(f"{pad}[{len(value)} items]")
        if value:
            shape(value[0], depth + 1)
    elif isinstance(value, str) and len(value) > 120:
        print(f"{pad}<str len={len(value)}> starts: {value[:80]!r}")
    else:
        print(f"{pad}{value!r}")
shape(payload)
PY
```

**Nach dem Lauf:** die tatsächliche Ausgabe oben eintragen (erledigt
2026-08-26). Weicht die Form künftig ab, ist `kg2/imagegen.py` — insbesondere
`decode_image` — entsprechend anzupassen, nicht dieses Dokument der
Bequemlichkeit halber der Annahme anzugleichen.

## Was schiefgehen kann

Diese Tabelle ist unabhängig davon korrekt, was die Sondierung ergibt — sie
beschreibt Fehlerklassen, nicht die genaue Erfolgsform.

| Fall | Erkennung | Verhalten |
|---|---|---|
| Kein `images` im Ergebnis (Modell antwortet in Text) | `KeyError`/leere Liste | `ImageError` → Traum `failed`, letztes Bild bleibt stehen (Spec §8) |
| `url` ist kein `data:`-URL | Präfixprüfung | `ImageError` |
| Bild kommt als JPEG statt PNG (Abweichung 3) | Byte-Header, nicht der deklarierte MIME-Typ | wird als gültiges Bild akzeptiert, landet mit `.jpg`-Endung auf der Platte |
| Bytes sind weder PNG noch JPEG (z. B. Fehlertext) | Byte-Header | `ImageError` → Traum `failed`, keine Datei bleibt liegen |
| HTTP 429 / 5xx | `raise_for_status` | `ImageError`, kein Retry-Sturm — der nächste Trigger versucht es erneut |
| Timeout | `httpx` | dito; das Zeitlimit steht in `config2.toml` (`image_timeout_s`) |

**Kein lokales Bildmodell als Fallback** (Spec §8, Brainstorm §5): zwei
Bildsprachen zu pflegen und eine GPU im Show-Rechner. Der physische
Rückfallweg ist ein LTE-Stick und steht im Runbook, nicht im Code.
