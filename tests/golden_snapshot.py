"""Snapshot of what the engine produces today, so refactoring cannot change it unnoticed.

Covers, for every test case of the full seed and every rule set version: the expected decision, the
expected files (TEEL0 per round, TEEK0 per insurer reply); for every seed submission: the check result
per validity date; and the insurer replies of a full Peter run.

Deliberately left out: explanation texts and spec sources (they change on purpose when the texts become
German and the Beispielpapier citations are fixed). Rule IDs, labels, fields and values are in.

Regenerate only on purpose, after reviewing why the output changed:

    uv run python -m tests.golden_snapshot
"""

from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

GOLDEN = Path(__file__).resolve().parent / "golden" / "engine.json"
RUN_VALID_ON = date(2027, 1, 1)


def _s(v: Any) -> Any:
    return v if v is None or isinstance(v, (str, int, bool)) else str(v)


def chains(kb) -> dict[str, Any]:
    from engine import families
    from engine.expected import build_chain, load_scenario
    from engine.rules import params as params_mod
    from engine.writer_messages import chain_files

    known = {f.id for f in families.all_families()}
    out: dict[str, Any] = {}
    for ref in sorted(kb.get_test_cases(include_hidden=True), key=lambda t: t.key):
        if (ref.family or families.DEFAULT) not in known:  # not built yet (ta-168 before G4)
            out[ref.key] = {"family_not_built": ref.family}
            continue
        per_version: dict[str, Any] = {}
        for v in params_mod.all_versions(kb):
            try:
                ch = build_chain(load_scenario(kb, ref.key), v, kb)
            except Exception as exc:  # noqa: BLE001 - a failing case is part of the snapshot too
                per_version[v] = {"error": f"{exc.__class__.__name__}: {exc}"}
                continue
            d = ch.decision
            per_version[v] = {
                "send_41": d.send,
                "chain": [[str(a.start), str(a.end)] for a in d.chain],
                "total_days": d.total_days,
                "failed": d.trace.failed,
                "efz": {k: str(x) for k, x in ch.efz.items()},
                "messages": [[m.step, m.round, m.actor, m.abgabegrund] for m in ch.messages],
                "files": chain_files(ch, ref.key, kb),
            }
        out[ref.key] = per_version
    return out


def checks(kb) -> dict[str, Any]:
    from engine.checker import check
    from tools.make_submissions import build_submissions

    out: dict[str, Any] = {}
    for s in build_submissions(kb):
        for valid_on in sorted(s.expected_label):
            res = check(kb, s.test_case_id, list(s.files.values()), date.fromisoformat(valid_on))
            out[f"{s.id}@{valid_on}"] = {
                "version": res.version,
                "label": res.label,
                "counts": dict(sorted(res.counts.items())),
                "deviations": [
                    {"step": d.step, "abgabegrund": d.abgabegrund, "record": d.record, "field": d.field,
                     "kind": d.kind, "label": d.label, "rule": d.rule, "expected": _s(d.expected),
                     "actual": _s(d.actual), "resolved_by": d.resolved_by}
                    for d in res.deviations
                ],
            }
    return out


def peter_run(kb) -> dict[str, Any]:
    from engine import runs
    from engine.expected import build_chain, load_scenario
    from engine.writer_messages import chain_files

    ch = build_chain(load_scenario(kb, "peter"), "13.4", kb)
    files = {k: v for k, v in chain_files(ch, "peter", kb).items() if k.startswith("TEEL0")}
    st, _ = runs.start(kb, "peter", RUN_VALID_ON)
    rounds = []
    for r in range(1, st.last_round + 1):
        name = f"TEEL0-peter-r{r}"
        res = runs.submit(kb, st, [files[name]] if name in files else [])
        rounds.append({"round": res.round, "ended": res.ended, "reply_name": res.reply_name, "reply": res.reply,
                       "outcomes": sorted([o.rule, o.outcome] for o in res.outcomes)})
    return {"last_round": st.last_round, "status": st.status, "rounds": rounds}


def snapshot(kb) -> dict[str, Any]:
    return {"chains": chains(kb), "checks": checks(kb), "peter_run": peter_run(kb)}


def dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> None:
    from kg.yaml_backend import YamlBackend

    with tempfile.TemporaryDirectory() as tmp:
        kb = YamlBackend(precedents_path=Path(tmp) / "precedents.yaml")
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(dumps(snapshot(kb)), encoding="utf-8", newline="\n")
    print(f"wrote {GOLDEN}")


if __name__ == "__main__":
    main()
