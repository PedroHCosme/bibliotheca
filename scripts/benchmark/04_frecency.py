#!/usr/bin/env python3
"""Frecency ranking benchmark — 6-config matrix comparison.

The corpus is built for HEADROOM: 6 topic clusters of 3 near-duplicate sibling
documents each. The siblings share ~70% of their vocabulary and differ on one
axis (which standard / which method / which context). Vector + FTS alone cannot
reliably tell the siblings apart, so cold retrieval ranks them close to
arbitrarily — often putting the wrong sibling first. The "gold" answer for every
query is one *specific* sibling: the one a simulated work session repeatedly hit.
Frecency's job is to resurface that sibling.

Three query sets, all with real cold headroom:
  reask  — the exact phrase the session used
  easy   — a natural-language paraphrase of the same need
  cross  — phrased with a neighbouring sibling's / cluster's vocabulary

Warm-up per config: for each cluster the session runs its `reask` query and
`biblio hit`s the gold sibling 3x (weight 5). Bibliotheca reset between configs.

Matrix: 3 fusion modes (flat / weighted / bonus) x 2 recording modes
(hits_only / hits+appearances). Cold (no_frecency) is the reference row.

Production ships ONE cell of this matrix — `bonus` fusion + `hits_only`
recording. The other five exist only here: `_rank()` below carries a frozen
local copy of all three fusion strategies plus the weight-1 appearance
recording, so "was deleting flat / weighted / hits+appear the right call"
stays re-runnable after those paths leave `biblio/`.
"""
import os
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
try:
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import sys
from math import exp
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from biblio import db, embed
from biblio.db import _tokens
from biblio.search import MULTIPLE

BONUS_HEADING = 0.03  # removed from biblio.search; kept here so this benchmark still reproduces the old behaviour

# ---------- corpus: 6 clusters x 3 near-duplicate siblings ----------
#
# Each value is (filename, body). The body is deliberately repetitive and
# heavy on the shared cluster vocabulary; exactly one sentence distinguishes
# the sibling. `_x3` at build time pads it to a chunkable length.

def _x3(intro: str, shared: str) -> str:
    return intro + "\n" + (shared + " ") * 3


