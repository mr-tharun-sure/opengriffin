"""Tests for seeding example memories and migrating package-dir memories."""

from opengriffin import memory, paths


def test_seed_copies_missing_files_only(tmp_path, monkeypatch):
    mem_dir = tmp_path / "memories"
    mem_dir.mkdir()
    (mem_dir / "SOUL.md").write_text("MY SOUL")  # pre-existing: must survive
    monkeypatch.setattr(memory, "MEM_DIR", mem_dir)
    copied = memory.seed_from_examples()
    assert "SOUL.presets.md" in copied
    assert "SOUL.md" not in copied
    assert (mem_dir / "SOUL.md").read_text() == "MY SOUL"
    assert "## companion" in (mem_dir / "SOUL.presets.md").read_text()
    # Idempotent.
    assert memory.seed_from_examples() == []


def test_migration_moves_package_dir_memories(tmp_path, monkeypatch):
    pkg = tmp_path / "pkg"
    (pkg / "memories").mkdir(parents=True)
    og_mem = tmp_path / "og" / "memories"
    og_mem.mkdir(parents=True)
    monkeypatch.setattr(paths, "_PKG_DIR", pkg)
    monkeypatch.setattr(paths, "MEM_DIR", og_mem)
    monkeypatch.setattr(paths, "USAGE_LOG", tmp_path / "og" / "usage.jsonl")
    (pkg / "memories" / "JOURNAL.md").write_text("journal")
    (pkg / "memories" / "SOUL.md").write_text("pkg soul")
    (og_mem / "SOUL.md").write_text("real soul")  # destination wins
    (pkg / "usage.jsonl").write_text("{}")
    moved = paths.migrate_package_dir_state()
    assert "memories/JOURNAL.md" in moved
    assert "usage.jsonl" in moved
    assert (og_mem / "JOURNAL.md").read_text() == "journal"
    assert (og_mem / "SOUL.md").read_text() == "real soul"
    assert (pkg / "memories" / "SOUL.md").exists()  # left for inspection
