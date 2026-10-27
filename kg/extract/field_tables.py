"""Field evidence from PDF table cells, never from neighbouring flattened text lines.

Keep the original name, explanation and checks, including conditional requirements.
The metadata is source-specific; M/m alone cannot establish a contradiction.
"""

from __future__ import annotations

import hashlib
import json
import re

import pdfplumber

from kg.common import BUILD_DIR, ROOT, field_key, layout_fields
from kg.extract.pdf_text import passage

CHAPTER = re.compile(r"(?m)^\s*(\d+(?:\.\d+)*)\s+(?:Datenbaustein|Datensatz)\s+([A-Z]{4})\b")
POSITION = re.compile(r"^(\d{3})-\s*(\d{3})$")


def extract(dv: dict, layouts: dict, warn) -> list[dict]:
    """Content-addressed cache also covers layout mappings and extractor revision."""
    fingerprint = hashlib.sha256((ROOT / dv["file"]).read_bytes())
    fingerprint.update(json.dumps(layouts, sort_keys=True, default=str).encode())
    fingerprint.update(f"cells-v2:{dv['doc']}@{dv['version']}".encode())
    cache = BUILD_DIR / "table_cells" / f"{fingerprint.hexdigest()}.json"
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        for message in data["warnings"]:
            warn(message)
        return data["rows"]
    warnings = []
    rows = _extract(dv, layouts, warnings.append)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"rows": rows, "warnings": warnings}, ensure_ascii=False), encoding="utf-8")
    for message in warnings:
        warn(message)
    return rows


def _extract(dv: dict, layouts: dict, warn) -> list[dict]:
    """Read bordered cells. Wrapped positions/names and page continuations stay in their own row."""
    out: dict[str, dict] = {}
    record = section = None
    last = None
    vb_sections = {str(lay["spec"]["section"]): rec for rec, lay in layouts.items()}
    with pdfplumber.open(ROOT / dv["file"]) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            headings = [m for m in CHAPTER.finditer(text) if "...." not in m[0]]
            if headings:
                next_section, next_record = headings[-1].groups()
                if next_record != record:
                    last = None
                section, record = next_section, next_record
            elif dv["doc"] == "VB":
                # VB uses unnumbered block headings; numbered field headings identify its section.
                for line in text.splitlines():
                    m = re.match(r"^(3\.\d+)(?:\.\d+)?\s", line)
                    if m and m[1] in vb_sections:
                        section, record = m[1], vb_sections[m[1]]
                        break
            if record is None:
                page.close()
                continue
            for table in page.extract_tables():
                for cells in table:
                    if len(cells) < 6:
                        continue
                    pos = POSITION.fullmatch((cells[0] or "").strip())
                    if not pos:
                        # A table row continued on the next page carries no repeated metadata.
                        if last and not any(cells[:5]):
                            for i, name in ((5, "explanation"), (6, "checks")):
                                if len(cells) > i and cells[i]:
                                    last["definition"][name] += "\n" + cells[i]
                                    last["text"] += "\n" + cells[i]
                        continue
                    start, end = map(int, pos.groups())
                    length, typ, marker = ((c or "").strip() for c in cells[1:4])
                    if not length.isdigit() or typ not in ("an", "n") or marker not in ("M", "m"):
                        warn(f"{dv['doc']}@{dv['version']} p{page.page_number} {record}:{start}: incomplete table cells")
                        continue
                    if end - start + 1 != int(length):
                        warn(f"{dv['doc']}@{dv['version']} p{page.page_number} {record}:{start}: inconsistent range")
                        continue
                    source_name = cells[4] or ""
                    candidates = [f for f in layout_fields(layouts.get(record, {}))
                                  if f["start"] == start and f["length"] == int(length)]
                    canonical = field_key(record, candidates[0]) if len(candidates) == 1 else None
                    explanation = cells[5] or ""
                    checks = cells[6] or "" if len(cells) > 6 else ""
                    key = f"{section}.f{start:03d}"
                    row = passage(dv["doc"], dv["version"], key,
                                  f"{record} {canonical.split('.', 1)[1] if canonical else source_name.splitlines()[0]}",
                                  f"{record} {start:03d}-{end:03d} {length} {typ} {marker}\n"
                                  f"{source_name}\n{explanation}\n{checks}".strip(), page.page_number, field=canonical)
                    row["definition"] = {"record": record, "start": start, "end": end, "length": int(length),
                                         "type": typ, "required": marker, "source_name": source_name,
                                         "explanation": explanation, "checks": checks,
                                         "extraction": "pdf_table_cells"}
                    if row["key"] in out:
                        warn(f"{row['key']}: repeated table position retained as first evidence")
                        continue
                    out[row["key"]] = row
                    last = row
            page.close()
    return list(out.values())
