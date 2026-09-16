"""Why a gold anchor is missed: no slice holds it, no ranker surfaces it, or RRF drops it.

Only locations that `search()` actually misses at top 3 are classified — a location it finds
needs no explanation, and counting those as anything would overstate every failure mode.

Runs over the FLOOR-sweep indexes (`scripts.eval.floor`), so it needs no agents and no
re-conversion. For every gold location it reports the best rank the anchor's slice reaches in
the vector list and in the FTS list, each taken alone and far deeper than search() ever looks.
"""
import sys
from pathlib import Path

from biblio import db, embed, paths, search
from scripts.eval import arms, floor, gold

DEPTH = 500
CANDIDATES = 5 * search.MULTIPLE  # what search() actually pulls from each ranker


def slices_with(folder: Path, anchor: str) -> set[str]:
    return {f.name for f in folder.glob("[0-9]*.md")
            if anchor in gold.normalize(f.read_text(encoding="utf-8"))}


def best_rank(ids: list[int], con, doc: str, files: set[str]) -> int | None:
    rows = db.details(con, ids)
    for position, chunk_id in enumerate(ids, start=1):
        row = rows.get(chunk_id)
        if row and row["doc"] == doc and row["file"] in files:
            return position
    return None


def verdict(hit: set[str], vec: int | None, fts: int | None) -> str:
    if not hit:
        return "no-slice"          # slicing lost it: no single slice holds the anchor
    if vec is None and fts is None:
        return "not-retrieved"     # in a slice, but neither ranker reaches it at all
    if (vec or DEPTH) > CANDIDATES and (fts or DEPTH) > CANDIDATES:
        return "out-of-pool"       # ranked, but below what search() even fuses
    return "fused-away"            # a ranker had it in the pool; RRF put it out of the top


def main(argv=None) -> None:
    corpus = (argv or sys.argv[1:] or ["robotics"])[0]
    paths.REGISTRY = floor.SWEEP / "registry.txt"
    names = floor.cache_raw(corpus)
    bib = floor.bib_dir(corpus, 400)
    con = db.connect(bib)
    counts: dict[str, int] = {}
    try:
        for q in gold.load(arms.DATA / "gold" / f"{corpus}.jsonl"):
            vector = embed.vectorize_query(q["question"])
            vec_ids = db.search_vector(con, vector, DEPTH)
            fts_ids = db.search_fts(con, q["question"], DEPTH)
            found = {(h["doc"], h["file"]) for h in
                     search.search(q["question"], output=bib, top=floor.TOP, no_frecency=True)}
            for loc in q["locations"]:
                doc = names.get(loc["file"].replace("\\", "/"))
                hit = slices_with(bib / doc, gold.normalize(loc["anchor"])) if doc else set()
                if any((doc, f) in found for f in hit):
                    counts["found"] = counts.get("found", 0) + 1
                    continue
                vec = best_rank(vec_ids, con, doc, hit) if hit else None
                fts = best_rank(fts_ids, con, doc, hit) if hit else None
                v = verdict(hit, vec, fts)
                counts[v] = counts.get(v, 0) + 1
                print(f"{q['id']:>4} {q['kind']:<8} {v:<14} slices={len(hit)} "
                      f"vector={vec} fts={fts}", flush=True)
    finally:
        con.close()
    print(f"\n{corpus}: {counts}")


if __name__ == "__main__":
    main()
