"""Build the eval's corpora, B-current bibliothecas, C slice folders and skill plugins.

Idempotent: existing source folders and bibliothecas are reused (biblio skips unchanged files).
"""
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.eval import arms
from scripts.eval.scramble import scramble

HOME = Path.home()
AIG = HOME / "aignosi" / "dev" / "repos" / "aig-docs"
ORGANIZED = [AIG / "04 - Clients & Deployments", AIG / "06 - Engineering & DevOps"]
SCRAMBLED_MD = AIG / "07 - Projects & R&D"
SCRAMBLED_MD_SAMPLE = 80
SCRAMBLED_PDF = HOME / "pedrocosme" / "dev" / "ufmg" / "conversores" / "pdf"
ROBOTICS = [HOME / "Downloads" / "Spong-RobotmodelingandControl.pdf",
            arms.REPO / "scripts" / "benchmark" / "inverse-kinematics.md"]
INGESTIBLE = (".pdf", ".md", ".txt")
CORPORA = ("organized", "robotics", "scrambled")


def biblio_exe() -> str:
    exe = Path(sys.executable).parent / "Scripts" / "biblio.exe"
    return str(exe) if exe.exists() else (shutil.which("biblio") or sys.exit("biblio not found"))


def build_sources(corpus: str) -> None:
    dest = arms.sources(corpus)
    if dest.exists():
        return
    if corpus == "organized":
        for root in ORGANIZED:
            for f in root.rglob("*"):
                if f.is_file() and f.suffix.lower() in INGESTIBLE and ".git" not in f.parts:
                    target = dest / root.name / f.relative_to(root)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)
    elif corpus == "robotics":
        dest.mkdir(parents=True)
        for f in ROBOTICS:
            shutil.copy2(f, dest / f.name)
    else:
        mds = sorted(SCRAMBLED_MD.rglob("*.md"), key=str)
        sample = random.Random(7).sample(mds, min(SCRAMBLED_MD_SAMPLE, len(mds)))
        scramble(sample, sorted(SCRAMBLED_PDF.glob("*.pdf")), dest,
                 arms.DATA / "manifests" / "scrambled.json")


def build_bibliotheca(corpus: str) -> None:
    reg = arms.registry(corpus)
    reg.parent.mkdir(parents=True, exist_ok=True)
    cmd = [biblio_exe(), "--out", str(arms.bibliotheca(corpus)), "add",
           str(arms.sources(corpus)), "--no-summary", "--max-ocr-pages", "0"]
    print(">", " ".join(cmd), flush=True)
    subprocess.run(cmd, env=dict(os.environ, BIBLIO_REGISTRY=str(reg)),
                   stdin=subprocess.DEVNULL)  # no tty: biblio never prompts


def build_slices(corpus: str) -> None:
    dest = arms.slices(corpus)
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(arms.bibliotheca(corpus), dest,
                    ignore=shutil.ignore_patterns("CLAUDE.md", "biblio.db*"))


def main(argv=None) -> None:
    chosen = (argv or sys.argv[1:]) or list(CORPORA)
    (arms.DATA / "registry").mkdir(parents=True, exist_ok=True)
    (arms.DATA / "registry" / "empty.txt").touch()
    for corpus in chosen:
        build_sources(corpus)
        build_bibliotheca(corpus)
        build_slices(corpus)
        arms.write_plugin(corpus)
        print(f"{corpus}: ready", flush=True)
    # `biblio add` reinstalls ~/.claude/skills/bibliotheca from the eval registry;
    # put the user's real skill back.
    subprocess.run([biblio_exe(), "skill"])


if __name__ == "__main__":
    main()
