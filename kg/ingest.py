"""Spec upload pipeline (SPEC_UPDATE_WORKFLOW.md section 2): a new document version goes in, the knowledge graph
and the test catalogue come out updated.

store -> chunk -> embed -> diff -> map -> analyse -> apply -> catalogue

What the upload learned is written as an overlay folder (DATA_DIR/ingested/<doc>@<version>/) that the seed build
loads on top of the starting point (kg.seed_graph.load_overlays), so both KG backends see it and Neo4j gets it
through the normal load. The AI only answers (llm.agents.change_analysis); this module validates nothing it did
not ask for and writes everything itself. Progress is stored as a job (Postgres `ingest_job`) after every stage.
"""

from __future__ import annotations

import logging
import re
import shutil
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

from kg.common import ROOT, dump_yaml, env, load_layouts, load_yaml

log = logging.getLogger(__name__)

STAGES = [
    ("store", "File stored"),
    ("chunk", "Chunked into passages"),
    ("embed", "Passages embedded"),
    ("diff", "Diffed against the previous version"),
    ("map", "Changes mapped to rules"),
    ("analyse", "AI analysis of the changes"),
    ("apply", "Knowledge graph updated"),
    ("catalogue", "Test catalogue recomputed"),
]

VALID_FROM_RE = re.compile(r"(?:gültig\s+)?ab[\s_]+(\d{2})\.(\d{2})\.(\d{4})", re.IGNORECASE)
VERSION_RE = re.compile(r"Version[\s_]+(\d+(?:\.\d+)+)", re.IGNORECASE)
DATED_FILE_RE = re.compile(r"^(\d{4})_(\d{2})_(\d{2})_")  # Rundschreiben: "2025_12_10_NS_FLB_..."
CALC_RE = re.compile(r"\d+(?:,\d+)?\s*(?:Prozent|%|v\. ?H\.|Wochen|Tage|Kalendertage|Monate|Jahre|Euro|EUR|€)",
                     re.IGNORECASE)
MESSAGE_TYPES = ["01", "02", "03", "41", "51", "61", "62", "88"]


def now() -> str:
    return datetime.now(UTC).isoformat()


def ingested_root() -> Path:
    from kg.seed_graph import ingested_dir

    return ingested_dir()


