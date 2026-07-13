"""Tests for per-chat topic/session state, archive, and persistence."""

import pytest

from opengriffin import topics

CHAT = 1001


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(topics, "STORE_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(topics, "_chats", {})
    monkeypatch.setattr(topics, "_loaded", False)


def test_default_topic_and_session_roundtrip():
    assert topics.active_topic(CHAT) == "default"
    assert topics.session_id_for(CHAT) is None
    topics.set_session_id(CHAT, "sess-1")
    assert topics.session_id_for(CHAT) == "sess-1"


def test_switch_keeps_per_topic_sessions():
    topics.set_session_id(CHAT, "sess-default")
    topics.switch(CHAT, "work")
    assert topics.session_id_for(CHAT) is None
    topics.set_session_id(CHAT, "sess-work")
    topics.switch(CHAT, "default")
    assert topics.session_id_for(CHAT) == "sess-default"
    names = [n for n, _, _ in topics.list_topics(CHAT)]
    assert names == ["default", "work"]


def test_reset_archives_and_restore_reactivates():
    topics.set_session_id(CHAT, "sess-old")
    prior = topics.reset(CHAT)
    assert prior == "sess-old"
    assert topics.session_id_for(CHAT) is None
    archive = topics.list_archive(CHAT)
    assert archive[0]["session_id"] == "sess-old"
    assert topics.restore_archived(CHAT, "sess-old") is True
    assert topics.session_id_for(CHAT) == "sess-old"
    assert topics.list_archive(CHAT) == []


def test_restore_unknown_session_fails():
    assert topics.restore_archived(CHAT, "nope") is False


def test_archive_is_bounded_to_100():
    for i in range(120):
        topics.set_session_id(CHAT, f"sess-{i}")
        topics.reset(CHAT)
    archive = topics.list_archive(CHAT)
    assert len(archive) == 100
    assert archive[0]["session_id"] == "sess-119"  # most recent first


def test_state_survives_reload_from_disk():
    topics.switch(CHAT, "research")
    topics.set_session_id(CHAT, "sess-r")
    # Simulate a bot restart: wipe in-memory state, force re-read from disk.
    topics._chats.clear()
    topics._loaded = False
    assert topics.active_topic(CHAT) == "research"
    assert topics.session_id_for(CHAT) == "sess-r"
