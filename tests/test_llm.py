import json

import pytest
from pydantic import BaseModel

from kg.llm import LLMClient, LLMError, strict_schema


class Inner(BaseModel):
    label: str


class Outer(BaseModel):
    count: int
    items: list[Inner]


def test_strict_schema_hardens_every_object_including_defs():
    schema = strict_schema(Outer)

    assert schema["additionalProperties"] is False
    assert sorted(schema["required"]) == ["count", "items"]
    inner = schema["$defs"]["Inner"]
    assert inner["additionalProperties"] is False
    assert inner["required"] == ["label"]


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply

        class Block:
            type = "text"
            text = reply

        class Response:
            stop_reason = "end_turn"
            content = [Block()]

        return Response()


class FakeAnthropic:
    def __init__(self, replies):
        self.messages = FakeMessages(replies)


def test_parse_returns_a_validated_model_and_sends_the_documented_parameters():
    fake = FakeAnthropic([json.dumps({"count": 2, "items": [{"label": "a"}]})])
    client = LLMClient(model="claude-opus-5", effort="high", max_tokens=16000, client=fake)

    result = client.parse(system="S", user="U", output_model=Outer)

    assert result.count == 2 and result.items[0].label == "a"
    call = fake.messages.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["output_config"]["effort"] == "high"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["system"] == "S"
    assert "thinking" not in call
    assert "temperature" not in call


def test_invalid_json_is_retried_once_then_raises():
    fake = FakeAnthropic(["not json", "still not json"])
    client = LLMClient(
        model="claude-opus-5", effort="high", max_tokens=16000, client=fake, max_attempts=2
    )

    with pytest.raises(LLMError):
        client.parse(system="S", user="U", output_model=Outer)
    assert len(fake.messages.calls) == 2


def test_a_retry_can_succeed():
    fake = FakeAnthropic(["broken", json.dumps({"count": 1, "items": []})])
    client = LLMClient(
        model="claude-opus-5", effort="high", max_tokens=16000, client=fake, max_attempts=2
    )

    assert client.parse(system="S", user="U", output_model=Outer).count == 1


def test_a_refusal_raises_llm_error():
    class RefusingMessages:
        def create(self, **kwargs):
            class Response:
                stop_reason = "refusal"
                content = []

            return Response()

    class RefusingClient:
        messages = RefusingMessages()

    client = LLMClient(
        model="claude-opus-5", effort="high", max_tokens=16000, client=RefusingClient(), max_attempts=1
    )

    with pytest.raises(LLMError):
        client.parse(system="S", user="U", output_model=Outer)


def test_a_max_tokens_cutoff_raises_llm_error_even_with_parseable_json():
    """A `max_tokens` stop is a truncated answer, never a normal one — even
    when the cut happens to leave syntactically valid JSON behind (e.g. a
    schema-constrained decoder closing the structure early). Silently
    parsing that would let a broken value through with nothing in the log to
    explain it (docs/... truncation incident)."""

    class CutoffMessages:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1

            class Block:
                type = "text"
                text = json.dumps({"count": 1, "items": []})

            class Response:
                stop_reason = "max_tokens"
                content = [Block()]

            return Response()

    class CutoffClient:
        def __init__(self):
            self.messages = CutoffMessages()

    fake = CutoffClient()
    client = LLMClient(
        model="claude-opus-5", effort="high", max_tokens=16000, client=fake, max_attempts=1
    )

    with pytest.raises(LLMError):
        client.parse(system="S", user="U", output_model=Outer)
    assert fake.messages.calls == 1


def test_max_tokens_cutoff_is_logged_as_a_warning(caplog):
    class CutoffMessages:
        def create(self, **kwargs):
            class Block:
                type = "text"
                text = json.dumps({"count": 1, "items": []})

            class Response:
                stop_reason = "max_tokens"
                content = [Block()]

            return Response()

    class CutoffClient:
        messages = CutoffMessages()

    client = LLMClient(
        model="claude-opus-5", effort="high", max_tokens=16000, client=CutoffClient(), max_attempts=1
    )

    with caplog.at_level("WARNING"):
        with pytest.raises(LLMError):
            client.parse(system="S", user="U", output_model=Outer)

    assert "max_tokens" in caplog.text


# --- der zweite API-Modus: OpenAI-kompatibles chat/completions -------------
#
# Alle Antwortformen unten sind am 2026-08-31 gegen Infomaniak gemessen, nicht
# erfunden — insbesondere die zwei Fehlerbilder von Kimi-K2.6 (`{{` statt `{`
# und `content: null` bei aktivem Reasoning).


