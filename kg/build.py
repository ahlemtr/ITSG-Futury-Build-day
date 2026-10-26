"""Entry point: python -m kg.build [--skip-extract] [--skip-load] [--skip-embed]

Run order (08 section 12): extract -> build -> validate -> load -> embed.
"""

from __future__ import annotations

import argparse
import sys

from kg import extract, seed_graph, validate
from kg.common import BUILD_DIR, LAYOUT_DIR, SEED_DIR


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m kg.build", description=__doc__)
    ap.add_argument("--skip-extract", action="store_true", help="reuse kg/build/passages.yaml")
    ap.add_argument("--skip-load", action="store_true", help="no Neo4j (implies --skip-embed)")
    ap.add_argument("--skip-embed", action="store_true", help="no OpenAI embeddings")
    args = ap.parse_args(argv)

    if args.skip_extract and (BUILD_DIR / "passages.yaml").exists():
        print("extract: skipped, using kg/build/passages.yaml")
    else:
        print("extract: passages from sources/")
        extract.run(SEED_DIR, LAYOUT_DIR, BUILD_DIR)

    graph = seed_graph.build(SEED_DIR, LAYOUT_DIR, BUILD_DIR / "passages.yaml")
    path = seed_graph.write(graph, BUILD_DIR)
    seed_graph.print_counts(*seed_graph.counts(graph), f"build: {path.relative_to(BUILD_DIR.parent.parent)}")

    errors, warnings = validate.validate(graph)
    validate.report(errors, warnings)
    if errors:
        return 1

    if args.skip_load:
        print("load: skipped")
        return 0
    from kg import load

    driver = load.connect()
    try:
        load.load(graph, driver)
        seed_graph.print_counts(*load.db_counts(driver), "load: Neo4j")
        if args.skip_embed:
            print("embed: skipped")
        else:
            from kg import embed

            embed.run(driver)
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
