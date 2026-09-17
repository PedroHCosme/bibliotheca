"""ingest(): the single entry point. CLI and GUI are shells over it."""
import re
from collections import Counter
from pathlib import Path

import yaml

from biblio import db, embed, meta, ollama, summarize, tex
from biblio.convert import convert
from biblio.normalize import normalize
from biblio.paths import root, register, slug
from biblio.slice import slice_doc
from biblio.triage import triage

EXTENSIONS = (".pdf", ".md", ".txt", ".tex")


def _files(target: Path) -> list[Path]:
    if target.is_dir():
        return sorted(p for p in target.rglob("*") if p.suffix.lower() in EXTENSIONS)
    return [target]


def survey(target: Path | str, max_ocr_pages: int = 25) -> dict:
    """Folder-wide triage: doc counts, OCR-page total, files over the cap.

    Pure — writes nothing. Used by `biblio add --dry-run` and by the CLI's
    pre-ingest cap gate. `max_ocr_pages` 0 disables the over-cap flagging.
    """
    files = _files(Path(target))
    by_ext = Counter(f.suffix.lower() for f in files)
    ocr_by_file = {f: len(triage(f)["ocr"])
                   for f in files if f.suffix.lower() == ".pdf"}
    over_cap = ({f: n for f, n in ocr_by_file.items() if n > max_ocr_pages}
                if max_ocr_pages else {})
    return {"files": files, "by_ext": dict(by_ext), "ocr_by_file": ocr_by_file,
            "total_ocr": sum(ocr_by_file.values()), "over_cap": over_cap,
            "max_ocr_pages": max_ocr_pages}


def _frontmatter(s, doc: str) -> str:
    parts = [f"{doc} §{s.section}"]
    if s.page_start is not None:
        parts.append(f"p.{s.page_start}-{s.page_end}")
    if s.parent is not None:
        parts.append(f"parent {s.parent}")
    return "<!-- " + " · ".join(parts) + " -->\n\n"


_SOURCE_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)


def _strip_source_frontmatter(text: str) -> str:
    """Obsidian vault: every .md already has its own YAML frontmatter."""
    m = _SOURCE_FRONTMATTER.match(text)
    if not m:
        return text
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        data = {}
    terms = data.get("aliases", []) + data.get("tags", []) if isinstance(data, dict) else []
    line = f"*{', '.join(map(str, terms))}*\n\n" if terms else ""
    return line + text[m.end():]


def _fast_page_count(path: Path) -> int:
    """Page count without layout analysis — just opens the PDF index."""
    import pymupdf
    with pymupdf.open(path) as doc:
        return len(doc)


def _get_text(path: Path, device: str, warn, name: str,
              fast: bool = False) -> tuple[str, dict]:
    """(raw markdown, route). Input that's already text skips triage and conversion."""
    if path.suffix.lower() != ".pdf":
        raw = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".tex":
            warn(f"{name}: converting LaTeX to markdown")
            raw = tex.to_markdown(raw)
        else:
            warn(f"{name}: already text, skipping conversion")
        return _strip_source_frontmatter(raw), {}
    # ponytail: fast mode skips triage entirely — find_tables() is the expensive
    # call and all pages go through pymupdf4llm anyway. Upgrade path: none, this
    # is the correct behavior.
    if fast:
        n = _fast_page_count(path)
        warn(f"{name}: {n} pages [fast: no triage]")
        route = {"native": list(range(1, n + 1)), "complex": [], "ocr": []}
        return convert(path, route, device=device, warn=warn, fast=True), route
    warn(f"{name}: triaging")
    route = triage(path)
    n_nat, n_cplx, n_ocr = len(route["native"]), len(route["complex"]), len(route["ocr"])
    parts = []
    if n_nat:
        parts.append(f"{n_nat} native")
    if n_cplx:
        parts.append(f"{n_cplx} with tables")
    if n_ocr:
        parts.append(f"{n_ocr} OCR (~{n_ocr * 30}s on CPU)")
    warn(f"{name}: {' + '.join(parts) or '0 pages'}"
         + (" [fast: no OCR]" if fast else ""))
    return convert(path, route, device=device, warn=warn, fast=fast), route


