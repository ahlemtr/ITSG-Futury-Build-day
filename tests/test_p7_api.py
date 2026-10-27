"""One httpx test per endpoint against seeded data (P7.4). LLM services off (ai=False)."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from store.repo import MemoryRepo


@pytest.fixture
def client(fresh_kb, tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNING_KEY_PATH", str(tmp_path / "key.pem"))
    app = create_app(kb=fresh_kb, repo=MemoryRepo(), ai=False, data_root=tmp_path, seed=True)
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_seed_counts(client):
    tcs = client.get("/test-cases").json()
    assert len(tcs) == 18 and len([t for t in tcs if not t["hidden"]]) == 16  # incl. ta-167, ta-168
    assert len(client.get("/submissions").json()) == 10
    assert [v["version"] for v in client.get("/versions").json()] == ["13.3", "13.4"]


def test_parse(client, itsg_bytes):
    r = client.post("/parse", files={"file": ("TEEL0", itsg_bytes)}).json()
    assert r["issues"] == [] and r["records"][2]["fields"]["DBVO.AU-AB-AG"] == "2026-03-11"


def test_rules(client):
    r = client.get("/rules", params={"version": "13.4"}).json()
    assert r["params"]["gap_inclusive"] is True and any(x["id"] == "R41-2" for x in r["rules"])


def test_test_case_and_expected(client):
    r = client.get("/test-cases/peter-gap-exact").json()
    assert r["chains"]["13.3"] == [] and r["chains"]["13.4"][0]["abgabegrund"] == "41"
    e = client.get("/test-cases/peter/expected", params={"version": "13.4"}).json()
    assert len(e["messages"]) == 7
    assert client.get("/test-cases/peter-gap-exact-hidden/expected", params={"version": "13.4"}).status_code == 403


def test_check_by_submission_and_by_files(client):
    r = client.post("/check", json={"submission_id": "s-legacy-1", "valid_on": "2026-11-01"}).json()
    assert r["label"] == "exact_match" and r["version"] == "13.3"
    r = client.post("/check", json={"submission_id": "s-legacy-1", "valid_on": "2027-01-01"}).json()
    assert r["label"] == "bug" and r["deviations"][0]["rule"] == "R41-2"
    r = client.post("/check", json={"test_case_id": "peter-gap-exact", "valid_on": "2027-01-01", "files": []}).json()
    assert r["label"] == "bug"


def test_intake(client, itsg_bytes):
    ok = client.post("/submissions", data={"test_case_id": "peter", "valid_on": "2027-01-01", "vendor": "acme"},
                     files=[("files", ("TEEL0-r1", itsg_bytes))]).json()
    assert ok["status"] == "accepted" and ok["files"][0]["messages"] == ["41"]
    text = itsg_bytes.decode()
    i = text.index("DBVO1") + 6
    bad = client.post("/submissions", data={"test_case_id": "peter"},
                      files=[("files", ("bad", (text[:i] + "X" + text[i + 1:]).encode()))]).json()
    assert bad["status"] == "rejected" and bad["issues"][0]["field"] == "AU-AB-AG"
    r = client.post("/check", json={"submission_id": ok["submission_id"], "valid_on": "2027-01-01"}).json()
    assert r["expected_messages"] == 4 and r["actual_messages"] == 1


def test_diff_view(client):
    r = client.get("/submissions/s-variant/diff", params={"valid_on": "2027-01-01"}).json()
    assert r["label"] == "exact_match" and r["labeled_deviations"] == 0 and r["plain_diff_count"] > 0
    r = client.get("/submissions/s-missing-july/diff", params={"valid_on": "2027-01-01"}).json()
    assert r["by_label"] == {"bug": 1}


def test_advisor_queue_and_decide(client):
    client.post("/check", json={"submission_id": "s-no-contact", "valid_on": "2027-01-01"})
    q = client.get("/advisor/queue").json()
    assert len(q) == 1 and q[0]["signature"] == "41|DSLW.MM-ANSPRECH|missing_block"
    r = client.post(f"/deviations/{q[0]['id']}/decide",
                    json={"label": "bug", "reason": "every 41 in BP 13.1 carries DBAP", "advisor": "ITSG"}).json()
    assert r["precedent"]["key"] == "41|DSLW.MM-ANSPRECH|missing_block"
    assert client.get("/advisor/queue").json() == []
    r = client.post("/check", json={"submission_id": "s-no-contact", "valid_on": "2027-01-01"}).json()
    assert r["label"] == "bug" and r["deviations"][0]["precedent_key"]


def test_runs(client):
    run = client.post("/runs", json={"test_case_id": "peter", "valid_on": "2027-01-01"}).json()
    assert run["rounds"] == 4 and "11.03.2026" in run["story"]
    sub = client.get("/submissions/s-itsg-ref/diff")  # files of the reference submission
    assert sub.status_code == 200
    r = client.post(f"/runs/{run['run_id']}/submit", files=[]).json()
    assert r["ended"] and r["status"] == "failed"
    v = client.get(f"/runs/{run['run_id']}/verdict").json()
    assert v["status"] == "failed"


def test_report(client):
    signed = client.get("/submissions/s-missing-july/report").json()
    assert signed["report"]["label"] == "bug" and signed["signature"]["algorithm"] == "Ed25519"
    assert client.post("/reports/verify", content=json.dumps(signed)).json() == {"valid": True}
    html = client.get("/submissions/s-missing-july/report", params={"format": "html"}).text
    assert "R41-3" in html
    assert "exact_match" in client.get("/submissions/s-itsg-ref/report", params={"format": "html"}).text


def test_specdiff(client):
    r = client.post("/specdiff", json={"document": "VB", "old_version": "13.3", "new_version": "13.4"}).json()
    assert sorted(r["recompute"]) == ["R41-2", "R41-3"]
    assert sorted(r["changed_tests"]) == ["peter-gap-exact", "peter-gap-exact-hidden"]


def test_builder_and_approve(client):
    b = client.post("/builder/boundaries", json={"rule_id": "R41-2", "base_test_case_id": "peter"}).json()
    assert [t["id"] for t in b] == ["peter-gap-in", "peter-gap-exact", "peter-gap-out"]
    c = client.post("/builder/clone", json={"base_id": "peter", "change": {"report_date": "2026-03-12"},
                                            "new_id": "peter-late"}).json()
    assert c["status"] == "draft" and c["parent"] == "peter"
    a = client.post("/test-cases/peter-late/approve", json={"approver": "ITSG", "decision": "approved"}).json()
    assert a["status"] == "approved"
    h = client.post("/builder/hidden", json={"test_case_id": "peter-gap-exact", "seed": 0}).json()
    assert h == {"id": "peter-gap-exact-hidden", "hidden": True, "parent": "peter-gap-exact", "status": "draft"}


def test_package(client):
    r = client.get("/test-cases/peter-gap-exact/package", params={"version": "13.4"})
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "story.txt" in names and "TEEL0-peter-gap-exact-r1" in names
    assert client.get("/test-cases/peter-gap-exact-hidden/package").status_code == 403


def test_passages_and_graph(client):
    p = client.get("/passages/VB/13.4/3.12/chaining").json()
    assert "nicht mehr als 6 Monate" in p["text"]
    assert any(x["key"].startswith("VB@") for x in client.get("/passages/search", params={"q": "Vorerkrankung"}).json())
    g = client.get("/graph/subgraph", params={"label": "Rule", "key": "R41-2"}).json()
    assert any(e["type"] == "SOURCED_FROM" for e in g["edges"])


def test_criteria_needs_llm(client):
    assert client.post("/criteria/extract", json={"version": "13.4", "section": "3.12"}).status_code == 503


def test_overview(client):
    o = client.get("/overview", params={"today": "2026-10-27"}).json()
    assert o["checksNow"]["ruleSet"] == "13.3" and o["checksNow"]["validUntil"] == "2026-12-31"
    assert o["checksNow"]["submissions"] == 10 and o["checksNow"]["withOpenDeviations"] == 1
    assert o["nextYear"]["ruleSet"] == "13.4" and o["nextYear"]["specChangesInScope"] > 0
    assert o["nextYear"]["testsToReapprove"] == 2
    assert o["resolution"]["waitingForAdvisor"] == 1


def test_seed_is_checked(client):
    subs = {s["id"]: s for s in client.get("/submissions").json()}
    assert subs["s-missing-july"]["label"] == "bug" and subs["s-three-periods"]["label"] == "correct_variant"
    assert subs["s-no-contact"]["vendor"] == "Abrechnung Süd Demo"


def test_run_rounds_store_submissions(client, itsg_bytes):
    run = client.post("/runs", json={"test_case_id": "peter", "valid_on": "2027-01-01", "vendor": "Lohnwerk"}).json()
    assert run["plan"][0] == {"round": 1, "expects": ["41"], "replies": ["61"]} and run["status"] == "open"
    text = itsg_bytes.decode()
    i = text.index("DBVO1") + 6
    bad = client.post(f"/runs/{run['run_id']}/submit", files=[("files", ("bad", (text[:i] + "X" + text[i + 1:]).encode()))])
    assert bad.json()["rejected"] and client.get(f"/runs/{run['run_id']}").json()["round"] == 0
    r = client.post(f"/runs/{run['run_id']}/submit", files=[("files", ("TEEL0-r1", itsg_bytes))]).json()
    assert r["receipt"]["status"] == "accepted" and r["reply_name"] and r["reply"].count("DSLW") == 1
    sid = r["receipt"]["submission_id"]
    sub = next(s for s in client.get("/submissions").json() if s["id"] == sid)
    assert sub["vendor"] == "Lohnwerk" and sub["label"] == "exact_match"
    again = client.get(f"/runs/{run['run_id']}").json()
    assert again["round"] == 1 and again["results"][0]["reply"] == r["reply"]


def test_hidden_run_shows_no_values(client, itsg_bytes):
    run = client.post("/runs", json={"test_case_id": "peter-gap-exact-hidden", "valid_on": "2027-01-01"}).json()
    assert all(set(p) == {"round"} for p in run["plan"])
    r = client.post(f"/runs/{run['run_id']}/submit", files=[]).json()
    assert "reply" not in r and all(set(o) == {"rule", "outcome"} for o in r["outcomes"])


def test_report_list(client):
    before = {r["submission_id"]: r for r in client.get("/reports").json()}
    assert before["s-missing-july"]["signed"] is None and before["s-missing-july"]["label"] == "bug"
    client.get("/submissions/s-missing-july/report")
    after = {r["submission_id"]: r for r in client.get("/reports", params={"vendor": "Gehalt 24 Demo"}).json()}
    assert after["s-missing-july"]["signed"] and "s-variant" not in after


def test_test_cases_flag_result_changes(client):
    tcs = {t["id"]: t for t in client.get("/test-cases").json()}
    assert tcs["peter-gap-exact"]["result_changes"] == ["13.4"] and tcs["peter"]["result_changes"] == []


def test_kg_stats_and_ask(client):
    s = client.get("/kg/stats").json()
    assert s["nodes"]["Passage"] > 500 and s["nodes"]["Chunk"] >= s["nodes"]["Passage"] and "VB@13.4" in s["versions"]
    r = client.get("/kg/ask", params={"q": "Vorerkrankung 6 Monate"}).json()["results"]
    chaining = next(x for x in r if x["passage"]["key"].endswith("#3.12/chaining"))
    assert "R41-2" in chaining["rules"] and "peter-gap-exact" in chaining["tests"] and chaining["passage"]["snippet"]
