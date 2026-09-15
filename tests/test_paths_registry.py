import importlib

import biblio.paths


def test_registry_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("BIBLIO_REGISTRY", str(tmp_path / "r.txt"))
    try:
        importlib.reload(biblio.paths)
        assert biblio.paths.REGISTRY == tmp_path / "r.txt"
    finally:
        monkeypatch.delenv("BIBLIO_REGISTRY")
        importlib.reload(biblio.paths)


def test_registry_default_without_env(monkeypatch):
    monkeypatch.delenv("BIBLIO_REGISTRY", raising=False)
    importlib.reload(biblio.paths)
    assert biblio.paths.REGISTRY.name == "bibliothecas.txt"
    assert biblio.paths.REGISTRY.parent.name == ".biblio"
