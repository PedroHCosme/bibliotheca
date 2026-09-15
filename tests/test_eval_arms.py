from scripts.eval import arms


def test_commands_isolate_arms(monkeypatch, tmp_path):
    monkeypatch.setattr(arms, "DATA", tmp_path)
    a = arms.command("A", "robotics", "claude")
    b = arms.command("B-current", "robotics", "claude")
    assert "--safe-mode" in a and "--safe-mode" in b
    assert "--plugin-dir" not in a
    assert b[b.index("--plugin-dir") + 1] == str(tmp_path / "plugin" / "current" / "robotics")
    assert a[a.index("--model") + 1] == "claude-sonnet-5"
    assert a[a.index("--tools") + 1] == "Read,Glob,Grep,Bash"


def test_cwd_and_env(monkeypatch, tmp_path):
    monkeypatch.setattr(arms, "DATA", tmp_path)
    assert arms.cwd("C", "robotics") == tmp_path / "c" / "robotics"
    assert arms.cwd("A", "robotics") == tmp_path / "corpora" / "robotics"
    assert arms.cwd("B-current", "robotics") == tmp_path / "corpora" / "robotics"
    assert arms.env("B-current", "robotics")["BIBLIO_REGISTRY"] == \
        str(tmp_path / "registry" / "current" / "robotics.txt")
    assert arms.env("A", "robotics")["BIBLIO_REGISTRY"] == str(tmp_path / "registry" / "empty.txt")
    assert arms.env("C", "robotics")["HF_HUB_OFFLINE"] == "1"


def test_write_plugin_lists_only_this_corpus(monkeypatch, tmp_path):
    monkeypatch.setattr(arms, "DATA", tmp_path)
    bib = arms.bibliotheca("robotics")
    bib.mkdir(parents=True)
    reg = arms.registry("robotics")
    reg.parent.mkdir(parents=True)
    reg.write_text(f"{bib}\n", encoding="utf-8")

    root = arms.write_plugin("robotics")

    text = (root / "skills" / "bibliotheca" / "SKILL.md").read_text(encoding="utf-8")
    assert "name: bibliotheca" in text
    assert "(bibliothecas: robotics)" in text
    assert (root / ".claude-plugin" / "plugin.json").is_file()
