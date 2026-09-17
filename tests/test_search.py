from biblio.search import search, format_results, rrf


def test_rrf_sums_both_lists():
    scores = rrf([[10, 20, 30], [30, 40]])
    assert scores[30] > scores[10], "id in both lists must beat the top of one"
    assert scores[10] > scores[20]


def test_rrf_empty_list_does_not_break():
    assert rrf([[], [7]]) == {7: 1 / 2}


def test_single_ranker_winner_beats_mediocre_agreement():
    """The bug K_RRF=60 caused: a chunk ranked 1 by one ranker lost to a chunk ranked 5 by both."""
    scores = rrf([[1, 90, 91, 92, 7], [2, 93, 94, 95, 7]])
    assert scores[1] > scores[7], "rank 1 in one list must beat rank 5 in both"
    assert scores[7] > scores[91], "agreement must still count for something"
    # not scores[90]: at K=1 rank 2 alone (1/3) ties rank 5 in both (1/6 + 1/6) exactly.


def test_portuguese_query_finds_right_file_in_top3(synthetic_bibliotheca):
    results = search("como calcular o comprimento de ancoragem", output=synthetic_bibliotheca, top=3)
    assert any(r["file"] == "09-ancoragem.md" for r in results), results


def test_exact_identifier_found_by_fts(synthetic_bibliotheca):
    results = search("inversor de frequencia", output=synthetic_bibliotheca, top=3)
    assert any(r["doc"] == "manual-inversor" for r in results), results


def test_doc_filter_restricts(synthetic_bibliotheca):
    results = search("aderencia", output=synthetic_bibliotheca, top=5, doc="nbr-7480-aco")
    assert results and all(r["doc"] == "nbr-7480-aco" for r in results)


def test_one_result_per_file(synthetic_bibliotheca):
    results = search("ancoragem aderencia concreto", output=synthetic_bibliotheca, top=5)
    paths = [r["path"] for r in results]
    assert len(paths) == len(set(paths))


def test_pointer_lines_have_no_body(synthetic_bibliotheca):
    """The pointer line itself stays a pure pointer; the body now lives in the
    indented snippet lines underneath it (Task 7 reverses the old "never the
    body" rule for the *overall* output, not for the pointer line `biblio hit`
    parses)."""
    results = search("comprimento de ancoragem", output=synthetic_bibliotheca, top=3)
    text = format_results(results)
    pointer_lines = [l for l in text.splitlines() if not l.startswith(" ")]
    assert all(".md:" in l for l in pointer_lines)
    assert all("resistencia de aderencia de calculo" not in l for l in pointer_lines), \
        "body leaked into pointer line"
    assert max(len(l) for l in pointer_lines) < 200, "pointer line too long"


def test_format_results_includes_matched_snippet():
    """format_results prints the matched-chunk text under the pointer, and the
    pointer line stays byte-identical to the pre-snippet format so
    `biblio hit "<path:start-end>"` keeps parsing it."""
    results = [{
        "path": "/x/y/doc.md", "doc": "y", "file": "doc.md", "section": "1 Intro",
        "line_start": 3, "line_end": 5, "score": 0.842,
        "snippet": "first matched line\nsecond matched line",
    }]
    text = format_results(results)
    lines = text.splitlines()
    assert lines[0] == "/x/y/doc.md:3-5  0.842  1 Intro"
    assert "first matched line" in text
    assert "second matched line" in text


def test_search_result_carries_snippet_from_tight_chunk_not_widened_section(synthetic_bibliotheca):
    results = search("comprimento de ancoragem", output=synthetic_bibliotheca, top=1)
    assert "snippet" in results[0]
    assert results[0]["snippet"].strip()


def test_returned_path_is_absolute_and_exists(synthetic_bibliotheca):
    from pathlib import Path
    result = search("comprimento de ancoragem", output=synthetic_bibliotheca, top=1)[0]
    p = Path(result["path"])
    assert p.is_absolute() and p.exists()


def test_context_section_returns_entire_slice(synthetic_bibliotheca):
    from pathlib import Path
    q = "comprimento de ancoragem"
    win = search(q, output=synthetic_bibliotheca, top=1, context="window")[0]
    sec = search(q, output=synthetic_bibliotheca, top=1, context="section")[0]
    n = len(Path(sec["path"]).read_text(encoding="utf-8").splitlines())
    assert (sec["line_start"], sec["line_end"]) == (1, n)
    assert sec["line_end"] - sec["line_start"] >= win["line_end"] - win["line_start"]


def test_search_covers_two_bibliothecas(synthetic_bibliotheca, secondary_bibliotheca):
    query = "fatigue of welded joints under cyclic loading"
    results = search(query, output=[synthetic_bibliotheca, secondary_bibliotheca], top=3)
    assert any(r["doc"] == "artigo-fadiga" for r in results), results


def test_lib_restricts_to_one_bibliotheca(synthetic_bibliotheca, secondary_bibliotheca):
    results = search("fatigue welded joints", output=synthetic_bibliotheca, top=3)
    assert all(r["doc"] != "artigo-fadiga" for r in results)
