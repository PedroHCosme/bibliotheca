"""One summary per document — never per chunk. Runs once, costs zero after."""
import re
from pathlib import Path

from biblio import ollama
from biblio.embed import _FRONTMATTER

MAX_SAMPLE = 6_000

# Prompt stays in Portuguese (user decision). RESUMO:/TERMOS: markers and parser stay.
PROMPT = """Voce recebe o inicio de um documento. Responda **no idioma do documento**, \
exatamente neste formato, sem preambulo:

RESUMO: <uma frase dizendo o que o documento e e para que serve>
TERMOS: <8 a 12 termos de busca do assunto, separados por virgula, sem numeracao. \
Use as palavras como aparecem no documento, sem traduzir>

Documento:
{amostra}"""


_TOC_LINE = re.compile(r"^\s*(?:[-*+]\s+)?(?:\[\[|\[[^\]]*\]\(#|\d+(?:\.\d+)*\s|.{0,50}\.{3,}\s*\d+\s*$)")
_ALIASES_LINE = re.compile(r"^\*[^*]+\*$")


def _is_prose(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped in ("---", "***") or stripped.startswith(
            ("#", "|", "```", "<!--")):
        return False
    if _ALIASES_LINE.match(stripped):
        return False
    return not _TOC_LINE.match(stripped)


def _sample(doc_dir: Path) -> str:
    files = sorted(doc_dir.glob("[0-9]*.md"))
    parts: list[str] = []
    total = 0
    for f in files:
        body = _FRONTMATTER.sub("", f.read_text(encoding="utf-8"))
        for line in body.splitlines():
            if line.startswith("#") or _is_prose(line):
                parts.append(line)
                total += len(line) + 1
        if total > MAX_SAMPLE:
            break
    text = "\n".join(parts).strip()[:MAX_SAMPLE]
    if len(text) >= 200:
        return text
    return _FRONTMATTER.sub("", "".join(
        f.read_text(encoding="utf-8") for f in files))[:MAX_SAMPLE]


def _extract(response: str) -> tuple[str, list[str]]:
    text = response.replace("*", "").strip()
    cut = re.search(r"(?i)\btermos?\s*:", text)
    before = text[:cut.start()] if cut else text
    after = text[cut.end():] if cut else ""

    m = re.search(r"(?i)\bresumo\s*:\s*(.+)", before, re.S)
    summary = (m.group(1) if m else before).strip().split("\n")[0].strip()

    after = after.split("\n\n")[0]
    terms = [t.strip(" .;\n\t-") for t in re.split(r"[,\n]", after)]
    return summary, [t for t in terms if t and len(t) <= 40][:15]


def summarize(doc_dir: Path) -> tuple[str, list[str]]:
    """Writes `_resumo.md` and returns (summary, terms). Raises if Ollama fails."""
    summary, terms = _extract(ollama.generate(PROMPT.format(amostra=_sample(doc_dir))))
    (doc_dir / "_resumo.md").write_text(
        f"{summary}\n\n**Termos:** {', '.join(terms)}\n", encoding="utf-8"
    )
    return summary, terms
