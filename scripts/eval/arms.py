"""Arms: where each one runs, which env it gets, and which `claude` flags isolate it.

A          sources + glob/grep, no skills
B-<ver>    sources + a plugin carrying only the Bibliotheca skill for that corpus
C          Bibliotheca slices (no CLAUDE.md, no db) + glob/grep, no skills
"""
import os
from pathlib import Path

from biblio import paths, skill

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "scripts" / "eval" / "data"
MODEL = "claude-sonnet-5"
TOOLS = "Read,Glob,Grep,Bash"
PROMPT = ("Answer the question below using only the documents available to you; "
          "the documents are in the current directory. For every claim, cite the "
          "file and the page or section it comes from. Be concise.\n\n"
          "Question: {question}\n")


def version(arm: str) -> str | None:
    return arm.split("-", 1)[1] if arm.startswith("B-") else None


def sources(corpus: str) -> Path:
    return DATA / "corpora" / corpus


def bibliotheca(corpus: str, ver: str = "current") -> Path:
    return DATA / "bib" / ver / corpus


def slices(corpus: str) -> Path:
    return DATA / "c" / corpus


def registry(corpus: str, ver: str = "current") -> Path:
    return DATA / "registry" / ver / f"{corpus}.txt"


def plugin(corpus: str, ver: str = "current") -> Path:
    return DATA / "plugin" / ver / corpus


def cwd(arm: str, corpus: str) -> Path:
    return slices(corpus) if arm == "C" else sources(corpus)


def env(arm: str, corpus: str) -> dict:
    ver = version(arm)
    reg = registry(corpus, ver) if ver else DATA / "registry" / "empty.txt"
    return dict(os.environ, HF_HUB_OFFLINE="1", BIBLIO_REGISTRY=str(reg))


def command(arm: str, corpus: str, claude: str, model: str = MODEL) -> list[str]:
    cmd = [claude, "-p", "--output-format", "stream-json", "--verbose",
           "--model", model, "--tools", TOOLS,
           "--permission-mode", "bypassPermissions",
           "--no-session-persistence", "--safe-mode"]
    ver = version(arm)
    if ver:
        cmd += ["--plugin-dir", str(plugin(corpus, ver))]
    return cmd


def write_plugin(corpus: str, ver: str = "current") -> Path:
    """Plugin whose only content is the skill `biblio skill` would install for this corpus."""
    root = plugin(corpus, ver)
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin" / "plugin.json").write_text(
        '{"name": "bibliotheca-eval", "version": "0.0.0"}\n', encoding="utf-8")
    saved, paths.REGISTRY = paths.REGISTRY, registry(corpus, ver)
    try:
        text = skill.skill_text()
    finally:
        paths.REGISTRY = saved
    (root / "skills" / "bibliotheca").mkdir(parents=True, exist_ok=True)
    (root / "skills" / "bibliotheca" / "SKILL.md").write_text(text, encoding="utf-8")
    return root
