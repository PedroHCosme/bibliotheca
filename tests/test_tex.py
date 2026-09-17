from biblio.tex import to_markdown


def test_drops_preamble_before_begin_document():
    src = r"\documentclass{article}\usepackage{foo}\begin{document}body\end{document}"
    assert to_markdown(src).strip() == "body"


def test_drops_end_document_and_after():
    src = r"\begin{document}body\end{document}\end{comment} trailing junk"
    assert to_markdown(src).strip() == "body"


def test_section_becomes_h1():
    src = r"\begin{document}\section{Intro}text\end{document}"
    assert "# Intro" in to_markdown(src)


def test_subsection_becomes_h2():
    src = r"\begin{document}\subsection{Details}text\end{document}"
    assert "## Details" in to_markdown(src)


def test_subsubsection_becomes_h3():
    src = r"\begin{document}\subsubsection{Minutiae}text\end{document}"
    assert "### Minutiae" in to_markdown(src)


def test_textbf_strips_markup_keeps_contents():
    src = r"\begin{document}this is \textbf{bold} text\end{document}"
    out = to_markdown(src)
    assert "bold" in out
    assert "\\textbf" not in out


def test_textit_strips_markup_keeps_contents():
    src = r"\begin{document}this is \textit{italic} text\end{document}"
    out = to_markdown(src)
    assert "italic" in out
    assert "\\textit" not in out


def test_cite_dropped_entirely():
    src = r"\begin{document}see~\cite{smith2020} for details\end{document}"
    out = to_markdown(src)
    assert "cite" not in out
    assert "smith2020" not in out


def test_itemize_items_become_dashes():
    src = (
        r"\begin{document}"
        r"\begin{itemize}"
        r"\item first"
        r"\item second"
        r"\end{itemize}"
        r"\end{document}"
    )
    out = to_markdown(src)
    assert "- first" in out
    assert "- second" in out
    assert r"\begin{itemize}" not in out
    assert r"\end{itemize}" not in out


def test_cite_inside_heading_does_not_corrupt_it():
    src = r"\begin{document}\section{Title with \cite{foo} reference}\end{document}"
    out = to_markdown(src)
    assert "Title with" in out
    assert "reference" in out


def test_multiline_section_heading_converts():
    src = "\\begin{document}\\section{A Long\nTitle}text\\end{document}"
    out = to_markdown(src)
    assert r"\section{" not in out
    assert "A Long" in out
    assert "Title" in out


def test_enumerate_items_become_dashes():
    src = (
        r"\begin{document}"
        r"\begin{enumerate}"
        r"\item first"
        r"\item second"
        r"\end{enumerate}"
        r"\end{document}"
    )
    out = to_markdown(src)
    assert "- first" in out
    assert "- second" in out
    assert r"\begin{enumerate}" not in out
    assert r"\end{enumerate}" not in out
