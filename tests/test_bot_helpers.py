"""Tests for pure helpers in bot.py and the optional-server registry."""

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


def test_optional_servers_all_load():
    """Every module in the registry must import and expose its server attr —
    build_mcp_servers logs-and-continues at runtime, but in CI a broken
    optional module should fail loudly."""
    import importlib

    for mod_name, attr in bot._OPTIONAL_SERVERS:
        mod = importlib.import_module(f"opengriffin.{mod_name}")
        assert hasattr(mod, attr), f"{mod_name} lacks {attr}"

    servers = bot.build_mcp_servers()
    for mod_name, _ in bot._OPTIONAL_SERVERS:
        assert mod_name in servers