def guess(filename: str, text: str = "") -> dict:
    """Version and valid-from date from the file name or the first page ("Version 13.4 ab 01.01.2027")."""
    out: dict = {}
    for source in (filename, text[:4000]):
        if "version" not in out and (m := VERSION_RE.search(source)):
            out["version"] = m.group(1)
        if "valid_from" not in out and (m := VALID_FROM_RE.search(source)):
            out["valid_from"] = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    if (m := DATED_FILE_RE.match(Path(filename).name)):  # a dated circular: its date is version and validity
        out.setdefault("version", f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
        out.setdefault("valid_from", f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
    return out


def new_job(repo, document: str, version: str, valid_from: date, filename: str, sha256: str) -> dict:
    job = {"id": f"ing-{uuid.uuid4().hex[:10]}", "document": document, "version": version,
           "valid_from": valid_from.isoformat(), "file": filename, "sha256": sha256, "status": "running",
           "created": now(), "stages": [{"name": n, "title": t, "status": "waiting", "counts": {}} for n, t in STAGES],
           "result": {}, "error": None}
    repo.save_job(job["id"], job)
    return job


class Pipeline:
    """Runs one upload. `on_kb` receives the new knowledge base when the graph has been updated."""

    def __init__(self, job: dict, pdf: Path, kb, repo, ai_factory: Callable | None, on_kb: Callable,
                 today: date | None = None):
        self.job, self.pdf, self.kb, self.repo = job, pdf, kb, repo
        self.ai_factory, self.on_kb = ai_factory, on_kb
        self.today = today or date.today()
        self.doc, self.version = job["document"], job["version"]
        self.valid_from = date.fromisoformat(job["valid_from"])
        self.folder = ingested_root() / f"{self.doc}@{self.version}"

    # ---------------------------------------------------------------- bookkeeping
    def stage(self, name: str, status: str, **counts) -> None:
        st = next(s for s in self.job["stages"] if s["name"] == name)
        st["status"] = status
        st["counts"].update(counts)
        if status == "running":
            st.setdefault("started", now())  # progress updates keep the stage's start time
        else:
            st["finished"] = now()
        self.repo.save_job(self.job["id"], self.job)

    def run(self) -> dict:
        current = None
        try:
            for name, _title in STAGES:
                current = name
                self.stage(name, "running")
                getattr(self, f"do_{name}")()
                self.stage(name, "done")
            self.job["status"] = "done"
        except Exception as e:
            log.exception("spec upload %s failed", self.job["id"])
            if current:
                self.stage(current, "failed")
            self.job["status"], self.job["error"] = "failed", f"{type(e).__name__}: {e}"
            self.job["trace"] = traceback.format_exc()[-2000:]
            shutil.rmtree(self.folder, ignore_errors=True)  # a failed upload leaves nothing behind
        self.repo.save_job(self.job["id"], self.job)
        return self.job

    # ---------------------------------------------------------------- stages
    def do_store(self) -> None:
        versions = self.kb.get_versions(self.doc)
        if any(v.version == self.version for v in versions):
            raise ValueError(f"{self.doc} {self.version} is already known")
        older = [v for v in versions if v.valid_from and v.valid_from < self.valid_from]
        self.previous = max(older, key=lambda v: v.valid_from) if older else None
        self.folder.mkdir(parents=True, exist_ok=True)
        target = self.folder / f"{self.doc}@{self.version}{self.pdf.suffix}"
        shutil.copyfile(self.pdf, target)
        self.file = target
        self.job["previous"] = self.previous.version if self.previous else None
        self.stage("store", "running", bytes=target.stat().st_size, previous=self.job["previous"])

    def do_chunk(self) -> None:
        from kg.extract import extract_document

        warnings: list[str] = []
        dv = {"doc": self.doc, "version": self.version, "file": str(self.file)}
        self.passages = extract_document(dv, load_layouts(), self.folder / "text", warnings.append)
        from kg.chunks import passage_chunks

        self.chunks = [c for p in self.passages for c in passage_chunks(p)]
        self.stage("chunk", "running", passages=len(self.passages), chunks=len(self.chunks),
                   sections=len({p["section"] for p in self.passages}), warnings=len(warnings))

    def do_embed(self) -> None:
        from kg import embed

        if not embed.available():
            self.stage("embed", "running", skipped="no OPENAI_API_KEY: full-text search only")
            return
        texts = [embed.passage_input(c["heading"], c["text"]) for c in self.chunks]
        embed.embed_texts(texts)  # cached by content; Neo4j gets the vectors in the apply stage
        self.stage("embed", "running", vectors=len(texts), model=embed.model())

    def do_diff(self) -> None:
        from engine import specdiff

        self.raws: list[dict] = []
        if self.previous:
            old_pdf = Path(self.previous.file)
            old_pdf = old_pdf if old_pdf.is_absolute() else ROOT / old_pdf
            prefix = f"{self.doc}-{self.previous.version}-{self.version}"
            self.raws = [{"tag": c.tag, "block": c.block, "field": c.field,
                          "old": c.old.split("\n") if c.old else [], "new": c.new.split("\n") if c.new else []}
                         for c in specdiff.diff_pdfs(old_pdf, self.file, prefix)]
        document = {"doc": self.doc, "title": self._title(), "version": self.version,
                    "published": self.job.get("published"), "valid_from": self.valid_from,
                    "file": str(self.file), "succeeds": self.previous.version if self.previous else None}
        dump_yaml(document, self.folder / "document.yaml")
        dump_yaml(self.passages, self.folder / "passages.yaml")
        import json

        (self.folder / "diff.json").write_text(json.dumps(self.raws, ensure_ascii=False, indent=1), encoding="utf-8")
        self.stage("diff", "running", changes=len(self.raws),
                   added=sum(1 for r in self.raws if r["tag"] == "insert"),
                   removed=sum(1 for r in self.raws if r["tag"] == "delete"),
                   replaced=sum(1 for r in self.raws if r["tag"] == "replace"))

    def do_map(self) -> None:
        """Raw changes -> modified passages -> rules citing them, on a staged graph with the new version."""
        self.candidates: list[dict] = []
        if not self.previous:
            return
        # the raw changes alone, so the staged graph links them to passages; curated set comes in the analysis
        old = self.previous.version
        dump_yaml({"document": self.doc, "old_version": old, "new_version": self.version, "changes": []},
                  self.folder / "changes.yaml")
        self.staged = _yaml_kb()
        prefix = f"{self.doc}-{old}-{self.version}"
        raws = {c.key: c for c in self.staged.get_changes(self.doc, old, self.version, in_scope_only=False)}
        for i, raw in enumerate(self.raws):
            key = f"{prefix}-{i:03d}"
            change = raws.get(key)
            if change is None:
                continue
            impact = self.staged.get_affected_rules([key])
            rules = impact.review + impact.recompute
            if rules or (self.calculation and CALC_RE.search(f"{change.old}\n{change.new}")):
                self.candidates.append({"key": key, "change": change, "rules": rules})
        self.candidates = self.candidates[:MAX_CANDIDATES]
        self.stage("map", "running", candidates=len(self.candidates),
                   rules=len({r.id for c in self.candidates for r in c["rules"]}))

    @property
    def calculation(self) -> bool:
        """The insurers' circulars: changes are read for calculation rules (W8)."""
        return self.doc.startswith("RS-")

    def do_analyse(self) -> None:
        if self.calculation:
            return self._analyse_calculations()
        old = self.previous.version if self.previous else None
        notes = {p["name"]: p.get("note", "") for p in load_yaml(ROOT / "kg" / "seed" / "parameters.yaml")["parameters"]}
        ai = self.ai_factory(self.staged) if (self.ai_factory and self.candidates) else None
        self.curated, self.param_changes, analysed, rejected = [], {}, 0, 0
        for n, c in enumerate(self.candidates):
            ch = c["change"]
            params = {}
            for r in c["rules"]:
                for name in r.params:
                    params[name] = {"value": self.kb.get_param(name, version=old), "note": notes.get(name, "")}
            answer = None
            if ai is not None:
                answer = ai.analyse_change(
                    {"key": ch.key, "block": ch.block, "field": ch.field, "old_text": ch.old, "new_text": ch.new,
                     "old_passages": ch.modifies_old, "new_passages": ch.modifies_new},
                    [{"id": r.id, "title": r.title, "params": r.params} for r in c["rules"]], params)
                analysed += 1
                rejected += answer is None
            entry = {"key": f"{self.doc}-{old}-{self.version}-C{n:03d}", "raw_keys": [ch.key],
                     "summary": answer.summary if answer else None,
                     "label": answer.label if answer else "unknown",
                     "in_scope": answer.in_scope if answer else True,
                     "changes_param": [p.name for p in answer.param_changes] if answer else [],
                     "modifies_old": ch.modifies_old, "modifies_new": ch.modifies_new,
                     "citations": answer.citations if answer else []}
            for p in (answer.param_changes if answer else []):
                self.param_changes[p.name] = {"value": p.new_value, "reason": p.reason, "change": entry["key"]}
            self.curated.append(entry)
            self.stage("analyse", "running", analysed=analysed, of=len(self.candidates), rejected=rejected,
                       param_changes=len(self.param_changes))
        if ai is None and self.candidates:
            self.stage("analyse", "running", skipped="no AI available: changes kept unlabelled")

    def _analyse_calculations(self) -> None:
        """Rundschreiben: calculation rules per change. Rules the engine does not compute become draft rules
        ("needs implementation"); a value for an engine parameter is a proposal for ITSG, never applied."""
        old = self.previous.version if self.previous else None
        notes = {p["name"]: p.get("note", "") for p in load_yaml(ROOT / "kg" / "seed" / "parameters.yaml")["parameters"]}
        vb = _latest_vb(self.kb)
        params = {n: {"value": self.kb.get_param(n, version=vb), "note": notes.get(n, "")} for n in _param_names()}
        ai = self.ai_factory(self.staged) if (self.ai_factory and self.candidates) else None
        self.curated, self.param_changes, self.calc_rules, self.proposals = [], {}, [], []
        analysed = rejected = 0
        for n, c in enumerate(self.candidates):
            ch = c["change"]
            answer = None
            if ai is not None:
                answer = ai.analyse_calculation(
                    {"key": ch.key, "old_text": ch.old, "new_text": ch.new, "old_passages": ch.modifies_old,
                     "new_passages": ch.modifies_new}, params, MESSAGE_TYPES)
                analysed += 1
                rejected += answer is None
            key = f"{self.doc}-{old}-{self.version}-C{n:03d}"
            in_scope = bool(answer and answer.is_calculation and answer.rules)
            self.curated.append({"key": key, "raw_keys": [ch.key], "summary": answer.summary if answer else None,
                                 "label": "law_change" if in_scope else ("editorial" if answer else "unknown"),
                                 "in_scope": in_scope, "changes_param": [], "modifies_old": ch.modifies_old,
                                 "modifies_new": ch.modifies_new})
            for r in (answer.rules if in_scope else []):
                rid = f"CALC-{self.doc}-{len(self.calc_rules) + 1}"
                self.calc_rules.append({
                    "id": rid, "title": r.title, "description": f"{r.rule} ({r.value}). Needs implementation in the "
                    f"engine; source: {self.doc} {self.version}.", "kind": "calculation", "status": "draft",
                    "applies_to": r.applies_to, "fields": [], "params": [r.parameter] if r.parameter else [],
                    "sources": ch.modifies_new or ch.modifies_old})
                if r.parameter is not None and r.parameter_value != params[r.parameter]["value"]:
                    self.proposals.append({"parameter": r.parameter, "current": params[r.parameter]["value"],
                                           "proposed": r.parameter_value, "rule": rid, "change": key})
            self.stage("analyse", "running", analysed=analysed, of=len(self.candidates), rejected=rejected,
                       calculation_rules=len(self.calc_rules), proposals=len(self.proposals))
        if ai is None and self.candidates:
            self.stage("analyse", "running", skipped="no AI available: changes kept unlabelled")
        dump_yaml(self.calc_rules, self.folder / "rules.yaml")
        self.job["result"]["calculation_rules"] = [r["id"] for r in self.calc_rules]
        self.job["result"]["parameter_proposals"] = self.proposals

    def do_apply(self) -> None:
        old = self.previous.version if self.previous else None
        if self.previous:
            dump_yaml({"document": self.doc, "old_version": old, "new_version": self.version,
                       "changes": self.curated}, self.folder / "changes.yaml")
        values = []
        self.param_changes = getattr(self, "param_changes", {})
        if self.doc == "VB":  # parameters are versioned with the Verfahrensbeschreibung
            for name in _param_names():
                value = self.param_changes[name]["value"] if name in self.param_changes else \
                    self.kb.get_param(name, version=old)
                values.append({"name": name, "version": self.version, "valid_from": self.valid_from, "value": value})
        dump_yaml(values, self.folder / "parameters.yaml")
        kb = _new_kb()
        pushed = _push_to_neo4j() if env("KG_BACKEND", "yaml") == "graph" else None
        self.kb = kb
        self.on_kb(kb)
        self.stage("apply", "running", passages=len(self.passages), changes=len(self.curated),
                   in_scope=sum(1 for c in self.curated if c["in_scope"]),
                   parameters_changed=len(self.param_changes), **({"neo4j": pushed} if pushed else {}))

    def do_catalogue(self) -> None:
        from engine import builder
        from engine.checker import Checker
        from engine.intake import load_files

        # expected results are versioned with the Verfahrensbeschreibung; other documents do not recompute them
        old = self.previous.version if self.previous and self.doc == "VB" else None
        flipped, expected, drafts = [], {}, []
        for tc in self.repo.list_test_cases():
            if old is None:
                continue
            r = builder.recompute(self.kb, [tc], old, self.version)[0]
            tc.expected[self.version] = r.new
            expected[tc.id] = r.new.model_dump(mode="json")
            if r.differs:
                flipped.append(tc.id)
                tc.status = "draft"  # needs re-approval: its expected result changes with the new version
            self.repo.upsert_test_case(tc)
        dump_yaml(expected, self.folder / "expected.yaml")
        recompute_rules = sorted({r.id for name in self.param_changes for r in self._rules_using(name)})
        base = next((t for t in self.repo.list_test_cases() if t.kind == "reference"), None)
        for rule in recompute_rules if base else []:
            try:
                for t in builder.boundaries(self.kb, rule, base):
                    self.repo.upsert_test_case(t)
                    drafts.append(t.id)
            except ValueError:
                continue  # no boundary builder for this rule
        for tid in list(dict.fromkeys(drafts)):
            tc = self.repo.get_test_case(tid)
            if tc and not tc.hidden and builder.recompute(self.kb, [tc], old, self.version)[0].differs:
                h = builder.hidden(self.kb, tc)
                self.repo.upsert_test_case(h)
                drafts.append(h.id)
        # the test cases this upload made become part of the knowledge graph (TestCase nodes, TARGETS rules)
        made = [self.repo.get_test_case(t) for t in dict.fromkeys(drafts)]
        dump_yaml([t.to_kb().model_dump(mode="json") | {"id": t.id} for t in made if t is not None],
                  self.folder / "tests.yaml")
        if made:
            self.on_kb(self._reload_kb())
        rechecked = 0
        if self.valid_from <= self.today:  # the rule set in force changes now: re-check the submissions
            for s in self.repo.list_submissions():
                tc = self.repo.get_test_case(s.test_case_id)
                if tc is None:
                    continue
                self.repo.save_check(s.id, Checker(self.kb).check(tc, list(load_files(s).values()), self.today))
                rechecked += 1
        self.job["result"] = self.job.get("result", {}) | {"flipped": flipped, "drafts": list(dict.fromkeys(drafts)), "rules": recompute_rules,
                              "rechecked": rechecked, "track": "now" if self.valid_from <= self.today else "next"}
        self.stage("catalogue", "running", test_cases=len(expected), flipped=len(flipped),
                   drafts=len(self.job["result"]["drafts"]), rechecked=rechecked)
        self.repo.add_event("spec_upload", {
            "document": self.doc, "version": self.version, "valid_from": self.valid_from.isoformat(),
            "passages": len(self.passages), "changes": len(self.raws),
            "in_scope": sum(1 for c in self.curated if c["in_scope"]) if self.previous else 0,
            "parameters_changed": sorted(self.param_changes), "tests_flipped": flipped,
            "drafts": self.job["result"]["drafts"]})

    # ---------------------------------------------------------------- helpers
    def _title(self) -> str:
        known = next((d for d in load_yaml(ROOT / "kg" / "seed" / "documents.yaml")["documents"]
                      if d["code"] == self.doc), None)
        return known["title"] if known else self.doc

    def _reload_kb(self):
        kb = _new_kb()
        if env("KG_BACKEND", "yaml") == "graph":
            _push_to_neo4j()
        self.kb = kb
        return kb

    def _rules_using(self, param: str):
        seen = {}
        for ag in ("41", "61", "62", "01", "88"):
            for r in self.kb.get_rules(ag, self.version):
                if param in r.params:
                    seen[r.id] = r
        return list(seen.values())


MAX_CANDIDATES = 40  # changes per upload sent to the AI (largest documents: keep the job in minutes)


def _latest_vb(kb) -> str:
    from engine.rules.params import latest

    return latest(kb)


def _param_names() -> list[str]:
    return [p["name"] for p in load_yaml(ROOT / "kg" / "seed" / "parameters.yaml")["parameters"]]


def _yaml_kb():
    from kg.yaml_backend import YamlBackend

    path = env("PRECEDENTS_PATH", "")
    return YamlBackend(precedents_path=Path(path)) if path else YamlBackend()


def _new_kb():
    from kg import get_kb

    return get_kb()


def _push_to_neo4j() -> dict:
    """The seed with every overlay into Neo4j (MERGE by key) and the missing embeddings."""
    from kg import embed, load, seed_graph

    graph = seed_graph.build()
    driver = load.connect()
    try:
        load.load(graph, driver)
        if embed.available():
            embed.run(driver)
        nodes, _edges = load.db_counts(driver)
    finally:
        driver.close()
    return {"nodes": sum(nodes.values()), "passages": nodes.get("Passage", 0)}
