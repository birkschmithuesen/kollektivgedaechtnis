# Bild-Endpunkt — Vertrag (NOCH NICHT VERIFIZIERT)

> ⚠️ **WARNUNG — vor der Ausstellung zu erledigen.**
> Die Request- und Response-Formen in diesem Dokument sind **ANGENOMMEN**,
> nicht am echten Endpunkt geprüft. Sie stammen aus der Modell-Dokumentation
> bzw. aus der Task-8-Planungsvorlage, nicht aus einem tatsächlichen Aufruf
> von `POST https://openrouter.ai/api/v1/chat/completions`. Grund: zum
> Zeitpunkt der Implementierung stand kein `OPENROUTER_API_KEY` zur Verfügung.
>
> Das Sondierungsskript, das die echte Form liefert, steht unten in
> **„Aktion für einen Menschen mit Schlüssel"**. Es muss **vor der
> Ausstellung** einmal mit einem echten Schlüssel ausgeführt werden.
>
> Weichen Code und Realität voneinander ab, gilt dieselbe Regel wie bei
> `docs/stt-contract.md`: **dieses Dokument ist die Autorität.** Zeigt die
> Sondierung eine andere Form, wird zuerst dieses Dokument korrigiert
> (Geprüft-am-Datum, Response-Abschnitt, Abweichungen-Zeile) und danach
> `kg2/imagegen.py` angepasst — nicht umgekehrt.

Wie `docs/stt-contract.md` für Tool 1: **erst am echten Endpunkt prüfen, dann
dagegen programmieren.** Ein Bildclient gegen eine vermutete Request-Form ist
genau die Sorte Fehler, die man vor Ort entdeckt. Für dieses Dokument wurde
dieser Schritt aus den oben genannten Gründen noch nicht durchgeführt — der
Code ist fertig und getestet, aber der Vertrag selbst ist offen.

| | |
|---|---|
| Geprüft am | — NOCH NICHT GEPRÜFT |
| Endpunkt | `POST https://openrouter.ai/api/v1/chat/completions` *(angenommen)* |
| Modell | `google/gemini-3-pro-image` *(angenommen)* |
| Auth | `Authorization: Bearer $OPENROUTER_API_KEY` *(angenommen)* |
| Abweichungen von Spec §5.2 | *(kann erst nach der Sondierung ausgefüllt werden)* |

## Request *(angenommene Form)*

```json
{
  "model": "google/gemini-3-pro-image",
  "modalities": ["image", "text"],
  "messages": [{"role": "user", "content": "<Prompt>"}]
}
```

`modalities` ist laut Modell-Dokumentation nicht optional: ohne den Eintrag
antwortet das Modell mit Text über das Bild statt mit dem Bild. Auch dies ist
Annahme, nicht Beobachtung — siehe Warnung oben.

## Response — ANGENOMMENE Form (nicht beobachtet)

Die folgende Struktur ist **nicht** mit dem Sondierungsskript geprüft worden.
Sie ist die Form, die Task 8 als Ausgangspunkt vorgibt und gegen die
`kg2/imagegen.py` geschrieben wurde:

```
choices: [1 items]
  message:
    role: 'assistant'
    content: ...
    images: [1 items]
      type: 'image_url'
      image_url:
        url: <str len=…> starts: 'data:image/png;base64,iVBORw0KGgo…'
```

Angenommen wird: Das Bild kommt als **Data-URL im Body**, nicht als Link, den
man nachladen müsste. Der Client dekodiert Base64 und schreibt PNG-Bytes
(`kg2.imagegen.decode_image`, `kg2.imagegen.save_image`). **Diese Annahme ist
nicht bestätigt.**

## Aktion für einen Menschen mit Schlüssel — vor der Ausstellung ausführen

Dieses Skript ist unverändert aus der Task-8-Vorgabe übernommen. Es braucht
`OPENROUTER_API_KEY` in der Umgebung und kostet einen Aufruf (ein paar Cent).
Es druckt nur die **Form** der Antwort, nicht die Bilddaten selbst.

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

**Nach dem Lauf:** die tatsächliche Ausgabe hier oben eintragen (Geprüft-am-
Datum setzen, Response-Abschnitt mit der echten Struktur ersetzen,
Abweichungen-Zeile ausfüllen oder „keine" eintragen). Weicht die Form ab, ist
`kg2/imagegen.py` — insbesondere `decode_image` — entsprechend anzupassen,
nicht dieses Dokument der Bequemlichkeit halber der Annahme anzugleichen.

## Was schiefgehen kann

Diese Tabelle ist unabhängig davon korrekt, was die Sondierung ergibt — sie
beschreibt Fehlerklassen, nicht die genaue Erfolgsform.

| Fall | Erkennung | Verhalten |
|---|---|---|
| Kein `images` im Ergebnis (Modell antwortet in Text) | `KeyError`/leere Liste | `ImageError` → Traum `failed`, letztes Bild bleibt stehen (Spec §8) |
| `url` ist kein `data:`-URL | Präfixprüfung | `ImageError` |
| HTTP 429 / 5xx | `raise_for_status` | `ImageError`, kein Retry-Sturm — der nächste Trigger versucht es erneut |
| Timeout | `httpx` | dito; das Zeitlimit steht in `config2.toml` (`image_timeout_s`) |

**Kein lokales Bildmodell als Fallback** (Spec §8, Brainstorm §5): zwei
Bildsprachen zu pflegen und eine GPU im Show-Rechner. Der physische
Rückfallweg ist ein LTE-Stick und steht im Runbook, nicht im Code.
