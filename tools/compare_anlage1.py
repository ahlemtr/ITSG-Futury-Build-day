"""Compare technical PDF table cells to layout YAML, classifying scope separately from structure.

python -m tools.compare_anlage1
M is the unconditional case of m, not an automatic contradiction. Conditions must be read in context.
"""

from __future__ import annotations

from kg.common import LAYOUT_DIR, layout_fields, load_documents, load_layouts, load_yaml
from kg.extract.field_tables import extract
from kg.field_evidence import classify

DOC = "GG-ANL1"
VERSION = "13.1.1"


def anlage1_rows() -> dict[str, dict[int, dict]]:
    """Bordered cells preserve wrapped rows and keep all metadata attached to the correct field."""
    out: dict[str, dict[int, dict]] = {}
    dv = next(d for d in load_documents() if d["doc"] == DOC and d["version"] == VERSION)
    for p in extract(dv, load_layouts(), print):
        row = p["definition"]
        out.setdefault(row["record"], {})[row["start"]] = row
    return out


def compare() -> tuple[list[str], int]:
    rows = anlage1_rows()
    diffs, compared = [], 0
    for path in sorted(LAYOUT_DIR.glob("*.yaml")):
        lay = load_yaml(path)
        a1 = rows.get(lay["record"], {})
        for f in layout_fields(lay):
            r = a1.get(f["start"])
            if r is None:
                continue
            compared += 1
            for key in ("length", "type", "required"):
                if str(r[key]) != str(f.get(key)):
                    category = classify(key, r[key], f.get(key))
                    diffs.append(f"[{category}] {lay['record']}.{f['name']} (Stelle {f['start']}): {key} Anlage 1 = {r[key]}, "
                                 f"layout = {f.get(key)}")
    return diffs, compared


def main() -> None:
    diffs, compared = compare()
    structural = sum(d.startswith("[structure_difference]") for d in diffs)
    print(f"{compared} fields compared, {len(diffs)} scope/structure findings ({structural} structural)")
    print("M/m alone is not a contradiction; inspect source conditions and block context.")
    for d in diffs:
        print("  " + d)


if __name__ == "__main__":
    main()