def _doc_name(path: Path, bibliotheca: Path) -> str:
    """File-name slug, unless another source owns that folder: then prefix parent folder names.

    `docs/alcoa/index.md` stays `index`; a later `docs/samarco/index.md` becomes `samarco-index`.
    Names already on disk never change, so re-running `add` stays idempotent.
    """
    source = str(path.resolve())
    parents = [slug(p) for p in path.resolve().parent.parts if slug(p)]
    for depth in range(len(parents) + 1):
        name = "-".join([*parents[len(parents) - depth:], slug(path.stem)])
        if meta.read(bibliotheca / name).get("source") in (None, source):
            return name
    # ponytail: only reachable when two sources share the whole path slug (e.g. "A b" vs "a-b")
    n = 2
    while meta.read(bibliotheca / f"{name}-{n}").get("source") not in (None, source):
        n += 1
    return f"{name}-{n}"


def _process_one(path: Path, bibliotheca: Path, device: str, force: bool,
                 warn, con, summarize_with_ollama: bool = False,
                 max_size_mb: float | None = None, fast: bool = False) -> str:
    name = _doc_name(path, bibliotheca)
    folder = bibliotheca / name
    size_mb = path.stat().st_size / (1024 * 1024)
    if max_size_mb is not None and size_mb > max_size_mb:
        warn(f"{name}: {size_mb:.1f}MB > limit of {max_size_mb}MB, skipping")
        return "skipped"

    digest = meta.hash_file(path)

    if not force and meta.already_processed(folder, digest):
        warn(f"{name}: unchanged, skipping")
        return "skipped"

    try:
        raw, route = _get_text(path, device, warn, name, fast=fast)
    except Exception as err:
        warn(f"{name}: FAILED ({err})")
        meta.write(folder, {"source": str(path.resolve()), "hash": digest,
                            "failed": str(err)[:120]})
        return "failed"

    warn(f"{name}: slicing")
    slices = slice_doc(normalize(raw), with_pages=bool(route))

    for old in folder.glob("[0-9]*.md"):
        old.unlink()
    folder.mkdir(parents=True, exist_ok=True)
    for s in slices:
        (folder / s.name).write_text(_frontmatter(s, name) + s.text + "\n",
                                     encoding="utf-8")

    record = meta.new_record(path, digest, route)
    record["slices"] = len(slices)

    warn(f"{name}: indexing")
    chunks = embed.doc_chunks(folder)
    db.replace_document(con, name, chunks,
                        embed.vectorize([c["text"] for c in chunks]))
    record["chunks"] = len(chunks)

    if summarize_with_ollama:
        try:
            s, terms = summarize.summarize(folder)
            record |= {"summary": s, "terms": terms}
        except Exception as err:
            warn(f"{name}: summary pending ({err})")
    meta.write(folder, record)
    warn(f"{name}: {len(slices)} slices")
    return "ok"


def ingest(target: Path | str, output: Path | str | None = None, device: str = "auto",
           force: bool = False, warn=print, ask=None,
           summary: str = "auto", max_size_mb: float | None = None,
           fast: bool = False, exclude=frozenset()) -> dict[str, int]:
    """Processes a file (.pdf/.md/.txt) or a folder.

    `warn` is the only progress channel: the GUI passes its own.
    `summary`: 'auto' uses Ollama IF already ready; 'yes' asks and installs;
    'no' never summarizes.
    `max_size_mb`: skips files larger than this (None = no limit).
    `fast`: skips Docling/OCR, uses pymupdf4llm for everything.
    `exclude`: paths to skip (the CLI's over-OCR-cap set).
    """
    bibliotheca = root(output)
    bibliotheca.mkdir(parents=True, exist_ok=True)
    register(bibliotheca)  # early: a multi-day or interrupted run must still be visible
    summarize_with_ollama = ollama.wants_summary(summary, ask, warn)

    count = {"ok": 0, "skipped": 0, "failed": 0}
    con = db.connect(bibliotheca)
    try:
        for f in _files(Path(target)):
            if f in exclude:
                count["skipped"] += 1
                continue
            try:
                count[_process_one(f, bibliotheca, device, force, warn, con,
                                   summarize_with_ollama,
                                   max_size_mb=max_size_mb, fast=fast)] += 1
            except Exception as err:
                warn(f"{f.name}: FAILED ({err})")
                count["failed"] += 1
    finally:
        con.close()

    if exclude:
        warn("\nskipped (over OCR budget):")
        for f in sorted(exclude):
            warn(f'  {f.stem}  — run: biblio add "{f}" --fast   '
                 f'(or --max-ocr-pages 0)')
    return count
