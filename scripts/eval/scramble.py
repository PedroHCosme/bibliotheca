"""Deterministic scrambled corpus: flat folder, opaque names, mixed .tex/.txt/.md/.pdf.

The manifest (origin of every output file) goes to `manifest_path`, which callers keep
outside the corpora tree, so no arm can read folder names back from it.
"""
import json
import random
import re
import shutil
from pathlib import Path

FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
HEADING = re.compile(r"(?m)^(#{1,6})\s+(.*)$")
LATEX_LEVEL = {1: "section", 2: "subsection", 3: "subsubsection"}


def body(md: str) -> str:
    return FRONTMATTER.sub("", md, count=1)


def md_to_tex(md: str) -> str:
    # ponytail: no escaping of & % _ — real .tex noise, and biblio must cope with it anyway
    text = body(md)
    text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
    text = re.sub(r"\*(.+?)\*", r"\\textit{\1}", text)
    text = HEADING.sub(
        lambda m: "\\%s{%s}" % (LATEX_LEVEL[min(len(m.group(1)), 3)], m.group(2).strip()),
        text)
    text = re.sub(r"(?m)(?<=[.!?])$", r"~\\cite{ref}", text)
    return f"\\documentclass{{article}}\n\\begin{{document}}\n{text}\n\\end{{document}}\n"


def md_to_txt(md: str) -> str:
    text = body(md)
    text = re.sub(r"(?m)^#{1,6}\s+", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return re.sub(r"[*`]+", "", text)


def scramble(md_files, pdf_files, out: Path, manifest_path: Path, seed: int = 7,
             tex_share: float = 0.4, txt_share: float = 0.3) -> dict[str, str]:
    rng = random.Random(seed)
    mds = sorted(md_files, key=str)
    rng.shuffle(mds)
    n_tex, n_txt = round(len(mds) * tex_share), round(len(mds) * txt_share)
    jobs = ([(f, ".tex") for f in mds[:n_tex]]
            + [(f, ".txt") for f in mds[n_tex:n_tex + n_txt]]
            + [(f, ".md") for f in mds[n_tex + n_txt:]]
            + [(f, ".pdf") for f in sorted(pdf_files, key=str)])
    rng.shuffle(jobs)

    out.mkdir(parents=True, exist_ok=True)
    convert = {".tex": md_to_tex, ".txt": md_to_txt, ".md": body}
    manifest = {}
    for i, (src, ext) in enumerate(jobs):
        name = f"doc_{i:03d}{ext}"
        if ext == ".pdf":
            shutil.copyfile(src, out / name)
        else:
            (out / name).write_text(convert[ext](src.read_text(encoding="utf-8")),
                                    encoding="utf-8")
        manifest[name] = str(src)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    return manifest
