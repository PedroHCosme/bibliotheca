"""argparse and nothing else. All logic lives in the modules; only parsing here."""
import argparse
import json
import sys
from pathlib import Path

from biblio import index, meta, pipeline, search, skill
from biblio.paths import known_bibliothecas, root


def _confirm(text: str) -> bool:
    return input(f"{text} [y/N] ").strip().lower() in ("y", "yes", "s", "sim")


def _minutes(ocr_pages: int) -> int:
    return round(ocr_pages * 30 / 60)  # ~30s/page on CPU


def _print_survey(report: dict, target: Path) -> None:
    by_ext = report["by_ext"]
    exts = ", ".join(f"{n} {ext}" for ext, n in sorted(by_ext.items()))
    total = report["total_ocr"]
    print(f"\n  {sum(by_ext.values())} documents  ({exts})")
    print(f"  OCR pages total: {total}  (~{_minutes(total)} min on CPU)")
    over = report["over_cap"]
    if over:
        print(f"\n  Over --max-ocr-pages ({report['max_ocr_pages']}):")
        for f, n in sorted(over.items(), key=lambda kv: -kv[1]):
            print(f"    {f.stem:<45} {n} OCR pages  (~{_minutes(n)} min)")
        print(f"\n  Proceed: biblio add {target}                 # prompts about the files above")
        print(f"           biblio add {target} --yes           # skips them, indexes the rest")
        print(f"           biblio add {target} --max-ocr-pages 0   # OCR everything, no cap")


def _over_cap_exclude(report: dict, interactive: bool) -> frozenset | None:
    """Returns the set of paths to exclude, or None to abort the run."""
    over = report["over_cap"]
    if interactive:
        raw = input(
            f"{len(over)} files exceed the OCR cap "
            f"(~{_minutes(sum(over.values()))} min total). "
            "[p]roceed with all / [s]kip them / [a]bort? ").strip().lower()
        choice = raw[:1] if raw[:1] in "psa" else "s"
        if choice == "p":
            return frozenset()
        if choice == "a":
            return None
    return frozenset(over)


def _hit(pointer: str) -> int:
    import re
    from biblio import db

    match = re.match(r"^(.+):(\d+)-(\d+)$", pointer)
    if not match:
        print(f"invalid pointer format: {pointer}", file=sys.stderr)
        return 1
    filepath = Path(match.group(1)).resolve()
    pstart, pend = int(match.group(2)), int(match.group(3))

    bibliotheca = None
    for parent in filepath.parents:
        if (parent / db.DB_FILE).exists():
            bibliotheca = parent
            break
    if bibliotheca is None:
        print(f"no bibliotheca found for: {filepath}", file=sys.stderr)
        return 1

    con = db.connect(bibliotheca)
    try:
        rel = filepath.relative_to(bibliotheca)
        doc, file = rel.parts[0], rel.parts[1]
        # search pointers use section intervals (often 1..N), not the raw chunk
        # range — rank an exact match first, then the chunk enclosing pstart,
        # then any chunk inside [pstart, pend], then the file's first chunk.
        row = con.execute(
            "SELECT id FROM chunks WHERE doc = ? AND file = ? "
            "ORDER BY CASE "
            " WHEN line_start = ? AND line_end = ? THEN 0 "
            " WHEN ? BETWEEN line_start AND line_end THEN 1 "
            " WHEN line_start BETWEEN ? AND ? THEN 2 ELSE 3 END, line_start "
            "LIMIT 1",
            (doc, file, pstart, pend, pstart, pstart, pend)).fetchone()
        if row is None:
            print(f"chunk not found: {doc}/{file}", file=sys.stderr)
            return 1
        vec_f16 = db.get_last_query_vec(con)
        if vec_f16 is None:
            print("no previous search found in this bibliotheca", file=sys.stderr)
            return 1
        # the only place the session counter advances — it's the frecency
        # decay clock: one hit == one confirmed-useful interaction, not one search
        session = db.increment_session(con)
        db.record_access(con, row["id"], vec_f16, weight=5, session_id=session)
    finally:
        con.close()
    return 0


