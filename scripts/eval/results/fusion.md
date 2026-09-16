# Fusion sweep (offline)

Follows the per-miss diagnosis (`scripts/eval/recall_debug.py`): 30 of 59 missed gold locations
were `fused-away` — the correct chunk ranked 1 or 2 in one ranker, far down in the other, and
RRF dropped it. Each variant changes only how two ranked lists become one score. Same harness as
the FLOOR sweep: FLOOR 400, top 3, all 60 gold questions.

Reproduce: `python -m scripts.eval.fusion` (writes `scripts/eval/data/floor/fusion.json`).

recall@3 / score (tokens read per query / recall — lower is better):

| variant | robotics | organized | scrambled |
|---|---|---|---|
| `rrf-60` + heading bonus (current) | 0.59 / 2858 | 0.18 / 7588 | 0.31 / 6788 |
| `rrf-60`, no heading bonus | 0.59 / 3638 | 0.36 / 3564 | 0.34 / 6849 |
| `rrf-10` | 0.59 / 3587 | 0.32 / 3929 | 0.31 / 7483 |
| `rrf-1` | 0.66 / 2427 | 0.39 / 3223 | 0.34 / 7183 |
| **`rrf-1`, no heading bonus** | **0.66 / 2393** | **0.43 / 2972** | **0.37 / 6621** |
| `rrf-0`, no heading bonus | 0.66 / 2375 | 0.43 / 3020 | 0.37 / 6624 |
| `rrf-3`, no heading bonus | 0.55 / 3032 | 0.43 / 2977 | 0.34 / 7162 |
| `max-60` (best list wins) | 0.45 / 6677 | 0.14 / 9214 | 0.26 / 7669 |
| `max-10` | 0.62 / 2524 | 0.39 / 3269 | 0.34 / 6731 |

## Two separate defects, both confirmed

**`K_RRF = 60` is far too large for two rankers.** With K=60 a chunk ranked 1 by one ranker scores
0.0164, while a chunk sitting at rank 5 in both scores 0.0308: agreement beats correctness. K=1
keeps the agreement bonus (rank 1 alone = 0.500, ranks 2+2 = 0.667) without letting it overrule a
clear single-ranker winner. K=60 is the value from the original RRF paper, where it fuses many
weak rankers — not two strong, complementary ones.

**`BONUS_HEADING = 0.03` is larger than any RRF score it adjusts.** At K=60 the entire fused score
is ~0.016–0.05, so a query-word match in a heading outweighs every ranking signal. Removing it
alone doubles organized recall (0.18 -> 0.36). Taking `max` instead of the sum is *worse* than the
current rule — the agreement signal is real, it was just drowning the single-ranker one.

## Recommendation for the candidate

`K_RRF = 1`, drop `BONUS_HEADING`. Two constants, no new code:
organized recall 0.18 -> 0.43 (targeted 0.14 -> 0.50), robotics 0.59 -> 0.66 (targeted 0.70 ->
0.80), scrambled 0.31 -> 0.37; score improves on all three corpora.

**Caveat:** K is tuned on 60 questions. K=0, 1 and 3 differ by a couple of locations, so treat the
exact value as noise and the order of magnitude as the finding. The agent-level candidate run is
what confirms it; this sweep only says which variant is worth spending runs on.
