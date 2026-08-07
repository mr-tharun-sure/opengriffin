"""Tests for the package-dir → OG_HOME state migration."""

from opengriffin import paths


def test_migrate_package_dir_state(tmp_path, monkeypatch):
    pkg = tmp_path / "pkg"
    og = tmp_path / "og"
    pkg.mkdir()
    og.mkdir()
    monkeypatch.setattr(paths, "_PKG_DIR", pkg)
    monkeypatch.setattr(paths, "SESSIONS", og / "sessions.json")
    monkeypatch.setattr(paths, "ALIASES", og / "aliases.json")
    monkeypatch.setattr(paths, "WEBHOOKS", og / "webhooks.json")

    (pkg / "sessions.json").write_text('{"chats": {}}')
    (pkg / "aliases.json").write_text('{"aliases": {}}')
    (og / "aliases.json").write_text("EXISTING")  # destination wins

    moved = paths.migrate_package_dir_state()

    assert moved == ["sessions.json"]
    assert (og / "sessions.json").read_text() == '{"chats": {}}'
    assert not (pkg / "sessions.json").exists()
    # Existing OG_HOME file untouched; package copy left for inspection.
    assert (og / "aliases.json").read_text() == "EXISTING"
    assert (pkg / "aliases.json").exists()
    # Absent files are a no-op; re-running is idempotent.
    assert paths.migrate_package_dir_state() == []
