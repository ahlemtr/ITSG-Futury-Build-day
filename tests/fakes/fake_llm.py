"""Scripted stand-in for the OpenAI transport (llm/client.py). Handlers are keyed by the name of the
output schema; each gets the message list and returns {"content": json} or {"tool_calls": [...]}."""

from __future__ import annotations

import json
from collections.abc import Callable


def content(obj) -> dict:
    return {"content": json.dumps(obj, ensure_ascii=False, default=str)}


def tool_call(name: str, args: dict, id_: str = "c1") -> dict:
    return {"tool_calls": [{"id": id_, "name": name, "arguments": json.dumps(args)}]}


def tool_results(messages: list[dict]) -> list:
    return [json.loads(m["content"]) for m in messages if m["role"] == "tool"]


def user_json(messages: list[dict]) -> dict:
    return json.loads(next(m["content"] for m in messages if m["role"] == "user"))


class ScriptedTransport:
    def __init__(self, handlers: dict[str, Callable[[list[dict]], dict]]):
        self.handlers = handlers
        self.calls: list[str] = []

    def __call__(self, messages, tools, schema, schema_name):
        self.calls.append(schema_name)
        return self.handlers[schema_name](messages)
