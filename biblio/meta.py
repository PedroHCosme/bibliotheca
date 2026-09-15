"""`_meta.yaml`: provenance, hash, and state. Makes reprocessing a folder cheap."""
import hashlib
from datetime import date
from pathlib import Path

import yaml

FILENAME = "_meta.yaml"


def hash_file(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(doc_dir: Path) -> dict:
    f = doc_dir / FILENAME
    if not f.exists():
        return {}
    return yaml.safe_load(f.read_text(encoding="utf-8")) or {}


def write(doc_dir: Path, data: dict) -> None:
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / FILENAME).write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def already_processed(doc_dir: Path, digest: str) -> bool:
    """Same hash and no recorded failure: nothing to redo."""
    prev = read(doc_dir)
    return prev.get("hash") == digest and not prev.get("failed")


def new_record(path: Path, digest: str, route: dict[str, list[int]]) -> dict:
    """Empty route = source was already text (.md, .txt): no pages, no OCR."""
    return {
        "source": str(path.resolve()),
        "format": path.suffix.lower().lstrip("."),
        "hash": digest,
        "pages": sum(len(v) for v in route.values()) or None,
        "route": {k: len(v) for k, v in route.items()},
        "date": date.today().isoformat(),
        "quality": "ok",
        "failed": None,
        "summary": "pending",
    }