CLUSTERS: dict[str, dict[str, str]] = {
    # -- 1. anchorage / development length of a reinforcing bar --
    "anchorage": {
        "anchorage_ec2": _x3(
            "# Anchorage length (Eurocode 2)",
            "The anchorage length lets a reinforcing bar develop its full yield "
            "force through bond stress between the bar and the surrounding "
            "concrete. Cover, transverse links and transverse pressure confine "
            "the bar and raise the attainable bond stress, shortening the length. "
            "Hooks and bends reduce a straight anchorage. This clause follows "
            "Eurocode 2: the design anchorage length lbd is the basic required "
            "length lb,rqd scaled by the alpha coefficients."),
        "anchorage_aci": _x3(
            "# Development length (ACI 318)",
            "The development length lets a reinforcing bar develop its full yield "
            "force through bond stress between the bar and the surrounding "
            "concrete. Cover, transverse reinforcement and transverse pressure "
            "confine the bar and raise the attainable bond stress, shortening the "
            "length. Hooks and headed bars reduce a straight embedment. This "
            "clause follows ACI 318: the tension development length ld is a "
            "function of bar diameter, yield strength and the confinement term."),
        "anchorage_fib": _x3(
            "# Anchorage from first principles (fib Model Code)",
            "The anchorage length lets a reinforcing bar develop its full yield "
            "force through bond stress between the bar and the surrounding "
            "concrete. Cover, transverse links and transverse pressure confine "
            "the bar and raise the attainable bond stress, shortening the length. "
            "Hooks and bends reduce a straight anchorage. From first principles "
            "the average bond stress integrated over the embedded bar surface "
            "must equal the bar force, as set out in the fib Model Code."),
    },
    # -- 2. splicing / joining two reinforcing bars in tension --
    "splice": {
        "splice_lap": _x3(
            "# Lap splice",
            "A splice joins two reinforcing bars so tension passes from one to "
            "the other. The transfer length depends on bar diameter, concrete "
            "strength, cover and the amount of transverse reinforcement across "
            "the joint. Staggering splices along the member reduces the peak "
            "demand at any section. In a lap splice the two bars simply overlap "
            "and the force crosses the gap through bond to the concrete."),
        "splice_sleeve": _x3(
            "# Grouted sleeve splice",
            "A splice joins two reinforcing bars so tension passes from one to "
            "the other. The transfer length depends on bar diameter, grout "
            "strength, confinement and the embedment of each bar in the sleeve. "
            "Staggering splices along the member reduces the peak demand at any "
            "section. In a grouted sleeve splice each bar is embedded in a "
            "filled steel sleeve and the force crosses through bond to the grout."),
        "splice_weld": _x3(
            "# Welded splice",
            "A splice joins two reinforcing bars so tension passes from one to "
            "the other. The capacity depends on the weld process, the bar "
            "weldability and the joint preparation rather than on bond length. "
            "Staggering splices along the member reduces the peak demand at any "
            "section. In a welded splice the bars are joined directly by a "
            "full-strength butt weld and no bond transfer length is needed."),
    },
    # -- 3. concrete cover over the reinforcement --
    "cover": {
        "cover_chloride": _x3(
            "# Cover for chloride exposure",
            "The nominal concrete cover is the distance from the concrete "
            "surface to the nearest reinforcing bar. It protects the steel and "
            "is set by the exposure condition, the intended service life and the "
            "concrete quality. Thicker cover and lower water-cement ratio both "
            "help. For chloride exposure near seawater or de-icing salts the "
            "cover is increased to slow chloride ingress to the bar."),
        "cover_carbonation": _x3(
            "# Cover for carbonation",
            "The nominal concrete cover is the distance from the concrete "
            "surface to the nearest reinforcing bar. It protects the steel and "
            "is set by the exposure condition, the intended service life and the "
            "concrete quality. Thicker cover and lower water-cement ratio both "
            "help. For carbonation exposure in humid air the cover is set so the "
            "carbonation front does not reach the bar within the design life."),
        "cover_fire": _x3(
            "# Cover for fire resistance",
            "The nominal concrete cover is the distance from the concrete "
            "surface to the nearest reinforcing bar. It protects the steel and "
            "is set by the exposure condition, the intended service life and the "
            "concrete quality. Thicker cover and lower water-cement ratio both "
            "help. For fire resistance the axis distance to the bar is set so the "
            "steel stays below its critical temperature for the required period."),
    },
    # -- 4. controlling crack width in concrete --
    "crackwidth": {
        "crack_flexural": _x3(
            "# Flexural crack width",
            "Crack width in a concrete member is controlled by limiting the bar "
            "stress and the bar spacing so the tension steel restrains the "
            "cracks to an acceptable opening. Smaller bars at closer spacing "
            "give finer cracks for the same steel area. Here the cracking is "
            "caused by flexural tension under the applied bending moment in "
            "service."),
        "crack_shrinkage": _x3(
            "# Shrinkage restraint cracking",
            "Crack width in a concrete member is controlled by limiting the bar "
            "stress and the bar spacing so the tension steel restrains the "
            "cracks to an acceptable opening. Smaller bars at closer spacing "
            "give finer cracks for the same steel area. Here the cracking is "
            "caused by drying shrinkage of the concrete restrained by the "
            "supports or by older adjacent pours."),
        "crack_thermal": _x3(
            "# Early-age thermal cracking",
            "Crack width in a concrete member is controlled by limiting the bar "
            "stress and the bar spacing so the tension steel restrains the "
            "cracks to an acceptable opening. Smaller bars at closer spacing "
            "give finer cracks for the same steel area. Here the cracking is "
            "caused by early-age heat of hydration: the core expands, the "
            "surface is restrained, and it cracks on cooling."),
    },
    # -- 5. reduced-voltage starting of an induction motor --
    "motorstart": {
        "start_vfd": _x3(
            "# Starting with a variable frequency drive",
            "Reduced-voltage starting limits the large inrush current an "
            "induction motor draws when connected straight to the line. It eases "
            "the voltage dip on the supply and the mechanical shock on the "
            "driven load, at the cost of reduced starting torque. A variable "
            "frequency drive ramps frequency and voltage together from zero, "
            "giving the lowest inrush and smooth controlled acceleration."),
        "start_stardelta": _x3(
            "# Star-delta starting",
            "Reduced-voltage starting limits the large inrush current an "
            "induction motor draws when connected straight to the line. It eases "
            "the voltage dip on the supply and the mechanical shock on the "
            "driven load, at the cost of reduced starting torque. A star-delta "
            "starter runs the windings in star for starting, cutting current and "
            "torque to a third, then switches to delta for running."),
        "start_autotx": _x3(
            "# Autotransformer starting",
            "Reduced-voltage starting limits the large inrush current an "
            "induction motor draws when connected straight to the line. It eases "
            "the voltage dip on the supply and the mechanical shock on the "
            "driven load, at the cost of reduced starting torque. An "
            "autotransformer starter applies a chosen tap voltage during "
            "starting, then transitions the motor to full line voltage."),
    },
    # -- 6. fatigue under cyclic load --
    "fatigue": {
        "fatigue_weld": _x3(
            "# Fatigue of welded details",
            "Fatigue life under repeated load depends on the stress range and "
            "the number of cycles, related by an S-N curve for the detail. "
            "Stress concentrations cut the life; residual stress and mean stress "
            "shift it. The critical location for a welded detail is the weld toe, "
            "and grinding or peening the toe improves the life."),
        "fatigue_bolt": _x3(
            "# Fatigue of bolted connections",
            "Fatigue life under repeated load depends on the stress range and "
            "the number of cycles, related by an S-N curve for the detail. "
            "Stress concentrations cut the life; residual stress and mean stress "
            "shift it. The critical location for a high-strength bolt is the "
            "thread root, and adequate preload keeps the stress range on the "
            "bolt small."),
        "fatigue_rebar": _x3(
            "# Fatigue of reinforcing bars",
            "Fatigue life under repeated load depends on the stress range and "
            "the number of cycles, related by an S-N curve for the detail. "
            "Stress concentrations cut the life; residual stress and mean stress "
            "shift it. The critical location for a reinforcing bar is the base "
            "of a rib or a bend, and bars are rarely spliced in high-cycle "
            "tension zones."),
    },
}

