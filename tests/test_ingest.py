"""Spec upload pipeline (SPEC_UPDATE_WORKFLOW.md W2): starting point VB 13.3, upload of the real VB 13.4 PDF."""

from datetime import date
from pathlib import Path

import pytest

from engine.model import Case
from kg import ingest
from kg.common import ROOT
from llm.agents.change_analysis import ChangeAnalysis, ParamChange
from store.repo import MemoryRepo

VB_13_4 = ROOT / "sources" / "2026_03_10_Endfassung_Verfahrensbeschreibung_DTA_EEL_Version_13.4_ab_01.01.2027.pdf"


class ScriptedAI:
    """Answers like the change-analysis agent: the 3.12 wording change makes a gap of exactly 6 months chain."""

    def __init__(self):
        self.calls = 0

    def analyse_change(self, change, rules, params):
        self.calls += 1
        if "nicht mindestens 6 Monate" in (change["old_text"] or "") and "gap_inclusive" in params:
            return ChangeAnalysis(summary="nicht mindestens -> nicht mehr als 6 Monate", label="law_change",
                                  in_scope=True, citations=change["new_passages"],
                                  param_changes=[ParamChange(name="gap_inclusive", new_value=True,
                                                             reason="a gap of exactly 6 months now chains")])
        return None


@pytest.fixture
def baseline(tmp_path, monkeypatch):
    monkeypatch.setenv("SPEC_BASELINE", "VB@13.3")
    monkeypatch.setenv("KG_BACKEND", "yaml")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PRECEDENTS_PATH", str(tmp_path / "precedents.yaml"))
    from kg import get_kb
    from store.seed import seed

    kb = get_kb()
    repo = MemoryRepo()
    seed(kb, repo, root=tmp_path, check=False)
    return kb, repo


def test_guess_reads_version_and_date():
    assert ingest.guess(VB_13_4.name) == {"version": "13.4", "valid_from": "2027-01-01"}


@pytest.mark.skipif(not VB_13_4.exists(), reason="VB 13.4 PDF missing")
def test_upload_vb_13_4(baseline):
    kb, repo = baseline
    assert [v.version for v in kb.get_versions("VB")] == ["13.3"]
    assert [t.id for t in repo.list_test_cases()] == ["peter"]
    job = ingest.new_job(repo, "VB", "13.4", date(2027, 1, 1), VB_13_4.name, "x")
    ai = ScriptedAI()
    seen = []
    job = ingest.Pipeline(job, VB_13_4, kb, repo, lambda staged: ai, seen.append, today=date(2026, 10, 27)).run()
    assert job["status"] == "done", job.get("trace")
    assert all(s["status"] == "done" for s in job["stages"])
    stages = {s["name"]: s["counts"] for s in job["stages"]}
    assert stages["chunk"]["passages"] > 100 and stages["diff"]["changes"] > 10
    assert stages["map"]["candidates"] >= 1 and ai.calls == stages["map"]["candidates"]
    new = seen[-1]
    assert [v.version for v in new.get_versions("VB")] == ["13.3", "13.4"]
    assert new.get_param("gap_inclusive", version="13.3") is False
    assert new.get_param("gap_inclusive", version="13.4") is True
    assert new.get_param("gap_months", version="13.4") == 6  # carried over
    assert "nicht mehr als 6 Monate" in new.get_passage("VB@13.4#3.12/chaining").text
    curated = [c for c in new.get_changes("VB", "13.3", "13.4") if c.summary]
    assert any("gap_inclusive" in c.changes_param for c in curated)
    result = job["result"]
    assert result["track"] == "next" and result["rules"] == ["R41-2", "R41-3"]
    assert "peter-gap-exact" in result["drafts"] and "peter-gap-exact-hidden" in result["drafts"]
    exact = repo.get_test_case("peter-gap-exact")
    assert isinstance(exact, Case) and exact.status == "draft"
    assert repo.list_events()[0]["parameters_changed"] == ["gap_inclusive"]
    graph_tests = {t.key for t in seen[-1].get_test_cases("R41-2", include_hidden=True)}
    assert {"peter-gap-exact", "peter-gap-exact-hidden"} <= graph_tests  # the graph grew with the new tests


def test_upload_rejects_a_known_version(baseline):
    kb, repo = baseline
    job = ingest.new_job(repo, "VB", "13.3", date(2026, 1, 1), "x.pdf", "x")
    job = ingest.Pipeline(job, Path(VB_13_4), kb, repo, None, lambda k: None).run()
    assert job["status"] == "failed" and "already known" in job["error"]


@pytest.mark.skipif(not VB_13_4.exists(), reason="VB 13.4 PDF missing")
def test_version_valid_now_rechecks_submissions(baseline, tmp_path):
    """A version valid today changes the rule set in force: open submissions are checked again under it."""
    kb, repo = baseline
    from engine.intake import receive

    sub = receive(kb, repo, {"TEEL0-r1": (ROOT / "fixtures" / "itsg" / "TEEL0-Test1-DBVO").read_bytes()}, "peter",
                  valid_on=date(2027, 1, 1), vendor="Lohnwerk", root=tmp_path)
    job = ingest.new_job(repo, "VB", "13.4", date(2027, 1, 1), VB_13_4.name, "x")
    seen = []
    job = ingest.Pipeline(job, VB_13_4, kb, repo, lambda staged: ScriptedAI(), seen.append,
                          today=date(2027, 2, 1)).run()
    assert job["status"] == "done", job.get("trace")
    assert job["result"]["track"] == "now" and job["result"]["rechecked"] == 1
    assert repo.get_check(sub.submission_id).version == "13.4"
