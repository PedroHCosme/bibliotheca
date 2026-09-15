from scripts.eval.gold import normalize, validate
from tests.conftest import _pdf


def test_normalize_expands_ligatures():
    assert normalize("ﬁnite  ﬁeld") == "finite field"


def _record(**over):
    rec = {"id": "o1", "corpus": "c", "kind": "targeted", "question": "q",
           "answer": "a", "locations": [{"file": "a.tex", "anchor": "The slip is   small."}]}
    rec.update(over)
    return rec


def test_valid_tex_anchor_ignores_latex_and_whitespace(tmp_path):
    (tmp_path / "a.tex").write_text(
        "\\section{X}\nThe \\textbf{slip} is small.~\\cite{ref}\n", encoding="utf-8")
    assert validate(_record(), tmp_path) == []


def test_pdf_anchor(tmp_path):
    _pdf(tmp_path / "d.pdf", ["Fatigue life of welded joints"])
    rec = _record(locations=[{"file": "d.pdf", "anchor": "welded joints", "page": 1}])
    assert validate(rec, tmp_path) == []


def test_errors_are_reported(tmp_path):
    (tmp_path / "a.md").write_text("hello world", encoding="utf-8")
    rec = _record(kind="other", answer="",
                  locations=[{"file": "a.md", "anchor": "goodbye"},
                             {"file": "nope.md", "anchor": "x"}])
    errors = validate(rec, tmp_path)
    assert any("kind" in e for e in errors)
    assert any("missing answer" in e for e in errors)
    assert any("anchor not found" in e for e in errors)
    assert any("no such file" in e for e in errors)
