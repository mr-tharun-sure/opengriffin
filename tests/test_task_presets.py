"""Tests for autonomous task presets and trigger delivery."""

import asyncio
from types import SimpleNamespace

import pytest

from opengriffin import task_presets, triggers


@pytest.fixture(autouse=True)
def _isolated_triggers(tmp_path, monkeypatch):
    monkeypatch.setattr(triggers, "TRIGGERS_FILE", tmp_path / "triggers.json")


def test_every_preset_builds_a_valid_trigger():
    for name in task_presets.PRESETS:
        t = task_presets.build(name)
        assert t["id"] == f"preset-{name}"
        assert t["enabled"] is True
        assert t["source"]["kind"] in ("cron", "poll")
        if t["source"]["kind"] == "cron":
            assert t["source"]["expr"]
        assert t["action"]["kind"] == "agent"
        assert t["action"]["prompt"]
        assert t["action"]["deliver_to"] == "home"


def test_build_unknown_preset_raises():
    with pytest.raises(KeyError):
        task_presets.build("nope")


def test_enable_persists_and_upserts():
    task_presets.enable("morning-digest", {"cron": "30 7 * * *"})
    task_presets.enable("morning-digest", {"cron": "0 8 * * *", "topics": "AI"})
    stored = triggers._load()["triggers"]
    assert len(stored) == 1
    assert stored[0]["source"]["expr"] == "0 8 * * *"
    assert "AI" in stored[0]["action"]["prompt"]


def test_params_flow_into_prompts():
    t = task_presets.build("github-watcher", {"repos": "acme/widgets"})
    assert "acme/widgets" in t["action"]["prompt"]
    t = task_presets.build(
        "web-monitor", {"url": "https://example.com/x", "condition": "Price under $10?"}
    )
    assert t["source"]["url"] == "https://example.com/x"
    assert t["predicate"] == "Price under $10?"


class _FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


def _run_agent_trigger(monkeypatch, reply):
    """Run one agent-action trigger through evaluate() with a stubbed model."""
    from opengriffin import bot, botctx

    fake = _FakeBot()
    monkeypatch.setattr(botctx, "CTX", SimpleNamespace(bot=fake, home_chat_id="123"))

    async def fake_ask(chat_id, prompt, tg_bot, status_msg_id=None):
        return reply

    monkeypatch.setattr(bot, "ask_claude_with_progress", fake_ask)
    trigger = {
        "id": "t1",
        "enabled": True,
        "source": {"kind": "cron", "expr": "0 7 * * *"},
        "predicate": "",
        "action": {"kind": "agent", "prompt": "do the thing", "deliver_to": "home"},
    }
    result = asyncio.run(triggers.evaluate(trigger))
    return result, fake.sent


def test_agent_trigger_result_is_delivered(monkeypatch):
    result, sent = _run_agent_trigger(monkeypatch, "3 new issues opened")
    assert result == "3 new issues opened"
    assert sent == [("123", "3 new issues opened")]


def test_silent_reply_is_not_delivered(monkeypatch):
    result, sent = _run_agent_trigger(monkeypatch, "SILENT")
    assert result == "SILENT"
    assert sent == []
