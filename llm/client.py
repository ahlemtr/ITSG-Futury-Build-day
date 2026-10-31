"""OpenAI client.

- Structured Outputs: every answer is JSON validated against a Pydantic model; invalid = retry once,
  then fail.
- Function calling: the model calls our tools (`llm/tools.py`) for data and exact date math.
- Cache: every call is cached by sha256 of its input in `data/llm_cache/`, so the demo runs offline.

The transport is injectable: tests pass a scripted fake, production uses the OpenAI SDK.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)
MAX_TOOL_TURNS = 8


class LLMUnavailable(RuntimeError):
    """No API key and no cached answer."""


class LLMInvalid(RuntimeError):
    """The model returned invalid output twice."""


class Transport(Protocol):
    def __call__(self, messages: list[dict], tools: list[dict], schema: dict, schema_name: str) -> dict:
        """-> {"content": str} or {"tool_calls": [{"id", "name", "arguments": str}]}"""
        ...


class OpenAITransport:
    def __init__(self, model: str | None = None, api_key: str | None = None):
        from openai import OpenAI

        self.model = model or os.environ.get("OPENAI_MODEL") or "gpt-4.1"
        self.client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    def __call__(self, messages, tools, schema, schema_name):
        kw: dict[str, Any] = {"model": self.model, "messages": messages,
                              "response_format": {"type": "json_schema",
                                                  "json_schema": {"name": schema_name, "schema": schema,
                                                                  "strict": False}}}
        if tools:
            kw["tools"] = tools
        msg = self._create(kw).choices[0].message
        if msg.tool_calls:
            return {"tool_calls": [{"id": c.id, "name": c.function.name, "arguments": c.function.arguments}
                                   for c in msg.tool_calls]}
        return {"content": msg.content or ""}

    def _create(self, kw: dict[str, Any]):
        """Any API error becomes LLMUnavailable, so the deterministic result stands. Reasoning models
        reject function tools on chat completions unless reasoning_effort is "none": retried once."""
        import openai

        try:
            return self.client.chat.completions.create(**kw)
        except openai.BadRequestError as e:
            if "reasoning_effort" in str(e) and "reasoning_effort" not in kw:
                return self._create(kw | {"reasoning_effort": "none"})
            raise LLMUnavailable(f"OpenAI rejected the request: {e}") from e
        except openai.OpenAIError as e:
            raise LLMUnavailable(f"OpenAI call failed: {e}") from e


def _cache_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "data")) / "llm_cache"


class LLMClient:
    def __init__(self, transport: Transport | None = None, cache_dir: Path | None = None, model: str | None = None):
        self.cache_dir = cache_dir or _cache_dir()
        self.model = model or os.environ.get("OPENAI_MODEL") or "gpt-4.1"
        self._transport = transport
        self.calls = 0  # transport calls (API calls), for tests and the demo metric

    @property
    def transport(self) -> Transport:
        if self._transport is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise LLMUnavailable("OPENAI_API_KEY not set and no cached answer")
            self._transport = OpenAITransport(self.model)
        return self._transport

    def _key(self, system: str, user: str, schema: type[BaseModel], tools: list[dict]) -> str:
        blob = json.dumps({"model": self.model, "system": system, "user": user, "schema": schema.model_json_schema(),
                           "tools": [t["function"]["name"] for t in tools]}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def structured(self, system: str, user: str, schema: type[T], tools: list[dict] | None = None,
                   call_tool: Callable[[str, dict], Any] | None = None,
                   validate: Callable[[T], str | None] | None = None) -> T:
        """Ask for an answer of type `schema`. `validate` returns an error text to reject an answer
        (e.g. no citation); a rejected or unparsable answer is retried once, then LLMInvalid."""
        tools = tools or []
        key = self._key(system, user, schema, tools)
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            return schema.model_validate_json(path.read_text(encoding="utf-8"))
        messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        error = None
        for attempt in range(2):
            if error:
                messages.append({"role": "user", "content": f"Your answer was rejected: {error}. Answer again as "
                                                            f"valid JSON for the schema, with citations."})
            content = self._loop(messages, tools, call_tool, schema)
            try:
                out = schema.model_validate_json(content)
                error = validate(out) if validate else None
            except ValidationError as e:
                error = f"invalid JSON for the schema: {e.errors()[:3]}"
            if not error:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                path.write_text(out.model_dump_json(), encoding="utf-8")
                return out
            messages.append({"role": "assistant", "content": content})
        raise LLMInvalid(error)

    def _loop(self, messages: list[dict], tools: list[dict], call_tool, schema: type[BaseModel]) -> str:
        for _ in range(MAX_TOOL_TURNS):
            self.calls += 1
            r = self.transport(messages, tools, schema.model_json_schema(), schema.__name__)
            if "tool_calls" not in r:
                return r["content"]
            messages.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
                for c in r["tool_calls"]]})
            for c in r["tool_calls"]:
                try:
                    result = call_tool(c["name"], json.loads(c["arguments"] or "{}")) if call_tool else None
                except Exception as e:  # noqa: BLE001 - tool errors go back to the model as data
                    result = {"error": str(e)}
                messages.append({"role": "tool", "tool_call_id": c["id"],
                                 "content": json.dumps(result, default=str, ensure_ascii=False)})
        raise LLMInvalid("too many tool calls")
