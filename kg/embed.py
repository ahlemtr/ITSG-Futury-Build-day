"""Step K9.4: OpenAI embeddings per passage, cached by sha256 of the input (08 section 12.4).

Without OPENAI_API_KEY the step is skipped; search then uses the full-text index.
"""

from __future__ import annotations

import functools
import hashlib
import json
from pathlib import Path

from kg.common import BUILD_DIR, env

MAX_CHARS = 12_000  # German spec text runs about 2.5 characters per token; the model takes 8192 tokens
BATCH = 100
CACHE = BUILD_DIR / "embeddings.jsonl"


def model() -> str:
    return env("OPENAI_EMBED_MODEL", "text-embedding-3-small")


def passage_input(heading: str | None, text: str | None) -> str:
    return f"{heading or ''}\n{text or ''}"[:MAX_CHARS]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_cache(path: Path = CACHE) -> dict[tuple[str, str], list[float]]:
    out = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    out[(row["sha256"], row["model"])] = row["vector"]
    return out


def embed_texts(texts: list[str], path: Path = CACHE) -> list[list[float]]:
    """Vectors for texts, calling OpenAI only on cache misses."""
    m = model()
    cache = read_cache(path)
    missing = list(dict.fromkeys(t for t in texts if (sha(t), m) not in cache))
    if missing:
        from openai import OpenAI

        client = OpenAI(api_key=env("OPENAI_API_KEY"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for i in range(0, len(missing), BATCH):
                chunk = missing[i:i + BATCH]
                resp = client.embeddings.create(model=m, input=chunk)
                for text, item in zip(chunk, resp.data):
                    cache[(sha(text), m)] = item.embedding
                    f.write(json.dumps({"sha256": sha(text), "model": m, "vector": item.embedding}) + "\n")
                print(f"  embedded {min(i + BATCH, len(missing))}/{len(missing)}")
    return [cache[(sha(t), m)] for t in texts]


def available() -> bool:
    return bool(env("OPENAI_API_KEY"))


@functools.lru_cache(maxsize=512)
def _query_vector(text: str, model_name: str) -> tuple[float, ...]:
    from openai import OpenAI

    resp = OpenAI(api_key=env("OPENAI_API_KEY")).embeddings.create(model=model_name, input=[text])
    return tuple(resp.data[0].embedding)


def embed_query(text: str) -> list[float]:
    """Vector for a search query: cached in memory per process, never written to the passage cache file."""
    return list(_query_vector(text[:MAX_CHARS], model()))


def ensure_index(session, dimensions: int) -> None:
    """Vector index sized for the vectors actually stored; an index of another size is recreated."""
    rows = [r.data() for r in session.run(
        "SHOW INDEXES YIELD name, options WHERE name = 'passage_embedding' RETURN options")]
    if rows:
        config = (rows[0]["options"] or {}).get("indexConfig", {})
        if config.get("vector.dimensions") == dimensions:
            return
        session.run("DROP INDEX passage_embedding IF EXISTS")
    session.run(
        "CREATE VECTOR INDEX passage_embedding IF NOT EXISTS FOR (p:Passage) ON p.embedding "
        f"OPTIONS {{indexConfig: {{`vector.dimensions`: {int(dimensions)}, "
        "`vector.similarity_function`: 'cosine'}}"
    )


def run(driver) -> None:
    with driver.session() as s:
        if not available():
            print("embed: skipped, OPENAI_API_KEY not set (search falls back to the full-text index)")
            return
        rows = [r.data() for r in s.run("MATCH (p:Passage) RETURN p.key AS key, p.heading AS heading, p.text AS text")]
        rows = [r for r in rows if (r["heading"] or r["text"])]
        vectors = embed_texts([passage_input(r["heading"], r["text"]) for r in rows])
        if not vectors:
            return
        data = [{"key": r["key"], "vector": v} for r, v in zip(rows, vectors, strict=True)]
        for i in range(0, len(data), 500):
            s.run("UNWIND $rows AS r MATCH (p:Passage {key: r.key}) SET p.embedding = r.vector", rows=data[i:i + 500])
        ensure_index(s, len(vectors[0]))  # the model (OPENAI_EMBED_MODEL) decides the size, not a constant
        s.run("CALL db.awaitIndexes(300)")
        print(f"embed: {len(data)} passages, model {model()}, {len(vectors[0])} dimensions")
