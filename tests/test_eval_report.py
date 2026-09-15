import math

import pytest

from scripts.eval.report import markdown, rows


def _run(key, tokens, tools):
    return {"key": key, "corpus": "c", "kind": "targeted", "arm": "A",
            "tokens": tokens, "tool_calls": [{}] * tools, "is_error": False, "used_biblio": False}


RUNS = [_run("q1|A|0", 1000, 2), _run("q1|A|1", 3000, 0)]


def test_answer_cost_is_tokens_over_correct_and_cited():
    row = rows(RUNS, [{"key": "q1|A|0", "correct": 1, "cited": 1},
                      {"key": "q1|A|1", "correct": 1, "cited": 0}])[0]
    assert row["answer_cost"] == 4000
    assert row["correct"] == 1.0 and row["cited"] == 0.5
    assert (row["tokens_min"], row["tokens_max"]) == (1000, 3000)
    assert row["tool_calls"] == 1.0


def test_no_good_answer_is_infinite_cost():
    row = rows(RUNS, [{"key": k, "correct": 0, "cited": 0} for k in ("q1|A|0", "q1|A|1")])[0]
    assert math.isinf(row["answer_cost"])
    assert "∞" in markdown([row])


def test_unjudged_run_fails_loudly():
    with pytest.raises(KeyError):
        rows(RUNS, [{"key": "q1|A|0", "correct": 1, "cited": 1}])
