import json

from scripts.eval import judge

Q = {"id": "q1", "question": "Q?", "answer": "facts",
     "locations": [{"file": "sub/Spong Book.pdf", "anchor": "four parameters", "page": 77}]}


def test_prompt_contains_gold_doc_id_and_answer():
    text = judge.prompt(Q, {"answer": "The answer."})
    assert "spong-book" in text and "page 77" in text
    assert "facts" in text and "The answer." in text


def test_parse_structured_output_and_fallback():
    assert judge.parse(json.dumps({"structured_output": {"correct": 1, "cited": 0, "reason": "r"}})) == \
        {"correct": 1, "cited": 0, "reason": "r"}
    assert judge.parse(json.dumps({"result": '{"correct": 0, "cited": 1, "reason": "x"}'}))["cited"] == 1


def test_errored_run_scores_zero_without_calling_the_model():
    calls = []
    verdict = judge.judge_one(Q, {"key": "k", "answer": "", "is_error": True}, "claude",
                              execute=lambda *a, **k: calls.append(1))
    assert verdict == {"key": "k", "correct": 0, "cited": 0, "reason": "no answer"}
    assert calls == []


def test_spot_check_samples_ten_percent():
    runs = [{"key": f"q{i}|A|0", "id": f"q{i}", "answer": "a"} for i in range(30)]
    verdicts = [{"key": r["key"], "correct": 1, "cited": 1, "reason": "ok"} for r in runs]
    questions = {f"q{i}": {"question": "?", "answer": "g", "locations": []} for i in range(30)}
    assert judge.spot_check(runs, verdicts, questions).count("\n## ") == 3
