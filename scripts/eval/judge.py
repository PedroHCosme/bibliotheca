"""Haiku judge: correct 0/1 and cited 0/1 against gold. Resumable; writes a 10% spot-check sheet."""
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

from biblio.paths import slug
from scripts.eval import arms, gold

JUDGE_MODEL = "claude-haiku-4-5-20251001"
SCHEMA = {"type": "object",
          "properties": {"correct": {"type": "integer", "enum": [0, 1]},
                         "cited": {"type": "integer", "enum": [0, 1]},
                         "reason": {"type": "string"}},
          "required": ["correct", "cited", "reason"]}
PROMPT = """You grade an answer against a gold answer. Reply only with the JSON object.

correct = 1 if the answer states every key fact of the gold answer and contradicts none; otherwise 0.
cited = 1 if the answer cites at least one gold document — by its file name, its document id, or a path
whose folder is the document id — and locates the answer within it: a section, chapter, example or
heading name that contains the gold anchor, or a page number. Gold pages are PDF page indexes; books
print their own numbering, often offset by up to ~20, so a page within 20 of the gold page counts.
A document named without any location inside it gets 0.

Question: {question}
Gold answer (key facts): {answer}
Gold documents: {documents}

Answer to grade:
<<<
{candidate}
>>>
"""


def documents(q: dict) -> str:
    return "; ".join(
        f'file "{loc["file"]}" (document id {slug(Path(loc["file"]).stem)}), '
        f'anchor "{loc["anchor"]}"' + (f', page {loc["page"]}' if loc.get("page") else "")
        for loc in q["locations"])


def prompt(q: dict, run: dict) -> str:
    return PROMPT.format(question=q["question"], answer=q["answer"],
                         documents=documents(q), candidate=run["answer"])


def command(claude: str) -> list[str]:
    return [claude, "-p", "--output-format", "json", "--model", JUDGE_MODEL,
            "--tools", "", "--safe-mode", "--no-session-persistence",
            "--json-schema", json.dumps(SCHEMA)]


def parse(stdout: str) -> dict:
    data = json.loads(stdout)
    v = data.get("structured_output") or json.loads(data["result"])
    return {"correct": int(v["correct"]), "cited": int(v["cited"]), "reason": v["reason"]}


def judge_one(q: dict, run: dict, claude: str, execute=subprocess.run) -> dict:
    if run.get("is_error") or not run.get("answer", "").strip():
        return {"key": run["key"], "correct": 0, "cited": 0, "reason": "no answer"}
    proc = execute(command(claude), input=prompt(q, run), capture_output=True,
                   text=True, encoding="utf-8", timeout=300)
    return {"key": run["key"], **parse(proc.stdout)}


def spot_check(runs, verdicts, questions, share=0.1, seed=7) -> str:
    by_key = {v["key"]: v for v in verdicts}
    sample = random.Random(seed).sample(runs, max(1, round(len(runs) * share)))
    parts = ["# Spot check\n\nMark each verdict AGREE or DISAGREE.\n"]
    for r in sample:
        q, v = questions[r["id"]], by_key[r["key"]]
        parts.append(f"\n## {r['key']}\n\n**Question:** {q['question']}\n\n"
                     f"**Gold:** {q['answer']}\n\n**Answer:**\n\n{r['answer']}\n\n"
                     f"**Verdict:** correct={v['correct']} cited={v['cited']} — {v['reason']}\n\n"
                     "**Review:** \n")
    return "".join(parts)


def main(argv=None) -> None:
    corpus = (argv or sys.argv[1:])[0]
    claude = shutil.which("claude") or sys.exit("claude not on PATH")
    questions = {q["id"]: q for q in gold.load(arms.DATA / "gold" / f"{corpus}.jsonl")}
    runs = gold.load(arms.DATA / "runs" / f"{corpus}.jsonl")
    out = arms.DATA / "judged" / f"{corpus}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    verdicts = gold.load(out) if out.exists() else []
    judged = {v["key"] for v in verdicts}

    failed = []
    for r in runs:
        if r["key"] in judged:
            continue
        try:
            v = judge_one(questions[r["id"]], r, claude)
        except (subprocess.SubprocessError, ValueError, KeyError) as err:
            # Not recorded: scoring a judge failure 0/0 would charge it to the arm. Re-run retries it.
            failed.append(r["key"])
            print(f"{r['key']} JUDGE FAILED: {err!r}"[:300], flush=True)
            continue
        verdicts.append(v)
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(v, ensure_ascii=False) + "\n")
        print(f"{v['key']} correct={v['correct']} cited={v['cited']}", flush=True)
    if failed:
        sys.exit(f"{len(failed)} runs not judged; re-run to retry: {failed}")

    sheet = arms.DATA / "spotcheck" / f"{corpus}.md"
    sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.write_text(spot_check(runs, verdicts, questions), encoding="utf-8")
    print(f"spot check: {sheet}")


if __name__ == "__main__":
    main()
