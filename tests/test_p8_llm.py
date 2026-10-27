"""LLM services (P8) against a scripted transport. No real API call is made."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from api.main import create_app
from engine.checker import check
from engine.expected import get_case
from engine.model import AiProposal
from llm.client import LLMClient, LLMInvalid
from llm.services import AIServices
from llm.tools import ToolBox
from store.repo import MemoryRepo
from tests.fakes.fake_llm import ScriptedTransport, content, tool_call, tool_results, user_json


def ai_with(kb, handlers, tmp_path):
    t = ScriptedTransport(handlers)
    return AIServices(kb, LLMClient(transport=t, cache_dir=tmp_path / "cache")), t


# ---------------------------------------------------------------- P8.1 client, tools, cache


class ParamAnswer(BaseModel):
    value: bool


def test_tool_call_and_cache(kb, tmp_path):
    def handler(messages):
        res = tool_results(messages)
        return content({"value": res[0]}) if res else tool_call("get_param", {"name": "gap_inclusive",
                                                                              "on_date": "2027-01-01"})

    t = ScriptedTransport({"ParamAnswer": handler})
    client = LLMClient(transport=t, cache_dir=tmp_path)
    tools = ToolBox(kb)
    a = client.structured("sys", "is a gap of exactly 6 months chained on 2027-01-01?", ParamAnswer,
                          tools.specs(["get_param"]), tools.call)
    assert a.value is True and tools.log == [("get_param", {"name": "gap_inclusive", "on_date": "2027-01-01"})]
    n = client.calls
    again = client.structured("sys", "is a gap of exactly 6 months chained on 2027-01-01?", ParamAnswer,
                              tools.specs(["get_param"]), tools.call)
    assert again.value is True and client.calls == n  # second run: no API call


def test_engine_tools(kb):
    tb = ToolBox(kb)
    assert tb.call("add_months", {"date": "2025-08-31", "n": 6}) == "2026-02-28"
    assert tb.call("count_days", {"start": "2026-03-11", "end": "2026-03-20"}) == 10
    r = tb.call("expected_result", {"test_case_id": "peter-gap-exact", "version": "13.3"})
    assert r["send_41"] is False
    assert tb.call("evaluate_rule", {"rule_id": "R41-3", "test_case_id": "peter", "version": "13.4",
                                     "vendor_values": {"send_41": True, "periods": [["2026-03-01", "2026-03-03"]]}}
                   )["ok"] is False


def test_retry_once_then_fail(kb, tmp_path, seeds):
    ai, t = ai_with(kb, {"AiProposal": lambda m: content({"proposal": "likely_bug", "reasoning": "x",
                                                          "citations": [], "confidence": 0.5})}, tmp_path)
    s = seeds["s-no-contact"]
    res = check(kb, s.test_case_id, list(s.files.values()), date(2027, 1, 1), triage=ai.triage)
    assert res.deviations[0].ai_proposal is None and t.calls == ["AiProposal", "AiProposal"]


# ---------------------------------------------------------------- P8.5, P8.6 triage, advisor, precedent

TRIAGE = {"proposal": "likely_bug", "confidence": 0.7, "citations": ["BP@13.3#13.1"],
          "reasoning": "Beispielpapier 13.1 shows every 41 with MM-ANSPRECH = J and a DBAP block."}


def test_no_contact_flow(fresh_kb, tmp_path, monkeypatch):
    kb = fresh_kb
    monkeypatch.setenv("SIGNING_KEY_PATH", str(tmp_path / "key.pem"))
    ai, t = ai_with(kb, {"AiProposal": lambda m: content(TRIAGE)}, tmp_path)
    c = TestClient(create_app(kb=kb, repo=MemoryRepo(), ai=ai, data_root=tmp_path, seed=True))
    r = c.post("/check", json={"submission_id": "s-no-contact", "valid_on": "2027-01-01"}).json()
    d = r["deviations"][0]
    assert d["label"] == "unclear" and d["ai_proposal"]["proposal"] == "likely_bug"
    assert "BP@13.3#13.1" in d["ai_proposal"]["citations"] and r["resolved_by"] == {"ai_proposal": 1}
    q = c.get("/advisor/queue").json()
    c.post(f"/deviations/{q[0]['id']}/decide", json={"label": "bug", "reason": "DBAP required", "advisor": "ITSG"})
    n = len(t.calls)
    r = c.post("/check", json={"submission_id": "s-no-contact", "valid_on": "2027-01-01"}).json()
    assert r["label"] == "bug" and r["deviations"][0]["resolved_by"] == "catalogue" and len(t.calls) == n


# ---------------------------------------------------------------- P8.3, P8.4 explain and story


def test_explain(kb, tmp_path, seeds):
    good = "The 41 does not list the July period. Rule R41-3 (VB 3.12) requires going back to the first illness."
    ai, _ = ai_with(kb, {"Explanation": lambda m: content({"text": good})}, tmp_path)
    s = seeds["s-missing-july"]
    d = check(kb, s.test_case_id, list(s.files.values()), date(2027, 1, 1)).deviations[0]
    assert ai.explain(d) == good
    ai2, t = ai_with(kb, {"Explanation": lambda m: content({"text": "Something is wrong. Fix it."})},
                     tmp_path / "other")
    assert ai2.explain(d) is None and len(t.calls) == 2  # rejected twice: no rule id / section


def test_story(kb, tmp_path):
    def handler(m):
        inp = user_json(m)["inputs"]
        f = lambda x: "{2}.{1}.{0}".format(*x.split("-"))
        lines = [f"AU vom {f(a['start'])} bis {f(a['end'])}" for a in inp["priors"]]
        return content({"text": "\n".join(lines + [f"Neue AU ab {f(inp['current']['start'])}"])})

    ai, _ = ai_with(kb, {"Story": handler}, tmp_path)
    text = ai.story(get_case(kb, "peter"))
    for d in ("14.07.2025", "01.10.2025", "01.12.2025", "01.03.2026", "11.03.2026"):
        assert d in text


# ---------------------------------------------------------------- P8.7, P8.8 agents


def test_spec_update_agent(kb, tmp_path):
    def handler(m):
        if not tool_results(m):
            return tool_call("get_affected_rules", {"changes": ["VB-13.3-13.4-DBVO-chaining"]})
        ch = "VB-13.3-13.4-DBVO-chaining"
        cite = ["VB@13.4#3.12/chaining"]
        return content({"decisions": [
            {"change_key": ch, "test_case_id": "peter-gap-exact", "decision": "update_test",
             "reasoning": "expected 41 under 13.4", "citations": cite},
            {"change_key": ch, "test_case_id": "peter-gap-exact-hidden", "decision": "update_test",
             "reasoning": "month-end variant flips too", "citations": cite},
            {"change_key": ch, "test_case_id": "peter", "decision": "no_change", "reasoning": "gap under 6 months",
             "citations": cite}]})

    ai, _ = ai_with(kb, {"SpecUpdate": handler}, tmp_path)
    out = ai.spec_update("VB", "13.3", "13.4")
    dec = {d["test_case_id"]: d["decision"] for d in out["decisions"]}
    assert dec == {"peter-gap-exact": "update_test", "peter-gap-exact-hidden": "update_test", "peter": "no_change"}
    assert out["status"] == "draft"


def test_report_draft(kb, tmp_path, seeds):
    s = seeds["s-missing-july"]
    res = check(kb, s.test_case_id, list(s.files.values()), date(2027, 1, 1))

    def handler(m):
        devs = user_json(m)["deviations"]
        return content({"items": [{"deviation_id": d["id"], "citations": ["VB@13.4#3.12/chaining"],
                                   "text": f"Rule {d['rule']}: the period {d['expected']} is missing."}
                                  for d in devs]})

    ai, _ = ai_with(kb, {"ReportDraft": handler}, tmp_path)
    out = ai.report_draft(res)
    assert out["status"] == "draft" and "R41-3" in out["items"][0]["text"]
    assert out["items"][0]["citations"] == ["VB@13.4#3.12/chaining"]


# ---------------------------------------------------------------- P8.2 requirements to criteria

CRIT = {"R41-1": "f41c7278", "R41-2": "0cefe80e", "R41-3": "aade0289", "R41-4": "9c8c9b58"}


def _quote(kb, key, start):
    t = kb.get_passage(key).text
    i = t.index(start)
    return t[i:i + 120]


def criteria_handlers(kb, drafts, reviews=None, calls=None):
    def find(m):
        if not tool_results(m):
            return tool_call("get_passage", {"key": "VB@13.4#3.12/conditions"})
        return content({"sentences": [
            {"passage_key": "VB@13.4#3.12/conditions", "quote": _quote(kb, "VB@13.4#3.12/conditions", "dem Arbeit")},
            {"passage_key": "VB@13.4#3.12/conditions", "quote": _quote(kb, "VB@13.4#3.12/conditions", "zusätzlich")},
            {"passage_key": "VB@13.4#3.12/chaining", "quote": _quote(kb, "VB@13.4#3.12/chaining", "Dies bedeutet")},
            {"passage_key": "VB@13.4#3.12/conditions", "quote": _quote(kb, "VB@13.4#3.12/conditions", "die kumul")},
        ]})

    def review(m):
        if calls is not None:
            calls.append(user_json(m))
        return content({"reviews": reviews or []})

    return {"Found": find, "Translated": lambda m: content({"drafts": drafts}), "Reviewed": review}


def _draft(rule, params, text=None, cites=("VB@13.4#3.12/conditions",)):
    return {"text": text or f"The system ensures {rule}", "applies_to": "41", "condition": "",
            "params": [{"name": k, "value": v} for k, v in params.items()], "maps_to_rule": rule,
            "citations": list(cites)}


GOOD = [_draft("R41-1", {}), _draft("R41-2", {"gap_months": 6, "gap_inclusive": True}),
        _draft("R41-3", {"gap_months": 6}, cites=["VB@13.4#3.12/chaining"]),
        _draft("R41-4", {"min_total_days": 30, "sum_window_months": 12})]


def test_criteria_all_found_exact_no_review_call(kb, tmp_path):
    calls = []
    ai, t = ai_with(kb, criteria_handlers(kb, GOOD, calls=calls), tmp_path)
    res = ai.criteria("VB", "13.4", "3.12")
    assert res.score.exact == 4 and res.score.missing == 0 and res.score.params_correct == 4
    assert {m.criterion[:8] for m in res.score.matches} == set(CRIT.values())
    assert "Reviewed" not in t.calls and calls == []
    ids = {tc.id for tc in res.test_cases}
    assert {"peter-gap-in", "peter-gap-exact", "peter-gap-out"} <= ids and "peter-b30" in ids
    n = len(t.calls)
    ai.criteria("VB", "13.4", "3.12")
    assert len(t.calls) == n  # cached


def test_criteria_wrong_value(kb, tmp_path):
    bad = [GOOD[0], _draft("R41-2", {"gap_months": 5}), GOOD[2], GOOD[3]]
    ai, t = ai_with(kb, criteria_handlers(kb, bad), tmp_path)
    res = ai.criteria("VB", "13.4", "3.12")
    m = {x.rule: x for x in res.score.matches}
    assert m["R41-2"].found and m["R41-2"].params_ok is False and res.score.params_correct == 3
    assert "Reviewed" not in t.calls  # a wrong value is never sent to the AI to be turned into a match


def test_criteria_merged_and_new_valid(kb, tmp_path):
    merged = _draft(None, {"gap_months": 6}, "AU periods chain while each gap is at most 6 months, back to the "
                                             "first illness", cites=["VB@13.4#3.12/chaining"])
    openend = _draft(None, {"open_end_days": 7}, "An open-ended AU counts one week from the report date")
    drafts = [GOOD[0], merged, GOOD[3], openend]

    def review(m):
        ds = user_json(m)["drafts"]
        assert sorted(user_json(m)["unfound_itsg_criteria"]) == ["R41-2", "R41-3"]
        return content({"reviews": [
            {"draft_id": ds[0]["id"], "proposal": "equivalent", "rules": ["R41-2", "R41-3"], "confidence": 0.8,
             "reasoning": "merges the gap and chaining criteria", "citations": ["VB@13.4#3.12/chaining"]},
            {"draft_id": ds[1]["id"], "proposal": "new_valid", "rules": ["R41-6"], "confidence": 0.7,
             "reasoning": "open end rule, no ITSG criterion", "citations": ["VB@13.4#3.12/conditions"]}]})

    h = criteria_handlers(kb, drafts)
    h["Reviewed"] = review
    ai, _ = ai_with(kb, h, tmp_path)
    res = ai.criteria("VB", "13.4", "3.12")
    assert res.score.exact == 2 and res.score.ai_proposed == 2 and res.score.new_requirements == 1
    assert [r.proposal for r in res.reviews] == ["equivalent", "new_valid"]


def test_criteria_draft_without_citation_rejected(kb, tmp_path):
    nocite = [dict(GOOD[0], citations=[])] + GOOD[1:]
    ai, t = ai_with(kb, criteria_handlers(kb, nocite), tmp_path)
    with pytest.raises(LLMInvalid):
        ai.criteria("VB", "13.4", "3.12")
    assert t.calls.count("Translated") == 2  # retried once, then failed


def test_criteria_endpoint(fresh_kb, tmp_path):
    kb = fresh_kb
    ai, _ = ai_with(kb, criteria_handlers(kb, GOOD), tmp_path)
    c = TestClient(create_app(kb=kb, repo=MemoryRepo(), ai=ai, data_root=tmp_path))
    r = c.post("/criteria/extract", json={"document": "VB", "version": "13.4", "section": "3.12"}).json()
    assert r["score"]["exact"] == 4 and "4 exact" in r["score"]["summary"]
    cid = r["drafts"][0]["id"]
    assert c.post(f"/criteria/{cid}/approve", json={"approver": "ITSG", "decision": "approved"}).json()["status"] == \
        "approved"


def test_triage_proposal_model():
    AiProposal(proposal="unclear", reasoning="r", citations=["VB@13.4#3.12"], confidence=0.1)


def _bad_request(text):
    import httpx
    import openai

    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return openai.BadRequestError(text, response=httpx.Response(400, request=req), body=None)


class _StubCompletions:
    def __init__(self, errors):
        self.errors, self.calls = list(errors), []

    def create(self, **kw):
        from types import SimpleNamespace

        self.calls.append(kw)
        if self.errors:
            raise self.errors.pop(0)
        msg = SimpleNamespace(tool_calls=None, content='{"ok": true}')
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _transport(errors):
    from types import SimpleNamespace

    from llm.client import OpenAITransport

    t = OpenAITransport.__new__(OpenAITransport)
    t.model, t.client = "m", SimpleNamespace(chat=SimpleNamespace(completions=_StubCompletions(errors)))
    return t, t.client.chat.completions


def test_transport_retries_tools_without_reasoning():
    t, stub = _transport([_bad_request("Function tools with reasoning_effort are not supported")])
    assert t([], [{"type": "function"}], {}, "x") == {"content": '{"ok": true}'}
    assert stub.calls[1]["reasoning_effort"] == "none"


def test_transport_api_error_degrades():
    from llm.client import LLMUnavailable

    t, _ = _transport([_bad_request("model not found")])
    with pytest.raises(LLMUnavailable):
        t([], [], {}, "x")


# ---------------------------------------------------------------- chat assistant (HANDOUT agenda 4)


def test_chat_retrieval_has_graph_context(kb):
    from llm.agents import chat

    ctx = chat.retrieve(kb, "Lücke von genau 6 Monaten zwischen zwei Arbeitsunfähigkeiten")
    assert ctx and all({"key", "snippet", "rules", "changes", "test_cases"} <= set(c) for c in ctx)
    assert any(c["rules"] for c in ctx)


def test_chat_answer_must_cite_real_passages(kb, tmp_path):
    from llm.agents import chat

    real = chat.retrieve(kb, "Vorerkrankung 41")[0]["key"]
    seen = []

    def handler(messages):
        seen.append(user_json(messages)["question"] if not seen else None)
        rejected = any(m["role"] == "user" and "rejected" in str(m["content"]) for m in messages)
        if not rejected:  # first try cites a passage that does not exist
            return content({"answer": "Siehe [VB@13.3#99.99].", "citations": ["VB@13.3#99.99"]})
        return content({"answer": f"Die 41 fragt Vorerkrankungen ab [{real}].", "citations": []})

    ai, _ = ai_with(kb, {"ChatAnswer": handler}, tmp_path)
    out = ai.chat("Wozu dient die 41?", [], "de", chat.retrieve(kb, "Wozu dient die 41?"))
    assert out is not None and out.citations == [real] and seen[0] == "Wozu dient die 41?"


def test_chat_api_without_ai_returns_sources_only(fresh_kb, tmp_path):
    client = TestClient(create_app(kb=fresh_kb, repo=MemoryRepo(), ai=False, data_root=tmp_path))
    r = client.post("/chat", json={"question": "Wann endet die Entgeltfortzahlung?"}).json()
    assert r["answer"] is None and r["citations"] == [] and r["context"]
