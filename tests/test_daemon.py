import threading

import pytest

from biblio import daemon


def test_handle_one_wraps_results_ok(monkeypatch):
    monkeypatch.setattr(daemon, "search", type("m", (), {
        "search": staticmethod(lambda **kw: [{"path": "x"}])}))
    assert daemon._handle_one({"query": "q"}) == {"ok": True, "results": [{"path": "x"}]}


def test_handle_one_wraps_exception_as_error(monkeypatch):
    def boom(**kw):
        raise SystemExit("not a bibliotheca")
    monkeypatch.setattr(daemon, "search", type("m", (), {"search": staticmethod(boom)}))
    response = daemon._handle_one({"query": "q"})
    assert response == {"ok": False, "error": "not a bibliotheca"}


def test_client_search_returns_none_when_no_daemon_listening():
    assert daemon.try_client_search(query="q") is None


def test_client_search_round_trips_through_a_real_listener(monkeypatch):
    """The wire protocol itself: a client request reaches the handler and the
    handler's response reaches the client, over the real loopback socket."""
    monkeypatch.setattr(daemon, "search", type("m", (), {
        "search": staticmethod(lambda **kw: [{"path": kw["query"]}])}))

    def serve_once():
        listener = daemon.Listener(daemon.ADDRESS, authkey=daemon.AUTHKEY)
        with listener.accept() as conn:
            conn.send(daemon._handle_one(conn.recv()))
        listener.close()

    t = threading.Thread(target=serve_once, daemon=True)
    t.start()
    try:
        results = daemon.try_client_search(query="ping")
    finally:
        t.join(timeout=5)
    assert results == [{"path": "ping"}]


def test_client_search_raises_systemexit_on_daemon_error(monkeypatch):
    def boom(**kw):
        raise SystemExit("bad bibliotheca")
    monkeypatch.setattr(daemon, "search", type("m", (), {"search": staticmethod(boom)}))

    def serve_once():
        listener = daemon.Listener(daemon.ADDRESS, authkey=daemon.AUTHKEY)
        with listener.accept() as conn:
            conn.send(daemon._handle_one(conn.recv()))
        listener.close()

    t = threading.Thread(target=serve_once, daemon=True)
    t.start()
    try:
        with pytest.raises(SystemExit, match="bad bibliotheca"):
            daemon.try_client_search(query="q")
    finally:
        t.join(timeout=5)