# 6 unrelated distractors
DISTRACTORS = {
    "d_geodesy": (
        "13-geodesy.md",
        "# Traverse adjustment\n"
        "A closed traverse is adjusted by distributing the angular misclosure "
        "equally among the stations, then balancing the departures and "
        "latitudes by the compass rule before computing coordinates. " * 4),
    "d_hvac": (
        "14-hvac.md",
        "# Duct sizing\n"
        "Supply ducts are sized by the equal-friction method: pick a friction "
        "rate per unit length and read the duct diameter for each branch flow "
        "from the chart, then check the resulting air velocity. " * 4),
    "d_lighting": (
        "15-lighting.md",
        "# Interior lighting\n"
        "The lumen method gives the number of luminaires for a target "
        "illuminance from the room index, the utilisation factor and the "
        "maintenance factor for the space. " * 4),
    "d_drainage": (
        "16-drainage.md",
        "# Road gullies\n"
        "Gully spacing on a carriageway follows from the rational-method runoff, "
        "the allowable spread of water in the channel and the intercept "
        "efficiency of the grating at the design flow. " * 4),
    "d_formwork": (
        "17-formwork.md",
        "# Wall formwork pressure\n"
        "The lateral concrete pressure on wall formwork depends on the pour "
        "rate, the concrete temperature and the set retardation; above a "
        "critical height the pressure is hydrostatic. " * 4),
    "d_coating": (
        "18-coating.md",
        "# Protective coatings\n"
        "A paint system for structural steel is specified by surface "
        "preparation grade, primer type and total dry film thickness for the "
        "corrosivity category and the required durability. " * 4),
}

# One simulated session per cluster: (reask query, gold sibling doc-folder name).
# The session runs this query and hits the gold sibling 3x.
SESSION = [
    ("anchorage length develop bar yield through bond stress", "anchorage_ec2"),
    ("splice transfer tension between two reinforcing bars",     "splice_sleeve"),
    ("nominal concrete cover to protect the reinforcement",      "cover_carbonation"),
    ("limit crack width by bar stress and bar spacing",          "crack_thermal"),
    ("reduced voltage starting to limit motor inrush current",   "start_stardelta"),
    ("fatigue life from stress range and S-N curve",             "fatigue_bolt"),
]

# reask == the session queries, verbatim.
REASK = list(SESSION)

