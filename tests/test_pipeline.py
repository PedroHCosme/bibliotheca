from biblio.normalize import normalize
from biblio.pipeline import EXTENSIONS, _files, _get_text, _strip_source_frontmatter
from biblio.slice import slice_doc


def test_tex_is_discovered_by_files(tmp_path):
    (tmp_path / "paper.tex").write_text(r"\begin{document}\section{Intro}text\end{document}",
                                        encoding="utf-8")
    assert ".tex" in EXTENSIONS
    assert _files(tmp_path) == [tmp_path / "paper.tex"]


def test_tex_ingested_through_get_text_and_slices(tmp_path):
    src = tmp_path / "paper.tex"
    src.write_text(
        r"\documentclass{article}\begin{document}"
        r"\section{Intro}"
        r"some \textbf{bold} text~\cite{ref1}"
        r"\subsection{Details}"
        r"\begin{itemize}\item first\item second\end{itemize}"
        r"\end{document}",
        encoding="utf-8",
    )
    raw, route = _get_text(src, "auto", warn=lambda *_: None, name="paper")
    assert route == {}
    assert "# Intro" in raw
    assert "## Details" in raw
    assert "\\textbf" not in raw
    assert "cite" not in raw

    slices = slice_doc(normalize(raw), with_pages=False)
    assert len(slices) >= 1
    assert any("- first" in s.text for s in slices)


def test_removes_source_frontmatter_and_keeps_body():
    md = "---\ntags: [a/b]\naliases: [x, y]\n---\n\n# Titulo\ncorpo"
    output = _strip_source_frontmatter(md)
    assert not output.startswith("---")
    assert "# Titulo\ncorpo" in output
    assert "*x, y, a/b*" in output, "aliases and tags become searchable line"


def test_no_frontmatter_passes_through():
    md = "# Titulo\ncorpo\n---\nhorizontal divider"
    assert _strip_source_frontmatter(md) == md
