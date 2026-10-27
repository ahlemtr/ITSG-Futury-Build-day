"""Hand the knowledge to a teammate: the same passages, embeddings and AI answers, without new OpenAI calls.

python -m tools.kg_bundle export [path.zip]   writes bundles/kg-bundle-<date>.zip (default)
python -m tools.kg_bundle import <path.zip>   unpacks it into kg/build/ and DATA_DIR/llm_cache/

What is in it (all gitignored, so a fresh clone does not have it):
- kg/build/: passages.yaml and text/ (extracted from sources/), embeddings.jsonl (OpenAI embeddings of every chunk),
  graph.json (the built graph);
- DATA_DIR/llm_cache/: every AI answer so far, keyed by the prompt, so the 13.4 upload, the spec-update agent and
  the chat give the same answers instantly (only with the same OPENAI_MODEL, see manifest.json).
Not in it: uploaded versions (data/ingested) and Postgres. After the import the teammate resets to the starting
point and uploads VB 13.4 in the UI, as in the demo; the cache makes that run identical.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

from tools.reset_baseline import ROOT, data_dir

BUILD = ROOT / "kg" / "build"


def _files() -> list[tuple[Path, str]]:
    """(file on disk, name in the zip)"""
    out = [(p, f"kg/build/{p.relative_to(BUILD).as_posix()}") for p in sorted(BUILD.rglob("*")) if p.is_file()]
    cache = data_dir() / "llm_cache"
    out += [(p, f"llm_cache/{p.relative_to(cache).as_posix()}") for p in sorted(cache.rglob("*")) if p.is_file()]
    return out


def export(target: Path) -> Path:
    from dotenv import load_dotenv

    load_dotenv()
    files = _files()
    if not (BUILD / "embeddings.jsonl").exists():
        sys.exit("kg/build/embeddings.jsonl is missing: build the graph first (python -m kg.build)")
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], check=False, cwd=ROOT, capture_output=True, text=True).stdout.strip()
    manifest = {"created": date.today().isoformat(), "commit": commit,
                "openai_model": os.environ.get("OPENAI_MODEL"), "spec_baseline": os.environ.get("SPEC_BASELINE"),
                "files": len(files), "llm_answers": sum(1 for _, n in files if n.startswith("llm_cache/"))}
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
        for path, name in files:
            z.write(path, name)
    print(f"wrote {target} ({target.stat().st_size / 1e6:.0f} MB): {manifest}")
    return target


def import_(source: Path) -> None:
    cache = data_dir() / "llm_cache"
    with zipfile.ZipFile(source) as z:
        manifest = json.loads(z.read("manifest.json"))
        for info in z.infolist():
            name = info.filename
            if name == "manifest.json" or name.endswith("/"):
                continue
            if name.startswith("kg/build/"):
                dest = BUILD / name.removeprefix("kg/build/")
            elif name.startswith("llm_cache/"):
                dest = cache / name.removeprefix("llm_cache/")
            else:
                continue
            dest = dest.resolve()
            if not (dest.is_relative_to(BUILD.resolve()) or dest.is_relative_to(cache.resolve())):
                sys.exit(f"refusing to write outside kg/build and llm_cache: {name}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(info))
    print(f"imported {source}: {manifest}")
    model = os.environ.get("OPENAI_MODEL")
    if manifest.get("openai_model") and model != manifest["openai_model"]:
        print(f"note: the cached AI answers were made with OPENAI_MODEL={manifest['openai_model']}; "
              f"set the same in .env (now {model!r}) or the AI is asked again")
    print("next: python -m tools.reset_baseline   (with SPEC_BASELINE=VB@13.3, Docker running, API stopped)")


def main(argv: list[str]) -> None:
    from dotenv import load_dotenv

    load_dotenv()
    if len(argv) >= 1 and argv[0] == "export":
        export(Path(argv[1]) if len(argv) > 1 else ROOT / "bundles" / f"kg-bundle-{date.today().isoformat()}.zip")
    elif len(argv) == 2 and argv[0] == "import":
        import_(Path(argv[1]))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