# easy: natural-language paraphrase of the same need; same gold sibling.
EASY = [
    ("how far must a rebar be embedded so it reaches its yield strength",
     "anchorage_ec2"),
    ("how do you join two reinforcement bars so they carry tension across the joint",
     "splice_sleeve"),
    ("how much concrete cover do you need over the steel to protect it",
     "cover_carbonation"),
    ("how are cracks in a concrete member kept narrow",
     "crack_thermal"),
    ("how do you start a big induction motor without a huge current spike",
     "start_stardelta"),
    ("how is the fatigue life of a detail estimated from cyclic stress",
     "fatigue_bolt"),
]

# cross: worded with a neighbouring sibling's / cluster's vocabulary. The gold
# sibling still answers the need, but cold retrieval is pulled toward a sibling
# (or a distractor). Frecency has to override the lexical pull.
CROSS = [
    ("development length of a deformed bar in tension per code",  # ACI wording
     "anchorage_ec2"),
    ("overlap length for lapped bars to pass force through bond", # lap wording
     "splice_sleeve"),
    ("axis distance to the bar for fire resistance period",       # fire wording
     "cover_carbonation"),
    ("controlling cracks from drying shrinkage restrained by supports",  # shrinkage wording
     "crack_thermal"),
    ("ramp frequency and voltage from zero for a smooth motor start",    # VFD wording
     "start_stardelta"),
    ("weld toe stress concentration and grinding to improve life",       # weld wording
     "fatigue_bolt"),
]


# ---------- helpers ----------

def build_bibliotheca(root: Path) -> Path:
    """Build a fresh bibliotheca with all cluster siblings + distractors."""
    con = db.connect(root)
    n = 1
    for cluster, siblings in CLUSTERS.items():
        for doc_name, body in siblings.items():
            folder = root / doc_name
            folder.mkdir(exist_ok=True)
            (folder / f"{n:02d}-{doc_name}.md").write_text(
                f"---\ndoc: {doc_name}\nsection: main\n---\n\n{body}\n",
                encoding="utf-8")
            n += 1
            chunks = embed.doc_chunks(folder)
            db.replace_document(con, doc_name, chunks,
                                embed.vectorize([c["text"] for c in chunks]))
    for doc_name, (filename, body) in DISTRACTORS.items():
        folder = root / doc_name
        folder.mkdir(exist_ok=True)
        (folder / filename).write_text(
            f"---\ndoc: {doc_name}\nsection: main\n---\n\n{body}\n",
            encoding="utf-8")
        chunks = embed.doc_chunks(folder)
        db.replace_document(con, doc_name, chunks,
                            embed.vectorize([c["text"] for c in chunks]))
    con.close()
    return root


# ---- frozen copy of the three fusion strategies (production ships `bonus`) ----
K_RRF = 60         # rrf: fusion constant                   (was biblio.search.K_RRF)
_W_BASE = 2.0      # weighted: frecency weight ceiling      (was db.BASE_WEIGHT)
_W_SCALE = 1.0     # weighted: saturation scale             (was db.FRECENCY_SCALE)
_BONUS_CAP = 0.03  # bonus: additive cap                    (db.MAX_BONUS)
_BONUS_SCALE = 1.0 # bonus: divisor                         (db.BONUS_SCALE)


def _rrf(lists, weights=None):
    scores: dict = {}
    for i, lst in enumerate(lists):
        w = weights[i] if weights else 1.0
        for pos, k in enumerate(lst, start=1):
            scores[k] = scores.get(k, 0.0) + w / (K_RRF + pos)
    return scores


def _rank(bib: Path, query: str, mode: str | None, top: int = 5) -> list[str]:
    """Top-N doc names for `query` under fusion `mode` (None = cold).

    Mirrors biblio.search.search() for a single bibliotheca, with the three
    fusion strategies frozen locally. `bonus` == what production ships.
    """
    con = db.connect(bib)
    try:
        vec = embed.vectorize_query(query)
        cand = top * MULTIPLE
        lists = [db.search_vector(con, vec, cand), db.search_fts(con, query, cand)]
        cand_ids = {i for r in lists for i in r}
        frec = dict(db.ranked_by_frecency(con, vec, cand_ids)) if mode else {}
        if mode in ("flat", "weighted") and frec:
            lists.append(sorted(frec, key=frec.get, reverse=True))
        rows = db.details(con, list(cand_ids | set(frec)))
    finally:
        con.close()

    if mode == "weighted" and frec:
        w = _W_BASE * (1 - exp(-max(frec.values()) / _W_SCALE))
        scored = _rrf(lists, [1.0, 1.0, w][:len(lists)])
    else:
        scored = _rrf(lists)

    if mode == "bonus":
        for k in list(scored):
            if k in frec:
                scored[k] += min(frec[k] / _BONUS_SCALE, _BONUS_CAP)

    q_tok = _tokens(query)
    if q_tok:
        for k, row in rows.items():
            m = q_tok & _tokens(row["section"] or "")
            if m:
                scored[k] = scored.get(k, 0.0) + BONUS_HEADING * len(m) / len(q_tok)

    seen: set[str] = set()
    out: list[str] = []
    for cid, _ in sorted(scored.items(), key=lambda p: -p[1]):
        row = rows.get(cid)
        if row is None or row["doc"] in seen:
            continue
        seen.add(row["doc"])
        out.append(row["doc"])
        if len(out) == top:
            break
    return out


