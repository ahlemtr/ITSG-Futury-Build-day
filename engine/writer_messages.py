"""Expected chain -> files (P3.3). Employer messages become TEEL0 files (the model solution),
insurer replies TEEK0 files. The envelope (VOSZ, DSKO, NCSZ) is copied from the ITSG reference
file: its content is not graded (plan/05 section 4)."""

from __future__ import annotations

from pathlib import Path

from engine.expected import ChainResult
from engine.model import ExpectedMessage
from engine.records import write_dslw
from kg.interface import KnowledgeBase

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "fixtures" / "itsg" / "TEEL0-Test1-DBVO"
NL = "\r\n"


def _envelope() -> tuple[list[str], list[str]]:
    lines = TEMPLATE.read_text(encoding="utf-8").splitlines()
    return [x for x in lines if x[:4] in ("VOSZ", "DSKO")], [x for x in lines if x.startswith("NCSZ")]


def write_message(m: ExpectedMessage, kb: KnowledgeBase) -> str:
    return write_dslw(m.head, m.blocks, kb)


def write_file(messages: list[ExpectedMessage], kb: KnowledgeBase, envelope: bool = True) -> str:
    head, tail = _envelope() if envelope else ([], [])
    return NL.join(head + [write_message(m, kb) for m in messages] + tail) + NL


def chain_files(chain: ChainResult, test_case_id: str, kb: KnowledgeBase) -> dict[str, str]:
    """One TEEL0 file per round (employer messages of that round), one TEEK0 file per insurer reply."""
    files: dict[str, str] = {}
    rounds = sorted({m.round for m in chain.messages if m.actor == "employer"})
    for r in rounds:
        msgs = [m for m in chain.messages if m.actor == "employer" and m.round == r]
        files[f"TEEL0-{test_case_id}-r{r}"] = write_file(msgs, kb)
    for m in chain.messages:
        if m.actor == "insurer":
            files[f"TEEK0-{test_case_id}-s{m.step}-{m.abgabegrund}"] = write_file([m], kb)
    return files


def save(files: dict[str, str], folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for name, text in files.items():
        p = folder / name
        p.write_bytes(text.encode("utf-8"))
        out.append(p)
    return out
