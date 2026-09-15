import pytest

from scripts.eval.transcript import parse, used_biblio

LINES = [
    '{"type":"system","subtype":"init","tools":["Read","Bash"],"skills":["bibliotheca"],"plugins":[]}',
    '{"type":"assistant","message":{"id":"m1","content":[{"type":"tool_use","name":"Bash","input":{"command":"\\"C:/x/biblio.exe\\" search \\"dh\\""}}],"usage":{"input_tokens":100,"cache_read_input_tokens":900,"output_tokens":20}}}',
    '{"type":"assistant","message":{"id":"m1","content":[{"type":"text","text":"..."}],"usage":{"input_tokens":100,"cache_read_input_tokens":900,"output_tokens":25}}}',
    '{"type":"user","message":{"content":[{"type":"tool_result","content":"x"}]}}',
    '{"type":"assistant","message":{"id":"m2","content":[{"type":"text","text":"Answer."}],"usage":{"input_tokens":50,"cache_creation_input_tokens":10,"cache_read_input_tokens":1000,"output_tokens":5}}}',
    'not json noise',
    '{"type":"result","subtype":"success","is_error":false,"result":"Answer.","num_turns":2,"usage":{"input_tokens":150}}',
]


def test_parse_sums_last_usage_per_message():
    r = parse(LINES)
    assert r["tokens"] == (100 + 900 + 25) + (50 + 10 + 1000 + 5)
    assert r["answer"] == "Answer."
    assert r["is_error"] is False
    assert r["num_turns"] == 2
    assert len(r["tool_calls"]) == 1
    assert r["init_skills"] == ["bibliotheca"]
    assert r["result_usage"] == {"input_tokens": 150}


def test_parse_without_result_raises():
    with pytest.raises(ValueError):
        parse(LINES[:3])


def test_used_biblio():
    assert used_biblio(parse(LINES)["tool_calls"])
    assert not used_biblio([{"name": "Grep", "input": {"pattern": "biblio"}}])
    assert not used_biblio([{"name": "Bash", "input": {"command": "rg Alves"}}])
