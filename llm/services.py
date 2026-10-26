"""One facade over the LLM services, used by the API. Every method degrades gracefully: when the
model is unavailable (no key, no cache) or answers invalidly twice, it returns None and the
deterministic result stands."""

from __future__ import annotations

import logging
import re

from engine.criteria import run_pipeline
from engine.model import Case, CheckResult, CriterionReview, Deviation
from kg.interface import KnowledgeBase
from llm import explain as explain_mod
from llm import story as story_mod
from llm.agents import check as check_agent
from llm.agents import spec_update
from llm.client import LLMClient, LLMInvalid, LLMUnavailable
from llm.extract import LLMExtractor
from llm.tools import ToolBox

log = logging.getLogger(__name__)
KEY_RE = re.compile(r"^[A-Z0-9-]+@[^#]+#.+$")


class AIServices:
    def __init__(self, kb: KnowledgeBase, client: LLMClient | None = None, repo=None):
        self.kb = kb
        self.client = client or LLMClient()
        self.tools = ToolBox(kb, repo)

    def cites_ok(self, citations: list[str]) -> str | None:
        """At least one citation, each a well-formed passage key, at least one the KB resolves."""
        if not citations:
            return "no citation"
        bad = [c for c in citations if not KEY_RE.match(c)]
        if bad:
            return f"not passage keys: {bad}"
        for c in citations:
            try:
                self.kb.get_passage(c)
                return None
            except KeyError:
                continue
        return f"no cited passage exists: {citations}"

    def _safe(self, fn, *args):
        try:
            return fn(*args)
        except (LLMUnavailable, LLMInvalid) as e:
            log.info("LLM skipped: %s", e)
            return None

    # P8.5: proposal for an unclear deviation; never a final label
    def triage(self, d: Deviation, version: str) -> None:
        prop = self._safe(check_agent.triage, self.client, self.tools, d, version, self.cites_ok)
        if prop is not None:
            d.ai_proposal = prop
            d.resolved_by = "ai_proposal"

    # P8.3
    def explain(self, d: Deviation) -> str | None:
        passage = None
        for k in d.sources:
            try:
                passage = self.kb.get_passage(k)
                break
            except KeyError:
                continue
        return self._safe(explain_mod.explain, self.client, d, passage)

    # P8.4
    def story(self, tc: Case) -> str | None:
        return self._safe(story_mod.story, self.client, tc)

    # P8.7
    def spec_update(self, document: str, old: str, new: str) -> dict | None:
        out = self._safe(spec_update.run, self.client, self.tools, document, old, new, self.cites_ok)
        return out.model_dump() if out else None

    # P8.8
    def report_draft(self, res: CheckResult) -> dict | None:
        out = self._safe(check_agent.report_draft, self.client, self.tools, res, self.cites_ok)
        return out.model_dump() if out else None

    # P8.2
    def criteria(self, document: str, version: str, section: str, decided: dict[str, CriterionReview] | None = None):
        ex = LLMExtractor(self.client, self.tools, self.cites_ok)
        return run_pipeline(self.kb, ex, document, version, section, decided)


def get_ai(kb: KnowledgeBase, repo=None) -> AIServices:
    return AIServices(kb, LLMClient(), repo)
