"""Local search daemon: loads the embedding model once, serves repeat searches
over a loopback socket instead of paying torch/sentence-transformers' import
and load cost (~20s) on every CLI invocation.

ponytail: stdlib `multiprocessing.connection` (Listener/Client) — no new
dependency, no threading (one search at a time is plenty for a local tool).
Not auto-started: run `biblio serve` in its own terminal; `biblio search`
uses it when present and silently falls back to loading the model itself
when it isn't.
"""
from multiprocessing.connection import Client, Listener

from biblio import search

ADDRESS = ("localhost", 8756)
AUTHKEY = b"biblio-local-daemon"  # ponytail: loopback-only trust boundary, not a secret


def _handle_one(kwargs: dict) -> dict:
    try:
        results = search.search(**kwargs)
        return {"ok": True, "results": results}
    except (Exception, SystemExit) as e:  # search() raises SystemExit for a bad bibliotheca
        return {"ok": False, "error": str(e)}


def serve() -> None:
    from biblio import embed

    print("loading model...")
    embed._model()  # pay the load cost once, before accepting any connection
    try:
        listener = Listener(ADDRESS, authkey=AUTHKEY)
    except OSError:
        raise SystemExit(
            f"port {ADDRESS[1]} is already in use — a daemon may already be running.")
    print(f"biblio daemon ready on {ADDRESS[0]}:{ADDRESS[1]} (Ctrl+C to stop)")
    try:
        while True:
            with listener.accept() as conn:
                try:
                    conn.send(_handle_one(conn.recv()))
                except EOFError:
                    pass
    except KeyboardInterrupt:
        print("\nstopping.")
    finally:
        listener.close()


def try_client_search(**kwargs) -> list[dict] | None:
    """None if no daemon is listening. Raises SystemExit for an error the daemon reports."""
    try:
        conn = Client(ADDRESS, authkey=AUTHKEY)
    except OSError:
        return None
    try:
        conn.send(kwargs)
        response = conn.recv()
    finally:
        conn.close()
    if not response["ok"]:
        raise SystemExit(response["error"])
    return response["results"]
