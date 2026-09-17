from biblio import embed
from biblio.normalize import normalize
from biblio.pipeline import EXTENSIONS, _files, _frontmatter, _get_text, _strip_source_frontmatter
from biblio.slice import Slice
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


def _slice(**overrides):
    fields = dict(order=1, section="Intro", level=1, text="body",
                 page_start=3, page_end=5, parent="01-parent.md")
    return Slice(**(fields | overrides))


def test_frontmatter_is_one_line_with_every_field():
    fm = _frontmatter(_slice(), "manual")
    comment = fm.split("\n", 1)[0]
    assert comment == "<!-- manual §Intro · p.3-5 · parent 01-parent.md -->"
    assert "\n" not in comment
    for field in ("manual", "§Intro", "p.3-5", "parent 01-parent.md"):
        assert field in comment


def test_frontmatter_omits_pages_when_absent():
    fm = _frontmatter(_slice(page_start=None, page_end=None), "manual")
    assert "p." not in fm


def test_frontmatter_omits_parent_when_absent():
    fm = _frontmatter(_slice(parent=None), "manual")
    assert "parent" not in fm


def test_frontmatter_glob_only_slice_still_citable():
    """A slice reached by glob alone (no search hit) must still carry doc/section/pages to cite."""
    fm = _frontmatter(_slice(section="Ancoragem"), "nbr-7480-aco")
    assert "nbr-7480-aco" in fm and "§Ancoragem" in fm and "p.3-5" in fm


def test_frontmatter_regex_strips_old_yaml_form():
    old = "---\ndoc: manual\nsection: Intro\nparent: null\n---\n\nbody text\n"
    body = embed._FRONTMATTER.sub("", old)
    assert body.strip() == "body text"


def test_frontmatter_regex_strips_new_oneline_form():
    new = _frontmatter(_slice(), "manual") + "body text\n"
    body = embed._FRONTMATTER.sub("", new)
    assert body.strip() == "body text"
