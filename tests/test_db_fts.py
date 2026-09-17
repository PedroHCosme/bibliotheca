import numpy as np

import biblio.db as db
import biblio.embed as embed


def _chunk():
    return {"file": "01-a.md", "section": "Overview",
            "line_start": 1, "line_end": 9,
            "text": "nothing about the client here"}


def test_document_name_is_searchable(tmp_path):
    con = db.connect(tmp_path)
    db.replace_document(con, "samarco-index", [_chunk()],
                        np.zeros((1, embed.DIM), dtype="float32"))
    assert db.search_fts(con, "samarco", 5) == [1]


def test_natural_language_query_ignores_stopword_noise(tmp_path):
    """A raw question must rank the same top document as its content words alone.

    Before cleaning, every stopword in the question ("what", "is", "the", "of", "a")
    becomes its own OR'd MATCH term. A distractor stuffed with those stopwords racks up
    more term matches than the real answer's few rare content words and wins on bm25,
    even though it barely mentions the topic.
    """
    con = db.connect(tmp_path)
    chunks = [
        {"file": "kinematics.md", "section": "s", "line_start": 1, "line_end": 5,
         "text": "kinematics robot arm"},
        {"file": "distractor.md", "section": "s", "line_start": 1, "line_end": 5,
         "text": "what is the of a what is the of a arm what is the of a"},
    ]
    db.replace_document(con, "doc1", chunks,
                        np.zeros((len(chunks), embed.DIM), dtype="float32"))

    ids = db.search_fts(con, "What is the kinematics of a robot arm?", 5)
    top_file = con.execute("SELECT file FROM chunks WHERE id=?", (ids[0],)).fetchone()["file"]
    assert top_file == "kinematics.md", ids


def test_old_index_is_rebuilt_not_broken(tmp_path):
    """A bibliotheca indexed before the name columns existed must keep working after an upgrade."""
    con = db.connect(tmp_path)
    db.replace_document(con, "samarco-index", [_chunk()],
                        np.zeros((1, embed.DIM), dtype="float32"))
    # A real pre-upgrade database: 2-column table, no version row. Deleting only the version
    # row would exercise the gate against the new table, not the column mismatch that breaks inserts.
    con.execute("DROP TABLE chunks_fts")
    con.execute("CREATE VIRTUAL TABLE chunks_fts USING fts5(text, section, "
                "content='chunks', content_rowid='id')")
    con.execute("DELETE FROM config WHERE key='fts_version'")
    con.commit()
    con.close()
    assert db.search_fts(db.connect(tmp_path), "samarco", 5) == [1]