def _record_appearances(bib: Path, query: str, mode: str) -> None:
    """The weight-1 'this section showed up in a search' record that the deleted
    `record_appearances=True` path used to write. Records the top-5 of the
    session's own search."""
    top5 = _rank(bib, query, mode)
    vec_f16 = np.asarray(embed.vectorize_query(query), dtype="float16").tobytes()
    con = db.connect(bib)
    try:
        session = db.get_session(con)
        for doc_name in top5:
            row = con.execute("SELECT id FROM chunks WHERE doc = ? LIMIT 1",
                              (doc_name,)).fetchone()
            if row:
                db.record_access(con, row["id"], vec_f16, weight=1,
                                 session_id=session)
        db.save_last_query_vec(con, vec_f16)
    finally:
        con.close()


def warm_up(bib: Path, mode: str, record_appearances: bool) -> None:
    """Simulate a working session: for each cluster, search (+ optionally record
    its appearances) then `biblio hit` the gold sibling 3x."""
    for query, gold_doc in SESSION:
        if record_appearances:
            _record_appearances(bib, query, mode)
        con = db.connect(bib)
        try:
            row = con.execute(
                "SELECT id FROM chunks WHERE doc = ? LIMIT 1", (gold_doc,)).fetchone()
            if row:
                vec_f16 = np.asarray(
                    embed.vectorize_query(query), dtype="float16").tobytes()
                for _ in range(3):
                    session = db.increment_session(con)
                    db.record_access(con, row["id"], vec_f16, weight=5,
                                     session_id=session)
        finally:
            con.close()


def report_calibration(bib: Path) -> None:
    """Median top frecency score across the gold siblings (feeds SCALE tuning)."""
    con = db.connect(bib)
    scores: list[float] = []
    try:
        for query, gold_doc in SESSION:
            cids = [r[0] for r in con.execute(
                "SELECT id FROM chunks WHERE doc = ?", (gold_doc,))]
            ranked = db.ranked_by_frecency(
                con, embed.vectorize_query(query), cids)
            if ranked:
                scores.append(ranked[0][1])
    finally:
        con.close()
    if scores:
        print(f"  median warm-up frecency score: {float(np.median(scores)):.4f}")
    else:
        print("  median warm-up frecency score: n/a (no frecency state)")


def evaluate(bib: Path, queries: list[tuple[str, str]], fusion_mode: str | None,
             top: int = 5) -> dict:
    """Run queries; return recall@1/@3, MRR and the per-query gold rank list.

    fusion_mode=None means cold (vector + FTS only).
    """
    ranks = []
    for query, gold_doc in queries:
        docs = _rank(bib, query, fusion_mode, top)
        rank = next((i for i, d in enumerate(docs, 1) if d == gold_doc), None)
        ranks.append(rank)

    n = len(queries)
    return {
        "recall@1": round(sum(1 for r in ranks if r == 1) / n, 3),
        "recall@3": round(sum(1 for r in ranks if r and r <= 3) / n, 3),
        "MRR": round(sum(1 / r for r in ranks if r) / n, 3),
        "ranks": ranks,
    }


def count_regressions(base_ranks: list, cand_ranks: list) -> int:
    """Queries where candidate ranks the gold worse than the baseline did."""
    return sum(1 for b, c in zip(base_ranks, cand_ranks)
               if b is not None and (c is None or c > b))


# ---------- main ----------

QSETS = [("reask", REASK), ("easy", EASY), ("cross", CROSS)]

CONFIGS = [
    ("flat + hits_only",       "flat",     False),
    ("weighted + hits_only",   "weighted", False),
    ("bonus + hits_only",      "bonus",    False),
    ("flat + hits+appear",     "flat",     True),
    ("weighted + hits+appear", "weighted", True),
    ("bonus + hits+appear",    "bonus",    True),
]


