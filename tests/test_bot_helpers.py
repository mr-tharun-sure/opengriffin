"""Tests for pure helpers in bot.py, stale-session recovery, and the
optional-server registry."""

import asyncio
import os
import subprocess
import sys

import pytest

from opengriffin import bot, topics

OBSERVED_STALE_ERROR = (
    "API Error: 400 diagnostics.previousmessageid: must be the id from a "
    "prior /v1/messages response (starts with msg_)"
)


def test_stale_session_markers():
    assert bot._looks_like_stale_session(OBSERVED_STALE_ERROR)
    assert bot._looks_like_stale_session("No conversation found with session ID abc")
    assert not bot._looks_like_stale_session("Error: connection reset by peer")


class _DummyTelegramBot:
    async def send_chat_action(self, **kwargs):
        pass

    async def edit_message_text(self, **kwargs):
        pass


@pytest.fixture
def stale_chat(tmp_path, monkeypatch):
    """A chat whose stored session id is about to turn out stale."""
    monkeypatch.setattr(topics, "STORE_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(topics, "_chats", {})
    monkeypatch.setattr(topics, "_loaded", True)
    monkeypatch.setattr(bot.usage_module, "record", lambda **kwargs: None)
    chat_id = 555
    topics.set_session_id(chat_id, "stale-sess")
    return chat_id


def test_stale_session_is_dropped_and_retried(stale_chat, monkeypatch):
    seen_sessions = []

    async def fake_stream(state, prompt):
        seen_sessions.append(topics.session_id_for(stale_chat))
        if len(seen_sessions) == 1:
            raise RuntimeError(OBSERVED_STALE_ERROR)
        return ("all good", "fresh-sess", 0.01, 10, 5)

    monkeypatch.setattr(bot, "_stream_claude", fake_stream)
    reply = asyncio.run(bot.ask_claude_with_progress(stale_chat, "hi", _DummyTelegramBot(), None))
    assert reply == "all good"
    # First attempt resumed the stale session; the retry started fresh.
    assert seen_sessions == ["stale-sess", None]
    assert topics.session_id_for(stale_chat) == "fresh-sess"
    # The dead session is archived, not lost.
    assert topics.list_archive(stale_chat)[0]["session_id"] == "stale-sess"


def test_stale_session_surfaced_as_result_text(stale_chat, monkeypatch):
    attempts = []

    async def fake_stream(state, prompt):
        attempts.append(1)
        if len(attempts) == 1:
            return (OBSERVED_STALE_ERROR, "stale-sess", None, None, None)
        return ("recovered", "fresh-sess", None, None, None)

    monkeypatch.setattr(bot, "_stream_claude", fake_stream)
    reply = asyncio.run(bot.ask_claude_with_progress(stale_chat, "hi", _DummyTelegramBot(), None))
    assert reply == "recovered"
    assert len(attempts) == 2


def test_unrelated_error_propagates_and_keeps_session(stale_chat, monkeypatch):
    async def fake_stream(state, prompt):
        raise RuntimeError("boom")

    monkeypatch.setattr(bot, "_stream_claude", fake_stream)
    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(bot.ask_claude_with_progress(stale_chat, "hi", _DummyTelegramBot(), None))
    assert topics.session_id_for(stale_chat) == "stale-sess"


def test_summarize_bash():
    assert bot._summarize_tool_input("Bash", {"command": "ls -la"}) == "ls -la"


def test_summarize_read_and_edit():
    assert bot._summarize_tool_input("Read", {"file_path": "/tmp/x"}) == "/tmp/x"
    assert (
        bot._summarize_tool_input("MultiEdit", {"file_path": "/tmp/x", "edits": [1, 2]})
        == "/tmp/x (2 edits)"
    )


def test_summarize_grep_with_path():
    assert bot._summarize_tool_input("Grep", {"pattern": "foo", "path": "src"}) == "foo in src"


def test_summarize_mcp_fallback_picks_useful_field():
    assert bot._summarize_tool_input("mcp__x__y", {"query": "cats"}) == "query=cats"


def test_summarize_non_dict_input():
    assert bot._summarize_tool_input("Bash", "not-a-dict") == ""


def test_optional_servers_all_load(tmp_path):
    """Every module in the registry must import and expose its server —
    build_mcp_servers logs-and-continues at runtime, but in CI a broken
    optional module should fail loudly.

    Runs in a subprocess with HOME redirected: importing the modules here
    would poison Python's module cache with real-HOME state paths, breaking
    the isolated-HOME tests in test_frontier_modules.py."""
    script = (
        "from opengriffin import bot\n"
        "servers = bot.build_mcp_servers()\n"
        "missing = [m for m, _ in bot._OPTIONAL_SERVERS if m not in servers]\n"
        "assert not missing, f'optional servers failed to load: {missing}'\n"
    )
    env = dict(os.environ, HOME=str(tmp_path))
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
