"""Splitter for GG, PTA, BP and the Rundschreiben."""

from __future__ import annotations

import re

from kg.extract.pdf_text import Line, is_successor, join_text, match_heading, passage, section_str

MAX_INDENT = 12  # GG indents sub-sections
# the GG annexes centre their chapter headings; only there a deeper indent is still a heading
MAX_INDENT_BY_DOC = {"GG-ANL1": 40, "VB-ANL1": 40, "GG-ANL2": 40, "GG-ANL3": 40}
# ... and give one- or two-word chapter titles after a single space ("6 Abrechnungsprogramm", "8 Entgeltart (...)"),
# which the general bare-heading rule refuses to keep PTA calendar rows out
ANNEX_HEADING_RE = re.compile(r"^ *(?P<num>\d{1,2})\s+(?P<title>[A-ZÄÖÜ][^=]*)$")
# A heading-shaped line ending in a page number is a TOC entry (RS-ANL3 has one per chapter, without dots)
TOC_ENTRY_RE = re.compile(r"\s\d{1,3}\s*$")

# Sections that must exist per document
REQUIRED = {
    "GG": ["2.1.1", "2.1.2", "2.2.1", "2.2.2", "2.5"],
    "PTA": ["5.14"],
    "BP": ["13.1", "13.2", "13.3", "13.4", "13.5", "16.1", "16.5", "16.7", "17.1", "23"],
}
PTA_CHAPTERS = {1, 2, 5, 8}  # process, EEL, permanent test cases


def split(doc: str, version: str, lines: list[Line], toc_last_page: int, warn) -> list[dict]:
    # the body starts on the page after the table of contents (wrapped TOC entries have no dots)
    body = [line for line in lines if line.page > toc_last_page]
    sections: list[tuple[tuple[int, ...] | None, str, list[Line]]] = [(None, "", [])]
    prev = None
    for line in body:
        h = match_heading(line.text, MAX_INDENT_BY_DOC.get(doc, MAX_INDENT), allow_bare=True)
        if h is None and doc in MAX_INDENT_BY_DOC and (m := ANNEX_HEADING_RE.match(line.text)):
            h = ((int(m["num"]),), m["title"], True)
        # refused as a heading, but kept as body text (PTA calendar rows like "2  Fr  Mo  6" look the same)
        if h and TOC_ENTRY_RE.search(line.text):
            h = None
        if h:
            num, _title, bare = h
            # a chapter without a dot only counts as a following chapter number ("9    Abkürzungsverzeichnis")
            ok = is_successor(num, prev) and (not bare or prev is None or num[0] - prev[0] in (1, 2))
            ok = ok and (prev is not None or num[0] <= 2)
            if ok:
                sections.append((num, " ".join(line.text.split()), []))
                prev = num
                continue
        sections[-1][2].append(line)

    out = []
    if len(sections) == 1:
        # no heading found: one passage per page (Rundschreiben)
        pages: dict[int, list[Line]] = {}
        for line in body:
            pages.setdefault(line.page, []).append(line)
        for page, chunk in sorted(pages.items()):
            text = join_text(chunk)
            if text:
                out.append(passage(doc, version, f"p{page}", f"Seite {page}", text, page))
        return out

    intro = sections[0][2]
    if join_text(intro) and doc != "PTA":
        out.append(passage(doc, version, "intro", "", join_text(intro), intro[0].page))
    for num, heading, chunk in sections[1:]:
        if doc == "PTA" and num[0] not in PTA_CHAPTERS:
            continue
        page = chunk[0].page if chunk else None
        out.append(passage(doc, version, section_str(num), heading, join_text(chunk), page))

    have = {p["section"] for p in out}
    for section in REQUIRED.get(doc, []):
        if section not in have:
            warn(f"{doc}@{version}#{section}: required section not found")
    return out
