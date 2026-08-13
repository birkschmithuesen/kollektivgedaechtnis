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
