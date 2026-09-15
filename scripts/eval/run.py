"""Run question × arm × repeat through headless Claude Code. Resumable: one JSON line per run."""
import argparse
import json
import shutil
import subprocess
import sys
import time

from scripts.eval import arms, gold, transcript

REPEATS = {"targeted": 3, "thematic": 1}
TIMEOUT_S = 900
BASELINE_ARMS = "A,B-current,C"


def key(q: dict, arm: str, rep: int) -> str:
    return f"{q['id']}|{arm}|{rep}"


def pending(questions, arm_names, done):
    for q in questions:
        for rep in range(REPEATS[q["kind"]]):
            for arm in arm_names:
                if key(q, arm, rep) not in done:
                    yield q, arm, rep


def run_one(q: dict, arm: str, rep: int, claude: str, execute=subprocess.run) -> dict:
    record = {"key": key(q, arm, rep), "id": q["id"], "corpus": q["corpus"],
              "kind": q["kind"], "arm": arm, "rep": rep}
    started = time.time()
    try:
        proc = execute(arms.command(arm, q["corpus"], claude),
                       input=arms.PROMPT.format(question=q["question"]),
                       capture_output=True, text=True, encoding="utf-8",
                       cwd=arms.cwd(arm, q["corpus"]), env=arms.env(arm, q["corpus"]),
                       timeout=TIMEOUT_S)
        record.update(transcript.parse(proc.stdout.splitlines()))
    except (subprocess.TimeoutExpired, ValueError) as err:
        record.update(answer="", is_error=True, tokens=0, tool_calls=[], error=str(err)[:500])
    record["seconds"] = round(time.time() - started, 1)
    record["used_biblio"] = transcript.used_biblio(record["tool_calls"])
    return record


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("corpus")
    p.add_argument("--arms", default=BASELINE_ARMS)
    p.add_argument("--limit", type=int, help="run at most N pending runs (pilot)")
    a = p.parse_args(argv)
    claude = shutil.which("claude") or sys.exit("claude not on PATH")

    questions = gold.load(arms.DATA / "gold" / f"{a.corpus}.jsonl")
    out = arms.DATA / "runs" / f"{a.corpus}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(line)["key"] for line in out.read_text(encoding="utf-8").splitlines()
            if line.strip()} if out.exists() else set()
    todo = list(pending(questions, a.arms.split(","), done))[:a.limit]

    for i, (q, arm, rep) in enumerate(todo, 1):
        rec = run_one(q, arm, rep, claude)
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[{i}/{len(todo)}] {rec['key']} tokens={rec['tokens']} "
              f"tools={len(rec['tool_calls'])} error={rec['is_error']} "
              f"biblio={rec['used_biblio']}", flush=True)


if __name__ == "__main__":
    main()
