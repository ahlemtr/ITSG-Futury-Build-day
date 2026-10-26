"""Word files: BVORERK (one passage per ITSG criterion) and HINWEISE (facts + chain) (08 section 5.4)."""

from __future__ import annotations

import re
from pathlib import Path

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from kg.extract.pdf_text import passage

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
REQUIRED_CRITERIA = ["f41c7278", "0cefe80e", "aade0289", "9c8c9b58"]


def _clean(text: str) -> str:
    return " ".join(text.split())


def blocks(path: Path) -> list[tuple[str, str]]:
    """Paragraphs and table rows in document order: [(kind, text)], kind 'p' or 'row'."""
    d = docx.Document(str(path))
    out = []
    for el in d.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = _clean(Paragraph(el, d).text)
            if text:
                out.append(("p", text))
        elif tag == "tbl":
            for row in Table(el, d).rows:
                cells = [_clean(c.text) for c in row.cells]
                if any(cells):
                    out.append(("row", " | ".join(cells)))
    return out


def split_bvorerk(doc: str, version: str, path: Path, warn) -> list[dict]:
    parts: list[tuple[str, list[str]]] = [("intro", [])]
    seen: set[str] = set()
    for _, text in blocks(path):
        m = UUID_RE.search(text)
        section = m.group(0).lower()[:8] if m else None
        # only the first mention of a criterion starts its passage; a later cross-reference stays in place
        if section and section not in seen:
            seen.add(section)
            parts.append((section, [text]))
        else:
            parts[-1][1].append(text)
    out = []
    for section, texts in parts:
        heading = "Szenario DBVO" if section == "intro" else f"Kriterium {section}"
        out.append(passage(doc, version, section, heading, "\n".join(texts), None))
    have = {p["section"] for p in out}
    for c in REQUIRED_CRITERIA:
        if c not in have:
            warn(f"{doc}@{version}#{c}: criterion not found")
    return out


def split_hinweise(doc: str, version: str, path: Path, warn) -> list[dict]:
    # The UUID-like values here are DATENSATZ-IDs, not criteria: no UUID split.
    items = blocks(path)
    facts = [t for kind, t in items if kind == "p"]
    chain = [t for kind, t in items if kind == "row"]
    if not chain:
        warn(f"{doc}@{version}: chain table not found")
    return [
        passage(doc, version, "facts", "Hinweise zur Testkonstellation EEL-Anwendungsprogramme", "\n".join(facts), None),
        passage(doc, version, "chain", "Tabelle zu den jeweils zu verwendenden ID’s bzw. AZVU", "\n".join(chain), None),
    ]
