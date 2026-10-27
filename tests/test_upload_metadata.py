from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from kg.ingest import guess
from llm.agents.document_metadata import DocumentMetadata, run
from store.repo import MemoryRepo


@pytest.mark.parametrize(("filename", "text", "document", "expected"), [
    ("upload.pdf", "Version: 13.1.3\nGültig ab: 01.01.2026", "VB-ANL1",
     {"version": "13.1.3", "valid_from": "2026-01-01"}),
    ("VB_EEL_V13.1.3_Anlage_1.pdf", "Gültig ab:\n1.1.2026", "VB-ANL1",
     {"version": "13.1.3", "valid_from": "2026-01-01"}),
    ("renamed.pdf", "in der ab\n01.01.2027 geltenden Fassung\nVersion 13.4", "VB",
     {"version": "13.4", "valid_from": "2027-01-01"}),
    ("2026_03_10_Version_13.4.pdf", "Stand: 10.03.2026", "VB", {"version": "13.4"}),
    ("upload.pdf", "Version: 13.4\nGültig ab: 31.02.2027", "VB", {"version": "13.4"}),
    ("2024_12_11_NS_FLB_Anl3.pdf", "", "RS-ANL3",
     {"version": "2024-12-11", "valid_from": "2024-12-11"}),
])
def test_guess_cover_labels_and_independent_publication_date(filename, text, document, expected):
    assert guess(filename, text, document) == expected


def test_upload_reads_cover_of_renamed_pdf_before_pipeline(kb, monkeypatch, tmp_path):
    from kg.common import ROOT

    class Pipeline:
        def __init__(self, *args):
            pass

        def run(self):
            pass

    monkeypatch.setattr(kb, "get_versions", lambda *args: [])
    monkeypatch.setattr("api.routes.specs.ingest.Pipeline", Pipeline)
    app = create_app(kb=kb, repo=MemoryRepo(), ai=False, data_root=tmp_path)
    pdf = ROOT / "sources/GG_EEL_V13.1_Anlage_1_24.03.2025.pdf"
    response = TestClient(app).post("/spec-versions", data={"document": "GG-ANL1"},
                                    files={"file": ("upload.pdf", pdf.read_bytes(), "application/pdf")})
    assert response.status_code == 202, response.text
    assert response.json()["version"] == "13.1.1"
    assert date.fromisoformat(response.json()["valid_from"]) == date(2026, 1, 1)


def test_metadata_agent_requires_cover_evidence():
    class Client:
        def structured(self, system, user, schema, tools, call, validate):
            invalid = DocumentMetadata(version="13.4", valid_from="2027-01-01", version_quote="Version 13.4",
                                       valid_from_quote="Gültig ab 01.01.2027")
            assert validate(invalid)
            valid = DocumentMetadata(version="13.4", version_quote="Version 13.4")
            assert validate(valid) is None
            return valid

    result = run(Client(), "upload.pdf", "Version 13.4\nStand: 10.03.2026")
    assert result.version == "13.4" and result.valid_from is None
