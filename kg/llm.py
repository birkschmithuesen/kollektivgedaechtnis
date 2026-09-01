"""LLM-Wrapper. Deterministischer Pipeline-Schritt, kein Agent (spec 2).

Zwei API-Modi, und der erste bleibt der Default:

* ``anthropic`` — der Weg, über den alles gebaut und der Referenzlauf 19c
  gefahren wurde: ``messages.create`` mit ``output_config`` (``effort`` +
  ``json_schema``). Unverändert.
* ``chat_completions`` — jeder OpenAI-kompatible Endpunkt, gemessen gegen
  Infomaniak (``https://api.infomaniak.com/2/ai/<produkt>/openai/v1``,
  2026-08-31). Dasselbe gehärtete Schema aus ``strict_schema`` reist hier als
  ``response_format`` mit ``strict: true``.

Umgeschaltet wird ausschließlich über die Konfiguration; eine unveränderte
``config.toml`` fährt weiter über Anthropic. Der zweite Modus ist eine
Ergänzung, kein Ersatz — beide Wege müssen jederzeit funktionsfähig bleiben
(Betriebsentscheidung Birk, 2026-08-31, Aufbau am 01.09.).

**Zwei gemessene Fehlerbilder des chat_completions-Wegs**, beide bei
``moonshotai/Kimi-K2.6``, beide mit HTTP 200 und ``finish_reason: "stop"``:

1. Der Inhalt beginnt mit ``{{`` statt ``{`` — fast richtiges JSON, an dem
   ``json.loads`` scheitert. 0 von 5 validen Antworten ohne
   ``reasoning_effort``, 0 von 8 mit ``"low"``, 8 von 8 mit ``"none"``. Das
   Feld gehört deshalb in den Request-Body (``reasoning_effort``), und die
   eine überzählige Klammer wird hier repariert, statt eine bezahlte Antwort
   wegzuwerfen.
2. Bei aktivem Reasoning steht der Gedankengang in ``message.reasoning`` und
   ``content`` ist ``null``. Als leerer String durchgereicht wäre das ein
   stillschweigend leeres Extraktionsergebnis — also ein Interview ohne
   Begriffe, ohne irgendeine Spur im Log. Deshalb ein Fehler.

Nicht als Default vorschlagen: die Qwen-Modelle brauchten in derselben Messung
28–37 s pro Antwort und sind für den heißen Pfad unbrauchbar.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TypeVar

from pydantic import BaseModel

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

#: Die zwei Wege. Ein Tippfehler in der config.toml soll beim Start auffallen,
#: nicht mitten in einem Interview.
API_MODES = ("anthropic", "chat_completions")

#: Großzügig: der Pipeline-Aufruf verdichtet ein ganzes Interview und läuft
#: nicht im heißen Pfad. Der Wake-Word-Client setzt sein eigenes, hartes Budget
#: (kg.stop_intent).
DEFAULT_TIMEOUT_S = 300.0

#: Woran ein AUSFALL DES ANBIETERS zu erkennen ist -- im Unterschied zu einer
#: schlechten Antwort. Der Unterschied entscheidet, ob Warten hilft: Gegen
#: kaputtes JSON hilft es nicht (das Modell antwortet ja), gegen einen
#: Dienst, der gerade weg ist, hilft nur es.
#:
#: Am 2026-09-01 war Infomaniak ZWEIMAL fuer ein bis fuenf Minuten komplett
#: weg. Die Fehlerbilder, wortwoertlich aus den Logs dieses Abends:
#:   „peer closed connection without sending complete message body
#:    (incomplete chunked read)"        -- der haeufigste
#:   „Response ended prematurely"       -- im STT-Backend
#:   HTTP 503 mit einer HTML-Seite      -- „Service momentanement indisponible"
#:
#: Geprueft wird am TEXT der Ausnahme und nicht an ihrer Klasse: durch diesen
#: Client laufen httpx-, anthropic- und Standardbibliotheks-Fehler, und die
#: Klassenliste waere beim naechsten Bibliotheks-Update still unvollstaendig.
#: Ein Textmuster, das nicht mehr passt, macht die Wiederholung hoechstens
#: wirkungslos -- eine falsch geratene Klasse laesst sie unbemerkt ausfallen.
_AUSFALL_MUSTER = (
    "peer closed connection",
    "incomplete chunked read",
    "connection broken",
    "response ended prematurely",
    "server disconnected",
    "connection reset",
    "connection refused",
    "timed out",
    "timeout",
    "temporarily unavailable",
    "service unavailable",
    " 429",
    " 500",
    " 502",
    " 503",
    " 504",
    "status_code=429",
    "status_code=500",
    "status_code=502",
    "status_code=503",
    "status_code=504",
)

#: Wartezeiten zwischen zwei Versuchen, in Sekunden. Nicht exponentiell ins
#: Blaue: die zwei gemessenen Ausfaelle dauerten rund 2 und rund 5 Minuten,
#: und der Anbieter kam beide Male ohne Vorwarnung zurueck. Deshalb erst
#: dicht nachfassen (ein 20-Sekunden-Ausfall soll kaum auffallen), dann
#: ruhiger, damit ein langer Ausfall nicht hunderte Anfragen erzeugt.
_WARTEPLAN = (2.0, 5.0, 10.0, 20.0, 30.0)


def _ist_ausfall(exc: Exception) -> bool:
    """Ist das ein Anbieter, der gerade weg ist -- oder eine schlechte Antwort?"""
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(muster in text for muster in _AUSFALL_MUSTER)


class LLMError(RuntimeError):
    """The model failed, refused, or returned something that is not our schema."""


def strict_schema(model: type[BaseModel]) -> dict:
    """Pydantic schema hardened for structured outputs.

    Structured outputs require additionalProperties: false and an explicit
    `required` list on every object, including nested $defs.
    """
    schema = model.model_json_schema()

    def harden(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for value in node.values():
                harden(value)
        elif isinstance(node, list):
            for item in node:
                harden(item)

    harden(schema)
    return schema


def _httpx_post(url: str, headers: dict, json: dict, timeout: float) -> dict:
    import httpx

    response = httpx.post(url, headers=headers, json=json, timeout=timeout)
    response.raise_for_status()
    return response.json()


def decode_json(text: str, *, repair_doubled_brace: bool) -> object:
    """``json.loads`` mit genau einer Reparatur, und nur wo sie gemessen wurde.

    ``repair_doubled_brace`` ist an den chat_completions-Modus gebunden: dort
    ist das führende ``{{`` real aufgetreten (Modul-Docstring). Der
    Anthropic-Pfad decodiert weiter strikt — er hat dieses Fehlerbild nie
    gezeigt, und ein Weg, der nachweislich läuft, wird nicht nebenbei
    toleranter gemacht.

    Die Reparatur gilt nur, wenn sie die Ausgabe wirklich parsebar macht;
    sonst bleibt es ein Fehlschlag und der Retry in `LLMClient.parse` greift.
    Eine Klammer wegzunehmen, die zufällig hilft, ist etwas anderes als aus
    kaputtem Text irgendein JSON zu schnitzen — Letzteres würde stillschweigend
    falsche Inhalte durchlassen.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if not (repair_doubled_brace and text.startswith("{{")):
            raise
        repaired = text[1:]
        log.warning("llm answer began with '{{'; repaired the doubled opening brace")
        return json.loads(repaired)


class LLMClient:
    def __init__(
        self,
        model: str,
        effort: str,
        max_tokens: int,
        api_key: str | None = None,
        client=None,
        max_attempts: int = 2,
        retry_budget_s: float = 0.0,
        api_mode: str = "anthropic",
        url: str | None = None,
        reasoning_effort: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
        post=_httpx_post,
    ) -> None:
        if api_mode not in API_MODES:
            raise ValueError(f"llm_api_mode must be one of {API_MODES}, not {api_mode!r}")
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.max_attempts = max_attempts
        #: Wie lange bei einem AUSFALL DES ANBIETERS insgesamt weiterversucht
        #: wird (Sekunden). 0 = das Verhalten von vor dem 2026-09-01: sofort
        #: aufgeben. Gilt NUR fuer Ausfaelle; eine schlechte Antwort wird
        #: weiterhin nur `max_attempts`-mal und ohne Pause wiederholt.
        self.retry_budget_s = retry_budget_s
        self.api_mode = api_mode
        self.api_key = api_key
        self.url = url
        self.reasoning_effort = reasoning_effort
        self.timeout = timeout
        self.post = post
        self._client = client
        if api_mode == "anthropic" and client is None:
            import anthropic

            self._client = (
                anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
            )

    def parse(self, system: str, user: str, output_model: type[T]) -> T:
        """Ein Aufruf, mit zwei verschiedenen Arten von Wiederholung.

        SCHLECHTE ANTWORT (kaputtes JSON, Schema verfehlt, Verweigerung):
        sofort noch einmal, bis `max_attempts`. Das ist das Verhalten von
        jeher -- Warten hilft hier nicht, das Modell hat ja geantwortet.

        ANBIETER WEG (HTTP 503, abgerissene Verbindung, Timeout): warten und
        weiterversuchen, bis `retry_budget_s` aufgebraucht ist. Diese zweite
        Art gibt es seit dem 2026-09-01 (Birk am Ausstellungsabend, nachdem
        Infomaniak zweimal fuer Minuten weg war). Vorher lief die Schleife
        ohne jede Pause: zwei Versuche gegen einen 503, der nach 0,1 s
        zurueckkommt, waren in 0,2 s aufgebraucht, und das Interview, das in
        dieses Fenster fiel, war verloren -- die Person haette als leere
        Scheibe an der Wand gestanden.

        Der Aufrufer entscheidet ueber `retry_budget_s`, und das ist wichtig:
        `kg.stop_intent` hat 6 Sekunden Budget im heissen Pfad einer
        laufenden Aufnahme und darf NIE warten (dort steht 0).
        """
        last_error: Exception | None = None
        frist = time.monotonic() + self.retry_budget_s
        wartend = 0        # wie oft schon wegen eines Ausfalls gewartet wurde
        antwortversuche = 0  # zaehlt nur die Versuche, die eine Antwort ergaben
        while True:
            try:
                if self.api_mode == "anthropic":
                    text = self._anthropic_text(system, user, output_model)
                else:
                    text = self._chat_completions_text(system, user, output_model)
                payload = decode_json(
                    text, repair_doubled_brace=self.api_mode == "chat_completions"
                )
                return output_model.model_validate(payload)
            except Exception as exc:  # JSONDecodeError, ValidationError, API errors, refusals
                last_error = exc
                if _ist_ausfall(exc) and time.monotonic() < frist:
                    pause = _WARTEPLAN[min(wartend, len(_WARTEPLAN) - 1)]
                    # Nie ueber die Frist hinaus schlafen: ein Budget, das erst
                    # nach dem Schlafen geprueft wird, ist keins.
                    pause = min(pause, max(0.0, frist - time.monotonic()))
                    wartend += 1
                    log.warning(
                        "llm: Anbieter nicht erreichbar (%s) — Versuch %s, "
                        "warte %.0f s (Budget noch %.0f s)",
                        exc, wartend + 1, pause, max(0.0, frist - time.monotonic()),
                    )
                    if pause > 0:
                        time.sleep(pause)
                    continue
                antwortversuche += 1
                log.warning(
                    "llm attempt %s/%s failed: %s", antwortversuche, self.max_attempts, exc
                )
                if antwortversuche >= self.max_attempts:
                    break
        raise LLMError(f"llm call failed after {self.max_attempts} attempts: {last_error}")

    def _anthropic_text(self, system: str, user: str, output_model: type[T]) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            output_config={
                "effort": self.effort,
                "format": {
                    "type": "json_schema",
                    "schema": strict_schema(output_model),
                },
            },
            messages=[{"role": "user", "content": user}],
        )
        if getattr(response, "stop_reason", None) == "refusal":
            raise LLMError("model refused the request")
        if getattr(response, "stop_reason", None) == "max_tokens":
            # A truncated answer is a failed answer, never a normal
            # one — even when the cut happens to leave syntactically
            # valid (but semantically broken) JSON behind, e.g. a
            # schema-constrained decoder closing structures early.
            # Left unchecked this used to pass json.loads silently
            # and hand a mid-word-truncated string on to the caller.
            raise LLMError("response was truncated at max_tokens")
        return next((b.text for b in response.content if getattr(b, "type", "") == "text"), "")

    def _chat_completions_text(self, system: str, user: str, output_model: type[T]) -> str:
        """Ein Request gegen einen OpenAI-kompatiblen ``chat/completions``-
        Endpunkt. ``post`` ist injizierbar, damit kein Test ins Netz geht —
        dieselbe Disziplin wie in kg.embeddings und kg2.imagegen.
        """
        if not self.api_key:
            raise LLMError(
                "no api key for the chat_completions route — set the environment "
                "variable named by llm_api_key_env"
            )
        if not self.url:
            raise LLMError("llm_url is empty — the chat_completions route needs an endpoint")

        body: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            # `system` wird zur ersten Message: dieser Modus kennt kein
            # eigenes Systemfeld. Die Anthropic-Form (`effort`) reist NICHT
            # mit — dort ist sie Pflicht, hier wäre sie ein unbekanntes Feld.
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": output_model.__name__,
                    "strict": True,
                    "schema": strict_schema(output_model),
                },
            },
        }
        if self.reasoning_effort:
            # Nur senden, wenn gesetzt: Modelle, die das Feld nicht kennen,
            # lehnen den Request sonst mit HTTP 400 ab.
            body["reasoning_effort"] = self.reasoning_effort

        payload = self.post(url=self.url, headers=self._headers(), json=body, timeout=self.timeout)

        try:
            choice = payload["choices"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"no choices in the completion response: {exc}") from exc

        finish = choice.get("finish_reason")
        if finish == "length":
            raise LLMError("response was truncated at max_tokens")
        if finish == "content_filter":
            raise LLMError("model refused the request")

        content = (choice.get("message") or {}).get("content")
        if content is None:
            # Gemessen: bei aktivem Reasoning steht der Text in
            # `message.reasoning`. Kein leeres Ergebnis, ein Fehler.
            raise LLMError(
                "the model returned content: null — set llm_reasoning_effort "
                '(measured: "none" for Kimi-K2.6)'
            )
        return content

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}


def build_llm(cfg) -> LLMClient:
    """Die eine Stelle, an der aus Tool 1s Konfiguration ein Client wird.

    Wie `kg.embeddings.build_embedder`: damit der Umbau auf einen zweiten
    Anbieter an EINER Stelle passiert und Station und Simulationslauf
    garantiert denselben Weg fahren.
    """
    return LLMClient(
        model=cfg.llm_model,
        effort=cfg.llm_effort,
        max_tokens=cfg.llm_max_tokens,
        api_key=cfg.llm_api_key,
        api_mode=cfg.llm_api_mode,
        url=cfg.llm_url,
        reasoning_effort=cfg.llm_reasoning_effort,
        retry_budget_s=getattr(cfg, "llm_retry_budget_s", 0.0),
    )
