import json
from pathlib import Path

from scripts.eval.scramble import md_to_tex, md_to_txt, scramble


def test_md_to_tex():
    tex = md_to_tex("---\ntitle: x\n---\n# Intro\nSome **bold** and *italic* text.\n\n## Part\nBody.\n")
    assert tex.startswith("\\documentclass{article}")
    assert "\\section{Intro}" in tex
    assert "\\subsection{Part}" in tex
    assert "\\textbf{bold}" in tex and "\\textit{italic}" in tex
    assert "text.~\\cite{ref}" in tex
    assert "title: x" not in tex


def test_md_to_txt():
    assert md_to_txt("# Intro\nSee [docs](http://x) and `code` **now**.") == \
        "Intro\nSee docs and code now."


def test_scramble_is_deterministic_opaque_and_mixed(tmp_path):
    folder = tmp_path / "src" / "Client" / "deep"
    folder.mkdir(parents=True)
    mds = []
    for i in range(10):
        f = folder / f"client-{i}.md"
        f.write_text(f"# Title {i}\nBody {i}.\n", encoding="utf-8")
        mds.append(f)
    pdf = tmp_path / "src" / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    manifest = tmp_path / "manifests" / "m1.json"
    m1 = scramble(mds, [pdf], tmp_path / "out1", manifest, seed=7)
    m2 = scramble(mds, [pdf], tmp_path / "out2", tmp_path / "manifests" / "m2.json", seed=7)

    assert m1 == m2
    files = sorted(p.name for p in (tmp_path / "out1").iterdir())
    assert len(files) == 11 and all(n.startswith("doc_") for n in files)
    assert {Path(n).suffix for n in files} == {".tex", ".txt", ".md", ".pdf"}
    assert m1[next(n for n in files if n.endswith(".pdf"))] == str(pdf)
    assert json.loads(manifest.read_text(encoding="utf-8")) == m1
