"""Paths, key formats and small helpers shared by the build scripts and both backends (08 sections 1 and 2)."""

from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
KG_DIR = ROOT / "kg"
SEED_DIR = KG_DIR / "seed"
BUILD_DIR = KG_DIR / "build"
LAYOUT_DIR = ROOT / "layouts"

# Field names: layouts write BEGINN-AU-{nn}, files and examples BEGINN-AU-1 (08 section 1.3)
REPEAT_SUFFIX = re.compile(r"-(\{nn\}|\d+)$")

# Documents whose file may be missing; their rule sources are optional (08 section 9.2)
OPTIONAL_DOCS = {"BP", "HINWEISE", "BVORERK"}


def norm_field(name: str) -> str:
    return REPEAT_SUFFIX.sub("", name)


def field_key(record: str, field: dict) -> str:
    """RECORD.NAME. Only repeating-group fields drop the occurrence suffix: DBVO.BEGINN-AU,
    but DBAL.LAG-BEGINN-1 and DBAL.LAG-BEGINN-2 stay two fields."""
    name = norm_field(field["name"]) if field.get("repeating") else field["name"]
    return f"{record}.{name}"


def load_dotenv() -> None:
    try:
        from dotenv import load_dotenv as _load
    except ImportError:
        return
    _load(ROOT / ".env")


def env(name: str, default: str | None = None) -> str | None:
    load_dotenv()
    value = os.environ.get(name)
    return value if value else default


def load_yaml(path: Path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def dump_yaml(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, width=1000, indent=2)


def iso(value):
    """Dates to ISO strings, everything else unchanged."""
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def to_date(value) -> dt.date | None:
    if value is None or isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def passage_doc_version(key: str) -> tuple[str, str]:
    """'VB@13.4#3.12/chaining' -> ('VB', '13.4')"""
    head = key.split("#", 1)[0]
    doc, version = head.split("@", 1)
    return doc, version


MAX_SUBGRAPH_DEPTH = 3


def resolve_vb(version: str, vb_versions: list[str]) -> str:
    """VB version for passages: the version itself, or the newest real one for simulated versions (07 section 8).

    vb_versions is sorted by valid_from."""
    if version in vb_versions:
        return version
    if version.startswith("sim-") and vb_versions:
        return vb_versions[-1]
    raise KeyError(f"unknown VB version {version!r}, known: {vb_versions}")


def resolve_passage_key(key: str, vb_versions: list[str]) -> str:
    doc, version = passage_doc_version(key)
    if doc == "VB" and version.startswith("sim-"):
        return key.replace(f"VB@{version}#", f"VB@{resolve_vb(version, vb_versions)}#", 1)
    return key


def keep_source(passage_key: str, vb: str | None) -> bool:
    """get_rules and the deviation context cite VB passages of one version only, other documents always."""
    doc, version = passage_doc_version(passage_key)
    return vb is None or doc != "VB" or version == vb


def load_documents(seed_dir: Path = SEED_DIR) -> list[dict]:
    """documents.yaml flattened to one dict per DocVersion, with `present` = file exists."""
    out = []
    for doc in load_yaml(seed_dir / "documents.yaml")["documents"]:
        for v in doc["versions"]:
            out.append({
                "doc": doc["code"],
                "title": doc["title"],
                "version": str(v["version"]),
                "published": v.get("published"),
                "valid_from": v.get("valid_from"),
                "file": v.get("file"),
                "succeeds": str(v["succeeds"]) if v.get("succeeds") else None,
                "present": bool(v.get("file")) and (ROOT / v["file"]).exists(),
            })
    return out


def load_layouts(layout_dir: Path = LAYOUT_DIR) -> dict[str, dict]:
    return {p.stem: load_yaml(p) for p in sorted(layout_dir.glob("*.yaml"))}


def layout_fields(layout: dict) -> list[dict]:
    """All fields of a layout in position order: fixed fields, then the repeating group."""
    fields = [dict(f, repeating=False) for f in layout.get("fields", [])]
    group = layout.get("repeating_group")
    if group:
        fields += [dict(f, repeating=True) for f in group["fields"]]
    return fields


def numbered_fields(layout: dict) -> list[tuple[int, dict]]:
    """Field sub-section numbers as the spec counts them: fields without `source`, from 1 (08 section 5.2)."""
    return list(enumerate((f for f in layout_fields(layout) if "source" not in f), start=1))
