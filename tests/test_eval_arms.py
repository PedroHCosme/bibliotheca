from scripts.eval import arms


def test_commands_isolate_arms(monkeypatch, tmp_path):
    monkeypatch.setattr(arms, "DATA", tmp_path)
    a = arms.command("A", "robotics", "claude")
    b = arms.command("B-current", "robotics", "claude")
    assert a == b  # arms differ only by cwd and env
    assert a[a.index("--setting-sources") + 1] == "project" and "--strict-mcp-config" in a
    assert "--safe-mode" not in a and "--plugin-dir" not in a
    assert '"includeGitInstructions": false' in a[a.index("--settings") + 1]
    assert a[a.index("--model") + 1] == "claude-sonnet-5"
    assert a[a.index("--tools") + 1] == "Read,Glob,Grep,Bash,Skill"


def test_cwd_and_env(monkeypatch, tmp_path):
    monkeypatch.setattr(arms, "DATA", tmp_path)
    assert arms.cwd("C", "robotics") == tmp_path / "c" / "robotics"
    assert arms.cwd("A", "robotics") == tmp_path / "corpora" / "robotics"
    assert arms.cwd("B-current", "robotics") == tmp_path / "b" / "current" / "robotics" / "docs"
    assert arms.env("B-current", "robotics")["BIBLIO_REGISTRY"] == \
        str(tmp_path / "registry" / "current" / "robotics.txt")
    assert arms.env("A", "robotics")["BIBLIO_REGISTRY"] == str(tmp_path / "registry" / "empty.txt")
    assert arms.env("C", "robotics")["HF_HUB_OFFLINE"] == "1"
    assert arms.env("A", "robotics")["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    assert arms.env("B-current", "robotics")["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] == "1"


def test_write_b_copies_sources_and_lists_only_this_corpus(monkeypatch, tmp_path):
    monkeypatch.setattr(arms, "DATA", tmp_path)
    bib = arms.bibliotheca("robotics")
    bib.mkdir(parents=True)
    reg = arms.registry("robotics")
    reg.parent.mkdir(parents=True)
    reg.write_text(f"{bib}\n", encoding="utf-8")
    arms.sources("robotics").mkdir(parents=True)
    (arms.sources("robotics") / "book.md").write_text("x", encoding="utf-8")

    root = arms.write_b("robotics")

    text = (root / ".claude" / "skills" / "bibliotheca" / "SKILL.md").read_text(encoding="utf-8")
    assert "name: bibliotheca" in text
    assert "(robotics)" in text
    assert (arms.cwd("B-current", "robotics") / "book.md").is_file()
