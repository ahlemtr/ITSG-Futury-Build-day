"""Spec text -> kg/build/passages.yaml."""

from __future__ import annotations

from pathlib import Path

from kg.common import BUILD_DIR, LAYOUT_DIR, ROOT, SEED_DIR, dump_yaml, load_documents, load_layouts
from kg.extract import docx as docx_split
from kg.extract import field_tables, generic, vb
from kg.extract.pdf_text import clean, pdf_to_text, read_lines

# these must hold on the generated passages (also checked by validate.py)
CHECKS_3_12 = [
    ("VB@13.3#3.12/chaining", "nicht mindestens 6 Monate", True),
    ("VB@13.4#3.12/chaining", "nicht mehr als 6 Monate", True),
    ("VB@13.4#3.12/chaining", "nicht mindestens", False),
    ("VB@13.4#3.12/insurer", "nicht mindestens 6 Monate", True),
    ("VB@13.4#3.12.7", "mehr als 6 Monate", True),
]


def check_3_12(passages: dict[str, dict]) -> list[str]:
    """Only for loaded versions: at the demo start VB 13.4 is not there yet."""
    errors = []
    loaded = {k.split("#")[0] for k in passages}
    for key, needle, wanted in CHECKS_3_12:
        if key.split("#")[0] not in loaded:
            continue
        p = passages.get(key)
        if p is None:
            errors.append(f"{key}: passage missing")
        elif (needle in p["text"]) != wanted:
            errors.append(f"{key}: {'missing' if wanted else 'must not contain'} {needle!r}")
    return errors


def extract_document(dv: dict, layouts: dict, text_dir: Path, warn) -> list[dict]:
    doc, version, path = dv["doc"], dv["version"], ROOT / dv["file"]
    if path.suffix.lower() == ".docx":
        if doc == "BVORERK":
            return docx_split.split_bvorerk(doc, version, path, warn)
        return docx_split.split_hinweise(doc, version, path, warn)
    txt = pdf_to_text(path, text_dir / f"{doc}@{version}.txt")
    lines, toc_last = read_lines(txt)
    toc_last_page = lines[toc_last].page if toc_last >= 0 else 0
    lines = clean(lines)
    if doc == "VB":
        passages = vb.split(doc, version, lines, layouts, warn)
    else:
        passages = generic.split(doc, version, lines, toc_last_page, warn)
    if doc == "VB" or dv.get("role") == "record_layout":
        passages += field_tables.extract(dv, layouts, warn)
    return passages


def run(seed_dir: Path = SEED_DIR, layout_dir: Path = LAYOUT_DIR, build_dir: Path = BUILD_DIR) -> list[dict]:
    layouts = load_layouts(layout_dir)
    warnings: list[str] = []

    def warn(msg: str) -> None:
        warnings.append(msg)
        print(f"WARNING: {msg}")

    passages: list[dict] = []
    for dv in load_documents(seed_dir):
        if not dv["present"]:
            warn(f"{dv['doc']}@{dv['version']}: file {dv['file']} missing, skipped")
            continue
        found = extract_document(dv, layouts, build_dir / "text", warn)
        print(f"  {dv['doc']}@{dv['version']}: {len(found)} passages")
        passages += found
    empty: dict[str, int] = {}
    for p in passages:
        if not p["text"]:
            empty[f"{p['doc']}@{p['version']}"] = empty.get(f"{p['doc']}@{p['version']}", 0) + 1
    if empty:
        # mostly chapter headings directly followed by their first sub-section
        warn("passages with empty text: " + ", ".join(f"{k} {n}" for k, n in empty.items()))
    keys = [p["key"] for p in passages]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        raise ValueError(f"duplicate passage keys: {dupes}")
    for err in check_3_12({p["key"]: p for p in passages}):
        warn(f"3.12 check failed: {err}")
    dump_yaml(passages, build_dir / "passages.yaml")
    return passages
