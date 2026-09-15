import subprocess
from types import SimpleNamespace

from scripts.eval import arms, run
from tests.test_eval_transcript import LINES


def test_pending_interleaves_arms_and_repeats_by_kind():
    qs = [{"id": "t", "kind": "targeted"}, {"id": "h", "kind": "thematic"}]
    todo = list(run.pending(qs, ["A", "C"], done={"t|A|0"}))
    assert [run.key(q, a, r) for q, a, r in todo] == \
        ["t|C|0", "t|A|1", "t|C|1", "t|A|2", "t|C|2", "h|A|0", "h|C|0"]


Q = {"id": "t", "corpus": "robotics", "kind": "targeted", "question": "q"}


def test_run_one_parses_transcript(monkeypatch, tmp_path):
    monkeypatch.setattr(arms, "DATA", tmp_path)
    seen = {}

    def fake(cmd, **kw):
        seen.update(kw)
        return SimpleNamespace(stdout="\n".join(LINES), returncode=0, stderr="")

    rec = run.run_one(Q, "B-current", 1, "claude", execute=fake)
    assert rec["key"] == "t|B-current|1"
    assert rec["tokens"] == 2090 and rec["used_biblio"] is True
    assert "Question: q" in seen["input"]
    assert seen["cwd"] == tmp_path / "corpora" / "robotics"


def test_run_one_records_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(arms, "DATA", tmp_path)

    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)

    rec = run.run_one(Q, "A", 0, "claude", execute=boom)
    assert rec["is_error"] is True and rec["tokens"] == 0 and rec["used_biblio"] is False
