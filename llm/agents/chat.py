"""RAG chat assistant (HANDOUT agenda 4): answers questions about the documents from the knowledge graph.

Retrieval: chunk-level hybrid search (`search_passages`, with the matching sentence) plus graph context per
passage (the rules sourced from it, the changes that modified it, the test cases on those rules, the rules'
parameters in the versions the graph knows). The model answers with citations; code checks that every cited
passage key exists. No citation, no answer: without the model (no key, no cache) or after two invalid
answers the result is retrieval only.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel

from llm.client import LLMClient
from llm.tools import ToolBox

SYSTEM = """You are the document assistant of the ITSG review platform for DTA EEL (German income replacement
benefit messages between employers and health insurers). You answer questions about the Verfahrensbeschreibung
(VB), the Gemeinsame Grundsätze (GG), the Beispielpapier (BP), the Rundschreiben and the test catalogue.

Answer only from the retrieved context and from what the tools return. Every statement of fact must be backed by
a passage key, written inline in square brackets exactly as given, e.g. [VB@13.4#3.12.5]. Put every key you cite
in `citations` too. If the context does not answer the question, say so in one sentence and cite the closest
passage. Do not compute dates yourself: use add_months and count_days. Keep the answer short: 2 to 6 sentences
or a short list. Legal terms stay German. Answer in the language given as `language` (de = German, en = English).

Technical annexes define record structure; the VB commentary supplies business context. Preserve both sources.
M (unconditional mandatory) is the unconditional case of m (mandatory under conditions); a marker difference
alone is not a contradiction. Read the quoted conditions and block introduction before interpreting a row.
Never invent a condition or assume an unspecified condition is always true. Numeric content can specialize an
alphanumeric technical field. Compare document applicability dates, not version numbers across document families.
Use get_field_definitions for field questions, and distinguish applicable from historical/future definitions.
"""

TOOLS = ["search_passages", "get_passage", "get_rules", "get_param", "get_versions", "get_changes", "get_test_case",
         "add_months", "count_days", "get_field_definitions"]
K = 6
CITE_RE = re.compile(r"\[([A-Z0-9-]+@[^#\]\s]+#[^\]\s]+)\]")


class ChatAnswer(BaseModel):
    answer: str
    citations: list[str]
    rules: list[str] = []
    test_cases: list[str] = []


def retrieve(kb, question: str, k: int = K, version: str | None = None, on_date=None) -> list[dict]:
    """The passages that match, each with its graph neighbourhood."""
    out = []
    for p in kb.search_passages(question, k, version=version, on_date=on_date):
        sub = kb.subgraph("Passage", p.key, 1)
        rule_nodes = {n.key: n.props for n in sub.nodes if n.label == "Rule"}
        rules = sorted({e.from_key for e in sub.edges if e.type == "SOURCED_FROM" and e.from_label == "Rule"}
                       | set(rule_nodes))
        changes = sorted({e.from_key for e in sub.edges if e.type in ("MODIFIES_OLD", "MODIFIES_NEW")})
        tests = sorted({t.key for r in rules for t in kb.get_test_cases(r)})
        definitions = kb.get_field_definitions(*p.field.split(".", 1), version=version, on_date=on_date) \
            if p.field else []
        introductions = []
        for d in definitions:
            if (version is not None or on_date is not None) and not d["applicable"]:
                continue
            block_key = d["key"].split(".f", 1)[0]
            try:
                block = kb.get_passage(block_key)
                if block.key not in {b["key"] for b in introductions}:
                    introductions.append({"key": block.key, "text": block.text[:2000]})
            except KeyError:
                pass
        out.append({"key": p.key, "heading": p.heading, "snippet": p.snippet, "text": p.text[:1500],
                    "field_definitions": definitions, "block_context": introductions,
                    "rules": [{"id": r, "title": (rule_nodes.get(r) or {}).get("title")} for r in rules],
                    "changes": changes, "test_cases": tests})
    return out


def answer(client: LLMClient, tools: ToolBox, question: str, history: list[dict], language: str,
           context: list[dict], cites_ok) -> ChatAnswer:
    user = json.dumps({"language": language, "question": question,
                       "conversation": [{"role": h.get("role"), "text": str(h.get("text", ""))[:1500]}
                                        for h in history[-6:]],
                       "context": context}, ensure_ascii=False, default=str)

    def validate(o: ChatAnswer) -> str | None:
        keys = list(dict.fromkeys(o.citations + CITE_RE.findall(o.answer)))
        if err := cites_ok(keys):
            return err
        missing = []
        for key in keys:
            try:
                tools.kb.get_passage(key)
            except KeyError:
                missing.append(key)
        return f"these passage keys do not exist: {missing}" if missing else None

    out = client.structured(SYSTEM, user, ChatAnswer, tools.specs(TOOLS), tools.call, validate=validate)
    out.citations = list(dict.fromkeys(out.citations + CITE_RE.findall(out.answer)))
    return out
