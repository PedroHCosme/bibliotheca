"""Hybrid search. Returns path, lines, score, and heading. Never the body."""
from pathlib import Path

import numpy as np

from biblio import db, embed
from biblio.paths import known_bibliothecas, register, all_libs

# Two rankers, not the paper's dozen: K=60 makes rank 5 in both beat rank 1 in either.
# Measured on 60 gold questions (scripts/eval/results/fusion.md).
K_RRF = 1
MULTIPLE = 4


def rrf(lists: list[list]) -> dict:
    """1/(K + position) per list, summed."""
    scores: dict = {}
    for lst in lists:
        for position, key in enumerate(lst, start=1):
            scores[key] = scores.get(key, 0.0) + 1 / (K_RRF + position)
    return scores


def _interval(filepath: str, row: dict, context: str) -> tuple[int, int]:
    """`window`: just the matched chunk. `section` (default): the entire slice."""
    if context == "window":
        return row["line_start"], row["line_end"]
    try:
        n = len(Path(filepath).read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return row["line_start"], row["line_end"]
    return 1, n


def search(query: str, output=None, top: int = 5, doc: str | None = None,
           context: str = "section", no_frecency: bool = False) -> list[dict]:
    """Covers all registered bibliothecas, unless `output` (path or list) restricts."""
    candidates = top * MULTIPLE
    vector = embed.vectorize_query(query)
    vec_f16 = np.asarray(vector, dtype="float16").tobytes()

    lists: list[list] = []
    rows: dict = {}
    frecency_scores: dict[tuple, float] = {}
    connections: dict[Path, object] = {}
    for bibliotheca in all_libs(output):
        if not (bibliotheca / db.DB_FILE).exists():
            if output is None:
                continue
            raise SystemExit(
                f'{bibliotheca}: not a biblio bibliotheca (missing {db.DB_FILE}).\n'
                f'Pass the folder path, or a name from `biblio libs`.')
        if output is not None and str(bibliotheca.resolve()) not in known_bibliothecas():
            register(bibliotheca)
        con = db.connect(bibliotheca)
        connections[bibliotheca] = con
        rankings = [db.search_vector(con, vector, candidates, doc),
                    db.search_fts(con, query, candidates, doc)]

        if not no_frecency:
            cand_ids = {i for r in rankings for i in r}
            for cid, sc in db.ranked_by_frecency(con, vector, cand_ids):
                frecency_scores[(bibliotheca, cid)] = sc

        for chunk_id, row in db.details(
                con, list({i for r in rankings for i in r})).items():
            rows[(bibliotheca, chunk_id)] = row
        lists += [[(bibliotheca, i) for i in r] for r in rankings]

    try:
        scored = rrf(lists)

        for key in list(scored):
            if key in frecency_scores:
                scored[key] += min(frecency_scores[key] / db.BONUS_SCALE, db.MAX_BONUS)

        results: list[dict] = []
        result_keys: list[tuple[Path, int]] = []
        seen: set[str] = set()
        for (bibliotheca, chunk_id), score in sorted(scored.items(),
                                                     key=lambda p: -p[1]):
            row = rows.get((bibliotheca, chunk_id))
            if row is None:
                continue
            filepath = str((bibliotheca / row["doc"] / row["file"]).resolve())
            if filepath in seen:
                continue
            seen.add(filepath)
            start, end = _interval(filepath, row, context)
            results.append({
                "path": filepath, "doc": row["doc"], "file": row["file"],
                "section": row["section"], "line_start": start,
                "line_end": end, "score": round(score, 4),
            })
            result_keys.append((bibliotheca, chunk_id))
            if len(results) == top:
                break

        if not no_frecency and result_keys:
            for bib in {b for b, _ in result_keys}:
                db.save_last_query_vec(connections[bib], vec_f16)

        return results
    finally:
        for con in connections.values():
            con.close()


def format_results(results: list[dict]) -> str:
    if not results:
        return "no results"
    return "\n".join(
        f"{r['path']}:{r['line_start']}-{r['line_end']}"
        f"  {r['score']:.3f}  {r['section']}"
        for r in results
    )
