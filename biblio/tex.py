"""LaTeX source to markdown. Regex only — headings are the point, slicing depends on them."""
import re

_BEGIN_DOCUMENT = re.compile(r"\\begin\{document\}")
_END_DOCUMENT = re.compile(r"\\end\{document\}.*", re.S)
_SECTION = re.compile(r"\\section\{(.*?)\}")
_SUBSECTION = re.compile(r"\\subsection\{(.*?)\}")
_SUBSUBSECTION = re.compile(r"\\subsubsection\{(.*?)\}")
_TEXTBF = re.compile(r"\\textbf\{(.*?)\}")
_TEXTIT = re.compile(r"\\textit\{(.*?)\}")
_CITE = re.compile(r"~?\\cite\{.*?\}")
_LIST_ENV = re.compile(r"\\begin\{(?:itemize|enumerate)\}|\\end\{(?:itemize|enumerate)\}")
_ITEM = re.compile(r"\\item\s*")


def to_markdown(text: str) -> str:
    """Best-effort LaTeX source to markdown: headings, emphasis, lists, no preamble."""
    m = _BEGIN_DOCUMENT.search(text)
    text = text[m.end():] if m else text
    text = _END_DOCUMENT.sub("", text)
    text = _SUBSUBSECTION.sub(r"### \1", text)
    text = _SUBSECTION.sub(r"## \1", text)
    text = _SECTION.sub(r"# \1", text)
    text = _TEXTBF.sub(r"\1", text)
    text = _TEXTIT.sub(r"\1", text)
    text = _CITE.sub("", text)
    text = _LIST_ENV.sub("", text)
    text = _ITEM.sub("- ", text)
    return text
