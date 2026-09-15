"""Arms: where each one runs, which env it gets, and which `claude` flags isolate it.

A          sources + glob/grep, no skills
B-<ver>    a copy of the sources under a folder whose .claude/skills holds only the Bibliotheca skill
C          Bibliotheca slices (no CLAUDE.md, no db) + glob/grep, no skills

Isolation (verified by probe): `--setting-sources project` drops the user's settings, plugins,
hooks, skills and CLAUDE.md, while project skills found above the cwd still load. `--safe-mode`
and `--plugin-dir` were rejected: safe mode disables plugins, and plugin skills never reach the
model's skill list.
"""
import os
import shutil
from pathlib import Path

from biblio import paths, skill

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "scripts" / "eval" / "data"
MODEL = "claude-sonnet-5"
# Skill is required for B to invoke the Bibliotheca skill; A and C have no skills, so it is inert there.
TOOLS = "Read,Glob,Grep,Bash,Skill"
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


def b_root(corpus: str, ver: str = "current") -> Path:
    """Holds `.claude/skills/bibliotheca/` and `docs/` (B's cwd), so glob in docs never sees the skill."""
    return DATA / "b" / ver / corpus


def cwd(arm: str, corpus: str) -> Path:
    ver = version(arm)
    if ver:
        return b_root(corpus, ver) / "docs"
    return slices(corpus) if arm == "C" else sources(corpus)


def env(arm: str, corpus: str) -> dict:
    ver = version(arm)
    reg = registry(corpus, ver) if ver else DATA / "registry" / "empty.txt"
    # Without these, this repo's auto-memory and the user's ~/.claude/CLAUDE.md leak into every arm.
    return dict(os.environ, HF_HUB_OFFLINE="1", BIBLIO_REGISTRY=str(reg),
                CLAUDE_CODE_DISABLE_AUTO_MEMORY="1", CLAUDE_CODE_DISABLE_CLAUDE_MDS="1")


def command(arm: str, corpus: str, claude: str, model: str = MODEL) -> list[str]:
    return [claude, "-p", "--output-format", "stream-json", "--verbose",
            "--model", model, "--tools", TOOLS,
            "--permission-mode", "bypassPermissions", "--no-session-persistence",
            "--setting-sources", "project", "--strict-mcp-config",
            # the cwd is inside this repo: its branch and commits would otherwise enter the context
            "--settings", '{"includeGitInstructions": false}']


def write_b(corpus: str, ver: str = "current") -> Path:
    """B's folder: a fresh copy of the sources plus the skill `biblio skill` would install for this corpus."""
    root = b_root(corpus, ver)
    shutil.rmtree(root / "docs", ignore_errors=True)
    shutil.copytree(sources(corpus), root / "docs")
    saved, paths.REGISTRY = paths.REGISTRY, registry(corpus, ver)
    try:
        text = skill.skill_text()
    finally:
        paths.REGISTRY = saved
    dest = root / ".claude" / "skills" / "bibliotheca"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text(text, encoding="utf-8")
    return root
