"""Tests for pure helpers in bot.py and the optional-server registry."""

import os
import subprocess
import sys

from opengriffin import bot


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
