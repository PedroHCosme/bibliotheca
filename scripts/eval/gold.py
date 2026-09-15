"""Gold records: load, and check that every anchor really exists in its source file."""
import json
import re
import sys
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

KINDS = ("targeted", "thematic")
PER_KIND = 10


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)  # PDF ligatures (ﬁ) → plain letters
    text = re.sub(r"\\(?:textbf|textit)\{(.*?)\}", r"\1", text)
    text = re.sub(r"~?\\cite\{[^}]*\}", "", text)
    text = re.sub(r"[*`#]", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


@lru_cache(maxsize=None)
def _source_text(path: str) -> str:
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        import pymupdf
        with pymupdf.open(p) as doc:
            return normalize("\n".join(page.get_text() for page in doc))
    return normalize(p.read_text(encoding="utf-8", errors="replace"))


def validate(record: dict, sources: Path) -> list[str]:
    errors = [f"missing {k}" for k in ("id", "corpus", "kind", "question", "answer", "locations")
              if not record.get(k)]
    if record.get("kind") not in KINDS:
        errors.append(f"bad kind: {record.get('kind')!r}")
    for loc in record.get("locations") or []:
        f = sources / loc.get("file", "")
        if not f.is_file():
            errors.append(f"no such file: {loc.get('file')}")
        elif normalize(loc.get("anchor", "")) not in _source_text(str(f)):
            errors.append(f"anchor not found in {loc['file']}: {loc.get('anchor')!r}")
    return errors


def main(argv=None) -> None:
    from scripts.eval import arms
    corpus = (argv or sys.argv[1:])[0]
    records = load(arms.DATA / "gold" / f"{corpus}.jsonl")
    failed = False
    for rec in records:
        for err in validate(rec, arms.sources(corpus)):
            print(f"{rec.get('id')}: {err}")
            failed = True
    ids = Counter(r.get("id") for r in records)
    dupes = [i for i, n in ids.items() if n > 1]
    kinds = Counter(r.get("kind") for r in records)
    print(f"{corpus}: {len(records)} records, kinds={dict(kinds)}, duplicate ids={dupes}")
    if failed or dupes or any(kinds.get(k) != PER_KIND for k in KINDS):
        sys.exit(1)


if __name__ == "__main__":
    main()
