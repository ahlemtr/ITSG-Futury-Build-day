"""Test builder: recompute expectations, clones, boundary variants, test packages,
hidden variants. Everything the builder produces is a `draft` until a human approves it.
What a case's family decides (its outcome, its boundary generators, hidden variants, story) comes
from `engine/families/<id>/`.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date

import yaml
from pydantic import BaseModel, SerializeAsAny

from engine import families
from engine.expected import build_chain, get_case, load_scenario
from engine.model import Case
from engine.rules import params as params_mod
from engine.writer_messages import chain_files, write_file
from kg.interface import KnowledgeBase

# ---------------------------------------------------------------- expectations


def outcome(kb: KnowledgeBase, tc: Case, version: str) -> BaseModel:
    return families.of_case(tc).outcome(kb, tc, version)


def with_expected(kb: KnowledgeBase, tc: Case, versions: list[str] | None = None) -> Case:
    tc.expected = {v: outcome(kb, tc, v) for v in (versions or params_mod.all_versions(kb))}
    return tc


class Recomputed(BaseModel):
    id: str
    old: SerializeAsAny[BaseModel]
    new: SerializeAsAny[BaseModel]
    differs: bool


def recompute(kb: KnowledgeBase, test_cases: list[str | Case], old: str, new: str) -> list[Recomputed]:
    """Expected results under both versions; `differs` marks the ones a spec change touches."""
    out = []
    for t in test_cases:
        tc = get_case(kb, t) if isinstance(t, str) else t
        o, n = outcome(kb, tc, old), outcome(kb, tc, new)
        out.append(Recomputed(id=tc.id, old=o, new=n, differs=o != n))
    return out


# ---------------------------------------------------------------- clones and boundaries


def clone(kb: KnowledgeBase, base: str | Case, branch_point: date | None, change: dict, new_id: str | None = None,
          targets: list[str] | None = None) -> Case:
    """Copy a test case, apply `change` to its inputs, keep `parent`. Status draft, origin builder."""
    b = get_case(kb, base) if isinstance(base, str) else base
    tc = b.model_copy(deep=True)
    inputs = tc.inputs.model_dump()
    inputs.update(change)
    tc.inputs = type(tc.inputs).model_validate(inputs)
    tc.id = new_id or f"{b.id}-clone"
    tc.parent, tc.kind, tc.origin, tc.status, tc.hidden = b.id, "clone", "builder", "draft", False
    tc.steps = "single"
    tc.branch_point = branch_point
    tc.targets = targets or b.targets
    return with_expected(kb, tc)


def boundaries(kb: KnowledgeBase, rule: str, base: str | Case) -> list[Case]:
    """Threshold -1 / = / +1 variants of one rule, from the family's generators."""
    b = get_case(kb, base) if isinstance(base, str) else base
    gen = families.of_case(b).generators().get(rule)
    if gen is None:
        raise ValueError(f"no boundary generator for {rule}")
    return gen(kb, b)


def hidden(kb: KnowledgeBase, test_case: str | Case, seed: int = 0) -> Case:
    """Same rule, other dates; expected results computed by the engine, never exported."""
    b = get_case(kb, test_case) if isinstance(test_case, str) else test_case
    return families.of_case(b).hidden(kb, b, seed)


# ---------------------------------------------------------------- story and package


def story_text(tc: Case) -> str:
    """Deterministic TA-style story (inputs only). llm/story.py can replace it with an LLM story."""
    return families.of_case(tc).story(tc)


def single_step_reply(kb: KnowledgeBase, tc: Case, version: str):
    """The insurer reply for a single-step test (round 1 only), or None."""
    sc = load_scenario(kb, tc)
    ch = build_chain(sc, version, kb)
    replies = families.of_case(tc).single_step_replies(kb, sc, ch)
    return replies[0] if replies else None


def package(kb: KnowledgeBase, tc: Case, version: str, story: str | None = None) -> dict[str, str]:
    """Scenario YAML + expected TEEL0 + TEEK0 + story. Refused for hidden tests."""
    if tc.hidden:
        raise PermissionError("hidden test cases are never exported")
    sc = load_scenario(kb, tc)
    ch = build_chain(sc, version, kb)
    files = {"scenario.yaml": yaml.safe_dump(tc.model_dump(mode="json"), allow_unicode=True, sort_keys=False)}
    files.update(chain_files(ch, tc.id, kb))
    if tc.steps == "single":
        for reply in families.of_case(tc).single_step_replies(kb, sc, ch):
            files[f"TEEK0-{tc.id}-s{reply.step}-{reply.abgabegrund}"] = write_file([reply], kb)
    files["story.txt"] = story or story_text(tc)
    return files


def package_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text.encode("utf-8"))
    return buf.getvalue()


__all__ = [
    "boundaries",
    "clone",
    "hidden",
    "outcome",
    "package",
    "package_zip",
    "recompute",
    "story_text",
]
