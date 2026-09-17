"""Embeddings: model and dimension decided by measurement."""
import functools
import os
import re
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import numpy as np

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIM = 384
QUERY_PREFIX = ""
DOC_PREFIX = ""

WINDOW = 2000
OVERLAP = 200

# Matches either frontmatter form: the old YAML block (still on disk in every
# bibliotheca built before this change, e.g. data/bib/current/, data/c/) or the
# new one-line HTML-comment form. Widened, not replaced — scripts/eval/floor.py
# strips the baseline arms' YAML slices with this same regex via cache_raw().
_FRONTMATTER = re.compile(r"\A(?:---\n.*?\n---\n|<!--.*?-->\n)", re.S)


@functools.lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    try:
        return SentenceTransformer(MODEL)
    except Exception:
        # genuine first run: model not cached. huggingface_hub froze
        # HF_HUB_OFFLINE into a module constant at import, so clearing the env
        # var alone is not enough — toggle the constant too. Retry once, restore.
        import huggingface_hub.constants as hf_const
        prev_env = os.environ.pop("HF_HUB_OFFLINE", None)
        prev_const = hf_const.HF_HUB_OFFLINE
        hf_const.HF_HUB_OFFLINE = False
        try:
            return SentenceTransformer(MODEL)
        finally:
            hf_const.HF_HUB_OFFLINE = prev_const
            if prev_env is not None:
                os.environ["HF_HUB_OFFLINE"] = prev_env


def windows(text: str, first_line: int = 1) -> list[dict]:
    """Slice by lines until the window is full. Returns text + 1-based inclusive pointer."""
    lines = text.split("\n")
    result, start = [], 0
    while start < len(lines):
        end, size = start, 0
        while end < len(lines) and (size == 0 or size + len(lines[end]) <= WINDOW):
            size += len(lines[end]) + 1
            end += 1
        block = "\n".join(lines[start:end]).strip()
        if block:
            result.append({"text": block,
                           "line_start": first_line + start,
                           "line_end": first_line + end - 1})
        if end >= len(lines):
            break
        rewind = 0
        while rewind < end - start - 1 and sum(
                len(l) + 1 for l in lines[end - rewind - 1:end]) < OVERLAP:
            rewind += 1
        start = end - rewind
    return result


def doc_chunks(doc_dir: Path) -> list[dict]:
    chunks = []
    for f in sorted(doc_dir.glob("[0-9]*.md")):
        content = f.read_text(encoding="utf-8")
        body = _FRONTMATTER.sub("", content)
        offset = content[:len(content) - len(body)].count("\n") + 1
        section = next((l for l in body.split("\n") if l.startswith("#")), f.stem)
        for win in windows(body, first_line=offset):
            chunks.append(win | {"file": f.name, "section": section.lstrip("# ")})
    return chunks


def vectorize(texts: list[str]) -> np.ndarray:
    """Vectorize corpus chunks. Document prefix, not query prefix."""
    if not texts:
        return np.empty((0, DIM), dtype="float32")
    return _model().encode([DOC_PREFIX + t for t in texts],
                           normalize_embeddings=True,
                           batch_size=16).astype("float32")


def vectorize_query(query: str) -> np.ndarray:
    return _model().encode([QUERY_PREFIX + query], normalize_embeddings=True,
                           batch_size=1).astype("float32")[0]
