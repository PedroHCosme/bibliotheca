"""Compare fusion rules on the FLOOR-400 indexes, offline.

`recall_debug` showed the main loss: a chunk ranked 1 by one ranker and absent from the other
scores 1/(60+1) = 0.016, below a chunk sitting at rank 5 in both (2/65 = 0.031). Each variant
below changes only how the two ranked lists become one score; everything else is untouched.
"""
import json

from biblio import paths, search
from scripts.eval import floor

CORPORA = ("robotics", "organized", "scrambled")


def rrf_with(k: float, combine) -> object:
    def fuse(lists: list[list]) -> dict:
        scores: dict = {}
        for lst in lists:
            for position, key in enumerate(lst, start=1):
                value = 1 / (k + position)
                scores[key] = combine(scores[key], value) if key in scores else value
        return scores
    return fuse


VARIANTS = {
    # name: (fusion function, heading bonus)
    "rrf-60 (current)": (rrf_with(60, lambda a, b: a + b), 0.03),
    "rrf-10": (rrf_with(10, lambda a, b: a + b), 0.03),
    "rrf-1": (rrf_with(1, lambda a, b: a + b), 0.03),
    "max-60": (rrf_with(60, max), 0.03),
    "max-10": (rrf_with(10, max), 0.03),
    "rrf-60 no heading bonus": (rrf_with(60, lambda a, b: a + b), 0.0),
}


def main() -> None:
    paths.REGISTRY = floor.SWEEP / "registry.txt"
    original, bonus = search.rrf, getattr(search, "BONUS_HEADING", 0.03)
    rows = []
    try:
        for name, (fuse, heading) in VARIANTS.items():
            search.rrf, search.BONUS_HEADING = fuse, heading
            for corpus in CORPORA:
                names = floor.cache_raw(corpus)
                row = floor.measure(corpus, 400, names) | {"variant": name}
                rows.append(row)
                print(f"{name:<24} {corpus:<10} recall={row['recall']:.3f} "
                      f"targeted={row['recall_targeted']:.3f} score={row['score']}", flush=True)
    finally:
        search.rrf, search.BONUS_HEADING = original, bonus
    (floor.SWEEP / "fusion.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
