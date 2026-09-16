"""Offline FLOOR sweep: re-slice each corpus at every FLOOR and measure cost vs recall.

No agents. For each gold question the query is the question text; a gold location counts as
found when one of the top-3 search hits is a slice of the gold document containing the anchor.
Cost is the text the agent would read to see those 3 slices (chars/4, frontmatter included).
Score = tokens read / recall@3; lowest wins.

Conversion is cached once per corpus, so the sweep only ever changes slicing.
"""
import json
import shutil
import sys
from pathlib import Path

from biblio import db, embed, meta, paths, search, slice as slicing
from biblio.normalize import normalize
from biblio.pipeline import _frontmatter
from scripts.eval import arms, gold

FLOORS = (400, 1500, 3000)
TOP = 3
CORPORA = ("robotics", "organized", "scrambled")
SWEEP = arms.DATA / "floor"


def raw_dir(corpus: str) -> Path:
    return SWEEP / "raw" / corpus


def bib_dir(corpus: str, floor: int) -> Path:
    return SWEEP / str(floor) / corpus


def cache_raw(corpus: str) -> dict[str, str]:
    """Rebuild each document's markdown from the baseline slices. Returns {source path: doc}.

    Re-converting the PDFs would cost hours and would change the text; the sweep must vary
    only the FLOOR. Page markers do not survive, so page fields in swept slices are absent.
    """
    out = raw_dir(corpus)
    index = out / "index.json"
    if index.exists():
        return json.loads(index.read_text(encoding="utf-8"))
    src = arms.sources(corpus).resolve()
    names = {}
    for folder in sorted(p for p in arms.bibliotheca(corpus).iterdir() if p.is_dir()):
        info = meta.read(folder)
        if info.get("failed") or not info.get("source"):
            continue
        parts = sorted(folder.glob("[0-9]*.md"), key=lambda f: int(f.name.split("-")[0]))
        text = "\n".join(
            embed._FRONTMATTER.sub("", f.read_text(encoding="utf-8")).strip()
            for f in parts)
        if not text.strip():
            continue
        names[str(Path(info["source"]).resolve().relative_to(src)).replace("\\", "/")] = folder.name
        (out / folder.name).mkdir(parents=True, exist_ok=True)
        (out / folder.name / "raw.md").write_text(text, encoding="utf-8")
        meta.write(out / folder.name, {"source": info["source"], "pages": False})
    index.write_text(json.dumps(names, indent=2), encoding="utf-8")
    return names


def build(corpus: str, floor: int) -> None:
    dest = bib_dir(corpus, floor)
    if (dest / db.DB_FILE).exists():
        return
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    slicing.FLOOR = floor
    con = db.connect(dest)
    try:
        for folder in sorted(p for p in raw_dir(corpus).iterdir() if p.is_dir()):
            name = folder.name
            info = meta.read(folder)
            slices = slicing.slice_doc(normalize((folder / "raw.md").read_text(encoding="utf-8")),
                                       with_pages=info["pages"])
            target = dest / name
            target.mkdir(parents=True, exist_ok=True)
            for s in slices:
                (target / s.name).write_text(_frontmatter(s, name) + s.text + "\n",
                                             encoding="utf-8")
            meta.write(target, info | {"slices": len(slices)})
            chunks = embed.doc_chunks(target)
            db.replace_document(con, name, chunks, embed.vectorize([c["text"] for c in chunks]))
            print(f"floor={floor} {corpus}/{name}: {len(slices)} slices", flush=True)
    finally:
        con.close()


def measure(corpus: str, floor: int, names: dict[str, str]) -> dict:
    dest = bib_dir(corpus, floor)
    questions = gold.load(arms.DATA / "gold" / f"{corpus}.jsonl")
    found = total = 0
    tokens = 0
    per_kind: dict[str, list[int]] = {"targeted": [0, 0], "thematic": [0, 0]}
    for q in questions:
        hits = search.search(q["question"], output=dest, top=TOP, no_frecency=True)
        texts = {(h["doc"], Path(h["path"]).read_text(encoding="utf-8")) for h in hits}
        tokens += sum(len(t) for _, t in texts) // 4
        for loc in q["locations"]:
            total += 1
            per_kind[q["kind"]][1] += 1
            doc = names.get(loc["file"].replace("\\", "/"))
            anchor = gold.normalize(loc["anchor"])
            if any(d == doc and anchor in gold.normalize(t) for d, t in texts):
                found += 1
                per_kind[q["kind"]][0] += 1
    recall = found / total
    slices = sum(1 for p in dest.rglob("[0-9]*.md"))
    return {"corpus": corpus, "floor": floor, "slices": slices,
            "recall": round(recall, 3), "tokens_per_query": tokens // len(questions),
            "score": round(tokens / len(questions) / recall) if recall else None,
            "recall_targeted": round(per_kind["targeted"][0] / per_kind["targeted"][1], 3),
            "recall_thematic": round(per_kind["thematic"][0] / per_kind["thematic"][1], 3)}


def main(argv=None) -> None:
    chosen = (argv or sys.argv[1:]) or list(CORPORA)
    SWEEP.mkdir(parents=True, exist_ok=True)
    paths.REGISTRY = SWEEP / "registry.txt"  # never touch the user's bibliothecas
    rows = []
    for corpus in chosen:
        names = cache_raw(corpus)
        for floor in FLOORS:
            build(corpus, floor)
            rows.append(measure(corpus, floor, names))
            print(json.dumps(rows[-1]), flush=True)
    (SWEEP / "results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
