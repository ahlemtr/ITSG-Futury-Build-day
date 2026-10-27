"""Spec diff (P5.1): port of plan/starter/tools/specdiff.py.

Line diff of two pdftotext outputs. Page footers, running headers and table-of-contents lines are
ignored (TOC page numbers shift between versions and are not changes). Each change is attributed
to its data block (section heading "3.x Datenbaustein DBxx") and field (layout row).
"""

from __future__ import annotations

import difflib
import re
import shutil
import subprocess
from pathlib import Path

from engine.model import Change
from kg.interface import KnowledgeBase

SEC_RE = re.compile(r"^\s*(\d(?:\.\d+)+)\s+(Datensatz|Datenbaustein)\s+(D[A-Z]{3})\b")
ROW_RE = re.compile(r"^\s*\d{3}\s*[-–]\s*\d{2,3}\s+(an|n|AN|N)\s+[MmKk]\s+(\S+)")
TOC_RE = re.compile(r"\.{4,}")


def extract_text(pdf: Path) -> str:
    """pdftotext (poppler), pdfplumber as fallback."""
    binaries = [shutil.which("pdftotext", path="C:/Program Files/Git/mingw64/bin"), shutil.which("pdftotext")]
    for binary in dict.fromkeys(b for b in binaries if b):
        result = subprocess.run([binary, "-enc", "UTF-8", "-layout", str(pdf), "-"],
                                capture_output=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.decode("utf-8")
    import pdfplumber

    with pdfplumber.open(pdf) as doc:
        texts = []
        for page in doc.pages:
            texts.append(page.extract_text() or "")
            page.close()
        return "\f".join(texts)


def normalise(text: str) -> list[tuple[str, str | None, str | None]]:
    out: list[tuple[str, str | None, str | None]] = []
    blk = fld = None
    body = False
    for line in text.replace("\f", "\n").split("\n"):
        s = " ".join(line.split())
        if not s or TOC_RE.search(s):
            continue
        if re.match(r"^Stand: \d", s) or re.match(r"^Seite \d+ von", s):
            continue
        if s.startswith("Datensatz DSLW – Datensatz Leistungswesen") and body and not SEC_RE.match(line):
            continue
        if re.match(r"^Datenbaustein D[A-Z]{3}", s) and not SEC_RE.match(line):
            continue
        m = SEC_RE.match(line)
        if m:
            blk, fld, body = m.group(3), None, True
        r = ROW_RE.match(line)
        if r:
            fld = re.sub(r"-?[„\"]?nn[“\"]?$", "", r.group(2))
        out.append((s, blk, fld))
    return out


def diff_texts(old: str, new: str, prefix: str = "VB-13.3-13.4", document: str = "VB", old_version: str = "13.3",
               new_version: str = "13.4") -> list[Change]:
    a, b = normalise(old), normalise(new)
    sm = difflib.SequenceMatcher(a=[x[0] for x in a], b=[x[0] for x in b], autojunk=False)
    out: list[Change] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        ctx = b[j1] if j1 < len(b) else b[-1]
        out.append(Change(key=f"{prefix}-{len(out):03d}", document=document, old_version=old_version,
                          new_version=new_version, tag=tag, block=ctx[1], field=ctx[2],
                          old="\n".join(x[0] for x in a[i1:i2]), new="\n".join(x[0] for x in b[j1:j2])))
    return out


def layout_rows_changed(changes: list[Change]) -> list[Change]:
    return [c for c in changes if any(ROW_RE.match(x) for x in (c.old + "\n" + c.new).split("\n"))]


def diff_pdfs(old_pdf: Path, new_pdf: Path, prefix: str) -> list[Change]:
    """prefix = DOC-OLD-NEW, e.g. VB-13.3-13.4."""
    doc, old, new = prefix.split("-", 2)[0], *prefix.split("-")[1:3]
    return diff_texts(extract_text(old_pdf), extract_text(new_pdf), prefix, doc, old, new)


def impact(changes: list[Change] | list[str], kb: KnowledgeBase):
    """P5.2: affected rules (recompute / review tiers) and test cases via the knowledge graph."""
    keys = [c.key if isinstance(c, Change) else c for c in changes]
    return kb.get_affected_rules(keys)
