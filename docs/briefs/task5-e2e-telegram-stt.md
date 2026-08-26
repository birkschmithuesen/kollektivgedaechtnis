# Task 5 — Ende-zu-Ende-Tests: Telegram-Foto und STT

Brief für eine **neue Session**. Alles unten ist verifiziert, nicht vermutet;
wo etwas offen ist, steht es als offen da.

## Auftrag (Birk, 2026-08-26)

Zwei Ende-zu-Ende-Tests, die die echten Ketten durchlaufen:

1. **Telegram-Foto** → Download → Portraitzuschnitt → Personenknoten auf der Wand
2. **STT** → Transkript → Interviewende → LLM-Extraktion → Begriffe auf der Wand

**Mit echtem Anthropic-Call** — Birks ausdrückliche Entscheidung. Die
aufgezeichnete Variante war angeboten und wurde verworfen: der Test soll die
Extraktion wirklich prüfen, nicht nur die Verkabelung. Tokenkosten sind
akzeptiert.

## Was schon steht

| Baustein | Ort | Zustand |
|---|---|---|
| Telegram-Poller | `kg/telegram_bot.py` | `TelegramSource.dispatch(update)` nimmt ein rohes Update-dict; `downloader` ist **injizierbar** (Konstruktor-Argument, Default lädt über den echten Bot) |
| Portraitzuschnitt | `kg/photos.py` (`make_portrait`) | fertig |
| STT-Consumer | `kg/stt_client.py` | `STTClient(url, ...)`, `line_source` ist **injizierbar** — ein Test kann SSE-Zeilen einspeisen, ohne einen Server zu starten |
| STT-Vertrag | `docs/stt-contract.md` | zehn Felder, nur `type == "final"` wird konsumiert; `extending` muss lediglich toleriert werden |
| Pipeline | `kg/pipeline.py` (`process_interview`) | ruft Extraktion + Merge |
| LLM-Client | `kg/llm.py` (`LLMClient`) | Modell/Effort/Tokens aus `Config` |

**Die beiden Injektionspunkte sind der Hebel.** Beide Adapter nehmen ihre
I/O-Quelle als Argument entgegen — kein Monkeypatching nötig.

## Vorschlag für den Zuschnitt

**Telegram:** Fake-Bot-Server, der die Telegram-HTTP-API nachstellt
(`getUpdates` liefert ein Foto-Update, `getFile` + Dateidownload liefern Bytes).
Der echte `TelegramSource` redet damit statt mit Telegram. Kein Bot-Token, kein
Netz. Ungetestet bleibt allein Telegrams eigene Antwortform — das ist der
bewusste Rest.

**STT:** Fake-SSE-Server nach `docs/stt-contract.md` (unbenannte Events, ein
JSON pro Zeile, `: keep-alive` dazwischen). Sendet ein Interview, dann den
Stopp. Danach läuft `process_interview` mit **echtem** Anthropic-Aufruf.

**Kostenbremse:** Ein Interview je Lauf, kurzes Transkript. Der Test gehört
hinter eine Markierung (`@pytest.mark.e2e` o. ä.) und darf nicht in der
Standardsuite laufen — sonst kostet jeder CI-Lauf Geld.

**Schlüssel:** `ANTHROPIC_API_KEY` in der Umgebung, nie in `config.toml`, nie
in einer Testdatei.

## Fallstricke aus dieser Session

- **Der Server hält Code im Speicher.** Änderungen an `kg/server.py` sind erst
  nach Neustart wirksam. Kostete hier eine falsche Fehlersuche: Live-Test gegen
  einen neuen Endpoint gab 404, weil der alte Prozess noch lief.
- **Playwright + `emit('tap')` bringt den vendorten Chromium zum Absturz**
  („Target crashed"), auch ganz ohne eigenen Code. Echte Mausklicks auf
  `renderedPosition()` benutzen.
- **Cytoscapes `'core'`-Selektor feuert umgekehrt zum Namen**: bei Knoten-Taps,
  nicht bei Hintergrund-Taps. Gemessen und in `quote-overlay.js` dokumentiert.
- **`Number(x) || 1` ist falsch für Werte, die 0 sein dürfen** — 0 ist falsy.
- **Nicht aus Zeitstempeln oder `.pyc`-Daten auf Fortschritt schließen.**
  Hängt ein Prozess, `py-spy dump --pid` benutzen — aber ein *einzelnes* Sample
  zeigt nur, wo der Prozess gerade ist, nicht wo er feststeckt.
- **Die volle Testsuite dauert ~15 min**, davon 11 min `test_prerender.py`
  (echte Chromium-Renderfilme, 21 Tests, alle grün). Kein Hänger — nur lang.
  `--ignore=tests/test_prerender.py` für schnelle Läufe.
- **`tests/test_dream_server.py` hängt unendlich** (SSE-Test ohne Timeout,
  Tool 2, uncommitteter Code). Ausschließen, bis das behoben ist.

## Nachschlagen

- `docs/stt-contract.md` — Drahtformat, verifiziert am Quellrepo
- `docs/operations.md` — Runbook, jetzt inkl. Touch, Zoom, Tempo
- `docs/simulationswerkzeuge.md` — Step-Server, Interview-Export, Portraits
- `docs/superpowers/specs/2026-08-12-kollektivgedaechtnis-design.md` — Spec
