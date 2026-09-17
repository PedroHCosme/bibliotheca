"""LaTeX source to markdown. Regex only — headings are the point, slicing depends on them."""
import re

_BEGIN_DOCUMENT = re.compile(r"\\begin\{document\}")
_END_DOCUMENT = re.compile(r"\\end\{document\}.*", re.S)
_SECTION = re.compile(r"\\section\{(.*?)\}", re.S)
_SUBSECTION = re.compile(r"\\subsection\{(.*?)\}", re.S)
_SUBSUBSECTION = re.compile(r"\\subsubsection\{(.*?)\}", re.S)
_TEXTBF = re.compile(r"\\textbf\{(.*?)\}", re.S)
_TEXTIT = re.compile(r"\\textit\{(.*?)\}", re.S)
_CITE = re.compile(r"~?\\cite\{.*?\}")
_LIST_ENV = re.compile(r"\\begin\{(?:itemize|enumerate)\}|\\end\{(?:itemize|enumerate)\}")
_ITEM = re.compile(r"\\item\s*")


def to_markdown(text: str) -> str:
    """Best-effort LaTeX source to markdown: headings, emphasis, lists, no preamble.

    Known limitations: this is a regex-only converter, not a real LaTeX parser.
    Brace matching is single-level (lazy `{(.*?)}`), so heading/emphasis content
    with its own nested braces beyond what's tested may still misbehave. Only
    `\\cite` is stripped — `\\citep`/`\\citet`/other natbib or biblatex variants
    pass through as literal text.
    """
    m = _BEGIN_DOCUMENT.search(text)
    text = text[m.end():] if m else text
    text = _END_DOCUMENT.sub("", text)
    text = _CITE.sub("", text)  # before headings: lazy brace regexes below would
                                # otherwise stop at a \cite{...}'s closing brace
    text = _SUBSUBSECTION.sub(r"### \1", text)
    text = _SUBSECTION.sub(r"## \1", text)
    text = _SECTION.sub(r"# \1", text)
    text = _TEXTBF.sub(r"\1", text)
    text = _TEXTIT.sub(r"\1", text)
    text = _LIST_ENV.sub("", text)
    text = _ITEM.sub("- ", text)
    return text
