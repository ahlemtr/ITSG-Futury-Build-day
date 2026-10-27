"""GG Anlage 2 (Schlüsselzahlen) -> kg/seed/key_values.yaml: the allowed codes per field, read from the extracted
passages (kg/build/passages.yaml), never typed by hand.

python -m tools.extract_key_values      (after python -m kg.extract or kg.build)

Each chapter of Anlage 2 is one code table: "01 = Kündigung des Arbeitgebers", "1= Stundenlohn",
"Grundstellung (0)". The field name comes from the chapter heading („GRUNDBEEND“), the records from the layouts.
"""

from __future__ import annotations

import re
from pathlib import Path

from kg.common import BUILD_DIR, LAYOUT_DIR, SEED_DIR, dump_yaml, load_yaml

DOC = "GG-ANL2"
# chapter 6 has no field name in quotes; chapter 2 also governs KORR-ABGABEGRUND
FIELD_BY_SECTION = {"6": ["ABRECHNUNGSPROGRAMM"], "2": ["ABGABEGRUND", "KORR-ABGABEGRUND"]}
CODE_RE = re.compile(r"(?:^|\s)(\d{1,2})\s*=\s*(\S[^=]*?)(?=\s+\d{1,2}\s*=|$)")
TAIL_RE = re.compile(r"\s*(?:Version \d+\.\d+|Grundstel-).*$")
QUOTED_RE = re.compile(r"„([A-Z0-9-]+?)(?:-„NN“)?“")


def layouts_with(field: str) -> list[str]:
    out = []
    for path in sorted(LAYOUT_DIR.glob("*.yaml")):
        lay = load_yaml(path)
        names = [f["name"] for f in lay.get("fields", [])]
        names += [f["name"] for f in (lay.get("repeating_group") or {}).get("fields", [])]
        if any(n == field or n.removesuffix("-{nn}") == field for n in names):
            out.append(lay["record"])
    return out


def extract(passages: list[dict]) -> list[dict]:
    tables = []
    for p in passages:
        if p["doc"] != DOC or not p["section"].isdigit() or p["section"] == "1":
            continue
        text = " ".join(p["text"].split())
        fields = FIELD_BY_SECTION.get(p["section"]) or QUOTED_RE.findall(p["heading"] + " " + text)[:1]
        # the last description runs into the page footer ("Version 13.0 Anlage 2 ...") or the Grundstellung line
        codes = {m.group(1): TAIL_RE.sub("", m.group(2)).strip() for m in CODE_RE.finditer(text)}
        if not fields or not codes:
            continue
        grundstellung = "Grundstel" in text  # "Grundstellung (0)", hyphenated in MM-KUG
        for field in fields:
            tables.append({"field": field, "records": layouts_with(field), "codes": codes,
                           "grundstellung_allowed": grundstellung, "source": p["key"]})
    return tables


def main() -> None:
    passages = load_yaml(BUILD_DIR / "passages.yaml")
    passages = passages["passages"] if isinstance(passages, dict) else passages
    version = next(p["version"] for p in passages if p["doc"] == DOC)
    tables = extract(passages)
    out = SEED_DIR / "key_values.yaml"
    dump_yaml({"document": DOC, "version": version, "valid_from": "2026-01-01", "tables": tables}, out)
    for t in tables:
        print(f"{t['field']:<20} {','.join(t['records']) or '-':<12} {len(t['codes'])} codes  ({t['source']})")
    print(f"wrote {Path(out).relative_to(SEED_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
