"""Verfahrensbeschreibung splitter: sections, field sub-sections, parts of the 3.12 intro."""

from __future__ import annotations

import re

from kg.common import field_key, norm_field, numbered_fields
from kg.extract.pdf_text import Line, is_successor, join_text, match_heading, passage, section_str

START_RE = re.compile(r"^2\. Grundsätzliches")
# Layout row in a block table: "033-    008    n     M   BEGINN-AU-„nn“"
ROW_RE = re.compile(r"^\s*(\d{3})\s*[-–]\s*\d{2,3}\s+(an|n|AN|N)\s+[MmKk]\s+(\S+)")
SPEC_SUFFIX = re.compile(r"-?(„nn“|\"nn\"|\{nn\}|nn)$", re.IGNORECASE)

# Block headings sit in column 0 or one or two spaces in ("  3.19       Datenbaustein DBID ...")
MAX_INDENT = 2

PARTS_3_12 = [
    ("conditions", "Die Vorerkrankungsanfrage (3.1.18"),
    ("chaining", "Bei der Anfrage sollen"),
    ("scope", "Der Arbeitgeber stellt eine"),
    ("insurer", "Die Rückmeldung durch die Krankenkasse"),
    ("uebergangsgeld", "Erfolgt die Meldung durch den Arbeitgeber für GKV"),
]


def split_sections(lines: list[Line]) -> list[tuple[str, str, list[Line]]]:
    """[(section, heading, body lines)], level 1. Everything before '2. Grundsätzliches' is section 1."""
    start = next((i for i, line in enumerate(lines) if START_RE.match(line.text)), None)
    if start is None:
        raise ValueError("VB: '2. Grundsätzliches' not found")
    sections = [("1", "Einführung", lines[:start])]
    prev: tuple[int, ...] | None = (1,)
    current = None
    for line in lines[start:]:
        h = match_heading(line.text, MAX_INDENT)
        if h:
            num, title, _ = h
            # chapter 3 only has blocks (3.N); deeper numbers there are field references in body text
            ok = is_successor(num, prev) and not (num[0] == 3 and len(num) > 2)
            if ok:
                if num == (4,) and title.startswith("Anlagen"):
                    break
                current = (section_str(num), " ".join(line.text.split()), [])
                sections.append(current)
                prev = num
                continue
        if current:
            current[2].append(line)
    return sections


def _spec_name(name: str) -> str:
    return norm_field(SPEC_SUFFIX.sub("", name))


def _indent(line: Line) -> int:
    return len(line.text) - len(line.text.lstrip())


def _heading_start(body: list[Line], row: int) -> int:
    """Index where a field passage starts: its heading above the row, or the row itself.

    A field heading is an isolated line (or up to 3 wrapped lines) indented at least 4 spaces,
    e.g. "           Grund der Anforderung". Blocks like 3.20 have no field headings; then the
    passage starts at the row, not at the last sentence of the previous field.
    """
    h = row - 1
    while h >= 0 and not body[h].text.strip():
        h -= 1
    if h < 0 or _indent(body[h]) < 4 or ROW_RE.match(body[h].text):
        return row
    top = h
    while top - 1 >= 0 and body[top - 1].text.strip() and _indent(body[top - 1]) >= 4 and h - top < 2:
        top -= 1
    if top == 0 or not body[top - 1].text.strip():
        return top
    return row


def split_fields(doc: str, version: str, section: str, body: list[Line], layout: dict, warn) -> tuple[int, list[dict]]:
    """Field passages of one block. Returns (index of the first field heading in body, passages).

    Rows are matched to layout fields by start position, since the spec shortens some names
    ("ABRECHNUNGSPRO-"); the name is only cross-checked.
    """
    by_start = {f["start"]: (n, f) for n, f in numbered_fields(layout)}
    found: list[tuple[int, int, int, dict]] = []  # (passage start, row index, number, field)
    last_number = 0
    for i, line in enumerate(body):
        m = ROW_RE.match(line.text)
        if not m or int(m.group(1)) not in by_start:
            continue
        number, field = by_start[int(m.group(1))]
        if number <= last_number:
            continue
        spec_name, layout_name = _spec_name(m.group(3)), norm_field(field["name"])
        # the spec hyphenates long names in the narrow column ("ABRECHNUNGSPRO-")
        if not layout_name.startswith(spec_name.rstrip("-")):
            warn(f"{doc}@{version}#{section}.{number}: row name {m.group(3)!r} differs from layout {field['name']!r}")
        found.append((_heading_start(body, i), i, number, field))
        last_number = number
    numbers = {n for _, _, n, _ in found}
    for n, f in numbered_fields(layout):
        if n not in numbers:
            warn(f"{doc}@{version}#{section}.{n} ({field_key(layout['record'], f)}): row not found")
    out = []
    for k, (h, row, number, field) in enumerate(found):
        end = found[k + 1][0] if k + 1 < len(found) else len(body)
        chunk = body[h:end]
        heading = join_text(body[h:row]) or " ".join(body[row].text.split())
        out.append(passage(
            doc, version, f"{section}.{number}", heading, join_text(chunk),
            chunk[0].page, field=field_key(layout["record"], field),
        ))
    first = found[0][0] if found else len(body)
    return first, out


def split_parts(doc: str, version: str, block: dict, warn) -> list[dict]:
    text = block["text"]
    found = []
    for part, anchor in PARTS_3_12:
        pos = text.find(anchor)
        if pos < 0:
            warn(f"{block['key']}: anchor for part {part!r} not found")
            continue
        found.append((pos, part))
    found.sort()
    out = []
    for k, (pos, part) in enumerate(found):
        end = found[k + 1][0] if k + 1 < len(found) else len(text)
        out.append(passage(doc, version, "3.12", block["heading"], text[pos:end].strip(), block["page"], part=part))
    return out


def split(doc: str, version: str, lines: list[Line], layouts: dict[str, dict], warn) -> list[dict]:
    by_section = {lay["spec"]["section"]: lay for lay in layouts.values()}
    out = []
    for section, heading, body in split_sections(lines):
        page = body[0].page if body else None
        layout = by_section.get(section)
        if layout:
            first, fields = split_fields(doc, version, section, body, layout, warn)
            # the block passage keeps the text before the first field; a block that opens with its
            # first field (3.1, 3.20, ...) keeps the whole block text, so citing it is not empty
            block = passage(doc, version, section, heading, join_text(body[:first]) or join_text(body), page)
            out.append(block)
            if section == "3.12":
                out += split_parts(doc, version, block, warn)
            out += fields
        else:
            out.append(passage(doc, version, section, heading, join_text(body), page))
    return out
