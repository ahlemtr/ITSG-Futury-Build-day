"""Intake: store the uploaded files with SHA-256, parse them, return a receipt
like eVpT's processing confirmation: accepted, or rejected with the format issues."""

from __future__ import annotations

import os
import uuid
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from engine.records import parse_file
from engine.signing import sha256
from kg.interface import KnowledgeBase
from store.repo import Submission, SubmissionFile


class FileReceipt(BaseModel):
    name: str
    sha256: str
    messages: list[str]  # Abgabegruende found
    issues: list[dict]


class Receipt(BaseModel):
    submission_id: str
    status: str  # accepted / rejected
    files: list[FileReceipt]
    issues: list[dict]


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "data"))


def receive(kb: KnowledgeBase, repo, files: dict[str, bytes], test_case_id: str, valid_on: date | None = None,
            vendor: str | None = None, submission_id: str | None = None, content: str | None = None,
            root: Path | None = None) -> Receipt:
    sid = submission_id or f"sub-{uuid.uuid4().hex[:12]}"
    folder = (root or data_dir()) / "submissions" / sid
    folder.mkdir(parents=True, exist_ok=True)
    receipts, stored, all_issues = [], [], []
    product = None
    for name, data in files.items():
        safe = Path(name).name or "upload"
        path = folder / safe
        path.write_bytes(data)
        pf = parse_file(data, kb)
        issues = [i.model_dump() | {"file": safe} for i in pf.issues]
        all_issues += issues
        product = product or next((m.get("DSLW.PRODUKT-IDENTIFIER") for m in pf.messages), None)
        receipts.append(FileReceipt(name=safe, sha256=sha256(data), messages=[m.abgabegrund for m in pf.messages],
                                    issues=issues))
        stored.append(SubmissionFile(name=safe, path=str(path), sha256=sha256(data)))
    status = "rejected" if all_issues else "accepted"
    repo.add_submission(Submission(id=sid, test_case_id=test_case_id, vendor=vendor, product_id=product,
                                   valid_on=valid_on, status=status, files=stored, issues=all_issues,
                                   content=content))
    return Receipt(submission_id=sid, status=status, files=receipts, issues=all_issues)


def load_files(sub: Submission) -> dict[str, bytes]:
    return {f.name: Path(f.path).read_bytes() for f in sub.files}
