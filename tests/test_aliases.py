"""Tests for alias templates and per-chat settings storage."""

import pytest

from opengriffin import aliases


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(aliases, "STORE_FILE", tmp_path / "aliases.json")


def test_render_positional_args():
    assert aliases.render("Summarize $1 for $2", ["url", "me"]) == "Summarize url for me"


def test_render_star_joins_all_args():
    assert aliases.render("Search: $*", ["red", "pandas"]) == "Search: red pandas"


def test_render_missing_args_leave_placeholder():
    assert aliases.render("Need $1 and $2", ["only-one"]) == "Need only-one and $2"


def test_alias_set_get_remove():
    aliases.set_alias("sum", "Summarize $1")
    assert aliases.get_alias("sum") == "Summarize $1"
    assert aliases.remove_alias("sum") is True
    assert aliases.get_alias("sum") is None
    assert aliases.remove_alias("sum") is False


def test_chat_sysprompt_set_and_clear():
    aliases.set_chat_sysprompt(42, "  be brief  ")
    assert aliases.get_chat_sysprompt(42) == "be brief"
    aliases.set_chat_sysprompt(42, "")
    assert aliases.get_chat_sysprompt(42) == ""


def test_chat_model_set_merge_and_reset():
    aliases.set_chat_model(7, "openai", None)
    assert aliases.get_chat_model(7) == {"provider": "openai"}
    aliases.set_chat_model(7, None, "gpt-4o")
    assert aliases.get_chat_model(7) == {"provider": "openai", "model": "gpt-4o"}
    aliases.set_chat_model(7, None, None)
    assert aliases.get_chat_model(7) == {}