def main():
    import shutil
    import tempfile

    base_dir = Path(tempfile.mkdtemp(prefix="frecency_bench_"))
    corpus_dir = base_dir / "corpus"
    corpus_dir.mkdir()
    print("Building corpus and embedding (one-time cost)...")
    build_bibliotheca(corpus_dir)
    print(f"Corpus: {sum(len(s) for s in CLUSTERS.values())} cluster siblings "
          f"+ {len(DISTRACTORS)} distractors at {corpus_dir}")

    # Cold reference — no frecency at all. One warm-free copy.
    cold_dir = base_dir / "cold"
    shutil.copytree(corpus_dir, cold_dir)
    cold = {name: evaluate(cold_dir, qs, None) for name, qs in QSETS}

    results = {}
    for config_name, fusion_mode, record_app in CONFIGS:
        print(f"\n{'='*60}\nConfig: {config_name}\n{'='*60}")
        run_dir = base_dir / config_name.replace(" ", "_").replace("+", "_")
        shutil.copytree(corpus_dir, run_dir)
        print("  Warming up...")
        warm_up(run_dir, fusion_mode, record_app)
        report_calibration(run_dir)
        results[config_name] = {}
        for name, qs in QSETS:
            print(f"  Evaluating {name}...")
            results[config_name][name] = evaluate(run_dir, qs, fusion_mode)

    # ---------- report ----------
    print(f"\n\n{'='*60}\nRESULTS\n{'='*60}")
    hdr = f"| {'row':<26} | {'R@1':>5} | {'R@3':>5} | {'MRR':>5} | {'regr':>4} |"
    sep = f"|{'-'*28}|{'-'*7}|{'-'*7}|{'-'*7}|{'-'*6}|"

    for qset, qlist in QSETS:
        print(f"\n### {qset} queries (n={len(qlist)})\n")
        print(hdr)
        print(sep)
        c = cold[qset]
        print(f"| {'COLD (no frecency)':<26} | {c['recall@1']:>5} | "
              f"{c['recall@3']:>5} | {c['MRR']:>5} | {'—':>4} |")
        for config_name, _, _ in CONFIGS:
            r = results[config_name][qset]
            regr = count_regressions(cold[qset]["ranks"], r["ranks"])
            print(f"| {config_name:<26} | {r['recall@1']:>5} | "
                  f"{r['recall@3']:>5} | {r['MRR']:>5} | {regr:>4} |")

    # avg MRR and regressions vs the cold reference, over the 3 sets
    def avg_mrr(res):  # res: {qset: metrics}
        return sum(res[q]["MRR"] for q, _ in QSETS) / len(QSETS)

    def total_regr_vs_cold(res):
        return sum(count_regressions(cold[q]["ranks"], res[q]["ranks"])
                   for q, _ in QSETS)

    print(f"\n### summary (avg MRR over the 3 sets)\n")
    print(f"| {'row':<26} | {'avgMRR':>6} | {'ΔvsCold':>8} | {'regr vs cold':>12} |")
    print(f"|{'-'*28}|{'-'*8}|{'-'*10}|{'-'*14}|")
    cold_avg = avg_mrr(cold)
    print(f"| {'COLD (no frecency)':<26} | {cold_avg:>6.3f} | {'—':>8} | {'—':>12} |")
    ranking = []
    for config_name, _, _ in CONFIGS:
        res = results[config_name]
        a = avg_mrr(res)
        ranking.append((config_name, a, total_regr_vs_cold(res)))
        print(f"| {config_name:<26} | {a:>6.3f} | {a - cold_avg:>+8.3f} | "
              f"{total_regr_vs_cold(res):>12} |")

    ranking.sort(key=lambda x: (-x[1], x[2]))
    win, win_mrr, win_regr = ranking[0]
    print(f"\nWinner: {win}  (avg MRR {win_mrr:.3f}, "
          f"{win_regr} regressions vs cold, +{win_mrr - cold_avg:.3f} over cold)")
    if win_mrr - cold_avg < 0.02:
        print("NOTE: winner is within 0.02 MRR of cold — frecency is not "
              "pulling its weight even on this harder corpus.")

    print(f"\nBenchmark data at: {base_dir}")


if __name__ == "__main__":
    main()