class FakePost:
    """Nimmt die Antworten der Reihe nach, merkt sich jeden Request."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, url, headers, json, timeout):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def chat_reply(content, finish_reason="stop"):
    return {"choices": [{"finish_reason": finish_reason, "message": {"content": content}}]}


def chat_client(replies, **kwargs):
    post = FakePost(replies)
    client = LLMClient(
        model="moonshotai/Kimi-K2.6",
        effort="high",
        max_tokens=16000,
        api_key="k",
        api_mode="chat_completions",
        url="https://example.invalid/v1/chat/completions",
        post=post,
        **kwargs,
    )
    return client, post


def test_the_default_api_mode_is_anthropic_and_never_touches_the_http_path():
    """Die unveränderte config.toml fährt weiter über den Anthropic-Client."""

    def exploding_post(**kwargs):
        raise AssertionError("der Anthropic-Pfad darf nie über HTTP gehen")

    fake = FakeAnthropic([json.dumps({"count": 1, "items": []})])
    client = LLMClient(
        model="claude-opus-5", effort="high", max_tokens=16000, client=fake, post=exploding_post
    )

    assert client.api_mode == "anthropic"
    assert client.parse(system="S", user="U", output_model=Outer).count == 1
    assert fake.messages.calls[0]["output_config"]["effort"] == "high"


def test_chat_completions_sends_the_openai_request_shape():
    client, post = chat_client([chat_reply(json.dumps({"count": 2, "items": []}))])

    result = client.parse(system="S", user="U", output_model=Outer)

    assert result.count == 2
    call = post.calls[0]
    assert call["url"] == "https://example.invalid/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer k"
    body = call["json"]
    assert body["model"] == "moonshotai/Kimi-K2.6"
    assert body["max_tokens"] == 16000
    # `system` wird zur ersten Message — der Modus kennt kein eigenes Feld dafür.
    assert body["messages"] == [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "U"},
    ]
    schema = body["response_format"]["json_schema"]
    assert body["response_format"]["type"] == "json_schema"
    assert schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    # `output_config` ist die Anthropic-Form und hat hier nichts zu suchen.
    assert "output_config" not in body


def test_chat_completions_sends_reasoning_effort_only_when_it_is_configured():
    """Gemessen am 2026-08-31: Kimi-K2.6 liefert ohne `reasoning_effort: "none"`
    0 von 5 validen JSON-Antworten, mit "none" 8 von 8. Das Feld ist deshalb
    konfigurierbar — und wird nur gesendet, wenn es gesetzt ist, weil Modelle,
    die es nicht kennen, den Request sonst mit 400 ablehnen."""
    client, post = chat_client([chat_reply(json.dumps({"count": 1, "items": []}))])
    client.parse(system="S", user="U", output_model=Outer)
    assert "reasoning_effort" not in post.calls[0]["json"]

    client, post = chat_client(
        [chat_reply(json.dumps({"count": 1, "items": []}))], reasoning_effort="none"
    )
    client.parse(system="S", user="U", output_model=Outer)
    assert post.calls[0]["json"]["reasoning_effort"] == "none"


def test_a_doubled_opening_brace_is_repaired_instead_of_wasting_the_answer():
    """Der gemessene Fehlermodus von Kimi-K2.6 (2026-08-31): HTTP 200,
    `finish_reason: "stop"`, aber der Inhalt beginnt mit `{{` statt `{` — also
    fast richtiges JSON, an dem json.loads scheitert. Ein Retry kostet eine
    zweite Antwort und kann denselben Fehler noch einmal machen; die Reparatur
    ist eine einzige Klammer und verändert nichts am Inhalt."""
    broken = "{{" + json.dumps({"count": 3, "items": []})[1:]
    client, post = chat_client([chat_reply(broken)])

    assert client.parse(system="S", user="U", output_model=Outer).count == 3
    assert len(post.calls) == 1  # kein Retry nötig


def test_a_doubled_brace_that_stays_broken_is_retried_and_then_raises():
    """Die Reparatur gilt nur, wenn sie die Ausgabe wirklich parsebar macht.
    Sonst bleibt es ein Fehlschlag und der bestehende Retry greift."""
    client, post = chat_client([chat_reply("{{ kaputt"), chat_reply("{{ immer noch kaputt")])

    with pytest.raises(LLMError):
        client.parse(system="S", user="U", output_model=Outer)
    assert len(post.calls) == 2


def test_the_anthropic_path_keeps_treating_a_doubled_brace_as_a_failure():
    """Die Reparatur ist an den neuen Modus gebunden. Der Anthropic-Pfad ist
    der, über den der Referenzlauf 19c gefahren wurde, und verhält sich Zeile
    für Zeile wie vorher — dieses Fehlerbild ist dort nie aufgetreten."""
    broken = "{{" + json.dumps({"count": 3, "items": []})[1:]
    fake = FakeAnthropic([broken, broken])
    client = LLMClient(
        model="claude-opus-5", effort="high", max_tokens=16000, client=fake, max_attempts=2
    )

    with pytest.raises(LLMError):
        client.parse(system="S", user="U", output_model=Outer)


def test_a_null_content_is_an_error_and_not_an_empty_result():
    """Bei aktivem Reasoning schreibt Kimi seinen Gedankengang nach
    `message.reasoning` und lässt `content: null` — HTTP 200, finish_reason
    "stop". Als leerer String durchgereicht würde daraus stillschweigend ein
    leeres Extraktionsergebnis, also ein Interview ohne Begriffe."""
    client, post = chat_client([chat_reply(None), chat_reply(None)])

    with pytest.raises(LLMError):
        client.parse(system="S", user="U", output_model=Outer)
    assert len(post.calls) == 2


def test_a_length_cutoff_raises_even_with_parseable_json():
    """Dasselbe Urteil wie beim Anthropic-`max_tokens`: abgeschnitten ist
    kaputt, auch wenn zufällig gültiges JSON dasteht."""
    client, _ = chat_client(
        [chat_reply(json.dumps({"count": 1, "items": []}), finish_reason="length")],
        max_attempts=1,
    )

    with pytest.raises(LLMError):
        client.parse(system="S", user="U", output_model=Outer)


def test_a_transport_failure_is_retried_like_every_other_failure():
    client, post = chat_client(
        [RuntimeError("connection reset"), chat_reply(json.dumps({"count": 7, "items": []}))]
    )

    assert client.parse(system="S", user="U", output_model=Outer).count == 7
    assert len(post.calls) == 2


def test_chat_completions_without_a_key_fails_loudly():
    client = LLMClient(
        model="m",
        effort="high",
        max_tokens=100,
        api_key=None,
        api_mode="chat_completions",
        url="u",
        post=lambda **kwargs: chat_reply("{}"),
        max_attempts=1,
    )

    with pytest.raises(LLMError, match="key"):
        client.parse(system="S", user="U", output_model=Outer)


def test_an_unknown_api_mode_is_refused_at_construction():
    """Ein Tippfehler in der config.toml darf nicht erst mitten in einem
    Interview auffallen."""
    with pytest.raises(ValueError, match="llm_api_mode"):
        LLMClient(model="m", effort="high", max_tokens=100, api_mode="openai", client=object())


# --- Wiederholen, wenn der Anbieter kurz weg ist (Birk, 2026-09-01) ---------
#
# Infomaniak war an diesem Abend ZWEIMAL fuer ein bis fuenf Minuten komplett
# weg (HTTP 503 auf allen Pfaden). Die Wiederholung, die es damals gab, lief
# ohne jede Pause: `max_attempts=2` gegen einen 503, der nach 0,1 s
# zurueckkommt, war in 0,2 s aufgebraucht. Ein Interview, das in dieses
# Fenster fiel, war verloren -- die Person haette als leere Scheibe an der
# Wand gestanden.
#
# Birk: „die retries wenn keine antwort kommt von infomaniak muessen auch in
# den script code rein. also genau wie du jetzt muss der code entsprechend oft
# neu versuchen."

import kg.llm as llm_modul


class _Antwort(BaseModel):
    ok: bool


def _client(post, **kw):
    return LLMClient(
        model="m", effort="low", max_tokens=10, api_key="k",
        api_mode="chat_completions", url="https://example.invalid/v1",
        post=post, **kw,
    )


def _gute_antwort():
    return {"choices": [{"message": {"content": '{"ok": true}'}}]}


def test_ein_kurzer_ausfall_wird_ausgesessen(monkeypatch):
    """Zwei 503 hintereinander, dann geht es wieder — das Ergebnis kommt an."""
    geschlafen = []
    monkeypatch.setattr(llm_modul.time, "sleep", geschlafen.append)

    versuche = []

    def post(url, headers, json, timeout):
        versuche.append(1)
        if len(versuche) < 3:
            raise RuntimeError("peer closed connection without sending complete message body")
        return _gute_antwort()

    ergebnis = _client(post, retry_budget_s=120.0).parse("s", "u", _Antwort)

    assert ergebnis.ok is True
    assert len(versuche) == 3
    # Und es wurde wirklich gewartet, nicht nur schnell dreimal gescheitert.
    assert geschlafen, "ohne Pause ist die Wiederholung gegen einen Ausfall wirkungslos"


def test_ohne_budget_bleibt_alles_wie_vorher(monkeypatch):
    """Der Weckwort-Pfad hat 6 s Budget und darf NICHT warten.

    Die Obergrenze im `post` steht aus demselben Grund wie in
    `test_das_budget_wird_eingehalten`, und zwar hier besonders: Bei Budget 0
    faellt die Pause auf 0 herunter, `time.sleep` wird also gar nicht erst
    aufgerufen. Ein Test, der allein am gepatchten Schlafen haengt, wuerde
    deshalb ENDLOS LAUFEN statt rot zu werden, sobald jemand die
    Fristpruefung aus der Bedingung nimmt — gemessen, nicht vermutet.
    `pytest.fail` bricht als BaseException durch das `except Exception` der
    Schleife hindurch und kommt wirklich heraus.
    """
    monkeypatch.setattr(llm_modul.time, "sleep", lambda s: pytest.fail("darf nicht schlafen"))

    versuche = []

    def post(url, headers, json, timeout):
        versuche.append(1)
        if len(versuche) > 3:
            pytest.fail("ohne Budget darf ein Ausfall nicht wiederholt werden")
        raise RuntimeError("503 Service Unavailable")

    with pytest.raises(LLMError):
        _client(post, max_attempts=1, retry_budget_s=0.0).parse("s", "u", _Antwort)

    assert len(versuche) == 1, f"max_attempts=1, aber {len(versuche)} Versuche"


def test_ein_schemafehler_wird_nicht_ausgesessen(monkeypatch):
    """Kaputtes JSON ist kein Ausfall — dagegen hilft Warten nicht, es kostet
    nur die Zeit, in der die naechste Person schon spricht."""
    geschlafen = []
    monkeypatch.setattr(llm_modul.time, "sleep", geschlafen.append)

    def post(url, headers, json, timeout):
        return {"choices": [{"message": {"content": "kein json"}}]}

    with pytest.raises(LLMError):
        _client(post, retry_budget_s=120.0).parse("s", "u", _Antwort)

    assert not geschlafen, "auf einen Schemafehler darf nicht gewartet werden"


def test_das_budget_wird_eingehalten(monkeypatch):
    """Es wird nicht ewig versucht — sonst haengt die Pipeline am toten Anbieter.

    Zum Aufbau, denn er ist hier die halbe Aussage: Die gepatchte Uhr rueckt
    bei JEDEM Ablesen ein Stueck vor, nicht erst beim Schlafen — und die Zahl
    der Versuche ist hart gedeckelt. Beides, weil dieser Test sonst als Wache
    wertlos waere: Haengt die Uhr allein am `time.sleep`, dann steht sie
    still, sobald jemand das Schlafen entfernt; das Budget liefe nie ab und
    der Test HINGE ENDLOS, statt rot zu werden. Ein Test, der bei einer
    Mutation haengt, meldet nichts — er faellt erst auf, wenn die Ausstellung
    schon laeuft. `pytest.fail` bricht dabei als BaseException durch das
    `except Exception` der Schleife hindurch, kommt also wirklich heraus.
    """
    jetzt = [0.0]

    def monotonic():
        # Schon das Ablesen der Uhr kostet Zeit. So laeuft das Budget auch
        # dann ab, wenn gar nicht geschlafen wird.
        jetzt[0] += 0.5
        return jetzt[0]

    monkeypatch.setattr(llm_modul.time, "monotonic", monotonic)
    monkeypatch.setattr(llm_modul.time, "sleep", lambda s: jetzt.__setitem__(0, jetzt[0] + s))

    versuche = []

    def post(url, headers, json, timeout):
        versuche.append(1)
        if len(versuche) > 12:
            pytest.fail(
                "es wird ewig weiterversucht: nach 12 Versuchen greift das "
                "Budget von 30 s immer noch nicht"
            )
        raise RuntimeError("peer closed connection")

    with pytest.raises(LLMError):
        _client(post, retry_budget_s=30.0).parse("s", "u", _Antwort)

    assert jetzt[0] <= 60.0, f"Budget 30 s deutlich ueberschritten: {jetzt[0]} s"
