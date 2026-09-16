# FLOOR sweep (offline)

Spec step 4. No agents: each corpus is re-sliced at FLOOR 400 / 1500 / 3000, re-indexed, and
every gold question is used as a `biblio search` query. A gold location counts as found when one
of the **top 3** hits is a slice of the gold document containing the gold anchor. Cost is the text
the agent would read to see those 3 slices (chars / 4, frontmatter included).
**Score = tokens read per query / recall@3 — lower is better.**

Reproduce: `python -m scripts.eval.floor` (results in `scripts/eval/data/floor/`).

| corpus | FLOOR | slices | recall@3 | targeted | thematic | tokens/query | score |
|---|---:|---:|---:|---:|---:|---:|---:|
| robotics | **400** | 365 | 0.59 | 0.70 | 0.53 | 1675 | **2858** |
| robotics | 1500 | 229 | 0.55 | 0.70 | 0.47 | 2763 | 5009 |
| robotics | 3000 | 154 | 0.55 | 0.70 | 0.47 | 4022 | 7291 |
| organized | **400** | 2901 | 0.18 | 0.14 | 0.21 | 1355 | **7588** |
| organized | 1500 | 1473 | 0.21 | 0.21 | 0.21 | 2192 | 10231 |
| organized | 3000 | 908 | 0.21 | 0.29 | 0.14 | 3183 | 14858 |
| scrambled | 400 | 282 | 0.31 | 0.40 | 0.25 | 2133 | 6788 |
| scrambled | **1500** | 150 | 0.46 | 0.67 | 0.30 | 2691 | **5887** |
| scrambled | 3000 | 106 | 0.40 | 0.53 | 0.30 | 3458 | 8647 |

## Reading

**Keep FLOOR = 400.** It wins robotics and organized outright, and loses scrambled only because
larger slices there recover targeted recall (0.40 → 0.67). Nothing in the sweep justifies changing
the default: bigger slices cost tokens in proportion to their size while recall stays flat.

**The real finding is the level, not the ranking.** Recall@3 never exceeds 0.59, and on the
organized corpus it is 0.18. Slice size is not the bottleneck — retrieval is. That matches the
baseline, where arm C (slices) lost to arm A (raw sources) on the organized corpus.

## Method notes

- Text is reconstructed from the baseline bibliotheca's slices instead of re-converting the PDFs,
  so the sweep varies only the FLOOR. Page markers do not survive the round trip, so swept slices
  carry no page fields; the metric does not use them.
- Tokens are chars / 4. The comparison is between FLOORs, so the constant cancels.
