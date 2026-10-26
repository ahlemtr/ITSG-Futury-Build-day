"""Parser and writer for DTA EEL fixed-width files (P1, plan/02 M1).

Layouts come from `kb.get_layout`. DSLW lines are parsed into a fixed part plus the blocks whose
MM flag is `J`, in `block_order`. DBVO has a repeating group counted by `ANZAHL-AU`. Envelope lines
(VOSZ, DSKO, NCSZ) are kept as raw lines. Lengths are counted in characters, not bytes (plan/02 s.9).
Errors are data: every problem becomes a `ParseIssue`, the parser never raises on bad input.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from engine.model import Block, Field, FieldValue, Layout, ParsedFile, ParseIssue, Record
from kg.interface import KnowledgeBase

ENVELOPE = {"VOSZ", "DSKO", "NCSZ"}
DEFAULT_VERSION = "13.4"  # layouts are identical in 13.3 and 13.4 (plan/04)


# ---------------------------------------------------------------- decoding


def decode(data: bytes) -> tuple[str, str]:
    """UTF-8 first, Latin-1 as fallback (plan/02 section 9)."""
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


def _split_lines(text: str) -> list[tuple[str, str]]:
    out = []
    for chunk in text.splitlines(keepends=True):
        body = chunk.rstrip("\r\n")
        out.append((body, chunk[len(body):]))
    return out


# ---------------------------------------------------------------- typed values


def to_value(f: Field, raw: str) -> tuple[Any, str | None]:
    """Raw string -> typed value. Returns (value, problem)."""
    if f.type == "an":
        return raw.rstrip(" "), None
    if not raw.isdigit():
        return None, f"non-numeric value {raw!r} in numeric field"
    if f.format == "date_yyyymmdd" and f.length == 8:
        if raw == "0" * 8:
            return None, None
        try:
            return date(int(raw[:4]), int(raw[4:6]), int(raw[6:])), None
        except ValueError:
            return None, f"invalid date {raw!r}"
    if f.format in ("amount_2dp", "hours_2dp"):
        return Decimal(int(raw)) / 100, None
    if f.length > 8 and f.format == "date_yyyymmdd":
        return raw, None  # timestamps like DATUM-ERSTELLUNG (20 digits) stay strings
    return int(raw), None


def format_value(f: Field, value: Any) -> str:
    """Typed value -> fixed-width string. `an` padded right with spaces, `n` left with zeros."""
    if isinstance(value, FieldValue):
        value = value.value
    if f.type == "an":
        s = "" if value is None else str(value)
        if len(s) > f.length:
            raise ValueError(f"{f.name}: {s!r} longer than {f.length}")
        return s.ljust(f.length)
    if value is None or value == "":
        return "0" * f.length
    if isinstance(value, date):
        s = value.strftime("%Y%m%d")
    elif isinstance(value, Decimal) or (isinstance(value, float) and f.format in ("amount_2dp", "hours_2dp")):
        s = str(int((Decimal(str(value)) * 100).to_integral_value()))
    elif isinstance(value, bool):
        raise ValueError(f"{f.name}: boolean in numeric field")
    else:
        s = str(value)
    if not s.isdigit() or len(s) > f.length:
        raise ValueError(f"{f.name}: {value!r} does not fit n{f.length}")
    return s.rjust(f.length, "0")


# ---------------------------------------------------------------- parser


class Parser:
    def __init__(self, kb: KnowledgeBase, version: str = DEFAULT_VERSION):
        self.kb = kb
        self.version = version
        self.dslw = kb.get_layout("DSLW", version)

    def _cut(self, line: str, f: Field, base: int, rec: str, issues: list[ParseIssue], line_no: int) -> FieldValue:
        a = base + f.start - 1
        raw = line[a: a + f.length]
        value, problem = to_value(f, raw) if len(raw) == f.length else (None, "line too short")
        if problem:
            issues.append(ParseIssue(record=rec, field=f.name, pos=a + 1, message=problem, line=line_no))
        return FieldValue(name=f.name, raw=raw, value=value, pos=a + 1)

    def _block(self, line: str, pos: int, lay: Layout, issues: list[ParseIssue], line_no: int) -> Block:
        """pos = 0-based index where the block starts."""
        b = Block(record=lay.record, pos=pos + 1)
        b.fields = {f.name: self._cut(line, f, pos, lay.record, issues, line_no) for f in lay.fields}
        length = lay.fixed_length
        rg = lay.repeating_group
        if rg:
            count = b.fields[rg.count_field].value or 0
            for k in range(count):
                base = pos + rg.starts_at - 1 + k * rg.group_length
                b.groups.append({
                    f.name: self._cut(line, f, base - f.start + f.offset_in_group, lay.record, issues, line_no)
                    for f in rg.fields
                })
            length += count * rg.group_length
        b.length = length
        return b

    def parse_line(self, line: str, line_no: int, newline: str = "") -> tuple[Record, list[ParseIssue]]:
        kind = line[:4]
        issues: list[ParseIssue] = []
        rec = Record(kind=kind, line_no=line_no, raw=line, newline=newline)
        if kind in ENVELOPE:
            return rec, issues
        if kind != "DSLW":
            issues.append(ParseIssue(record=kind, message=f"unknown record {kind!r}", line=line_no, pos=1))
            return rec, issues
        if len(line) < self.dslw.fixed_length:
            issues.append(ParseIssue(record="DSLW", message=f"record length {len(line)} shorter than the fixed part "
                                                            f"({self.dslw.fixed_length})", line=line_no))
            return rec, issues
        rec.head = {f.name: self._cut(line, f, 0, "DSLW", issues, line_no) for f in self.dslw.fields}
        pos = self.dslw.fixed_length
        for blk in self.dslw.block_order:
            lay = self.kb.get_layout(blk, self.version)
            flag = rec.head.get(lay.announced_by) if lay.announced_by else None
            if not flag or flag.value != "J":
                continue
            found = line[pos: pos + 4]
            if found != blk:
                issues.append(ParseIssue(record="DSLW", field=lay.announced_by, pos=pos + 1, line=line_no,
                                         message=f"{lay.announced_by}=J but found {found!r} instead of {blk}"))
                rec.tail = line[pos:]
                return rec, issues
            if lay.status == "missing":
                issues.append(ParseIssue(record=blk, pos=pos + 1, line=line_no,
                                         message=f"unknown block {blk}: layout not available (status missing)"))
                rec.tail = line[pos:]
                return rec, issues
            block = self._block(line, pos, lay, issues, line_no)
            rec.blocks[blk] = block
            pos += block.length
        if pos != len(line):
            rest = line[pos:]
            msg = f"record length {len(line)}, layouts account for {pos}"
            if rest[:4].isalpha() and rest[:2] == "DB":
                msg += f"; unannounced block {rest[:4]!r} at {pos + 1}"
            issues.append(ParseIssue(record="DSLW", pos=pos + 1, line=line_no, message=msg))
            rec.tail = rest
        return rec, issues


def parse_file(text: str | bytes, kb: KnowledgeBase, version: str = DEFAULT_VERSION) -> ParsedFile:
    encoding = "utf-8"
    if isinstance(text, bytes):
        text, encoding = decode(text)
    p = Parser(kb, version)
    out = ParsedFile(encoding=encoding)
    for n, (line, nl) in enumerate(_split_lines(text), 1):
        if not line.strip():
            out.records.append(Record(kind="", line_no=n, raw=line, newline=nl))
            continue
        rec, issues = p.parse_line(line, n, nl)
        out.records.append(rec)
        out.issues.extend(issues)
    return out


# ---------------------------------------------------------------- writer


def write_dslw(head: dict[str, Any], blocks: dict[str, dict[str, Any]], kb: KnowledgeBase,
               version: str = DEFAULT_VERSION) -> str:
    """Build one DSLW line. MM flags are set from the blocks present. `blocks[name]` is a
    field -> value dict; DBVO carries `groups: [ {BEGINN-AU: date, ...}, ... ]`. Missing fields:
    constants for `KENNUNG`, else zeros / spaces."""
    dslw = kb.get_layout("DSLW", version)
    head = {k: (v.value if isinstance(v, FieldValue) else v) for k, v in head.items()}
    for blk in dslw.block_order:
        lay = kb.get_layout(blk, version)
        if lay.announced_by:
            head[lay.announced_by] = "J" if blk in blocks else "N"
    head.setdefault("KENNUNG", "DSLW")
    line = "".join(format_value(f, head.get(f.name, f.constant)) for f in dslw.fields)
    for blk in dslw.block_order:
        if blk not in blocks:
            continue
        lay = kb.get_layout(blk, version)
        vals = dict(blocks[blk])
        groups = vals.pop("groups", [])
        rg = lay.repeating_group
        if rg and vals.get(rg.count_field) is None:
            vals[rg.count_field] = len(groups)
        vals.setdefault("KENNUNG", blk)
        line += "".join(format_value(f, vals.get(f.name, f.constant)) for f in lay.fields)
        if rg:
            for g in groups:
                line += "".join(format_value(f, g.get(f.name)) for f in sorted(rg.fields, key=lambda f: f.offset_in_group))
    return line


def record_to_dicts(rec: Record) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Parsed record -> (head, blocks) in writer form."""
    head = {k: v.value for k, v in rec.head.items()}
    blocks: dict[str, dict[str, Any]] = {}
    for name, b in rec.blocks.items():
        d: dict[str, Any] = {k: v.value for k, v in b.fields.items()}
        if b.groups:
            d["groups"] = [{k: v.value for k, v in g.items()} for g in b.groups]
        blocks[name] = d
    return head, blocks


def write_file(parsed: ParsedFile, kb: KnowledgeBase, version: str = DEFAULT_VERSION) -> str:
    """Write a parsed file back: envelope lines raw, DSLW lines rebuilt from their values."""
    out = []
    for rec in parsed.records:
        if rec.kind == "DSLW" and rec.head and not rec.tail:
            head, blocks = record_to_dicts(rec)
            out.append(write_dslw(head, blocks, kb, version) + rec.newline)
        else:
            out.append(rec.raw + rec.newline)
    return "".join(out)


def encode(text: str, encoding: str = "utf-8") -> bytes:
    return text.encode(encoding)
