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