def _status(args) -> int:
    bibliotheca = root(args.out)
    if not bibliotheca.exists():
        print(f"empty bibliotheca: {bibliotheca}")
        return 0
    for folder in sorted(p for p in bibliotheca.iterdir() if p.is_dir()):
        data = meta.read(folder)
        if not data:
            continue
        state = data.get("failed") or (
            "summary pending" if data.get("summary") == "pending" else "ok")
        source = f"{data['pages']} pages" if data.get("pages") else data.get(
            "format", "?")
        print(f"{folder.name:<45} {source:>8}  "
              f"{data.get('slices','?'):>3} slices  {state}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="biblio",
                                description="Document memory layer for agents")
    p.add_argument("--out", help="bibliotheca folder (default: ~/biblio)")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("add", help="ingest .pdf, .md or .txt — file or folder")
    a.add_argument("target")
    a.add_argument("--device", default="auto", help="auto | cpu | cuda")
    a.add_argument("--force", action="store_true", help="reprocess even without changes")
    a.add_argument("--summary", dest="summary_mode", action="store_const", const="yes",
                   default="auto", help="generate summary/terms per document; downloads "
                   "Ollama+qwen if needed (asks first)")
    a.add_argument("--no-summary", dest="summary_mode", action="store_const", const="no",
                   help="never generate summary/terms, even with Ollama available")
    a.add_argument("--max-size", type=float, default=None, metavar="MB",
                   help="skip files larger than N megabytes (e.g. --max-size 10)")
    a.add_argument("--fast", action="store_true",
                   help="skip OCR (Docling), use only native extraction — fast but "
                   "scanned pages come out empty")
    a.add_argument("--dry-run", action="store_true",
                   help="triage the folder, print the OCR estimate, write nothing")
    a.add_argument("--max-ocr-pages", type=int, default=25, metavar="N",
                   help="hold back files needing more than N OCR pages (0 = no cap)")
    a.add_argument("--yes", action="store_true",
                   help="non-interactive: skip files over --max-ocr-pages without asking")

    b = sub.add_parser("search", help="search and return pointers")
    b.add_argument("query")
    b.add_argument("--top", type=int, default=5)
    b.add_argument("--doc", help="restrict to one document")
    b.add_argument("--lib", help="restrict to one bibliotheca: path or name "
                                 "(default: all known)")
    b.add_argument("--context", choices=("section", "window"), default="section",
                   help="section: entire slice (default); window: only the matched chunk")
    b.add_argument("--json", action="store_true")
    b.add_argument("--no-frecency", action="store_true",
                   help="disable the frecency boost for this search")

    i = sub.add_parser("index", help="regenerate INDEX.md and CLAUDE.md without reprocessing")
    i.add_argument("--summary", dest="summary_mode", action="store_const", const="yes",
                   default="auto", help="fill pending summaries; installs "
                   "Ollama+qwen if needed (asks first)")
    i.add_argument("--no-summary", dest="summary_mode", action="store_const", const="no",
                   help="only regenerate INDEX.md/CLAUDE.md, without touching summaries")
    sub.add_parser("status", help="what was ingested, what failed, what's pending")
    sub.add_parser("libs", help="registered bibliothecas")
    sub.add_parser("skill", help="install the Claude Code skill (without creating shortcut)")
    sub.add_parser("gui", help="launch the localhost interface")
    sub.add_parser("shortcut", help="create the desktop shortcut")
    h = sub.add_parser("hit", help="record an explicit access (weight 5) for a search result")
    h.add_argument("pointer", help='path:start-end as returned by biblio search')

    sub.add_parser("version", help="show installed version")
    sub.add_parser("update", help="update to the latest GitHub version")

    args = p.parse_args(argv)

    if args.command in ("add", "gui", "index"):
        from biblio.version_check import check
        check()

    if args.command == "add":
        target = Path(args.target)
        # ponytail: survey calls triage (find_tables) on every PDF — skip it
        # when --fast since OCR routing is irrelevant. No upgrade path needed.
        report = (pipeline.survey(target, args.max_ocr_pages)
                  if not args.fast and (args.dry_run or (target.is_dir() and args.max_ocr_pages))
                  else None)
        if args.dry_run:
            _print_survey(report, target)
            return 0

        exclude = frozenset()
        if report and report["over_cap"]:
            interactive = not args.yes and sys.stdin.isatty()
            exclude = _over_cap_exclude(report, interactive)
            if exclude is None:
                print("aborted.")
                return 1

        ask = _confirm if sys.stdin.isatty() and not args.yes else None
        count = pipeline.ingest(target, output=args.out, device=args.device,
                                force=args.force, ask=ask,
                                summary=args.summary_mode, max_size_mb=args.max_size,
                                fast=args.fast, exclude=exclude)
        index.generate(output=args.out, summary="no")
        if count["ok"]:
            skill.install()
        print(f"\n{count['ok']} processed, {count['skipped']} unchanged, "
              f"{count['failed']} failed")
        return 1 if count["failed"] else 0

    if args.command == "search":
        results = search.search(args.query, output=args.lib or args.out,
                                top=args.top, doc=args.doc, context=args.context,
                                no_frecency=args.no_frecency)
        print(json.dumps(results, ensure_ascii=False) if args.json
              else search.format_results(results))
        return 0

    if args.command == "index":
        dest = index.generate(output=args.out, summary=args.summary_mode,
                              ask=(_confirm if sys.stdin.isatty() else None))
        skill.install()
        print(dest)
        return 0

    if args.command == "hit":
        return _hit(args.pointer)

    if args.command == "status":
        return _status(args)

    if args.command == "libs":
        for path in known_bibliothecas() or ["(none; run `biblio add`)"]:
            print(path)
        return 0

    if args.command == "skill":
        print(skill.install())
        return 0

    if args.command == "gui":
        from biblio.gui import launch
        launch(output=args.out)
        return 0

    if args.command == "shortcut":
        from biblio.shortcut import create
        if lnk := create():
            print(lnk)
        return 0

    if args.command == "version":
        from importlib.metadata import version
        print(f"biblio {version('biblio')}")
        return 0

    if args.command == "update":
        url = "git+https://github.com/PedroHCosme/bibliotheca.git"
        if sys.platform == "win32":
            print("biblio can't update itself on Windows (the running .exe is locked).\n"
                  "Run this in a fresh shell:\n\n"
                  f'  "{sys.executable}" -m pip install --upgrade {url}')
            return 0
        import subprocess
        print(f"Updating from {url} ...")
        return subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", url]).returncode

    return 1


if __name__ == "__main__":
    sys.exit(main())
