"""One SQLite file per bibliotheca: FTS5 + vectors.

ponytail: brute-force vector search in numpy. For the measured corpus size
it's instant and avoids a native extension dependency.
"""
import base64
import re
import sqlite3
import unicodedata
from pathlib import Path

import numpy as np

from biblio.embed import DIM, MODEL

DB_FILE = "biblio.db"

_STOPWORDS = set("o a e de do da os as em para por com como ou no na um uma dos das que "
                 "qual quais entre sobre the of a an is are what how why".split())


def _tokens(text: str) -> set[str]:
    no_accent = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return {t for t in re.findall(r"[a-z0-9]{3,}", no_accent.lower()) if t not in _STOPWORDS}

SCHEMA = """
CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS chunks (
  id         INTEGER PRIMARY KEY,
  doc        TEXT NOT NULL,
  file       TEXT NOT NULL,
  section    TEXT,
  line_start INTEGER NOT NULL,
  line_end   INTEGER NOT NULL,
  text       TEXT NOT NULL,
  vector     BLOB
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  text, section, doc, file, content='chunks', content_rowid='id',
  tokenize="unicode61 remove_diacritics 2"
);
CREATE TABLE IF NOT EXISTS accesses (
    id         INTEGER PRIMARY KEY,
    chunk_id   INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    query_vec  BLOB NOT NULL,
    weight     INTEGER NOT NULL,
    session_id INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_accesses_chunk ON accesses(chunk_id);
"""


def connect(bibliotheca: Path) -> sqlite3.Connection:
    con = sqlite3.connect(bibliotheca / DB_FILE)
    con.execute("PRAGMA foreign_keys = ON")
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    con.execute("INSERT OR IGNORE INTO config VALUES('session_counter', '0')")
    con.commit()
    _check_model(con)
    _check_fts(con)
    return con


def _check_model(con: sqlite3.Connection) -> None:
    """Vectors from one model compared with another aren't bad results, they're noise."""
    with con:
        saved = con.execute(
            "SELECT value FROM config WHERE key = 'model'").fetchone()
        if saved is None:
            con.execute("INSERT INTO config VALUES('model', ?)", (MODEL,))
        elif saved[0] != MODEL:
            raise SystemExit(
                f"This bibliotheca was indexed with '{saved[0]}', and this biblio uses "
                f"'{MODEL}'. The vectors are not comparable.\n"
                f"Reindex with: biblio add <source> --force")


FTS_VERSION = "2"   # bump when the FTS columns change


def _check_fts(con: sqlite3.Connection) -> None:
    """Rebuild the FTS index in place when its columns change. Vectors are untouched: no re-embedding."""
    row = con.execute("SELECT value FROM config WHERE key='fts_version'").fetchone()
    if row and row[0] == FTS_VERSION:
        return
    with con:
        con.execute("DROP TABLE IF EXISTS chunks_fts")
        con.executescript(SCHEMA)
        con.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        con.execute("INSERT OR REPLACE INTO config VALUES('fts_version', ?)", (FTS_VERSION,))


ACCESS_CAP = 20
HALF_LIFE = 7
SIMILARITY_THRESHOLD = 0.3
PRUNE_THRESHOLD = 0.01
MAX_BONUS = 0.15      # cap on the post-fusion frecency bonus (~2 RRF positions at K_RRF=1)
BONUS_SCALE = 1.0     # observed scores >> this, so MAX_BONUS is the effective cap


def get_session(con: sqlite3.Connection) -> int:
    row = con.execute("SELECT value FROM config WHERE key='session_counter'").fetchone()
    return int(row[0]) if row else 0


def increment_session(con: sqlite3.Connection) -> int:
    with con:
        con.execute("UPDATE config SET value = CAST(value AS INTEGER) + 1 "
                    "WHERE key = 'session_counter'")
    return get_session(con)


def record_access(con: sqlite3.Connection, chunk_id: int, query_vec_f16: bytes,
                  weight: int, session_id: int) -> None:
    with con:
        con.execute("INSERT INTO accesses(chunk_id, query_vec, weight, session_id) "
                    "VALUES(?, ?, ?, ?)",
                    (chunk_id, query_vec_f16, weight, session_id))
        count = con.execute("SELECT COUNT(*) FROM accesses WHERE chunk_id = ?",
                            (chunk_id,)).fetchone()[0]
        if count > ACCESS_CAP:
            con.execute("DELETE FROM accesses WHERE id IN ("
                        "SELECT id FROM accesses WHERE chunk_id = ? "
                        "ORDER BY session_id ASC LIMIT ?)",
                        (chunk_id, count - ACCESS_CAP))


def save_last_query_vec(con: sqlite3.Connection, vec_f16: bytes) -> None:
    encoded = base64.b64encode(vec_f16).decode()
    with con:
        con.execute("INSERT OR REPLACE INTO config VALUES('last_query_vec', ?)",
                    (encoded,))


def get_last_query_vec(con: sqlite3.Connection) -> bytes | None:
    row = con.execute("SELECT value FROM config WHERE key='last_query_vec'").fetchone()
    return base64.b64decode(row[0]) if row else None


