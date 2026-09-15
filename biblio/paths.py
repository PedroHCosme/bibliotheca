"""Where bibliothecas live and how names become paths."""
import os
import re
import unicodedata
from pathlib import Path

ROOT = Path.home() / "biblio"
DEFAULT_BIBLIOTHECA = ROOT / "geral"

# Overridable so an eval (or a test harness) can isolate itself from the user's bibliothecas.
REGISTRY = Path(os.environ.get("BIBLIO_REGISTRY")
                or Path.home() / ".biblio" / "bibliothecas.txt")


def slug(text: str, limit: int = 60) -> str:
    no_accent = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    clean = re.sub(r"[^a-z0-9]+", "-", no_accent.lower()).strip("-")
    return clean[:limit].rstrip("-") or "untitled"


def root(output: Path | str | None = None) -> Path:
    """Accepts name or path, symmetric with --lib in search."""
    if not output:
        return DEFAULT_BIBLIOTHECA
    text = str(output)
    return ROOT / slug(text) if Path(text).parent == Path(".") else Path(text)


def register(bibliotheca: Path) -> None:
    """Move the bibliotheca to the top of the list."""
    path = str(bibliotheca.resolve())
    known = [c for c in known_bibliothecas() if c != path]
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text("\n".join([path, *known]) + "\n", encoding="utf-8")


def known_bibliothecas() -> list[str]:
    """Most recent first. Removes entries deleted from disk."""
    if not REGISTRY.exists():
        return []
    return [line for line in REGISTRY.read_text(encoding="utf-8").splitlines()
            if line.strip() and Path(line).is_dir()]


def all_libs(output=None) -> list[Path]:
    """Bibliothecas to search: the requested one(s), or all known, or just the default."""
    if isinstance(output, (list, tuple)):
        return [Path(c) for c in output]
    if output:
        requested = Path(output)
        if requested.is_dir():
            return [requested]
        known = [c for c in known_bibliothecas() if Path(c).name == str(output)]
        return [Path(known[0])] if known else [requested]
    return [Path(c) for c in known_bibliothecas()] or [DEFAULT_BIBLIOTHECA]
