"""Answer cost per corpus × kind × arm = total tokens ÷ answers both correct and cited."""
import math
import sys
from collections import defaultdict
from statistics import mean

from scripts.eval import arms, gold


def rows(runs, verdicts) -> list[dict]:
    by_key = {v["key"]: v for v in verdicts}
    groups = defaultdict(list)
    for r in runs:
        groups[(r["corpus"], r["kind"], r["arm"])].append(r)
    out = []
    for (corpus, kind, arm), rs in sorted(groups.items()):
        vs = [by_key[r["key"]] for r in rs]  # KeyError on purpose: judge everything first
        good = sum(1 for v in vs if v["correct"] and v["cited"])
        tokens = [r["tokens"] for r in rs]
        out.append({
            "corpus": corpus, "kind": kind, "arm": arm, "runs": len(rs),
            "answer_cost": sum(tokens) / good if good else math.inf,
            "correct": mean(v["correct"] for v in vs),
            "cited": mean(v["cited"] for v in vs),
            "tokens_min": min(tokens), "tokens_max": max(tokens),
            "tool_calls": mean(len(r["tool_calls"]) for r in rs),
            "errors": sum(r["is_error"] for r in rs),
            "used_biblio": sum(r["used_biblio"] for r in rs),
        })
    return out


def markdown(table) -> str:
    lines = ["| corpus | kind | arm | runs | answer cost | correct | cited | tokens min–max | tool calls | errors | used biblio |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in table:
        cost = "∞" if math.isinf(r["answer_cost"]) else f"{r['answer_cost']:,.0f}"
        lines.append(f"| {r['corpus']} | {r['kind']} | {r['arm']} | {r['runs']} | {cost} | "
                     f"{r['correct']:.0%} | {r['cited']:.0%} | "
                     f"{r['tokens_min']:,}–{r['tokens_max']:,} | {r['tool_calls']:.1f} | "
                     f"{r['errors']} | {r['used_biblio']} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    name = (argv or sys.argv[1:] or ["baseline"])[0]
    runs, verdicts = [], []
    for f in sorted((arms.DATA / "runs").glob("*.jsonl")):
        runs += gold.load(f)
        verdicts += gold.load(arms.DATA / "judged" / f.name)
    text = f"# Eval: {name}\n\n" + markdown(rows(runs, verdicts))
    dest = arms.REPO / "scripts" / "eval" / "results" / f"{name}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
