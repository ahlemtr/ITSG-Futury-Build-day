"""PDF to clean lines with page numbers (08 section 5.1), and the heading rules shared by all splitters."""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

FOOTER_RES = [
    re.compile(r"^\s*Stand:? \d"),
    re.compile(r"^\s*Seite \d+ von"),
    # GG running header: "Gemeinsame Grundsätze ... im Rahmen des        Stand: 06.05.2025"
    re.compile(r"\sStand: \d{2}\.\d{2}\.\d{4}\s*$"),
    # PTA page footer (two lines)
    re.compile(r"^\s*Informationstechnische Servicestelle\b"),
    re.compile(r"^\s*der gesetzlichen Krankenversicherung\s+Alle Rechte vorbehalten"),
]
PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,3}\s*$")
TOC_RE = re.compile(r"\.{4,}")
GG_FOOTNOTE_RE = re.compile(r"^\s*1 Das Bundesministerium")

# Numbered heading: "3.12 Datenbaustein ...", "23. Abgabegrund 88 ...". The title starts upper case,
# which skips cross-references like '3.7 „Datenbaustein ...' at line start.
HEADING_RE = re.compile(r"^(?P<indent> *)(?P<num>\d+\.|\d+\.\d+(?:\.\d+)*)\s+(?P<title>[A-ZÄÖÜ].*)$")
# Chapter without a dot, as in the PTA: "8     Systemprüfung / Modulprüfung". Some pdftotext builds (4.00 on
# Windows) keep a single space ("3 Zuordnung der Testaufgaben ..."): accepted when the title has 3+ words,
# so calendar rows like "5 Fr" never match
BARE_HEADING_RE = re.compile(
    r"^(?P<indent> *)(?P<num>\d{1,2})(?:\s{2,}|\s(?=\S+(?:\s+\S+){2,}))(?P<title>[A-ZÄÖÜ].*)$")

TOC_SEARCH_PAGES = 20


@dataclass
class Line:
    idx: int  # line index in the pdftotext output
    page: int
    text: str  # form feeds removed, indentation kept


def pdf_to_text(pdf: Path, out_txt: Path) -> Path:
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("pdftotext"):
        subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", str(pdf), str(out_txt)], check=True)
        return out_txt
    # Fallback (09 section 2): pdfplumber, pages joined by form feeds like pdftotext does
    print(f"WARNING: pdftotext not found, using pdfplumber for {pdf.name} (layout may differ)")
    import pdfplumber

    with pdfplumber.open(pdf) as doc:
        pages = [(p.extract_text(layout=True) or "") for p in doc.pages]
    out_txt.write_text("\f".join(pages), encoding="utf-8")
    return out_txt


def read_lines(txt: Path) -> tuple[list[Line], int]:
    """All lines with their page number, plus the index of the last table-of-contents line (-1 if none)."""
    raw = txt.read_text(encoding="utf-8")
    lines, page, toc_last = [], 1, -1
    for i, text in enumerate(raw.split("\n")):
        page += text.count("\f")
        text = text.replace("\f", "").rstrip()
        if page <= TOC_SEARCH_PAGES and TOC_RE.search(text):
            toc_last = i
        lines.append(Line(i, page, text))
    return lines, toc_last


def is_footer(text: str) -> bool:
    return any(r.match(text) for r in FOOTER_RES)


def clean(lines: list[Line]) -> list[Line]:
    """Remove footers, page-number lines, running headers, GG footnotes and TOC lines (08 section 5.1).

    A running header is a line directly after a footer (no blank line in between, at most 3 lines) whose
    text repeats after other footers too. Headings are never treated as running headers.
    """
    footer = [is_footer(line.text) for line in lines]
    candidates: set[int] = set()
    for i, is_f in enumerate(footer):
        if not is_f:
            continue
        j = i + 1
        while j < len(lines) and j <= i + 3 and lines[j].text.strip() and not footer[j]:
            candidates.add(j)
            j += 1
    counts = Counter(lines[j].text.strip() for j in candidates)
    header = {
        j for j in candidates
        if counts[lines[j].text.strip()] >= 2 and not HEADING_RE.match(lines[j].text)
    }
    out = []
    for i, line in enumerate(lines):
        t = line.text
        if footer[i] or i in header:
            continue
        if PAGE_NUMBER_RE.match(t) or TOC_RE.search(t) or GG_FOOTNOTE_RE.match(t):
            continue
        out.append(line)
    return out


_KEEP_HYPHEN_BEFORE = {"und", "oder", "bzw.", "sowie", "bis"}


def join_text(lines: list[Line]) -> str:
    """Passage text: lines joined, whitespace collapsed, hyphenation removed (08 section 5.1 step 5)."""
    out = ""
    for line in lines:
        t = " ".join(line.text.split())
        if not t:
            continue
        first_word = t.split(" ", 1)[0]
        if out.endswith("-") and t[:1].islower() and first_word not in _KEEP_HYPHEN_BEFORE:
            out = out[:-1] + t
        elif out:
            out += " " + t
        else:
            out = t
    return out


def join_strings(parts: list[str]) -> str:
    return join_text([Line(0, 0, p) for p in parts])


def num_tuple(num: str) -> tuple[int, ...]:
    return tuple(int(x) for x in num.rstrip(".").split("."))


def is_successor(cand: tuple[int, ...], prev: tuple[int, ...] | None, top_jump: int = 2, jump: int = 5) -> bool:
    """A heading number is accepted only if it plausibly follows the previous one.

    Stricter than "greater than the previous" (08 section 5.2): body lines like "13. November 2007, ..."
    are greater than 3.4 but jump chapters, and are rejected.
    """
    if prev is None:
        return True
    if cand <= prev:
        return False
    if cand[0] - prev[0] > top_jump:
        return False
    i = 0
    while i < min(len(cand), len(prev)) and cand[i] == prev[i]:
        i += 1
    if i < len(prev) and i > 0 and cand[i] - prev[i] > jump:
        return False
    # components below the one that changed must start low (a new chapter starts at .1)
    return all(c <= 3 for c in cand[i + 1:]) and (i < len(prev) or cand[i] <= 3)


def match_heading(text: str, max_indent: int, allow_bare: bool = False):
    """(number tuple, title, is_bare) or None."""
    m = HEADING_RE.match(text)
    if m and len(m.group("indent")) <= max_indent:
        return num_tuple(m.group("num")), m.group("title").strip(), False
    if allow_bare:
        m = BARE_HEADING_RE.match(text)
        if m and len(m.group("indent")) <= max_indent:
            return (int(m.group("num")),), m.group("title").strip(), True
    return None


def section_str(num: tuple[int, ...]) -> str:
    return ".".join(str(n) for n in num)


def passage(doc: str, version: str, section: str, heading: str, text: str, page: int | None,
            part: str | None = None, field: str | None = None) -> dict:
    key = f"{doc}@{version}#{section}" + (f"/{part}" if part else "")
    return {
        "key": key,
        "doc": doc,
        "version": version,
        "section": section,
        "part": part,
        "heading": heading,
        "text": text,
        "page": page,
        "field": field,
    }
