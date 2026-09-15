import pytest

from biblio.pipeline import ingest


@pytest.fixture
def ingested_bibliotheca(tmp_path, native_pdf):
    output = tmp_path / "lib"
    ingest(native_pdf, output=output)
    return output, native_pdf


def _signature(folder):
    return {p.name: (p.stat().st_mtime_ns, p.read_bytes())
            for p in sorted(folder.rglob("*")) if p.is_file() and p.suffix != ".db"}


def test_second_run_skips_document(ingested_bibliotheca):
    output, pdf = ingested_bibliotheca
    assert ingest(pdf, output=output) == {"ok": 0, "skipped": 1, "failed": 0}


def test_second_run_does_not_rewrite_any_file(ingested_bibliotheca):
    output, pdf = ingested_bibliotheca
    before = _signature(output)
    ingest(pdf, output=output)
    assert _signature(output) == before


def test_force_reprocesses(ingested_bibliotheca):
    output, pdf = ingested_bibliotheca
    assert ingest(pdf, output=output, force=True)["ok"] == 1


def test_reprocessing_does_not_duplicate_chunks(ingested_bibliotheca):
    from biblio import db
    output, pdf = ingested_bibliotheca
    con = db.connect(output)
    before = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
    con.close()
    ingest(pdf, output=output, force=True)
    con = db.connect(output)
    after = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
    con.close()
    assert before == after > 0


def test_same_file_name_in_different_folders_keeps_both(tmp_path):
    docs = tmp_path / "docs"
    for client in ("alcoa", "samarco"):
        (docs / client).mkdir(parents=True)
        (docs / client / "index.md").write_text(
            f"# {client}\n" + f"{client} deployment notes. " * 60, encoding="utf-8")
    output = tmp_path / "lib"

    assert ingest(docs, output=output)["ok"] == 2
    folders = sorted(p.name for p in output.iterdir() if (p / "_meta.yaml").exists())
    assert folders == ["index", "samarco-index"]
    assert "samarco" in next((output / "samarco-index").glob("[0-9]*.md")).read_text(
        encoding="utf-8")
    assert ingest(docs, output=output) == {"ok": 0, "skipped": 2, "failed": 0}


def test_markdown_input_is_also_idempotent(tmp_path):
    source = tmp_path / "already-converted.md"
    source.write_text("# Escopo\n" + "texto tecnico. " * 60, encoding="utf-8")
    output = tmp_path / "lib"

    assert ingest(source, output=output)["ok"] == 1
    frontmatter = next((output / "already-converted").glob("[0-9]*.md")).read_text(
        encoding="utf-8")
    assert "pages:" not in frontmatter, "source without pages should not invent pages"
    assert ingest(source, output=output) == {"ok": 0, "skipped": 1, "failed": 0}
