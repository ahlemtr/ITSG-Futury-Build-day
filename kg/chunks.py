"""Chunks for retrieval: a passage split into overlapping pieces of about CHUNK_CHARS
characters at sentence borders, so search ranks the part of a long passage that matches, not the whole passage.
Short passages are one chunk. Chunk keys: <passage key>~<n>."""

from __future__ import annotations

import re

CHUNK_CHARS = 1000
OVERLAP_CHARS = 200
_SENTENCE = re.compile(r"(?<=[.!?:;])\s+(?=[A-ZÄÖÜ0-9„\"(])")
_WORD = re.compile(r"[\wÄÖÜäöüß]{3,}")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(" ".join(text.split())) if s.strip()]


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    parts = sentences(text)
    if not parts:
        return []
    out: list[str] = []
    cur: list[str] = []
    for s in parts:
        while len(s) > size:  # a sentence longer than a chunk (tables): cut it
            head, s = s[:size], s[size - overlap:]
            if cur:
                out.append(" ".join(cur))
                cur = []
            out.append(head)
        if cur and len(" ".join(cur)) + 1 + len(s) > size:
            out.append(" ".join(cur))
            tail: list[str] = []  # carry the last sentences (up to `overlap` characters) into the next chunk
            for prev in reversed(cur):
                if len(" ".join([prev, *tail])) > overlap:
                    break
                tail.insert(0, prev)
            cur = tail
        cur.append(s)
    if cur:
        out.append(" ".join(cur))
    return out


def passage_chunks(p: dict) -> list[dict]:
    """Chunks of one passage (dict as in passages.yaml); the heading leads every chunk so it keeps its context."""
    heading = p.get("heading") or ""
    return [{"key": f"{p['key']}~{n}", "passage": p["key"], "n": n, "text": t, "heading": heading}
            for n, t in enumerate(chunk_text(p.get("text") or ""))]


def snippet(text: str, query: str, width: int = 320) -> str:
    """The sentence of `text` that shares the most words with the query (shortened to `width`)."""
    words = {w.lower() for w in _WORD.findall(query)}
    best, best_hits = "", -1
    for s in sentences(text):
        hits = sum(1 for w in _WORD.findall(s) if w.lower() in words or any(w.lower().startswith(q) for q in words))
        if hits > best_hits:
            best, best_hits = s, hits
    return best if len(best) <= width else best[: width - 1].rstrip() + "…"
