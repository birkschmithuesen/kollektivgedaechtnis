"""Anthropic wrapper. Deterministic pipeline step, not an agent (spec 2)."""

from __future__ import annotations

import json
import logging
from typing import TypeVar

from pydantic import BaseModel

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


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


class LLMClient:
    def __init__(
        self,
        model: str,
        effort: str,
        max_tokens: int,
        api_key: str | None = None,
        client=None,
        max_attempts: int = 2,
    ) -> None:
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.max_attempts = max_attempts
        if client is not None:
            self._client = client
        else:
            import anthropic

            self._client = (
                anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
            )

    def parse(self, system: str, user: str, output_model: type[T]) -> T:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
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
                text = next(
                    (b.text for b in response.content if getattr(b, "type", "") == "text"), ""
                )
                return output_model.model_validate(json.loads(text))
            except Exception as exc:  # JSONDecodeError, ValidationError, API errors, refusals
                last_error = exc
                log.warning("llm attempt %s/%s failed: %s", attempt, self.max_attempts, exc)
        raise LLMError(f"llm call failed after {self.max_attempts} attempts: {last_error}")