def frecency_score(accesses: list, query_vec: np.ndarray,
                   current_session: int, half_life: int = HALF_LIFE
                   ) -> tuple[float, list[int]]:
    score = 0.0
    prune_ids = []
    for acc in accesses:
        stored = np.frombuffer(acc["query_vec"], dtype="float16").astype("float32")
        similarity = float(query_vec @ stored)
        if similarity < SIMILARITY_THRESHOLD:
            continue
        age = current_session - acc["session_id"]
        decay = 2.0 ** (-age / half_life)
        contribution = acc["weight"] * similarity * decay
        if contribution < PRUNE_THRESHOLD:
            prune_ids.append(acc["id"])
            continue
        score += contribution
    return score, prune_ids


def ranked_by_frecency(con: sqlite3.Connection, query_vec: np.ndarray,
                       chunk_ids) -> list[tuple[int, float]]:
    """Frecency score for the candidate chunks that carry access history.

    Scoped to the caller's candidate set (the vector/FTS hits), so cost is
    O(candidates) per search — not O(every chunk ever accessed). Returns
    (chunk_id, score) pairs sorted by score descending; chunks with no history
    or a zero score are omitted. Negligible access rows found along the way are
    pruned.
    """
    chunk_ids = list(chunk_ids)
    if not chunk_ids:
        return []
    session = get_session(con)
    placeholders = ",".join("?" * len(chunk_ids))
    by_chunk: dict[int, list[dict]] = {}
    for r in con.execute(
            f"SELECT id, chunk_id, query_vec, weight, session_id FROM accesses "
            f"WHERE chunk_id IN ({placeholders})", chunk_ids):
        by_chunk.setdefault(r["chunk_id"], []).append(dict(r))

    scores: dict[int, float] = {}
    all_prune: list[int] = []
    for cid, accs in by_chunk.items():
        sc, prune = frecency_score(accs, query_vec, session)
        if sc > 0:
            scores[cid] = sc
        all_prune.extend(prune)

    if all_prune:
        ph = ",".join("?" * len(all_prune))
        with con:
            con.execute(f"DELETE FROM accesses WHERE id IN ({ph})", all_prune)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def replace_document(con: sqlite3.Connection, doc: str, chunks: list[dict],
                     vectors: np.ndarray) -> None:
    """Deletes and reinserts the entire document. Reprocessing never duplicates."""
    with con:
        old = [tuple(r) for r in con.execute(
            "SELECT id, text, section, doc, file FROM chunks WHERE doc = ?", (doc,))]
        con.executemany("INSERT INTO chunks_fts(chunks_fts, rowid, text, section, doc, file) "
                        "VALUES('delete', ?, ?, ?, ?, ?)", old)
        con.execute("DELETE FROM chunks WHERE doc = ?", (doc,))
        for chunk, vector in zip(chunks, vectors):
            cursor = con.execute(
                "INSERT INTO chunks(doc, file, section, line_start, line_end, text, vector)"
                " VALUES(?,?,?,?,?,?,?)",
                (doc, chunk["file"], chunk["section"], chunk["line_start"],
                 chunk["line_end"], chunk["text"],
                 np.asarray(vector, dtype="float32").tobytes()),
            )
            con.execute("INSERT INTO chunks_fts(rowid, text, section, doc, file) VALUES(?,?,?,?,?)",
                        (cursor.lastrowid, chunk["text"], chunk["section"], doc, chunk["file"]))


def search_fts(con: sqlite3.Connection, query: str, k: int,
               doc: str | None = None) -> list[int]:
    words = _tokens(query) or set(query.split())  # fall back to raw query if cleaning empties it
    terms = " OR ".join(f'"{t}"' for t in words if t)
    if not terms:
        return []
    sql = ("SELECT c.id FROM chunks_fts f JOIN chunks c ON c.id = f.rowid "
           "WHERE chunks_fts MATCH ?")
    params: list = [terms]
    if doc:
        sql += " AND c.doc = ?"
        params.append(doc)
    sql += " ORDER BY bm25(chunks_fts) LIMIT ?"
    params.append(k)
    return [row["id"] for row in con.execute(sql, params)]


def search_vector(con: sqlite3.Connection, query: np.ndarray, k: int,
                  doc: str | None = None) -> list[int]:
    sql = "SELECT id, vector FROM chunks WHERE vector IS NOT NULL"
    params: list = []
    if doc:
        sql += " AND doc = ?"
        params.append(doc)
    rows = con.execute(sql, params).fetchall()
    if not rows:
        return []
    ids = np.array([row["id"] for row in rows])
    matrix = np.frombuffer(b"".join(row["vector"] for row in rows),
                           dtype="float32").reshape(len(ids), DIM)
    scores = matrix @ np.asarray(query, dtype="float32")
    best = np.argsort(scores)[::-1][:k]
    return [int(ids[i]) for i in best]


def details(con: sqlite3.Connection, ids: list[int]) -> dict[int, sqlite3.Row]:
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    return {row["id"]: row for row in con.execute(
        f"SELECT id, doc, file, section, line_start, line_end FROM chunks "
        f"WHERE id IN ({placeholders})", ids)}
